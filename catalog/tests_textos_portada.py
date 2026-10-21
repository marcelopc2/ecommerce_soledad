"""Textos de la portada editables desde el panel."""
import json
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from catalog.models import TextosPortada
from catalog.textos_portada import ORIGINALES

User = get_user_model()


class TextosPortadaTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin@ib.cl', email='admin@ib.cl', is_staff=True)

    def _api(self):
        return self.client.get(reverse('textos-portada')).json()

    def _guardar(self, **cambios):
        datos = {**ORIGINALES, **cambios}
        self.client.force_login(self.admin)
        return self.client.post(reverse('panel:textos_portada'), datos)

    def test_sin_cambios_salen_los_originales(self):
        self.assertEqual(self._api(), ORIGINALES)

    def test_lo_cambiado_en_el_panel_sale_en_la_portada(self):
        r = self._guardar(hero_titulo='la **mejor** experiencia', instagram_url='https://instagram.com/ingenioblocks')
        self.assertRedirects(r, reverse('panel:textos_portada'))
        datos = self._api()
        self.assertEqual(datos['hero_titulo'], 'la **mejor** experiencia')
        self.assertEqual(datos['instagram_url'], 'https://instagram.com/ingenioblocks')
        self.assertEqual(datos['quienes_titulo'], ORIGINALES['quienes_titulo'])
        # Solo se guarda lo cambiado.
        self.assertEqual(set(TextosPortada.obtener().textos), {'hero_titulo', 'instagram_url'})

    def test_vaciar_un_campo_vuelve_al_original(self):
        self._guardar(como_titulo='cómo se usa')
        self._guardar(como_titulo='')
        self.assertEqual(self._api()['como_titulo'], ORIGINALES['como_titulo'])

    def test_valida_correo_y_enlaces(self):
        r = self._guardar(contacto_email='no-es-un-correo', facebook_url='no es enlace')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(TextosPortada.obtener().textos)

    def test_solo_gestion(self):
        alumno = User.objects.create_user(username='a@b.cl', email='a@b.cl')
        self.client.force_login(alumno)
        self.client.post(reverse('panel:textos_portada'), {**ORIGINALES, 'hero_boton': 'hackeado'})
        self.assertEqual(self._api()['hero_boton'], ORIGINALES['hero_boton'])

    def test_la_pagina_del_panel_muestra_todas_las_secciones(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse('panel:textos_portada'))
        for seccion in ('Portada principal', 'Beneficios', 'Quiénes somos', 'Contacto', 'Pie de página'):
            self.assertContains(r, seccion)

    def test_la_copia_del_sitio_es_igual_a_la_del_servidor(self):
        """El sitio trae su propia copia para cuando la API no responde."""
        copia = Path(settings.BASE_DIR) / 'frontend' / 'src' / 'textosPortada.json'
        self.assertEqual(json.loads(copia.read_text(encoding='utf-8')), ORIGINALES)
