"""El buscador de Alumnos: todos los campos, sin tildes, en cualquier orden."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from lms.models import Membership
from panel.busqueda import coincide

User = get_user_model()


class CoincideTests(SimpleTestCase):
    CAMPOS = ('catalina.rojas@correo.cl', 'Catalina Rojas', 'Tomás Rojas')
    TEL = ('+56 9 7123 4581',)

    def test_sin_tildes_ni_mayusculas(self):
        self.assertTrue(coincide('tomas', self.CAMPOS, self.TEL))
        self.assertTrue(coincide('TOMÁS', self.CAMPOS, self.TEL))

    def test_varias_palabras_en_cualquier_orden_y_campo(self):
        self.assertTrue(coincide('rojas tomas', self.CAMPOS, self.TEL))
        self.assertTrue(coincide('catalina tomas', self.CAMPOS, self.TEL))
        self.assertFalse(coincide('catalina perez', self.CAMPOS, self.TEL))

    def test_telefono_escrito_como_sea(self):
        for q in ('7123 4581', '+56971234581', '971234581', '4581'):
            self.assertTrue(coincide(q, self.CAMPOS, self.TEL), q)
        self.assertFalse(coincide('9999 0000', self.CAMPOS, self.TEL))

    def test_correo_parcial(self):
        self.assertTrue(coincide('catalina.rojas', self.CAMPOS, self.TEL))
        self.assertTrue(coincide('correo.cl', self.CAMPOS, self.TEL))


class BuscadorAlumnosTests(TestCase):
    def setUp(self):
        admin = User.objects.create_user(username='admin@ib.cl', email='admin@ib.cl', is_staff=True)
        self.client.force_login(admin)
        for correo, apoderado, alumno, tel in [
            ('catalina.rojas@correo.cl', 'Catalina Rojas', 'Tomás Rojas', '+56 9 7123 4581'),
            ('fmunoz@correo.cl', 'Francisco Muñoz', 'Isidora Muñoz', '+56 9 6234 1190'),
        ]:
            u = User.objects.create_user(username=correo, email=correo)
            Membership.objects.create(user=u, parent_name=apoderado, student_name=alumno, phone=tel,
                                      expires_at=timezone.now() + timedelta(days=30))

    def buscar(self, q):
        return self.client.get(reverse('panel:memberships'), {'q': q}).content.decode()

    def test_encuentra_por_cualquier_campo(self):
        for q, esperado, no in [('tomas', 'Tomás', 'Isidora'), ('isidora munoz', 'Isidora', 'Tomás'),
                                ('fmunoz', 'Isidora', 'Tomás'), ('7123 4581', 'Tomás', 'Isidora'),
                                ('Rojas Tomás', 'Tomás', 'Isidora')]:
            html = self.buscar(q)
            self.assertIn(esperado, html, q)
            self.assertNotIn(no, html, q)
