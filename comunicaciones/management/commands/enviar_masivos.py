"""Despacha de a poco los correos masivos que se mandaron desde el panel.

Corre cada minuto desde cron (/etc/cron.d/ingenioblocks-masivos) y en cada
pasada manda un puñado, con una pausa entre uno y otro. Ver el porqué en
comunicaciones/envio.py.

    manage.py enviar_masivos
    manage.py enviar_masivos --lote 10 --pausa 3

Si no hay nada en cola no hace nada, así que puede quedar corriendo siempre.
También suelta los correos programados cuya hora llegó (y avisa por Telegram
cuando empiezan y terminan de salir).
Con el freno de correos puesto (servidor de pruebas) tampoco: el panel ni
siquiera deja encolar, pero si algo quedara en cola, no sale.
"""
import logging

from django.conf import settings
from django.core.management.base import BaseCommand

from comunicaciones.envio import procesar, soltar_programados
from comunicaciones.models import DestinatarioMasivo, EnvioMasivo
from core.alertas import avisar

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
        from comunicaciones.freno import correos_a_clientes
        freno = not correos_a_clientes()

        # Con el freno puesto solo salen las pruebas programadas (al equipo).
        for programado, problema in soltar_programados(solo_pruebas=freno):
            if programado.audiencia == EnvioMasivo.PRUEBA and not problema:
                n = len(getattr(programado, 'llegaron', []))
                avisar(f'🧪 Salió la prueba programada «{programado.asunto}» a {n} del equipo.')
            elif problema:
                log.warning('Correo programado "%s" no salió: %s', programado.asunto, problema)
                avisar(f'⚠️ El correo programado «{programado.asunto}» no salió: {problema} '
                       'Quedó como borrador en el panel.')
            else:
                n = programado.destinatarios.filter(estado=DestinatarioMasivo.PENDIENTE).count()
                log.info('Correo programado "%s" empezó a salir a %s personas', programado.asunto, n)
                avisar(f'📨 Empezó a salir el correo programado «{programado.asunto}» a {n} personas.')

        if freno:
            self.stdout.write('Freno de correos puesto: no se manda nada a clientes.')
            return

        envio, cuenta = procesar(lote=op['lote'], pausa=op['pausa'])
        if envio is None:
            return
        envio.refresh_from_db()
        if envio.programado_para and envio.estado == EnvioMasivo.TERMINADO:
            c = envio.contadores()
            avisar(f'✅ Terminó de salir el correo programado «{envio.asunto}»: '
                   f'{c[DestinatarioMasivo.ENVIADO]} enviados'
                   + (f', {c[DestinatarioMasivo.FALLIDO]} fallaron' if c[DestinatarioMasivo.FALLIDO] else '')
                   + '.')
        resumen = ', '.join('%s %d' % (k.lower(), v) for k, v in cuenta.items()) or 'sin cambios'
        self.stdout.write('"%s": %s' % (envio.asunto, resumen))
        log.info('enviar_masivos "%s": %s', envio.asunto, resumen)
