"""Editar un recurso de un curso sin borrarlo y volver a crearlo.

Borrar y recrear mandaba el recurso al final del curso y les quitaba a los
alumnos la marca de "visto". Editando se conservan las dos cosas.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from lms.models import Course, Lesson, LessonProgress, Membership

User = get_user_model()


class EditarRecursoTests(TestCase):
    def setUp(self):
        admin = User.objects.create_user(username='admin@ib.cl', email='admin@ib.cl', is_staff=True)
        self.client.force_login(admin)
        self.curso = Course.objects.create(title='Taladro', slug='taladro')
        self.primero = Lesson.objects.create(course=self.curso, title='Paso 1', lesson_type='IMAGE', order=1)
        self.segundo = Lesson.objects.create(
            course=self.curso, title='Paso 2', lesson_type='VIDEO', order=2,
            video_embed_url='https://www.youtube.com/embed/abc123def45',
        )
        alumno = User.objects.create_user(username='a@b.cl', email='a@b.cl')
        self.m = Membership.objects.create(user=alumno, expires_at=timezone.now() + timedelta(days=30))
        LessonProgress.objects.create(membership=self.m, lesson=self.primero)

    def test_la_lista_trae_el_boton_de_editar(self):
        r = self.client.get(reverse('panel:course_edit', args=[self.curso.pk]))
        self.assertContains(r, reverse('panel:lesson_edit', args=[self.primero.pk]))

    def test_el_formulario_viene_con_los_datos_actuales(self):
        r = self.client.get(reverse('panel:lesson_edit', args=[self.segundo.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'value="Paso 2"')
        self.assertContains(r, 'abc123def45')

    def test_guardar_conserva_el_orden_y_el_avance(self):
        r = self.client.post(reverse('panel:lesson_edit', args=[self.primero.pk]), {
            'title': 'Paso 1 corregido', 'lesson_type': 'IMAGE', 'description': 'Nuevo texto',
        })
        self.assertRedirects(r, reverse('panel:course_edit', args=[self.curso.pk]))
        self.primero.refresh_from_db()
        self.assertEqual(self.primero.title, 'Paso 1 corregido')
        self.assertEqual(self.primero.description, 'Nuevo texto')
        self.assertEqual(self.primero.order, 1)
        self.assertTrue(LessonProgress.objects.filter(membership=self.m, lesson=self.primero).exists())
        self.assertEqual(self.curso.lessons.count(), 2)

    def test_un_link_de_youtube_normal_se_convierte_igual_que_al_agregar(self):
        self.client.post(reverse('panel:lesson_edit', args=[self.segundo.pk]), {
            'title': 'Paso 2', 'lesson_type': 'VIDEO',
            'video_embed_url': 'https://www.youtube.com/watch?v=zzz999yyy88',
        })
        self.segundo.refresh_from_db()
        self.assertEqual(self.segundo.video_embed_url, 'https://www.youtube.com/embed/zzz999yyy88')

    def test_un_alumno_no_puede_editar(self):
        self.client.force_login(self.m.user)
        r = self.client.post(reverse('panel:lesson_edit', args=[self.primero.pk]), {
            'title': 'Hackeado', 'lesson_type': 'IMAGE',
        })
        self.assertNotEqual(r.status_code, 200)
        self.primero.refresh_from_db()
        self.assertEqual(self.primero.title, 'Paso 1')
