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
        datos = {**ORIGINALES, 'tema': 'normal', **cambios}
        self.client.force_login(self.admin)
        return self.client.post(reverse('panel:textos_portada'), datos)

    def test_sin_cambios_salen_los_originales(self):
        datos = self._api()
        self.assertEqual({k: datos[k] for k in ORIGINALES}, ORIGINALES)
        self.assertEqual((datos['tema'], datos['hero_imagen'], datos['quienes_imagen']), ('normal', None, None))

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


class TemporadaYFotosTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin@ib.cl', email='admin@ib.cl', is_staff=True)
        self.client.force_login(self.admin)

    def _guardar(self, **cambios):
        return self.client.post(reverse('panel:textos_portada'), {**ORIGINALES, 'tema': 'normal', **cambios})

    def test_la_temporada_sale_solo_entre_sus_fechas(self):
        from datetime import timedelta
        from django.utils import timezone
        hoy = timezone.localdate()
        self._guardar(tema='navidad', tema_desde=hoy - timedelta(days=1), tema_hasta=hoy + timedelta(days=1))
        self.assertEqual(self.client.get(reverse('textos-portada')).json()['tema'], 'navidad')
        self._guardar(tema='navidad', tema_desde=hoy + timedelta(days=5), tema_hasta=hoy + timedelta(days=9))
        self.assertEqual(self.client.get(reverse('textos-portada')).json()['tema'], 'normal')
        fila = TextosPortada.obtener()
        self.assertEqual(fila.tema_vigente(hoy + timedelta(days=6)), 'navidad')
        self.assertEqual(fila.tema_vigente(hoy + timedelta(days=10)), 'normal')

    def test_sin_fechas_queda_hasta_volver_a_normal(self):
        self._guardar(tema='halloween')
        self.assertEqual(self.client.get(reverse('textos-portada')).json()['tema'], 'halloween')

    def test_fechas_al_reves_no_se_guardan(self):
        r = self._guardar(tema='navidad', tema_desde='2026-12-20', tema_hasta='2026-12-01')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(TextosPortada.obtener().tema, 'normal')

    def test_subir_y_quitar_una_foto(self):
        import shutil, tempfile
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import override_settings
        carpeta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, carpeta, True)
        with override_settings(MEDIA_ROOT=carpeta):
            foto = SimpleUploadedFile('navidad.png', b'PNG' + b'0' * 100, content_type='image/png')
            self._guardar(hero_imagen=foto)
            url = self.client.get(reverse('textos-portada')).json()['hero_imagen']
            self.assertIn('/media/portada/', url)
            self._guardar(quitar_hero_imagen='on')
            self.assertIsNone(self.client.get(reverse('textos-portada')).json()['hero_imagen'])

    def test_no_acepta_otros_archivos(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        r = self._guardar(hero_imagen=SimpleUploadedFile('virus.html', b'<script>', content_type='text/html'))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(TextosPortada.obtener().hero_imagen)

    def test_fechas_sugeridas(self):
        from datetime import date
        from catalog.textos_portada import fechas_sugeridas
        sug = {t: (d, h) for t, _, d, h in fechas_sugeridas(date(2027, 1, 10))}
        self.assertEqual(sug['pascua'][1], date(2027, 3, 28))       # domingo de Pascua 2027
        self.assertEqual(sug['dia_nino'][1], date(2027, 8, 8))      # 2º domingo de agosto
        self.assertEqual(sug['dia_madre'][1], date(2027, 5, 9))     # 2º domingo de mayo
        self.assertEqual(sug['navidad'], (date(2027, 12, 1), date(2027, 12, 26)))
        self.assertEqual(sug['verano'][1], date(2027, 2, 28))      # la que está corriendo

    def test_los_temas_del_sitio_son_los_del_panel(self):
        """frontend/src/temas.js tiene los adornos de cada tema del panel."""
        import re
        from pathlib import Path
        from django.conf import settings
        js = (Path(settings.BASE_DIR) / 'frontend' / 'src' / 'temas.js').read_text(encoding='utf-8')
        en_el_sitio = set(re.findall(r'^  (\w+): \{', js, re.M))
        en_el_panel = {t for t, _ in TextosPortada.TEMAS} - {TextosPortada.NORMAL}
        self.assertEqual(en_el_sitio, en_el_panel)
