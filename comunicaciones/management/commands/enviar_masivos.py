"""Despacha de a poco los correos masivos que se mandaron desde el panel.

Corre cada minuto desde cron (/etc/cron.d/ingenioblocks-masivos) y en cada
pasada manda un puñado, con una pausa entre uno y otro. Ver el porqué en
comunicaciones/envio.py.

    manage.py enviar_masivos
    manage.py enviar_masivos --lote 10 --pausa 3

Si no hay nada en cola no hace nada, así que puede quedar corriendo siempre.
Con el freno de correos puesto (servidor de pruebas) tampoco: el panel ni
siquiera deja encolar, pero si algo quedara en cola, no sale.
"""
import logging

from django.conf import settings
from django.core.management.base import BaseCommand

from comunicaciones.envio import procesar

log = logging.getLogger('ingenioblocks.pagos')


class Command(BaseCommand):
    help = 'Envía de a poco los correos masivos en cola.'

    def add_arguments(self, parser):
        # 25 con 1,5 s de pausa son unos 40 segundos: termina antes de que cron
        # lo vuelva a lanzar al minuto siguiente.
        parser.add_argument('--lote', type=int, default=25,
                            help='Cuántos correos manda en esta pasada (por omisión 25)')
        parser.add_argument('--pausa', type=float, default=1.5,
                            help='Segundos entre un correo y otro (por omisión 1,5)')

    def handle(self, *args, **op):
        if not settings.ENVIAR_CORREOS:
            self.stdout.write('Freno de correos puesto: no se manda nada.')
            return

        envio, cuenta = procesar(lote=op['lote'], pausa=op['pausa'])
        if envio is None:
            return
        resumen = ', '.join('%s %d' % (k.lower(), v) for k, v in cuenta.items()) or 'sin cambios'
        self.stdout.write('"%s": %s' % (envio.asunto, resumen))
        log.info('enviar_masivos "%s": %s', envio.asunto, resumen)
