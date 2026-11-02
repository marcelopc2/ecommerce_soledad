"""Alertas al celular, por Telegram, para quien mantiene el sitio.

Llegan tres tipos de mensaje:
- Problemas: cualquier error que el sitio registre (un 500, una boleta que no
  se emitió, un correo que no salió, un cobro que no se sabe si pasó…). Entran
  solos por el ManejadorTelegram del LOGGING, más los avisos explícitos de
  cobros rechazados y de `vigilar_sitio`.
- Mensajes de clientes: cada mensaje del formulario de contacto.
- El resumen diario (`resumen_diario`).

Configuración en el .env: TELEGRAM_BOT_TOKEN (la clave que da @BotFather) y
TELEGRAM_CHAT_ID (a quién le escribe). Sin las dos, no se manda nada; y en el
computador local nunca hay (ver CLAVES_DE_SERVICIOS_REALES en settings).

Una alerta NUNCA puede romper lo que la provocó: todo va en try y con timeout
corto. Y no puede inundar: el mismo problema se avisa una vez cada 30 minutos
(la marca vive en un caché en disco, compartido por el sitio y los cron).
"""
import hashlib
import logging
import traceback

import requests
from django.conf import settings
from django.utils import timezone

MINUTOS_ENTRE_REPETIDOS = 30


def configurado():
    return bool(getattr(settings, 'TELEGRAM_BOT_TOKEN', '') and getattr(settings, 'TELEGRAM_CHAT_ID', ''))


def _ya_avisado(firma):
    """True si este mismo problema ya se avisó hace poco (y si no, lo marca)."""
    try:
        from django.core.cache import caches
        clave = 'alerta:' + hashlib.md5(firma.encode('utf-8')).hexdigest()
        return not caches['alertas'].add(clave, 1, MINUTOS_ENTRE_REPETIDOS * 60)
    except Exception:
        return False


def avisar(texto, firma=None):
    """Manda `texto` por Telegram. Devuelve True si salió.

    `firma` agrupa repeticiones: con la misma firma, solo sale la primera de
    cada 30 minutos. Sin firma sale siempre (mensajes de clientes, resumen).
    """
    if not configurado():
        return False
    if firma and _ya_avisado(firma):
        return False
    try:
        return _mandar(settings.TELEGRAM_CHAT_ID, texto)
    except Exception:
        return False


def _mandar(chat_id, texto):
    r = requests.post(
        f'https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage',
        data={'chat_id': chat_id, 'text': texto[:4000], 'disable_web_page_preview': 'true'},
        timeout=5,
    )
    if r.ok:
        return True
    # Cuando un grupo se vuelve "supergrupo" (pasa solo al cambiar ciertos
    # ajustes del grupo), Telegram le cambia el número y rechaza el viejo
    # diciendo cuál es el nuevo. Se sigue al nuevo para no perder alertas; el
    # .env conviene actualizarlo igual (queda advertido en el log).
    try:
        nuevo = (r.json().get('parameters') or {}).get('migrate_to_chat_id')
    except Exception:
        nuevo = None
    if nuevo:
        logging.getLogger('ingenioblocks.alertas').warning(
            'El grupo de alertas cambió de número: poner TELEGRAM_CHAT_ID=%s en el .env', nuevo)
        return _mandar(nuevo, texto)
    return False


def clp(n):
    return f'${int(n or 0):,}'.replace(',', '.')


def hora():
    return timezone.localtime().strftime('%d-%m %H:%M')


class ManejadorTelegram(logging.Handler):
    """Manda por Telegram cada error que se registre en el sitio.

    Se ignoran los de django.security: son robots que entran por la IP del
    servidor en vez del dominio (cientos al mes, ninguno es un problema).
    """
    IGNORADOS = ('django.security',)

    def emit(self, record):
        if record.name.startswith(self.IGNORADOS):
            return
        try:
            mensaje = record.getMessage()
            primera = (mensaje.splitlines() or [''])[0][:400]
            detalle = ''
            if record.exc_info and record.exc_info[1] is not None:
                detalle = ''.join(traceback.format_exception_only(*record.exc_info[:2])).strip()[:300]
            texto = f'🔴 Problema en ingenioblocks.com ({hora()})\n\n{primera}'
            if detalle:
                texto += f'\n\n{detalle}'
            avisar(texto, firma=f'{record.name}:{primera[:120]}')
        except Exception:
            pass   # una alerta que falla no puede generar otro error
