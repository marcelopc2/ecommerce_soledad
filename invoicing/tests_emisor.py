"""Datos del emisor de la boleta cuando OpenFactura no responde."""
import json
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, override_settings

from invoicing import services


class Respuesta:
    def __init__(self, codigo, datos=None):
        self.status_code, self._datos, self.text = codigo, datos or {}, json.dumps(datos or {'code': 'OF-22'})

    def json(self):
        return self._datos


class EmisorTests(SimpleTestCase):
    def setUp(self):
        self.carpeta = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.carpeta, True)
        self.cfg = override_settings(PROTECTED_MEDIA_ROOT=self.carpeta)
        self.cfg.enable()
        self.addCleanup(self.cfg.disable)
        services._ORG_CACHE = None
        self.addCleanup(setattr, services, '_ORG_CACHE', None)

    def test_si_responde_guarda_una_copia_y_si_despues_falla_la_usa(self):
        org = {'rut': '76123456-7', 'razonSocial': 'Ingenio SpA'}
        with mock.patch('invoicing.services.requests.get', return_value=Respuesta(200, org)):
            self.assertEqual(services.get_organization(), org)
        services._ORG_CACHE = None
        with mock.patch('invoicing.services.requests.get', return_value=Respuesta(500)):
            self.assertEqual(services.get_organization(), org)

    def test_sin_copia_usa_el_env(self):
        env = {'OPENFACTURA_EMISOR_RUT': '76123456-7', 'OPENFACTURA_EMISOR_RAZON_SOCIAL': 'Ingenio SpA'}
        with mock.patch('invoicing.services.requests.get', return_value=Respuesta(500)),                 mock.patch.dict('os.environ', env):
            self.assertEqual(services.get_organization()['rut'], '76123456-7')

    def test_sin_nada_falla_en_vez_de_inventar(self):
        with mock.patch('invoicing.services.requests.get', return_value=Respuesta(500)):
            with self.assertRaises(RuntimeError):
                services.get_organization()
