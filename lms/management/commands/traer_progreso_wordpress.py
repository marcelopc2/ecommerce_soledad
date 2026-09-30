"""Trae SOLO el avance de los alumnos desde un volcado de WordPress.

    python manage.py traer_progreso_wordpress --dump volcado.sql            # ensayo
    python manage.py traer_progreso_wordpress --dump volcado.sql --aplicar

No crea ni borra alumnos, modelos ni pasos: agrega a cada alumno que ya existe
los modelos que terminó en el sitio viejo (y los pasos que vio, si el paso
todavía existe acá). No quita nada: si alguien avanzó en el sitio nuevo, eso
se queda. Se puede correr las veces que haga falta.

Existe porque la actualización del 30-09-2026 trasladó 250 de los 1.500
modelos terminados: los títulos no calzaban ("001-Taladro" contra
"001 - Taladro"). Ya está corregido en el importador; esto repara la base sin
volver a borrar y crear a todos los alumnos.

Al terminar da por avisado lo que queda desbloqueado y los diplomas que ya
existían, igual que rehacer_migracion: más avance significa más modelos
abiertos, y para el alumno no son novedad (los viene viendo en el sitio viejo).
"""
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from lms.models import CourseProgress, DiplomaAward, LessonProgress, Membership, UnlockNotice

from .importar_wordpress import RE_NUMERO, Command as Importador, _fecha

User = get_user_model()


class Command(BaseCommand):
    help = 'Agrega a los alumnos existentes el avance que tenían en WordPress.'

    def add_arguments(self, parser):
        parser.add_argument('--dump', required=True)
        parser.add_argument('--aplicar', action='store_true')

    def handle(self, *args, **op):
        if not os.path.exists(op['dump']):
            raise CommandError('No encuentro el volcado: %s' % op['dump'])

        imp = Importador(stdout=self.stdout, stderr=self.stderr)
        self.stdout.write('Leyendo el volcado...')
        d = imp._leer(op['dump'])

        cursos_wp = {i: p for i, p in d['posts'].items()
                     if p.get('post_type') == 'stm-courses' and p.get('post_status') == 'publish'}

        def clave(par):
            m = RE_NUMERO.match((par[1].get('post_title') or '').strip())
            return (1, int(m.group(1))) if m else (0, 0)
        ordenados = sorted(cursos_wp.items(), key=clave)
        pasos_de = {}
        for m in d['materiales']:
            cid = d['secciones'].get(m.get('section_id'))
            if cid in cursos_wp:
                pasos_de.setdefault(cid, []).append((int(m.get('order') or 0), m.get('post_id')))
        for v in pasos_de.values():
            v.sort()

        curso_de_wp, leccion_de_wp, sin_par, _ = imp._emparejar_con_lo_que_hay(ordenados, pasos_de, d)
        self.stdout.write(f'Modelos ubicados: {len(curso_de_wp)} de {len(cursos_wp)}')
        if sin_par:
            self.stdout.write(self.style.WARNING('  sin pareja: ' + ', '.join(sin_par)))

        # Usuario de WordPress -> membresía de acá, por correo.
        membresia_de_correo = {
            (m.user.email or m.user.username).lower().strip(): m
            for m in Membership.objects.select_related('user')
        }
        mem_de_wp = {}
        for uid, u in d['usuarios'].items():
            m = membresia_de_correo.get((u.get('user_email') or '').lower().strip())
            if m:
                mem_de_wp[uid] = m

        ahora = timezone.now()
        cursos, pasos = {}, {}
        for r in d['insc']:
            try:
                pct = float(r.get('progress_percent') or 0)
            except ValueError:
                pct = 0
            mem, curso = mem_de_wp.get(r.get('user_id')), curso_de_wp.get(r.get('course_id'))
            if pct >= 100 and mem and curso:
                cursos[(mem.pk, curso.pk)] = CourseProgress(
                    membership=mem, course=curso, completed_at=_fecha(r.get('end_time')) or ahora)
        for r in d['lecc_vistas']:
            mem, leccion = mem_de_wp.get(r.get('user_id')), leccion_de_wp.get(r.get('lesson_id'))
            if mem and leccion:
                pasos[(mem.pk, leccion.pk)] = LessonProgress(
                    membership=mem, lesson=leccion, completed_at=_fecha(r.get('end_time')) or ahora)

        ya_cursos = set(CourseProgress.objects.values_list('membership_id', 'course_id'))
        ya_pasos = set(LessonProgress.objects.values_list('membership_id', 'lesson_id'))
        nuevos_cursos = [v for k, v in cursos.items() if k not in ya_cursos]
        nuevos_pasos = [v for k, v in pasos.items() if k not in ya_pasos]
        alumnos = len({k[0] for k in cursos})

        self.stdout.write(f'Modelos terminados en WordPress (de alumnos que existen acá): {len(cursos)}, '
                          f'de {alumnos} alumno(s)')
        self.stdout.write(f'  ya estaban: {len(cursos) - len(nuevos_cursos)} | se agregan: {len(nuevos_cursos)}')
        self.stdout.write(f'Pasos vistos que existen acá: {len(pasos)} | se agregan: {len(nuevos_pasos)}')

        if not op['aplicar']:
            self.stdout.write(self.style.WARNING('\nEnsayo: no se guardó nada. Agrega --aplicar.'))
            return

        with transaction.atomic():
            CourseProgress.objects.bulk_create(nuevos_cursos, ignore_conflicts=True, batch_size=500)
            LessonProgress.objects.bulk_create(nuevos_pasos, ignore_conflicts=True, batch_size=500)
        self.stdout.write(self.style.SUCCESS(
            f'\nListo: {len(nuevos_cursos)} modelos terminados y {len(nuevos_pasos)} pasos agregados.'))
        self._dar_por_avisado()

    def _dar_por_avisado(self):
        """Nada de esto es novedad para el alumno: no tiene que llegarle un
        correo de "se desbloqueó" ni de "ganaste un diploma" por avance viejo."""
        from lms.services import get_course_access, get_sequence_access

        avisos = []
        for m in Membership.objects.all().iterator():
            for entrada in get_course_access(m):
                if entrada['unlocked']:
                    avisos.append(UnlockNotice(membership=m, course=entrada['course']))
            # Abrir la secuencia es lo que crea los diplomas ganados.
            get_sequence_access(m)
        UnlockNotice.objects.bulk_create(avisos, ignore_conflicts=True, batch_size=500)
        n = DiplomaAward.objects.filter(email_sent_at__isnull=True).update(email_sent_at=timezone.now())
        self.stdout.write(f'Desbloqueos marcados como avisados: {len(avisos)} | '
                          f'diplomas marcados como avisados: {n} (no se manda ningún correo).')
