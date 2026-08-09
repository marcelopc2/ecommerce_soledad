"""Registro de accesos y de visitas.

Todo lo que escribe en las tablas de `panel.models` pasa por acá, para que las
vistas y las señales no repitan el cálculo de la IP ni el de la huella.
"""
import hashlib
import logging
from datetime import date
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth.signals import (
    user_logged_in, user_logged_out, user_login_failed,
)
from django.db.models import F
from django.dispatch import receiver
from django.utils import timezone

from .models import OrigenDiario, RegistroAcceso, VisitaDiaria, VisitanteDiario

log = logging.getLogger('ingenioblocks')


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def ip_del_request(request):
    """IP real del visitante.

    Solo se mira X-Forwarded-For si hay un proxy declarado (PROXY_COUNT>0), y
    en ese caso nginx lo SOBRESCRIBE con la IP real: el cliente no puede
    inventarla. Sin proxy declarado se usa REMOTE_ADDR, porque el encabezado lo
    puede escribir cualquiera y creerle permitiría falsear el origen.
    """
    if request is None:
        return None
    if getattr(settings, 'NUM_PROXIES', 0) > 0:
        reenviada = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if reenviada:
            return reenviada.split(',')[0].strip() or None
    return request.META.get('REMOTE_ADDR') or None


# Se buscan en orden: los motores van ANTES que el navegador base porque casi
# todos se presentan además como Chrome o Safari y, al revés, siempre ganaría
# el genérico.
_NAVEGADORES = [
    ('Edg/', 'Edge'), ('OPR/', 'Opera'), ('SamsungBrowser', 'Samsung Internet'),
    ('Firefox', 'Firefox'), ('Chrome', 'Chrome'), ('Safari', 'Safari'),
]
_SISTEMAS = [
    ('iPhone', 'iPhone'), ('iPad', 'iPad'), ('Android', 'Android'),
    ('Windows', 'Windows'), ('Mac OS', 'Mac'), ('Linux', 'Linux'),
]


def describir_dispositivo(user_agent):
    """"Chrome en Android" a partir del User-Agent, que es ilegible para quien
    administra la tienda. Si no se reconoce, se guarda el original recortado."""
    ua = user_agent or ''
    navegador = next((n for clave, n in _NAVEGADORES if clave in ua), '')
    sistema = next((s for clave, s in _SISTEMAS if clave in ua), '')
    if navegador and sistema:
        return f'{navegador} en {sistema}'
    return navegador or sistema or ua[:60]


def _huella(ip, user_agent, dia):
    """Identificador anónimo y diario de un visitante.

    Lleva la SECRET_KEY como sal y la fecha: sin la sal, cualquiera con la
    tabla podría probar IPs hasta dar con el hash; con la fecha adentro, la
    huella cambia todos los días y no se puede seguir a nadie entre jornadas.
    """
    crudo = f'{ip}|{user_agent}|{dia.isoformat()}|{settings.SECRET_KEY}'
    return hashlib.sha256(crudo.encode('utf-8')).hexdigest()


# Cadenas típicas de robots. No es una lista exhaustiva -es imposible-, pero
# saca el grueso del ruido para que los números signifiquen algo.
_BOTS = (
    'bot', 'crawler', 'spider', 'slurp', 'curl', 'wget', 'python-requests',
    'headlesschrome', 'facebookexternalhit', 'preview', 'monitor', 'scan',
)


def es_robot(user_agent):
    ua = (user_agent or '').lower()
    if not ua:
        return True   # sin identificarse: no es un navegador de persona
    return any(marca in ua for marca in _BOTS)


# ---------------------------------------------------------------------------
# Visitas
# ---------------------------------------------------------------------------

def registrar_visita(request, ruta, referrer=''):
    """Suma una página vista. Nunca lanza: una métrica no puede tumbar la web."""
    try:
        ua = request.META.get('HTTP_USER_AGENT', '')
        if es_robot(ua):
            return False

        hoy = timezone.localdate()
        ruta = (ruta or '/')[:200]

        VisitaDiaria.objects.update_or_create(
            fecha=hoy, ruta=ruta, defaults={},
        )
        VisitaDiaria.objects.filter(fecha=hoy, ruta=ruta).update(vistas=F('vistas') + 1)

        # Visitante único del día. get_or_create + unique_together resuelve la
        # carrera de dos pestañas abiertas a la vez sin contar dos veces.
        huella = _huella(ip_del_request(request), ua, hoy)
        _, nuevo = VisitanteDiario.objects.get_or_create(fecha=hoy, huella=huella)

        # El origen solo se cuenta la primera vez que aparece el visitante: si
        # no, alguien que navega 10 páginas sumaría 10 a "llegó desde Google".
        if nuevo:
            origen = _origen(referrer)
            OrigenDiario.objects.update_or_create(fecha=hoy, origen=origen, defaults={})
            OrigenDiario.objects.filter(fecha=hoy, origen=origen).update(
                visitas=F('visitas') + 1,
            )
        return True
    except Exception:
        log.exception('No se pudo registrar la visita a %s', ruta)
        return False


def _origen(referrer):
    """Dominio de procedencia. Las visitas que vienen del propio sitio no son
    un origen: al navegar entre páginas el referrer es el sitio mismo."""
    if not referrer:
        return 'directo'
    try:
        host = (urlparse(referrer).hostname or '').lower()
    except Exception:
        return 'directo'
    if not host:
        return 'directo'
    propio = (urlparse(settings.FRONTEND_URL).hostname or '').lower()
    if propio and (host == propio or host.endswith('.' + propio)):
        return 'directo'
    return host[:120]


# ---------------------------------------------------------------------------
# Accesos (señales de Django: cubren el panel y el Aula por igual)
# ---------------------------------------------------------------------------

def _zona(request):
    """El panel y el Aula comparten el mismo modelo de usuario, así que la zona
    se deduce de la URL por la que entró."""
    ruta = getattr(request, 'path', '') or ''
    return RegistroAcceso.PANEL if ruta.startswith('/gestion') else RegistroAcceso.SITIO


def anotar_acceso(request, tipo, usuario=None, email=''):
    """Escribe una línea del registro. Nunca lanza: si falla el registro, el
    login tiene que seguir funcionando igual."""
    try:
        RegistroAcceso.objects.create(
            usuario=usuario if (usuario and usuario.is_authenticated) else None,
            email=(email or (getattr(usuario, 'email', '') or ''))[:254],
            tipo=tipo,
            zona=_zona(request),
            ip=ip_del_request(request),
            dispositivo=describir_dispositivo(
                request.META.get('HTTP_USER_AGENT', '') if request else ''
            )[:200],
        )
    except Exception:
        log.exception('No se pudo anotar el acceso (%s)', tipo)


@receiver(user_logged_in)
def _al_entrar(sender, request, user, **kwargs):
    anotar_acceso(request, RegistroAcceso.ENTRADA, usuario=user)


@receiver(user_logged_out)
def _al_salir(sender, request, user, **kwargs):
    if user is not None:
        anotar_acceso(request, RegistroAcceso.SALIDA, usuario=user)


@receiver(user_login_failed)
def _al_fallar(sender, credentials, request=None, **kwargs):
    # `credentials` trae también la clave con la que se intentó autenticar.
    # Acá se toma SOLO el identificador: la contraseña tecleada jamás debe
    # llegar a la base de datos.
    intento = credentials.get('username') or credentials.get('email') or ''

    # Se busca la cuenta a la que apuntaba el intento. Sirve para dos cosas:
    # mostrar el correo de verdad (el panel autentica por `username`, que no
    # siempre es el correo) y distinguir "alguien está probando claves de una
    # cuenta REAL" de "alguien tira correos al azar" — lo primero es una alerta,
    # lo segundo es ruido de bots.
    usuario = None
    if intento:
        from django.contrib.auth.models import User
        usuario = (
            User.objects.filter(username__iexact=intento).first()
            or User.objects.filter(email__iexact=intento).first()
        )

    anotar_acceso(
        request, RegistroAcceso.FALLIDO,
        usuario=usuario,
        email=(usuario.email if usuario and usuario.email else intento),
    )
