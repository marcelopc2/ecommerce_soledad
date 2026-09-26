"""Qué correos se pueden dejar de recibir, y quién se dio de baja.

Hay tres tipos de correo, y la diferencia importa:

  SERVICIO   compra, boleta, bienvenida, recuperar clave, despacho, retiro.
             Son parte de lo que el cliente pagó: se mandan SIEMPRE y no tienen
             enlace de baja. Nadie puede quedarse sin su confirmación de compra
             por haberse dado de baja de otra cosa.

  AULA       "se abrió un modelo nuevo", "ganaste un diploma". Son del servicio,
             pero semanales: a un apoderado le pueden cansar, así que se pueden
             apagar aparte.

  NOVEDADES  los correos masivos que se mandan desde el panel.

Darse de baja de una categoría no toca las otras.

Las bajas se guardan por DIRECCIÓN DE CORREO y no en la ficha del alumno, a
propósito: la importación desde WordPress borra y vuelve a crear a todos los
alumnos. Guardado en la ficha, un "no me escriban más" se perdía en la próxima
importación y se le volvía a escribir a alguien que pidió que no, que es
justamente lo que prohíbe la Ley del Consumidor (art. 28 B).
"""
from django.conf import settings
from django.core import signing

SERVICIO = 'servicio'
AULA = 'aula'
NOVEDADES = 'novedades'

#: Las plantillas que NO son del servicio. Todo lo que no esté acá se manda
#: siempre: si mañana se agrega un correo nuevo y nadie se acuerda de
#: anotarlo, queda del lado seguro -se entrega- y no se pierde en silencio.
CATEGORIA_POR_PLANTILLA = {
    'curso_desbloqueado': AULA,
    'diploma_obtenido': AULA,
    'novedades': NOVEDADES,
}

#: Cómo se nombra cada una frente al cliente, en el pie del correo y en la
#: página de preferencias.
NOMBRES = {
    NOVEDADES: 'novedades de Ingenio Blocks',
    AULA: 'avisos del Aula (modelos nuevos y diplomas)',
}

#: El nombre visible del remitente. Los masivos salen con uno propio: la gente
#: los distingue de un vistazo de los correos de su compra, y puede filtrarlos
#: sin perder los otros.
REMITENTES = {
    NOVEDADES: 'Ingenio Blocks · Novedades',
}

_SAL = 'comunicaciones.baja'


def categoria_de(plantilla):
    return CATEGORIA_POR_PLANTILLA.get(plantilla, SERVICIO)


def normalizar(email):
    return (email or '').strip().lower()


def esta_de_baja(email, categoria):
    from .models import BajaDeCorreo
    return BajaDeCorreo.objects.filter(email=normalizar(email), categoria=categoria).exists()


def dar_de_baja(email, categoria, origen=''):
    from .models import BajaDeCorreo
    BajaDeCorreo.objects.get_or_create(
        email=normalizar(email), categoria=categoria, defaults={'origen': origen})


def volver_a_suscribir(email, categoria):
    from .models import BajaDeCorreo
    BajaDeCorreo.objects.filter(email=normalizar(email), categoria=categoria).delete()


def correos_de_gestion():
    """Las direcciones del equipo: reciben la prueba de cada correo masivo y
    son las únicas que pasan el freno del servidor de pruebas."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return sorted({
        normalizar(e) for e in User.objects
        .filter(is_staff=True, is_active=True).exclude(email='')
        .values_list('email', flat=True)
    })


# --- Enlaces firmados -------------------------------------------------------
#
# El enlace de baja no pide iniciar sesión: la gente lo aprieta desde el correo,
# muchas veces en el teléfono y sin acordarse de su clave. En su lugar lleva la
# dirección y la categoría FIRMADAS con la SECRET_KEY: nadie puede fabricar el
# enlace de otra persona para darla de baja, y no caduca, porque un "no me
# escriban más" tiene que funcionar aunque el correo sea de hace un año.

def token_de(email, categoria):
    return signing.dumps({'e': normalizar(email), 'c': categoria}, salt=_SAL, compress=True)


def leer_token(token):
    """(email, categoria), o BadSignature si el enlace fue alterado."""
    datos = signing.loads(token, salt=_SAL)
    if datos.get('c') not in NOMBRES:
        raise signing.BadSignature('categoría desconocida')
    return datos['e'], datos['c']


def _base():
    return (settings.BACKEND_PUBLIC_URL or settings.FRONTEND_URL).rstrip('/')


def url_preferencias(email, categoria):
    return '%s/api/correos/preferencias/%s/' % (_base(), token_de(email, categoria))


def url_baja_un_clic(email, categoria):
    return '%s/api/correos/baja/%s/' % (_base(), token_de(email, categoria))
