"""Panel: ver el Aula como la ve un alumno, y cuántos modelos tiene abiertos."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from lms.models import CategoryCourse, Course, CourseCategory, CourseProgress, Lesson, LessonProgress, Membership, MembershipCategory

User = get_user_model()


class VistaAulaTests(TestCase):
    def setUp(self):
        admin = User.objects.create_user(username='admin@ib.cl', email='admin@ib.cl', is_staff=True)
        self.client.force_login(admin)
        cat = CourseCategory.objects.create(nombre='General', slug='general', cursos_iniciales=2)
        self.cursos = []
        for i in range(1, 5):
            c = Course.objects.create(title=f'00{i} - Modelo {i}', slug=f'm{i}', order=i, is_active=True)
            Lesson.objects.create(course=c, title='Paso 1', order=1)
            CategoryCourse.objects.create(categoria=cat, curso=c, orden=i)
            self.cursos.append(c)
        u = User.objects.create_user(username='a@b.cl', email='a@b.cl')
        self.m = Membership.objects.create(user=u, student_name='Isidora', expires_at=timezone.now() + timedelta(days=90))
        MembershipCategory.objects.create(membership=self.m, categoria=cat, obtenida_en=timezone.now() - timedelta(days=40))
        c1 = self.cursos[0]
        LessonProgress.objects.create(membership=self.m, lesson=c1.lessons.first())
        CourseProgress.objects.create(membership=self.m, course=c1)

    def test_la_vista_muestra_lo_mismo_que_el_aula(self):
        r = self.client.get(reverse('panel:membership_aula', args=[self.m.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Avance de Isidora')
        self.assertContains(r, 'modelos desbloqueados')
        self.assertContains(r, 'Terminado')
        self.assertContains(r, 'Modelo 2')

    def test_la_lista_dice_cuantos_tiene_desbloqueados_y_lleva_a_su_aula(self):
        r = self.client.get(reverse('panel:memberships'))
        self.assertContains(r, 'desbloqueado')
        self.assertContains(r, reverse('panel:membership_aula', args=[self.m.pk]))

    def test_mirar_no_marca_avance(self):
        antes = LessonProgress.objects.count()
        self.client.get(reverse('panel:membership_aula', args=[self.m.pk]))
        self.assertEqual(LessonProgress.objects.count(), antes)

    def test_solo_gestion(self):
        self.client.force_login(self.m.user)
        r = self.client.get(reverse('panel:membership_aula', args=[self.m.pk]))
        self.assertNotEqual(r.status_code, 200)


class AvanceManualTests(VistaAulaTests):
    """Corregir a mano el avance (lo que se perdió al traspasar la cuenta)."""

    def _post(self, curso, accion):
        return self.client.post(reverse('panel:membership_avance', args=[self.m.pk]),
                                {'curso': curso.pk, 'accion': accion})

    def test_hasta_aqui_marca_ese_y_los_anteriores_aunque_esten_cerrados(self):
        from django.core import mail
        from django.core.management import call_command
        from lms.models import UnlockNotice
        r = self._post(self.cursos[2], 'hasta')
        self.assertRedirects(r, reverse('panel:membership_aula', args=[self.m.pk]))
        terminados = set(CourseProgress.objects.filter(membership=self.m).values_list('course_id', flat=True))
        self.assertEqual(terminados, {c.pk for c in self.cursos[:3]})
        self.assertEqual(LessonProgress.objects.filter(membership=self.m).count(), 3)
        # Lo que quedó abierto se da por avisado: el aviso diario no le escribe.
        self.assertTrue(UnlockNotice.objects.filter(membership=self.m).exists())
        with self.settings(ENVIAR_CORREOS=True):
            call_command('enviar_avisos_desbloqueo', stdout=open(__import__('os').devnull, 'w'))
        self.assertEqual(len(mail.outbox), 0)

    def test_terminar_solo_uno(self):
        self._post(self.cursos[1], 'terminar')
        self.assertTrue(CourseProgress.objects.filter(membership=self.m, course=self.cursos[1]).exists())
        self.assertFalse(CourseProgress.objects.filter(membership=self.m, course=self.cursos[2]).exists())

    def test_quitar_avance(self):
        self._post(self.cursos[0], 'quitar')
        self.assertFalse(CourseProgress.objects.filter(membership=self.m).exists())
        self.assertFalse(LessonProgress.objects.filter(membership=self.m).exists())

    def test_curso_ajeno_no(self):
        otro = Course.objects.create(title='Fuera', slug='fuera', order=99, is_active=True)
        self._post(otro, 'terminar')
        self.assertFalse(CourseProgress.objects.filter(membership=self.m, course=otro).exists())

    def test_alumno_no_puede(self):
        self.client.force_login(self.m.user)
        self._post(self.cursos[3], 'hasta')
        self.assertEqual(CourseProgress.objects.filter(membership=self.m).count(), 1)

    def test_botones_en_la_pagina(self):
        r = self.client.get(reverse('panel:membership_aula', args=[self.m.pk]))
        self.assertContains(r, 'Quitar avance')
        self.assertContains(r, 'Hasta aquí')
        self.assertContains(r, 'Terminados hasta:')
        self.assertContains(r, '4. 004 - Modelo 4')
