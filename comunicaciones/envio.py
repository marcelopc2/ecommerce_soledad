"""Cómo sale un correo masivo: la prueba, la cola y el envío de a poco.

Por qué no se manda todo de una vez desde el panel
--------------------------------------------------
Son cientos de correos por la misma cuenta de Gmail que manda las
confirmaciones de compra. Mandados de golpe, la pantalla del panel quedaría
colgada varios minutos y Google podría tomarlo como abuso y frenar la cuenta
por un día -y ese día nadie recibiría la confirmación de su compra-. En vez de
eso el panel solo arma la lista, y un comando que corre cada minuto la va
despachando de a poco (`manage.py enviar_masivos`).

Por qué la prueba es obligatoria
--------------------------------
El envío a todos no se habilita hasta que se mandó la prueba de ESE contenido,
sin cambios desde entonces. Del otro lado hay cientos de clientes y un correo
enviado no se puede recoger.
"""
import logging
import time
from collections import Counter
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.emails import enviar_email

from .models import BajaDeCorreo, DestinatarioMasivo, EnvioMasivo
from .preferencias import NOVEDADES, correos_de_gestion, normalizar

log = logging.getLogger('ingenioblocks.pagos')

#: Una fila que quedó "enviándose" más de esto es de un envío que se cortó a la
#: mitad (reinicio del servidor, por ejemplo). Se da por fallida y NO se
#: reintenta: mandarle el mismo correo dos veces a alguien es peor que dejar a
#: uno sin recibirlo, y ese caso queda a la vista en el historial.
INTERRUMPIDO_TRAS = timedelta(minutes=10)


def correos_de_la_audiencia(audiencia):
    """Las direcciones a las que iría el correo, sin repetir y sin el equipo.

    "Todos los clientes" son los alumnos y también quien compró algo que no
    trae Aula: un correo de novedades le sirve igual. El equipo no entra porque
    ya recibió la prueba.
    """
    from lms.models import Membership
    from payments.models import Order

    alumnos = (Membership.objects
               .filter(user__is_staff=False, user__is_active=True)
               .exclude(user__email=''))
    if audiencia == EnvioMasivo.VIGENTES:
        alumnos = alumnos.filter(Membership.VIGENTE)
    correos = {normalizar(e) for e in alumnos.values_list('user__email', flat=True)}

    if audiencia == EnvioMasivo.TODOS:
        correos |= {normalizar(e) for e in Order.objects
                    .filter(status='PAID').exclude(customer_email='')
                    .values_list('customer_email', flat=True)}

    correos.discard('')
    return sorted(correos - set(correos_de_gestion()))


def cuantos(audiencia):
    correos = correos_de_la_audiencia(audiencia)
    de_baja = BajaDeCorreo.objects.filter(categoria=NOVEDADES, email__in=correos).count()
    return {'total': len(correos), 'de_baja': de_baja, 'a_enviar': len(correos) - de_baja}


def contexto_de(envio):
    parrafos = envio.parrafos()
    return {
        'titulo': envio.asunto,
        'preheader': parrafos[0][:140] if parrafos else envio.asunto,
        'parrafos': parrafos,
        'boton_texto': envio.boton_texto,
        'boton_url': envio.boton_url,
    }


def enviar_a(envio, email, prueba=False):
    """Manda el correo a UNA persona. None si no salió porque se dio de baja.

    fail_silently=False: acá sí interesa saber si falló, para anotarlo en el
    historial. En los correos de una compra es al revés (ver core/emails.py).
    """
    asunto = ('[PRUEBA] ' if prueba else '') + envio.asunto
    return enviar_email('novedades', asunto, [email], contexto=contexto_de(envio),
                        reply_to=[settings.CONTACT_EMAIL], fail_silently=False,
                        es_prueba=prueba)


def enviar_prueba(envio):
    """Manda el correo al equipo y deja anotado QUÉ contenido se probó."""
    destinos = correos_de_gestion()
    llegaron = [e for e in destinos if enviar_a(envio, e, prueba=True)]
    envio.prueba_enviada_en = timezone.now()
    envio.prueba_huella = envio.huella()
    envio.save(update_fields=['prueba_enviada_en', 'prueba_huella', 'actualizado_en'])
    return llegaron


class NoSePuedeEnviar(Exception):
    pass


def motivo_para_no_enviar(envio):
    """Por qué el botón de "enviar a todos" está apagado, o None si se puede."""
    if not envio.editable:
        return 'Este correo ya se envió.'
    if not settings.ENVIAR_CORREOS:
        return ('El envío a todos se activa cuando el sitio esté en su dominio '
                'definitivo. Mientras tanto funciona solo la prueba al equipo.')
    if not envio.prueba_enviada_en:
        return 'Primero mándate la prueba y revisa que se vea bien.'
    if not envio.prueba_al_dia:
        return ('Cambiaste el correo después de la prueba. Manda una prueba '
                'nueva para ver cómo quedó.')
    return None


def encolar(envio):
    """Arma la lista de destinatarios y la deja lista para salir.

    La lista se congela ACÁ: quien compre mañana no recibe un correo que se
    decidió hoy, y el historial dice exactamente a quién se le mandó. Los que
    ya se habían dado de baja quedan anotados como omitidos, no desaparecen.
    """
    motivo = motivo_para_no_enviar(envio)
    if motivo:
        raise NoSePuedeEnviar(motivo)

    correos = correos_de_la_audiencia(envio.audiencia)
    bajas = set(BajaDeCorreo.objects.filter(categoria=NOVEDADES, email__in=correos)
                .values_list('email', flat=True))

    with transaction.atomic():
        envio = EnvioMasivo.objects.select_for_update().get(pk=envio.pk)
        if envio.estado != EnvioMasivo.BORRADOR:   # dos clics seguidos
            raise NoSePuedeEnviar('Este correo ya se envió.')
        DestinatarioMasivo.objects.bulk_create([
            DestinatarioMasivo(
                envio=envio, email=e,
                estado=DestinatarioMasivo.OMITIDO if e in bajas else DestinatarioMasivo.PENDIENTE,
                error='Se había dado de baja de las novedades' if e in bajas else '')
            for e in correos
        ])
        envio.estado = EnvioMasivo.EN_COLA
        envio.encolado_en = timezone.now()
        envio.save(update_fields=['estado', 'encolado_en', 'actualizado_en'])
    return envio


def _rescatar_interrumpidos():
    limite = timezone.now() - INTERRUMPIDO_TRAS
    return DestinatarioMasivo.objects.filter(
        estado=DestinatarioMasivo.ENVIANDO, enviado_en__lt=limite,
    ).update(estado=DestinatarioMasivo.FALLIDO,
             error='El envío se interrumpió a la mitad. No se reintenta para no '
                   'mandarlo dos veces.')


def procesar(lote=25, pausa=1.5, dormir=time.sleep):
    """Despacha hasta `lote` correos del envío más antiguo en cola.

    Cada fila se "reserva" con un UPDATE condicionado a que siga pendiente: si
    por algún motivo corrieran dos procesos a la vez, solo uno gana cada fila y
    nadie recibe el correo dos veces. Funciona igual en cualquier base de datos.
    """
    _rescatar_interrumpidos()
    envio = EnvioMasivo.objects.filter(estado=EnvioMasivo.EN_COLA).order_by('encolado_en', 'id').first()
    if envio is None:
        return None, Counter()

    ids = list(envio.destinatarios.filter(estado=DestinatarioMasivo.PENDIENTE)
               .order_by('id').values_list('id', flat=True)[:lote])
    cuenta = Counter()
    for i, pk in enumerate(ids):
        # Si alguien lo canceló desde el panel, se para en el acto.
        if not EnvioMasivo.objects.filter(pk=envio.pk, estado=EnvioMasivo.EN_COLA).exists():
            break
        reservado = DestinatarioMasivo.objects.filter(
            pk=pk, estado=DestinatarioMasivo.PENDIENTE,
        ).update(estado=DestinatarioMasivo.ENVIANDO, enviado_en=timezone.now())
        if not reservado:
            continue

        d = DestinatarioMasivo.objects.get(pk=pk)
        try:
            salio = enviar_a(envio, d.email)
            # None = se dio de baja DESPUÉS de armada la lista: se respeta.
            d.estado = DestinatarioMasivo.ENVIADO if salio else DestinatarioMasivo.OMITIDO
            if not salio:
                d.error = 'Se dio de baja antes de que le llegara'
        except Exception as e:
            d.estado = DestinatarioMasivo.FALLIDO
            d.error = str(e)[:300]
            log.warning('Correo masivo "%s" no le llegó a %s: %s', envio.asunto, d.email, e)
        d.enviado_en = timezone.now()
        d.save(update_fields=['estado', 'error', 'enviado_en'])
        cuenta[d.estado] += 1

        if pausa and i < len(ids) - 1:
            dormir(pausa)

    quedan = envio.destinatarios.filter(
        estado__in=[DestinatarioMasivo.PENDIENTE, DestinatarioMasivo.ENVIANDO]).exists()
    if not quedan:
        EnvioMasivo.objects.filter(pk=envio.pk, estado=EnvioMasivo.EN_COLA).update(
            estado=EnvioMasivo.TERMINADO, terminado_en=timezone.now())
    return envio, cuenta
