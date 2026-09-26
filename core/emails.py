"""Envío de correos con plantilla HTML + alternativa en texto plano.

Todos los correos del sitio pasan por acá para que compartan diseño, pie y
manejo de errores. Cada correo tiene DOS plantillas en templates/emails/:
`<nombre>.html` y `<nombre>.txt`.

Por qué el texto plano no es opcional:
- Los filtros de spam penalizan los correos que solo traen HTML.
- Los relojes, lectores de pantalla y clientes en modo texto muestran esa parte.
- Si el HTML no carga, el mensaje igual se entiende.
"""
import logging
from email.utils import formataddr, parseaddr

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

log = logging.getLogger('ingenioblocks.pagos')

_IMG_DIR = settings.BASE_DIR / 'core' / 'static' / 'emails'

# Logo de la cabecera. Es PNG y no el SVG del sitio porque Gmail, Outlook y
# Apple Mail no renderizan SVG en correo. Está a 2x (310x158) y se muestra a
# 155px para que se vea nítido en pantallas retina.
#
# PARA CAMBIARLO: reemplazar este archivo por el logo definitivo (idealmente
# 310x158 px, fondo transparente, en blanco porque va sobre morado). No hay que
# tocar código: el ancho/alto de visualización está fijo en la plantilla.
LOGO_PATH = _IMG_DIR / 'logo-ingenioblocks.png'
LOGO_CID = 'logo-ingenioblocks'

# Mosaico de 28x28 con la cuadrícula del sitio (líneas blancas al 5% sobre
# transparente). En el sitio esto se hace con linear-gradient repetido, pero
# eso no existe en correo: la única forma portable es una imagen que se repita.
GRID_PATH = _IMG_DIR / 'grid-tile.png'
GRID_CID = 'grid-tile'


def _contexto_base(extra):
    """Datos que necesitan TODAS las plantillas (pie de página, enlaces)."""
    ctx = {
        'contacto_email': settings.CONTACT_EMAIL,
        'frontend_url': settings.FRONTEND_URL,
        # Referencias a las imágenes adjuntas. El visor de desarrollo las
        # reemplaza por data URI, porque "cid:" solo resuelve dentro de un
        # cliente de correo.
        'logo_src': f'cid:{LOGO_CID}',
        'grid_src': f'cid:{GRID_CID}',
    }
    ctx.update(extra or {})
    return ctx


class _CorreoConLogo(EmailMultiAlternatives):
    """Correo que incrusta el logo como imagen en línea (CID).

    Por qué CID y no otra cosa:
    - Una URL remota (<img src="https://...">) NO sirve: Gmail, Outlook y casi
      todos los clientes bloquean las imágenes externas hasta que la persona
      aprieta "mostrar imágenes". El logo quedaría invisible justo en la primera
      impresión, que es la que importa.
    - Una data URI tampoco: Gmail y Outlook las descartan en correo.

    Por qué se arma acá y no con `attach()`:
    Django mete todo lo adjuntado en un multipart/MIXED, y ahí el cliente marca
    el correo con el clip de "tiene adjuntos" —cada correo aparecería con un
    archivo pegado—. (Django 6 quitó `mixed_subtype`, que antes servía para
    esto.)

    La imagen se agrega a la PARTE HTML, no al mensaje completo. El resultado
    es la estructura estándar:

        multipart/alternative
        ├── text/plain
        └── multipart/related
            ├── text/html
            └── image/png  (Content-ID)

    Así la imagen queda ligada solo al HTML que la usa: el cliente la resuelve
    por cid: y no la lista como adjunto. Envolver el mensaje entero no es
    posible —Python no deja convertir un multipart/alternative en related—, y
    tampoco sería correcto: la versión de texto no referencia ninguna imagen.
    """

    def message(self, **kwargs):
        msg = super().message(**kwargs)
        parte_html = msg.get_body(preferencelist=('html',))
        if parte_html is None:
            return msg
        # Si falta algún archivo el correo igual sale: el logo tiene alt y la
        # cuadrícula es decorativa (queda el morado sólido de respaldo).
        for ruta, cid, nombre in (
            (LOGO_PATH, LOGO_CID, 'ingenioblocks.png'),
            (GRID_PATH, GRID_CID, 'grid.png'),
        ):
            if ruta.exists():
                parte_html.add_related(
                    ruta.read_bytes(),
                    maintype='image', subtype='png',
                    cid=f'<{cid}>',
                    disposition='inline',
                    filename=nombre,
                )
        return msg


def enviar_email(plantilla, asunto, destinatarios, contexto=None,
                 reply_to=None, fail_silently=True, es_prueba=False):
    """Renderiza `emails/<plantilla>.html` + `.txt` y los manda como multipart.

    fail_silently=True por defecto A PROPÓSITO: estos correos se disparan
    dentro de flujos críticos (confirmar un pago, otorgar acceso). Si el SMTP
    está caído, es preferible que la compra se complete y el correo se pierda,
    antes que reventar la transacción y dejar al cliente pagado sin orden.
    Los casos donde sí importa saberlo (formulario de contacto) lo llaman con
    fail_silently=False y manejan el error.

    Devuelve el mensaje, o None si no salió a nadie (freno o bajas).
    `es_prueba` salta las bajas: la prueba de un masivo tiene que llegarle al
    equipo aunque alguien de gestión se haya dado de baja de las novedades.
    """
    from comunicaciones.preferencias import (
        NOMBRES, REMITENTES, SERVICIO, categoria_de, correos_de_gestion,
        esta_de_baja, normalizar, url_baja_un_clic, url_preferencias)

    destinatarios = [d for d in destinatarios if d]

    # Freno de mano: fuera del sitio de verdad no sale NADA a un cliente. Va
    # acá, en el único punto por donde pasan todos los correos, y no en cada
    # comando: basta que alguien agregue un envío nuevo sin acordarse del freno
    # para repetir el accidente. Ver settings.ENVIAR_CORREOS.
    #
    # La única excepción es el equipo: no son clientes, que es a quien el freno
    # protege. Sin ella no se podía probar un correo masivo antes del
    # lanzamiento, ni recuperar la clave del panel.
    if not settings.ENVIAR_CORREOS:
        equipo = set(correos_de_gestion())
        frenados = [d for d in destinatarios if normalizar(d) not in equipo]
        if frenados:
            log.warning(
                'CORREO NO ENVIADO (servidor de pruebas): plantilla=%s asunto=%r '
                'destinatarios=%s', plantilla, asunto, frenados)
        destinatarios = [d for d in destinatarios if normalizar(d) in equipo]
        if not destinatarios:
            return None

    categoria = categoria_de(plantilla)
    if categoria == SERVICIO:
        return _armar_y_mandar(plantilla, asunto, destinatarios, contexto,
                               reply_to, fail_silently)

    # Los que se pueden dar de baja salen UNO POR PERSONA: cada uno lleva su
    # propio enlace firmado, y un enlace compartido le permitiría a uno dar de
    # baja al otro.
    remitente = settings.DEFAULT_FROM_EMAIL
    if categoria in REMITENTES:
        remitente = formataddr((REMITENTES[categoria],
                                parseaddr(settings.DEFAULT_FROM_EMAIL)[1]))
    salio = None
    for d in destinatarios:
        if not es_prueba and esta_de_baja(d, categoria):
            log.info('CORREO OMITIDO: %s se dio de baja de %s (plantilla=%s)',
                     d, categoria, plantilla)
            continue
        ctx = dict(contexto or {})
        ctx['baja_url'] = url_preferencias(d, categoria)
        ctx['baja_de'] = NOMBRES[categoria]
        # La cabecera estándar de baja (RFC 8058): Gmail y Apple Mail muestran
        # su propio botón "Cancelar suscripción" junto al remitente. Es lo que
        # más protege la cuenta: quien no quiere más correos se da de baja ahí
        # en vez de apretar "spam", que es lo que hace que Google la frene.
        cabeceras = {
            'List-Unsubscribe': '<%s>' % url_baja_un_clic(d, categoria),
            'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click',
        }
        salio = _armar_y_mandar(plantilla, asunto, [d], ctx, reply_to,
                                fail_silently, cabeceras, remitente) or salio
    return salio


def _armar_y_mandar(plantilla, asunto, destinatarios, contexto, reply_to,
                    fail_silently, cabeceras=None, remitente=None):
    ctx = _contexto_base(contexto)
    cuerpo_txt = render_to_string(f'emails/{plantilla}.txt', ctx)
    cuerpo_html = render_to_string(f'emails/{plantilla}.html', ctx)

    msg = _CorreoConLogo(
        subject=asunto,
        body=cuerpo_txt,                       # parte de texto
        from_email=remitente or settings.DEFAULT_FROM_EMAIL,
        to=destinatarios,
        reply_to=reply_to,
        headers=cabeceras,
    )
    msg.attach_alternative(cuerpo_html, 'text/html')   # parte HTML
    msg.send(fail_silently=fail_silently)
    return msg


def formato_clp(valor):
    """12900 -> '$12.900' (separador de miles chileno)."""
    try:
        return f'${int(valor):,}'.replace(',', '.')
    except (TypeError, ValueError):
        return '—'
