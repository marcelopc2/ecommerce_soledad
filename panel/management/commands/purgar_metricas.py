"""Borra métricas y registros de acceso antiguos.

Sin esto las tablas crecen para siempre: `VisitanteDiario` suma una fila por
persona y por día, y `RegistroAcceso` una por cada intento de login —incluidos
los fallidos de los bots, que son miles—. Nadie va a consultar de qué IP entró
alguien hace tres años, pero el disco sí se llena.

Se conservan por defecto 2 años de visitas (para poder comparar temporadas) y
1 año de accesos. Se corre desde el mismo cron diario del respaldo.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from panel.models import OrigenDiario, RegistroAcceso, VisitaDiaria, VisitanteDiario


class Command(BaseCommand):
    help = 'Borra métricas de visitas y registros de acceso antiguos.'

    def add_arguments(self, parser):
        parser.add_argument('--dias-visitas', type=int, default=730)
        parser.add_argument('--dias-accesos', type=int, default=365)
        parser.add_argument(
            '--simular', action='store_true',
            help='Muestra cuánto borraría, sin borrar nada.',
        )

    def handle(self, *args, **opciones):
        hoy = timezone.localdate()
        corte_visitas = hoy - timedelta(days=opciones['dias_visitas'])
        corte_accesos = timezone.now() - timedelta(days=opciones['dias_accesos'])
        simular = opciones['simular']

        objetivos = [
            ('visitas diarias', VisitaDiaria.objects.filter(fecha__lt=corte_visitas)),
            ('visitantes diarios', VisitanteDiario.objects.filter(fecha__lt=corte_visitas)),
            ('orígenes diarios', OrigenDiario.objects.filter(fecha__lt=corte_visitas)),
            ('registros de acceso', RegistroAcceso.objects.filter(momento__lt=corte_accesos)),
        ]

        if simular:
            self.stdout.write('Modo simulación: no se borra nada.')

        for nombre, qs in objetivos:
            cuantos = qs.count()
            if not cuantos:
                continue
            if not simular:
                qs.delete()
            verbo = 'se borrarían' if simular else 'borrados'
            self.stdout.write(f'{cuantos} {nombre} {verbo}.')

        self.stdout.write(self.style.SUCCESS('Listo.'))
