"""Spam del formulario de contacto (catalog/antispam.py).

El caso real (08-11-2026): un robot mandó "hljLYiHOcVqhZhTykY SukQLiwRbHwNhpwNtBEPrvn"
con un Gmail lleno de puntos y un teléfono de Canadá. Tiene que quedar marcado
sin avisar a nadie; y un mensaje de una familia de verdad tiene que pasar igual.
"""
import time
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from catalog.antispam import motivo_de_spam
from catalog.models import MensajeContacto

ROBOT = {'nombre': 'hljLYiHOcVqhZhTykY', 'apellido': 'SukQLiwRbHwNhpwNtBEPrvn',
         'email': 'komor.ur.u.j8.5@gmail.com', 'telefono': '6046574275', 'comentarios': 'CWoJhqyheLyJhwRer'}
FAMILIA = {'nombre': 'María José', 'apellido': "O'Higgins DeLaFuente", 'email': 'mj@correo.cl',
           'telefono': '+56 9 1234 5678', 'comentarios': '¿Tienen despacho a Puerto Montt? Mi hijo ama el kit.'}


def hace(segundos):
    return int((time.time() - segundos) * 1000)


class MotivoTests(SimpleTestCase):
    def test_el_robot_real_se_reconoce(self):
        self.assertIn('al azar', motivo_de_spam({**ROBOT, 't': hace(30)}))

    def test_una_familia_no_es_spam(self):
        self.assertEqual(motivo_de_spam({**FAMILIA, 't': hace(30)}), '')

    def test_nombres_con_mayusculas_reales_pasan(self):
        for nombre in ('McDonald', 'DeLaFuente', 'MacArthur', 'JUAN PÉREZ', 'Ana-María'):
            with self.subTest(nombre=nombre):
                self.assertEqual(motivo_de_spam({'nombre': nombre, 't': hace(30)}), '')

    def test_campo_trampa(self):
        self.assertIn('trampa', motivo_de_spam({**FAMILIA, 'sitio_web': 'http://x', 't': hace(30)}))

    def test_demasiado_rapido(self):
        self.assertIn('3 segundos', motivo_de_spam({**FAMILIA, 't': hace(1)}))


class FormularioTests(TestCase):
    def setUp(self):
        cache.clear()
        p = patch('core.alertas.avisar')
        self.avisar = p.start()
        self.addCleanup(p.stop)
        p = patch('catalog.views.enviar_email')
        self.correo = p.start()
        self.addCleanup(p.stop)

    def enviar(self, datos):
        return APIClient().post('/api/catalog/contacto/', datos, format='json')

    def test_spam_se_guarda_marcado_y_no_avisa(self):
        r = self.enviar({**ROBOT, 't': hace(30), 'sitio_web': ''})
        self.assertEqual(r.status_code, 200)          # el robot cree que funcionó
        m = MensajeContacto.objects.get()
        self.assertTrue(m.es_spam)
        self.avisar.assert_not_called()
        self.correo.assert_not_called()

    def test_mensaje_real_avisa(self):
        r = self.enviar({**FAMILIA, 't': hace(30), 'sitio_web': ''})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(MensajeContacto.objects.get().es_spam)
        self.avisar.assert_called_once()
        self.correo.assert_called_once()
