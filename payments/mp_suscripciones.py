"""Suscripciones pagadas con Mercado Pago (su API de "preapproval").

A diferencia de Oneclick, acá NO cobramos nosotros: el cliente autoriza la
suscripción en la página de Mercado Pago y desde ahí Mercado Pago le cobra solo
cada N meses, en sus fechas, y nos avisa cada cobro. Lo nuestro es enterarse de
esos cobros y hacer con cada uno lo mismo que con cualquier compra: boleta,
extender la membresía y correo.

Cómo nos enteramos de un cobro (los tres terminan en `registrar_pago`, que es
idempotente por id de pago, así que da igual cuál llegue primero):
1. El webhook (`subscription_authorized_payment`, y `payment` para los pagos que
   Mercado Pago avisa por el tópico normal).
2. La vuelta del navegador después de suscribirse.
3. `manage.py sincronizar_suscripciones_mp`, una vez al día: la red de
   seguridad por si un webhook no llegó.

Mercado Pago exige que el correo del pagador (`payer_email`) sea el de una
cuenta de Mercado Pago existente: si no, responde "Both payer and collector
must be real or test users".
"""
import logging
from datetime import datetime

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.utils import timezone

from .models import Order, Suscripcion
from .services import get_mercadopago_payment, get_mercadopago_sdk

log = logging.getLogger('ingenioblocks.pagos')


class ErrorMercadoPago(Exception):
    """Mercado Pago respondió con error. `sin_cuenta` = el correo no tiene cuenta."""

    def __init__(self, mensaje, sin_cuenta=False):
        super().__init__(mensaje)
        self.sin_cuenta = sin_cuenta


def _respuesta(r):
    datos = r.get('response') or {}
    if r.get('status', 500) >= 400:
        mensaje = str(datos.get('message') or datos)
        raise ErrorMercadoPago(mensaje, sin_cuenta='real or test users' in mensaje)
    return datos


def crear(order, producto, payer_email, back_url):
    """Crea la suscripción en Mercado Pago, pendiente de que el cliente la autorice.

    Devuelve (id, init_point): init_point es la página donde la autoriza y se
    le hace el primer cobro.
    """
    datos = _respuesta(get_mercadopago_sdk().preapproval().create({
        'reason': producto.name[:250],
        'external_reference': str(order.order_id),
        'payer_email': payer_email,
        'back_url': back_url,
        'status': 'pending',
        'auto_recurring': {
            'frequency': max(1, producto.access_months or 1),
            'frequency_type': 'months',
            'transaction_amount': int(order.total_amount),
            'currency_id': 'CLP',
        },
    }))
    if not datos.get('id') or not datos.get('init_point'):
        raise ErrorMercadoPago(f'Respuesta sin id o init_point: {datos}')
    return datos['id'], datos['init_point']


def obtener(preapproval_id):
    return _respuesta(get_mercadopago_sdk().preapproval().get(preapproval_id))


def cambiar_estado(preapproval_id, estado):
    """'cancelled', 'paused' o 'authorized' (reanudar)."""
    return _respuesta(get_mercadopago_sdk().preapproval().update(preapproval_id, {'status': estado}))


def _fecha(texto):
    """'2026-12-01T13:42:51.000-04:00' -> date (hora de Chile)."""
    if not texto:
        return None
    try:
        return timezone.localdate(datetime.fromisoformat(texto))
    except (TypeError, ValueError):
        return None


ESTADOS_LOCALES = {
    'authorized': Suscripcion.ACTIVA,
    'paused': Suscripcion.PAUSADA,
    'cancelled': Suscripcion.CANCELADA,
}


def sincronizar_estado(preapproval):
    """Copia a nuestra Suscripcion el estado y la próxima fecha de Mercado Pago.

    El cliente puede pausar o cancelar desde la app de Mercado Pago, sin pasar
    por el sitio: así el panel no muestra activa una suscripción que ya no cobra.
    """
    s = Suscripcion.objects.filter(mp_preapproval_id=preapproval.get('id')).first()
    if s is None:
        return None
    campos = []
    nuevo = ESTADOS_LOCALES.get(preapproval.get('status'))
    if nuevo and s.estado != nuevo:
        log.info('Suscripción %s: Mercado Pago dice %s (antes %s)', s.pk, nuevo, s.estado)
        s.estado = nuevo
        campos.append('estado')
        if nuevo == Suscripcion.CANCELADA and not s.cancelada_en:
            s.cancelada_en = timezone.now()
            campos.append('cancelada_en')
    proxima = _fecha(preapproval.get('next_payment_date'))
    if proxima and proxima != s.proximo_cobro and s.estado == Suscripcion.ACTIVA:
        s.proximo_cobro = proxima
        campos.append('proximo_cobro')
    if campos:
        s.save(update_fields=campos)
    return s


def registrar_pago(preapproval, payment, entregar):
    """Registra un cobro de la suscripción. Devuelve la orden pagada, o None.

    `payment` es el pago leído de la API de Mercado Pago (nunca lo que dice la
    URL o el cuerpo del webhook). El primer cobro aprobado paga la orden con
    que se contrató y crea la Suscripcion; los siguientes crean una orden de
    renovación cada uno. `entregar` es payments.views._entregar_compra.
    """
    pago_id = str(payment.get('id') or '')
    if not pago_id:
        return None
    estado_pago = payment.get('status')
    a_entregar = None

    with transaction.atomic():
        # Se bloquea la orden inicial: el webhook, la vuelta del navegador y la
        # revisión diaria pueden llegar a la vez con el mismo pago.
        inicial = (Order.objects.select_for_update()
                   .filter(mp_preapproval_id=preapproval.get('id')).first())
        if inicial is None:
            log.error('Pago %s de una suscripción de Mercado Pago (%s) que no es de esta tienda',
                      pago_id, preapproval.get('id'))
            return None
        ya = Order.objects.filter(mp_payment_id=pago_id).first()
        if ya is not None:
            return ya

        s = Suscripcion.objects.filter(mp_preapproval_id=preapproval.get('id')).first()

        if estado_pago != 'approved':
            if estado_pago in ('rejected', 'cancelled') and s is not None:
                s.intentos_fallidos += 1
                s.ultimo_error = 'Mercado Pago rechazó el cobro (lo reintenta solo)'
                s.save(update_fields=['intentos_fallidos', 'ultimo_error'])
                log.info('Suscripción %s: Mercado Pago rechazó el pago %s', s.pk, pago_id)
                from core.alertas import avisar, clp
                avisar(f'⚠️ Mercado Pago rechazó el cobro de {s.email} ({clp(s.monto)}). '
                       f'Mercado Pago lo reintenta solo.')
            return None

        monto = int(payment.get('transaction_amount') or 0)
        if monto != int(inicial.total_amount):
            log.error('MONTO NO COINCIDE en la suscripción de Mercado Pago %s: cobró %s y se contrató por %s',
                      preapproval.get('id'), monto, inicial.total_amount)
            return None

        hoy = timezone.localdate()
        proxima = _fecha(preapproval.get('next_payment_date'))
        if s is None:
            # Primer cobro: paga la orden con que se contrató.
            producto = next((p for p in inicial.products.all() if p.es_suscripcion), None)
            if producto is None:
                log.error('La orden %s no trae un producto de suscripción', inicial.order_id)
                return None
            meses = max(1, producto.access_months or 1)
            inicial.status = 'PAID'
            inicial.mp_payment_id = pago_id
            inicial.save(update_fields=['status', 'mp_payment_id', 'updated_at'])
            s = Suscripcion.objects.create(
                email=inicial.customer_email.strip().lower(),
                producto=producto,
                pasarela=Suscripcion.MERCADOPAGO,
                mp_preapproval_id=preapproval['id'],
                orden_inicial=inicial,
                monto=int(inicial.total_amount),
                cada_meses=meses,
                proximo_cobro=proxima if proxima and proxima > hoy else hoy + relativedelta(months=meses),
            )
            a_entregar = inicial
            log.info('Suscripción %s (Mercado Pago) contratada: orden %s pagada (pago %s)',
                     s.pk, inicial.order_id, pago_id)
        else:
            from .oneclick import orden_de_renovacion
            orden = orden_de_renovacion(s, pasarela=Order.MERCADOPAGO)
            orden.status = 'PAID'
            orden.mp_payment_id = pago_id
            orden.save(update_fields=['status', 'mp_payment_id', 'updated_at'])
            s.intentos_fallidos = 0
            s.ultimo_error = ''
            s.proximo_cobro = proxima if proxima and proxima > hoy else hoy + relativedelta(months=s.cada_meses)
            s.save(update_fields=['intentos_fallidos', 'ultimo_error', 'proximo_cobro'])
            a_entregar = orden
            log.info('Suscripción %s cobrada por Mercado Pago: orden %s (pago %s)', s.pk, orden.order_id, pago_id)

    # Fuera de la transacción: boleta, acceso y correo hacen llamadas de red.
    entregar(a_entregar)
    return a_entregar


def revisar(preapproval_id, entregar):
    """Lee la suscripción y TODOS sus cobros en Mercado Pago y registra lo que falte.

    Es lo que usan la vuelta del navegador y la revisión diaria. Devuelve el
    preapproval leído.
    """
    preapproval = obtener(preapproval_id)
    r = get_mercadopago_sdk().invoice().search(filters={'preapproval_id': preapproval_id})
    for cobro in (_respuesta(r).get('results') or []):
        pago_id = (cobro.get('payment') or {}).get('id')
        if not pago_id or Order.objects.filter(mp_payment_id=str(pago_id)).exists():
            continue
        pago = get_mercadopago_payment(pago_id)
        # Solo los aprobados: los rechazos se cuentan una vez, por el webhook.
        # Contarlos acá los sumaría de nuevo en cada revisión.
        if pago.get('status') == 'approved':
            registrar_pago(preapproval, pago, entregar)
    sincronizar_estado(preapproval)
    return preapproval


def procesar_notificacion(tipo, recurso_id, entregar):
    """El webhook de los tópicos de suscripción."""
    if tipo == 'subscription_authorized_payment':
        cobro = _respuesta(get_mercadopago_sdk().invoice().get(recurso_id))
        pago = cobro.get('payment') or {}
        if cobro.get('preapproval_id') and pago.get('id'):
            preapproval = obtener(cobro['preapproval_id'])
            registrar_pago(preapproval, get_mercadopago_payment(pago['id']), entregar)
            sincronizar_estado(preapproval)
    elif tipo == 'subscription_preapproval':
        sincronizar_estado(obtener(recurso_id))
