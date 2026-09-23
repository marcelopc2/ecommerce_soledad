"""Mueve el reloj de una cuenta de prueba para ver el goteo sin esperar semanas.

Para qué sirve
--------------
El goteo entrega dos modelos el día de la compra y uno por semana después. Eso
significa que revisar cómo se ve el Aula "al mes y medio" implicaría esperar mes
y medio. Este comando corre la fecha de compra hacia atrás, que es exactamente
lo mismo que adelantar el calendario.

    manage.py simular_paso_del_tiempo --email yo@correo.cl --semanas 6
    manage.py simular_paso_del_tiempo --email yo@correo.cl --semanas 6 --aplicar

Es una herramienta de PRUEBA. Reescribe la fecha en que el alumno obtuvo cada
categoría y su vencimiento, así que sobre una cuenta real le cambiaría lo que ve
y cuándo se le vence. Por eso no hace nada sin `--aplicar` y muestra a quién le
va a tocar antes de tocarlo.

Qué NO simula
-------------
El segundo candado. Un modelo se abre por fecha Y por haber terminado el
anterior, así que correr el reloj seis semanas no muestra seis modelos abiertos
si el alumno no completó ninguno: muestra hasta dónde llegó la fecha y el resto
esperando. Eso es fiel a lo que vería un alumno de verdad que no entra nunca.
"""
from datetime import timedelta

from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from lms.models import Membership
from lms.services import get_course_access

User = get_user_model()


class Command(BaseCommand):
    help = 'Corre hacia atrás la fecha de compra de una cuenta para ver el goteo más adelante.'

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True,
                            help='Correo de la cuenta a mover')
        parser.add_argument('--semanas', type=int, required=True,
                            help='Cuántas semanas hace que compró (0 = recién comprado)')
        parser.add_argument('--meses-de-acceso', type=int, default=6,
                            help='Cuántos meses dura su plan (por omisión 6, el del Kit Inicial)')
        parser.add_argument('--aplicar', action='store_true',
                            help='Hace el cambio. Sin esto solo dice qué haría.')

    def handle(self, *args, **op):
        semanas = op['semanas']
        if semanas < 0:
            raise CommandError('Las semanas no pueden ser negativas: el reloj va hacia atrás.')

        correo = op['email'].strip().lower()
        try:
            membresia = Membership.objects.select_related('user').get(
                user__email__iexact=correo)
        except Membership.DoesNotExist:
            raise CommandError('No hay ninguna membresía con el correo %s' % correo)

        if membresia.user.is_staff:
            # Una cuenta de gestión no tiene por qué ser también alumno de
            # prueba, y si lo es conviene notarlo antes de moverle las fechas.
            self.stdout.write(self.style.WARNING(
                '  Ojo: %s es una cuenta de gestión.' % correo))

        compra = timezone.now() - timedelta(weeks=semanas)
        vence = compra + relativedelta(months=op['meses_de_acceso'])

        self.stdout.write(self.style.MIGRATE_HEADING(
            'Simular que %s compró hace %d semana(s)' % (correo, semanas)))
        self.stdout.write('  fecha de compra  : %s' % timezone.localtime(compra).strftime('%d-%m-%Y'))
        self.stdout.write('  vencería el      : %s' % timezone.localtime(vence).strftime('%d-%m-%Y'))

        if not op['aplicar']:
            self.stdout.write(self.style.WARNING(
                '\nEnsayo: no se tocó nada. Agrega --aplicar para hacerlo.'))
            return

        membresia.expires_at = vence
        membresia.sin_vencimiento = False
        membresia.save(update_fields=['expires_at', 'sin_vencimiento'])

        # Se mueven TODAS sus categorías al mismo día: la cuenta de prueba
        # representa una sola compra, y dejar una categoría con otra fecha
        # mostraría un calendario que ningún alumno real tendría.
        movidas = membresia.categorias_obtenidas.all()
        for mc in movidas:
            mc.obtenida_en = compra
            # Si venía de una reanudación, se limpia: con la fecha de compra
            # movida a mano, un ancla vieja daría un calendario incoherente.
            mc.reanudada_en = None
            mc.entregados_al_reanudar = 0
            mc.pausa_al_reanudar = 0
            mc.save(update_fields=['obtenida_en', 'reanudada_en',
                                   'entregados_al_reanudar', 'pausa_al_reanudar'])

        self.stdout.write('  %d categoría(s) movida(s)' % len(movidas))
        self._mostrar_lo_que_veria(membresia)

    def _mostrar_lo_que_veria(self, membresia):
        """Lo calcula con la misma función que usa el Aula, no con una copia de
        la regla: si algún día cambia el goteo, esto cambia con él."""
        acceso = get_course_access(membresia)
        abiertos = [a for a in acceso if a['unlocked']]
        self.stdout.write(self.style.SUCCESS(
            '\n  Ahora ve %d de %d modelos abiertos.' % (len(abiertos), len(acceso))))

        # Se mira `lock_reason` y NO la fecha: un modelo trabado por no haber
        # terminado el anterior igual trae una fecha, y muchas veces ya pasada.
        # Mostrarla daba a entender que la plataforma estaba fallando.
        for a in acceso[:8]:
            if a['unlocked']:
                estado = 'abierto' + ('  (terminado)' if a['completed'] else '')
            elif a['lock_reason'] == 'previo':
                falta = a['required_course']
                estado = 'falta terminar "%s"' % (falta.title[:28] if falta else 'el anterior')
            elif a['lock_reason'] == 'vencida':
                estado = 'la suscripción está vencida'
            elif a['unlock_date']:
                estado = 'se abre el %s' % a['unlock_date'].strftime('%d-%m-%Y')
            else:
                estado = 'cerrado'
            self.stdout.write('    %-34s %s' % (a['course'].title[:34], estado))
        if len(acceso) > 8:
            self.stdout.write('    ... y %d más' % (len(acceso) - 8))
