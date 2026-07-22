"""Avisa por correo cuando a un alumno se le libera un modelo nuevo o gana un diploma.

Se corre UNA VEZ AL DÍA desde cron. El goteo depende del paso del tiempo y no de
una acción del usuario, así que no hay ninguna petición web donde enganchar
estos correos: sin este comando el alumno tiene que entrar a adivinar si ya se
liberó algo, y "un modelo nuevo cada semana" es la promesa central del plan.

Cada alumno tiene su propio calendario, contado desde SU fecha de compra: el que
compró un miércoles recibe su aviso los miércoles.

    # todos los días a las 9:00 (hora de Chile, ver TIME_ZONE)
    0 9 * * * cd /srv/ingenioblocks && venv/bin/python manage.py enviar_avisos_desbloqueo

Es idempotente: lo que ya se avisó queda registrado en UnlockNotice y en
DiplomaAward.email_sent_at, así que correrlo dos veces el mismo día no manda
nada repetido. Se puede ejecutar sin miedo.
"""
import logging

from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction
from django.utils import timezone

from lms.models import Membership, UnlockNotice, DiplomaAward
from lms.services import get_course_access, send_course_unlocked_email, send_diploma_email

log = logging.getLogger('ingenioblocks.pagos')


class Command(BaseCommand):
    help = 'Envía los avisos de modelo desbloqueado y de diploma obtenido (correr a diario).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--simular', action='store_true',
            help='Muestra qué correos se mandarían, sin enviar ni registrar nada.',
        )

    def handle(self, *args, **opciones):
        simular = opciones['simular']
        if simular:
            self.stdout.write(self.style.WARNING('Modo simulación: no se envía ni se guarda nada.\n'))

        avisos_curso = self._avisar_cursos(simular)
        avisos_diploma = self._avisar_diplomas(simular)

        resumen = (f'{avisos_curso} aviso(s) de modelo nuevo, '
                   f'{avisos_diploma} aviso(s) de diploma.')
        self.stdout.write(self.style.SUCCESS(f'\nListo: {resumen}'))
        if not simular and (avisos_curso or avisos_diploma):
            log.info('enviar_avisos_desbloqueo: %s', resumen)

    # ------------------------------------------------------------------
    def _avisar_cursos(self, simular):
        """Un aviso por cada curso que se acaba de abrir y todavía no se avisó."""
        enviados = 0
        # Solo membresías vigentes: no tiene sentido avisarle de un modelo nuevo
        # a alguien cuyo acceso ya venció.
        membresias = (Membership.objects
                      .filter(expires_at__gt=timezone.now(), user__is_active=True)
                      .select_related('user')
                      .prefetch_related('courses'))

        for m in membresias:
            if m.is_paused:
                continue   # con la suscripción pausada el calendario está congelado

            # Los que ya se avisaron, en una sola consulta por membresía.
            ya_avisados = set(
                UnlockNotice.objects.filter(membership=m).values_list('course_id', flat=True)
            )

            for numero, acceso in enumerate(get_course_access(m), start=1):
                if not acceso['unlocked'] or acceso['completed']:
                    continue
                curso = acceso['course']
                if curso.id in ya_avisados:
                    continue

                if simular:
                    self.stdout.write(f'  [simulado] {m.user.email} -> "{curso.title}"')
                    enviados += 1
                    continue

                # Se registra ANTES de enviar: si el correo falla, el aviso queda
                # marcado igual y no se reintenta al día siguiente. Es preferible
                # perder un aviso a mandarle el mismo correo todos los días a un
                # cliente porque el servidor SMTP anda intermitente.
                try:
                    with transaction.atomic():
                        UnlockNotice.objects.create(membership=m, course=curso)
                except IntegrityError:
                    continue   # otra ejecución se adelantó

                try:
                    send_course_unlocked_email(m, curso, numero)
                    enviados += 1
                    self.stdout.write(f'  {m.user.email} -> "{curso.title}"')
                except Exception:
                    log.exception('No se pudo avisar el desbloqueo de "%s" a %s',
                                  curso.title, m.user.email)

        return enviados

    # ------------------------------------------------------------------
    def _avisar_diplomas(self, simular):
        """Avisa los diplomas ya otorgados que todavía no tienen correo enviado.

        El DiplomaAward lo crea get_sequence_access cuando el alumno abre su
        página, así que acá solo se recogen los que quedaron sin avisar.
        """
        enviados = 0
        pendientes = (DiplomaAward.objects
                      .filter(email_sent_at__isnull=True)
                      .select_related('membership__user', 'diploma'))

        for award in pendientes:
            usuario = award.membership.user
            if not usuario.is_active:
                continue

            if simular:
                self.stdout.write(f'  [simulado] {usuario.email} -> diploma "{award.diploma.title}"')
                enviados += 1
                continue

            # Igual que arriba: se marca primero para no repetir el correo.
            award.email_sent_at = timezone.now()
            award.save(update_fields=['email_sent_at'])
            try:
                send_diploma_email(award.membership, award.diploma, award.awarded_at)
                enviados += 1
                self.stdout.write(f'  {usuario.email} -> diploma "{award.diploma.title}"')
            except Exception:
                log.exception('No se pudo avisar el diploma "%s" a %s',
                              award.diploma.title, usuario.email)

        return enviados
