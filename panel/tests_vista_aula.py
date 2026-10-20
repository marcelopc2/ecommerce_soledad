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
        self.assertContains(r, 'Así ve el Aula Isidora')
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
