"""Cuenta de gestión que arrastra una membresía vencida de WordPress.

Le pasó a la dueña: la migración le trajo la suscripción de cuando probaba la
tienda, vencida en 2025, y el Aula la trataba como alumna vencida ("tu
suscripción venció") en vez de dejarla revisar los cursos en vista previa.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from lms.models import Course, Membership

User = get_user_model()


class GestionConMembresiaViejaTests(TestCase):
    def setUp(self):
        self.curso = Course.objects.create(title='Taladro', slug='taladro', is_active=True)
        self.api = APIClient()

    def _cuenta(self, correo, is_staff, vence_en_dias):
        u = User.objects.create_user(username=correo, email=correo, is_staff=is_staff)
        Membership.objects.create(user=u, expires_at=timezone.now() + timedelta(days=vence_en_dias))
        self.api.force_authenticate(u)
        return u

    def test_gestion_con_membresia_vencida_entra_en_vista_previa(self):
        self._cuenta('duena@ib.cl', is_staff=True, vence_en_dias=-400)

        r = self.api.get('/api/lms/my-courses/')
        self.assertTrue(r.data.get('preview'))
        self.assertIsNone(r.data['membership'])

        r = self.api.get('/api/lms/courses/taladro/')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data['preview'])

        # El encabezado del Aula tampoco le debe mostrar "venció".
        self.assertIsNone(self.api.get('/api/auth/me/').data['membership'])

    def test_gestion_con_membresia_al_dia_usa_la_suya(self):
        self._cuenta('prueba@ib.cl', is_staff=True, vence_en_dias=30)
        r = self.api.get('/api/lms/my-courses/')
        self.assertFalse(r.data.get('preview', False))
        self.assertTrue(r.data['membership']['active'])

    def test_alumno_vencido_sigue_viendo_que_vencio(self):
        self._cuenta('alumno@b.cl', is_staff=False, vence_en_dias=-10)
        r = self.api.get('/api/lms/my-courses/')
        self.assertFalse(r.data.get('preview', False))
        self.assertFalse(r.data['membership']['active'])
        self.assertFalse(self.api.get('/api/auth/me/').data['membership']['active'])
