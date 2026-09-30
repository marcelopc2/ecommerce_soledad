"""Transbank Oneclick Mall: inscribir una tarjeta y cobrarle.

Es la pasarela de la tienda porque es lo que el comercio tiene contratado con
Transbank (Webpay Plus no). Sirve para las dos cosas:

- Compra normal: se inscribe la tarjeta y en el mismo retorno se cobra una vez.
- Suscripción: se guarda la tarjeta inscrita y se le vuelve a cobrar sola cada
  mes (ver cobrar_suscripcion y manage.py cobrar_suscripciones).

Oneclick "Mall" significa que hay dos códigos de comercio: el del MALL, con el
que se autentica todo, y el de la TIENDA hija, que es la que recibe cada cobro.
Van en el .env:

    TBK_API_KEY_ID           código del mall
    TBK_API_KEY_SECRET       llave secreta
    TBK_ONECLICK_TIENDA      código de la tienda hija
    TBK_ENVIRONMENT          INTEGRACION (pruebas) o PRODUCCION

Sin nada configurado se usan los códigos PÚBLICOS de integración de Transbank,
que no cobran de verdad.
"""
import hashlib
import logging
import os

from dateutil.relativedelta import relativedelta
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone
from transbank.common.integration_api_keys import IntegrationApiKeys
from transbank.common.integration_commerce_codes import IntegrationCommerceCodes
from transbank.common.integration_type import IntegrationType
from transbank.common.options import WebpayOptions
from transbank.webpay.oneclick.mall_inscription import MallInscription
from transbank.webpay.oneclick.mall_transaction import MallTransaction
from transbank.webpay.oneclick.request import MallTransactionAuthorizeDetails

from .models import Order, OrderItem, Suscripcion, TarjetaOneclick

log = logging.getLogger('ingenioblocks.pagos')


# -- configuración --------------------------------------------------------

def _produccion():
    return os.environ.get('TBK_ENVIRONMENT', 'INTEGRACION').upper() == 'PRODUCCION'


def _opciones():
    produccion = _produccion()
    return WebpayOptions(
        os.environ.get('TBK_API_KEY_ID', IntegrationCommerceCodes.ONECLICK_MALL),
        os.environ.get('TBK_API_KEY_SECRET', IntegrationApiKeys.WEBPAY),
        IntegrationType.LIVE if produccion else IntegrationType.TEST,
    )


def codigo_tienda():
    """El código de la tienda hija, que es la que recibe la plata.

    En producción no tiene valor por omisión: caer al código de pruebas le
    mandaría el cobro a una tienda que no es la nuestra. Mejor que falle.
    """
    codigo = os.environ.get('TBK_ONECLICK_TIENDA', '').strip()
    if codigo:
        return codigo
    if _produccion():
        raise ImproperlyConfigured('Falta TBK_ONECLICK_TIENDA en el .env (código de la tienda hija de Oneclick).')
    return IntegrationCommerceCodes.ONECLICK_MALL_CHILD1


def username_de(email):
    """El `username` con que se inscribe una tarjeta en Transbank.

    Transbank lo exige (máximo 40 caracteres) y hay que repetirlo en cada cobro.
    Se deriva del correo con un hash y no se usa el correo tal cual: hay correos
    de más de 40 caracteres, y truncarlos podía hacer chocar a dos personas.
    """
    return 'ib-' + hashlib.sha256(email.strip().lower().encode()).hexdigest()[:30]


def ordenes_de_compra(order):
    """Las dos órdenes de compra que pide Transbank (máximo 26 caracteres).

    Una es del mall y otra de la tienda hija, y tienen que ser distintas. Salen
    del uuid de la orden: el principio para el mall, el final para la tienda.
    """
    h = order.order_id.hex
    return h[:26], h[-26:]


# -- inscripción ----------------------------------------------------------

def iniciar_inscripcion(email, url_retorno):
    """Pide a Transbank la página donde el cliente registra su tarjeta.

    Devuelve (token, url). El navegador tiene que llegar a `url` con un POST
    que lleve `TBK_TOKEN=token`.
    """
    codigo_tienda()   # si falta la configuración, que falle ANTES de mandar al cliente a Transbank
    r = MallInscription(_opciones()).start(username_de(email), email.strip().lower(), url_retorno)
    return r['token'], r['url_webpay']


def terminar_inscripcion(token, email):
    """Cierra la inscripción. Devuelve la TarjetaOneclick, o None si no quedó.

    Transbank responde `response_code` 0 cuando la tarjeta quedó inscrita. Si
    la persona canceló o el banco la rechazó viene otro número, y ahí no hay
    tarjeta con que cobrar.
    """
    r = MallInscription(_opciones()).finish(token)
    if r.get('response_code') != 0 or not r.get('tbk_user'):
        log.info('Inscripción Oneclick sin tarjeta para %s (response_code %s)',
                 email, r.get('response_code'))
        return None
    numero = str(r.get('card_number') or '')
    return TarjetaOneclick.objects.create(
        email=email.strip().lower(),
        username=username_de(email),
        tbk_user=r['tbk_user'],
        tipo=r.get('card_type') or '',
        ultimos4=numero[-4:],
    )


# -- cobro ----------------------------------------------------------------

AUTORIZADO = 'AUTORIZADO'
RECHAZADO = 'RECHAZADO'
DESCONOCIDO = 'DESCONOCIDO'


def _estado_de(respuesta):
    detalles = (respuesta or {}).get('details') or []
    if detalles and detalles[0].get('status') == 'AUTHORIZED' and detalles[0].get('response_code') == 0:
        return AUTORIZADO
    return RECHAZADO


def cobrar(order, tarjeta):
    """Le cobra a la tarjeta el total de la orden. Devuelve AUTORIZADO,
    RECHAZADO o DESCONOCIDO.

    DESCONOCIDO es cuando la llamada falló y tampoco se pudo preguntar después
    cómo quedó: puede haberse cobrado. Esa orden va a revisión manual y NO se
    reintenta, porque reintentar un cobro que sí pasó es cobrar dos veces.
    """
    padre, hija = ordenes_de_compra(order)
    tx = MallTransaction(_opciones())
    detalle = MallTransactionAuthorizeDetails(codigo_tienda(), hija, 1, int(order.total_amount))
    try:
        return _estado_de(tx.authorize(tarjeta.username, tarjeta.tbk_user, padre, detalle))
    except Exception:
        log.exception('Falló el cobro Oneclick de la orden %s; se pregunta el estado', order.order_id)

    # Se corta la red DESPUÉS de que Transbank cobró es el caso que importa: la
    # orden de compra es única, así que se puede preguntar cómo quedó.
    try:
        return _estado_de(tx.status(padre))
    except Exception:
        log.exception('REVISAR A MANO: no se sabe si se cobró la orden %s (monto %s). '
                      'Confirmar en el portal de Transbank.', order.order_id, order.total_amount)
        return DESCONOCIDO


def aplicar_resultado(order, resultado):
    """Deja la orden en el estado que corresponde al resultado del cobro."""
    order.status = {AUTORIZADO: 'PAID', RECHAZADO: 'FAILED'}.get(resultado, 'REVIEW')
    order.save(update_fields=['status', 'updated_at'])


def crear_suscripcion(order, tarjeta):
    """Si la orden pagada trae un producto de suscripción, la deja andando.

    El próximo cobro es dentro de `access_months` meses: la primera compra ya
    pagó ese período. Se cobra el precio del producto sin cupón: un cupón es
    un descuento para la primera compra, no para siempre.
    """
    producto = next((p for p in order.products.all() if p.es_suscripcion), None)
    if producto is None or hasattr(order, 'suscripcion_iniciada'):
        return None
    meses = max(1, producto.access_months or 1)
    return Suscripcion.objects.create(
        email=order.customer_email.strip().lower(),
        producto=producto,
        tarjeta=tarjeta,
        orden_inicial=order,
        monto=int(producto.effective_price),
        cada_meses=meses,
        proximo_cobro=timezone.localdate() + relativedelta(months=meses),
    )


def orden_de_renovacion(suscripcion):
    """La orden del cobro de este mes, con los datos de la primera compra."""
    base = suscripcion.orden_inicial
    with transaction.atomic():
        order = Order.objects.create(
            customer_email=suscripcion.email,
            customer_name=base.customer_name,
            student_name=base.student_name,
            customer_phone=base.customer_phone,
            total_amount=suscripcion.monto,
            status='PENDING',
            pasarela=Order.ONECLICK,
            suscripcion=suscripcion,
        )
        order.products.set([suscripcion.producto])
        OrderItem.objects.create(
            order=order, product=suscripcion.producto,
            name=suscripcion.producto.name, unit_price=suscripcion.monto,
        )
    return order


def cobrar_suscripcion(suscripcion, entregar):
    """Hace el cobro que toca. Devuelve (orden, resultado).

    `entregar` es la función que emite la boleta, extiende la membresía y
    manda el correo de una orden pagada (payments.views._entregar_compra): la
    misma que usa una compra hecha a mano, para que un cobro automático no se
    comporte distinto.
    """
    order = orden_de_renovacion(suscripcion)
    resultado = cobrar(order, suscripcion.tarjeta)
    aplicar_resultado(order, resultado)
    hoy = timezone.localdate()

    if resultado == AUTORIZADO:
        suscripcion.proximo_cobro = suscripcion.proximo_cobro + relativedelta(months=suscripcion.cada_meses)
        # Si llevaba días atrasada por rechazos, no se le cobra dos veces
        # seguidas para "ponerse al día": el próximo cobro nunca queda en el pasado.
        if suscripcion.proximo_cobro <= hoy:
            suscripcion.proximo_cobro = hoy + relativedelta(months=suscripcion.cada_meses)
        suscripcion.intentos_fallidos = 0
        suscripcion.ultimo_error = ''
        suscripcion.save()
        log.info('Suscripción %s cobrada: orden %s por %s', suscripcion.pk, order.order_id, order.total_amount)
        entregar(order)
    elif resultado == RECHAZADO:
        suscripcion.intentos_fallidos += 1
        suscripcion.ultimo_error = 'Transbank rechazó el cobro'
        if suscripcion.intentos_fallidos >= Suscripcion.INTENTOS_MAXIMOS:
            suscripcion.estado = Suscripcion.SUSPENDIDA
        else:
            suscripcion.proximo_cobro = hoy + relativedelta(days=Suscripcion.DIAS_ENTRE_INTENTOS)
        suscripcion.save()
        log.info('Suscripción %s: cobro rechazado (%s de %s)', suscripcion.pk,
                 suscripcion.intentos_fallidos, Suscripcion.INTENTOS_MAXIMOS)
    else:
        # No se sabe si se cobró: se suspende hasta que alguien lo revise en el
        # portal de Transbank. Seguir cobrando podía cobrarle dos veces el mes.
        suscripcion.estado = Suscripcion.SUSPENDIDA
        suscripcion.ultimo_error = 'No se supo si el cobro pasó: revisar en Transbank'
        suscripcion.save()

    return order, resultado
