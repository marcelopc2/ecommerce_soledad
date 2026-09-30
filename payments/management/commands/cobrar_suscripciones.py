"""Cobra las suscripciones a las que les toca hoy.

    python manage.py cobrar_suscripciones --simular   # solo dice a quién
    python manage.py cobrar_suscripciones             # cobra de verdad

Va una vez al día por cron. Cada cobro es una orden normal con su boleta, y
extiende la membresía igual que una compra hecha a mano.

Mientras el sitio siga en pruebas el cron NO está instalado: con las
credenciales de producción esto le cobra a tarjetas reales.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from payments import oneclick
from payments.models import Suscripcion


class Command(BaseCommand):
    help = 'Cobra las suscripciones cuyo próximo cobro ya llegó.'

    def add_arguments(self, parser):
        parser.add_argument('--simular', action='store_true',
                            help='No cobra nada: solo lista a quién le tocaría.')

    def handle(self, *args, **op):
        # Import tardío: views arrastra toda la app de pagos y la boleta.
        from payments.views import _entregar_compra

        hoy = timezone.localdate()
        pendientes = (Suscripcion.objects
                      .filter(estado=Suscripcion.ACTIVA, proximo_cobro__lte=hoy)
                      .select_related('producto', 'tarjeta', 'orden_inicial'))

        cobradas = rechazadas = dudosas = 0
        for s in pendientes:
            if op['simular']:
                self.stdout.write(f'  [simulado] {s.email} -> ${s.monto} ({s.producto.name})')
                continue
            _, resultado = oneclick.cobrar_suscripcion(s, entregar=_entregar_compra)
            if resultado == oneclick.AUTORIZADO:
                cobradas += 1
            elif resultado == oneclick.RECHAZADO:
                rechazadas += 1
            else:
                dudosas += 1
            self.stdout.write(f'  {s.email}: {resultado}')

        if op['simular']:
            self.stdout.write(f'Simulación: {pendientes.count()} cobro(s) pendientes, no se cobró nada.')
        else:
            self.stdout.write(f'Listo: {cobradas} cobrada(s), {rechazadas} rechazada(s), '
                              f'{dudosas} para revisar a mano.')
