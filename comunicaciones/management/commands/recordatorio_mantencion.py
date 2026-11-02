"""Recordatorio mensual de mantención, por Telegram.

    0 10 1 * * cd /srv/ingenioblocks && venv/bin/python manage.py recordatorio_mantencion

El primer día de cada mes manda qué hay para actualizar (librerías del sitio
y sistema del servidor) y un texto listo para copiar y pegarle a Claude, que
hace la actualización: primero en local con todas las pruebas, y solo si pasan
la sube.

--ver  muestra el mensaje acá en vez de mandarlo.
"""
import json
import subprocess
import sys
from pathlib import Path

from django.core.management.base import BaseCommand

from core.alertas import avisar, configurado

#: Las que importan: si alguna tiene versión nueva, se nombra en el mensaje.
IMPORTANTES = ('django', 'djangorestframework', 'djangorestframework-simplejwt', 'django-axes',
               'transbank-sdk', 'mercadopago', 'requests', 'nh3', 'gunicorn', 'pillow')

PROMPT = ('Mantención mensual de ingenioblocks.com: revisa las actualizaciones pendientes '
          '(sistema del servidor, Django y librerías de Python, y paquetes del frontend). '
          'Actualiza primero en local y corre todas las pruebas; súbelas solo si todo pasa. '
          'Si el servidor pide reinicio, reinícialo de madrugada. Al final dime qué cambió.')


class Command(BaseCommand):
    help = 'Manda por Telegram el recordatorio mensual de actualizaciones.'

    def add_arguments(self, parser):
        parser.add_argument('--ver', action='store_true')

    def handle(self, *args, **op):
        lineas = ['🛠️ Mantención del mes · ingenioblocks.com', '']

        try:
            r = subprocess.run([sys.executable, '-m', 'pip', 'list', '--outdated', '--format=json'],
                               capture_output=True, text=True, timeout=180)
            viejas = json.loads(r.stdout or '[]')
            claves = [p for p in viejas if p['name'].lower() in IMPORTANTES]
            lineas.append(f'📦 Librerías del sitio con versión nueva: {len(viejas)}')
            lineas += [f"  • {p['name']} {p['version']} → {p['latest_version']}" for p in claves]
        except Exception:
            lineas.append('📦 No se pudo revisar las librerías del sitio.')

        try:
            r = subprocess.run(['/usr/lib/update-notifier/apt-check'], capture_output=True,
                               text=True, timeout=60)
            normales, seguridad = (int(x) for x in r.stderr.strip().split(';')[:2])
            lineas.append(f'🖥️ Sistema del servidor: {normales} actualizaciones ({seguridad} de seguridad)')
        except Exception:
            pass
        if Path('/var/run/reboot-required').exists():
            lineas.append('🔁 El servidor pide un reinicio.')

        lineas += ['', 'Para hacerla, copia y pégale esto a Claude:', '', PROMPT]
        texto = '\n'.join(lineas)
        if op['ver'] or not configurado():
            self.stdout.write(texto)
        else:
            avisar(texto)
            self.stdout.write('Recordatorio enviado.')
