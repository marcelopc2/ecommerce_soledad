"""Vuelve a mandar los correos que no salieron (ver comunicaciones.CorreoPendiente).

    */10 * * * * cd /srv/ingenioblocks && venv/bin/python manage.py reintentar_correos

Hasta 6 intentos (una hora). Cuando uno sale avisa por Telegram que se
recuperó; si después de los 6 sigue sin salir, avisa como problema para
revisarlo a mano.
"""
import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from comunicaciones.models import CorreoPendiente
from core.alertas import avisar
from core.emails import reenviar_pendiente

log = logging.getLogger('ingenioblocks.pagos')


class Command(BaseCommand):
    help = 'Reintenta los correos a clientes que no salieron.'

    def handle(self, *args, **op):
        pendientes = CorreoPendiente.objects.filter(
            enviado_en__isnull=True, intentos__lt=CorreoPendiente.INTENTOS_MAXIMOS)
        for p in pendientes:
            try:
                salio = reenviar_pendiente(p)
                error = '' if salio else 'sin respuesta'
            except Exception as e:
                salio, error = False, f'{type(e).__name__}: {e}'[:300]
            p.intentos += 1
            if salio:
                p.enviado_en = timezone.now()
                p.save(update_fields=['intentos', 'enviado_en'])
                log.info('Correo reenviado: %s a %s (intento %s)', p.plantilla, p.destinatarios, p.intentos)
                avisar(f'✅ Se reenvió el correo «{p.asunto}» a {", ".join(p.destinatarios)}, '
                       'que antes no había salido.')
                self.stdout.write(f'reenviado: {p}')
            else:
                p.ultimo_error = error
                p.save(update_fields=['intentos', 'ultimo_error'])
                if p.intentos >= CorreoPendiente.INTENTOS_MAXIMOS:
                    log.error('CORREO PERDIDO tras %s intentos: %r a %s (%s). Mandarlo a mano.',
                              p.intentos, p.asunto, p.destinatarios, error)
