"""Mensajes del formulario de contacto: se guardan y se ven en el panel."""
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from catalog.models import MensajeContacto

User = get_user_model()


class MensajesTests(TestCase):
    def _enviar(self):
        return self.client.post(reverse('contact'), {
            'nombre': 'Pedro', 'apellido': 'Soto', 'email': 'pedro@correo.cl',
            'telefono': '+56912345678', 'comentarios': 'Hola'}, format='json')

    def test_el_formulario_guarda_el_mensaje(self):
        self.assertEqual(self._enviar().status_code, 200)
        m = MensajeContacto.objects.get()
        self.assertEqual((m.nombre, m.leido, m.origen), ('Pedro Soto', False, MensajeContacto.SITIO))

    def test_si_el_correo_falla_el_mensaje_igual_queda(self):
        with mock.patch('catalog.views.enviar_email', side_effect=RuntimeError('smtp caído')):
            self.assertEqual(self._enviar().status_code, 200)
        self.assertEqual(MensajeContacto.objects.count(), 1)

    def test_panel_lista_y_marca_leido(self):
        self._enviar()
        admin = User.objects.create_user(username='admin@ib.cl', email='admin@ib.cl', is_staff=True)
        self.client.force_login(admin)
        self.assertContains(self.client.get(reverse('panel:dashboard')), 'Mensajes sin leer')
        r = self.client.get(reverse('panel:mensajes') + '?ver=sin_leer')
        self.assertContains(r, 'pedro@correo.cl')
        m = MensajeContacto.objects.get()
        self.client.post(reverse('panel:mensaje_leido', args=[m.pk]), {'valor': '1'})
        m.refresh_from_db()
        self.assertTrue(m.leido)

    def test_solo_gestion(self):
        alumno = User.objects.create_user(username='a@b.cl', email='a@b.cl')
        self.client.force_login(alumno)
        self.assertNotEqual(self.client.get(reverse('panel:mensajes')).status_code, 200)
