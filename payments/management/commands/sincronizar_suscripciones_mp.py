"""Revisa en Mercado Pago las suscripciones pagadas con Mercado Pago.

Es la red de seguridad de los webhooks: si un aviso de cobro no llegó (el
servidor estaba reiniciando, Mercado Pago no lo mandó, el webhook no está
configurado), acá se recoge. Registra los cobros que falten (boleta, acceso y
correo, una sola vez por cobro) y copia el estado: si el cliente pausó o
canceló desde la app de Mercado Pago, el panel lo muestra.

No cobra nada: los cobros los hace Mercado Pago. Se corre una vez al día.

    0 11 * * * cd /srv/ingenioblocks && venv/bin/python manage.py sincronizar_suscripciones_mp
"""
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from payments import mp_suscripciones
from payments.models import Order, Suscripcion

log = logging.getLogger('ingenioblocks.pagos')


class Command(BaseCommand):
    help = 'Registra los cobros y cambios de las suscripciones de Mercado Pago que no avisó el webhook.'

    def handle(self, *args, **op):
        from payments.views import _entregar_compra

        ids = set(Suscripcion.objects
                  .filter(pasarela=Suscripcion.MERCADOPAGO)
                  .exclude(estado=Suscripcion.CANCELADA)
                  .values_list('mp_preapproval_id', flat=True))
        # Las que se contrataron y todavía no registran su primer cobro: puede
        # que Mercado Pago lo haya aprobado después de que el cliente volvió.
        hace_un_mes = timezone.now() - timedelta(days=30)
        ids |= set(Order.objects
                   .filter(status='PENDING', created_at__gte=hace_un_mes)
                   .exclude(mp_preapproval_id=None)
                   .values_list('mp_preapproval_id', flat=True))
        ids.discard(None)

        antes = Order.objects.filter(status='PAID').exclude(mp_payment_id=None).count()
        errores = 0
        for preapproval_id in sorted(ids):
            try:
                mp_suscripciones.revisar(preapproval_id, _entregar_compra)
            except Exception:
                errores += 1
                log.exception('No se pudo revisar la suscripción %s en Mercado Pago', preapproval_id)
        nuevos = Order.objects.filter(status='PAID').exclude(mp_payment_id=None).count() - antes

        resumen = f'{len(ids)} suscripción(es) revisadas, {nuevos} cobro(s) nuevos registrados, {errores} error(es).'
        self.stdout.write(resumen)
        if nuevos or errores:
            log.info('sincronizar_suscripciones_mp: %s', resumen)
