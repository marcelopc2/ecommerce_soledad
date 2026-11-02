"""Revisa cada 10 minutos que el sitio esté bien y avisa por Telegram si no.

    */10 * * * * cd /srv/ingenioblocks && venv/bin/python manage.py vigilar_sitio

Qué mira:
- Que ingenioblocks.com responda, entrando por internet como un cliente
  (pasa por nginx, el certificado y la aplicación).
- Que quede espacio en el disco.
- Que al certificado le queden más de 20 días.

Cada problema se avisa una vez cada 30 minutos, y cuando se arregla llega un
"volvió". Si se cae el servidor entero esto no corre: para eso está el aviso
externo (UptimeRobot) y, si no llega el resumen de la noche, también es señal.
"""
import shutil
import socket
import ssl
from datetime import datetime, timezone as tz

import requests
from django.conf import settings
from django.core.cache import caches
from django.core.management.base import BaseCommand

from core.alertas import avisar, hora


def _dominio():
    return settings.FRONTEND_URL.split('://', 1)[-1].split('/', 1)[0]


def revisar_sitio():
    try:
        r = requests.get(f'{settings.FRONTEND_URL}/api/health/', timeout=15)
        if r.status_code == 200:
            return None
        return f'El sitio responde con error {r.status_code}.'
    except Exception as e:
        return f'El sitio no responde ({type(e).__name__}).'


def revisar_disco():
    uso = shutil.disk_usage(str(settings.BASE_DIR))
    porcentaje = round(uso.used * 100 / uso.total)
    if porcentaje >= 90:
        return f'El disco del servidor está al {porcentaje}%.'
    return None


def dias_de_certificado():
    dominio = _dominio()
    ctx = ssl.create_default_context()
    with socket.create_connection((dominio, 443), timeout=10) as s:
        with ctx.wrap_socket(s, server_hostname=dominio) as c:
            vence = datetime.strptime(c.getpeercert()['notAfter'], '%b %d %H:%M:%S %Y %Z')
    return (vence.replace(tzinfo=tz.utc) - datetime.now(tz.utc)).days


def revisar_certificado():
    try:
        dias = dias_de_certificado()
    except Exception as e:
        return f'No se pudo revisar el certificado ({type(e).__name__}).'
    if dias < 20:
        return f'Al certificado del sitio le quedan {dias} días (se debería renovar solo).'
    return None


class Command(BaseCommand):
    help = 'Revisa que el sitio esté arriba, con disco y certificado, y avisa por Telegram.'

    def handle(self, *args, **op):
        estado = caches['alertas']
        for clave, revisar in (('sitio', revisar_sitio), ('disco', revisar_disco),
                               ('certificado', revisar_certificado)):
            problema = revisar()
            marca = f'vigilar:{clave}:caido'
            if problema:
                estado.set(marca, problema, None)
                avisar(f'🔴 {problema} ({hora()})', firma=f'vigilar:{clave}')
                self.stdout.write(f'PROBLEMA {clave}: {problema}')
            elif estado.get(marca):
                estado.delete(marca)
                avisar(f'✅ Resuelto: {clave} volvió a estar bien ({hora()}).')
                self.stdout.write(f'resuelto {clave}')
