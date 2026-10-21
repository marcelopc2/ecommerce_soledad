"""La sección "Club Ingenio Blocks": se muestra u oculta y se edita desde el panel."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from catalog.models import SeccionClub

User = get_user_model()


class ClubTests(TestCase):
    def test_nace_oculta_y_la_portada_no_recibe_los_textos(self):
        r = APIClient().get(reverse('club'))
        self.assertEqual(r.data, {'visible': False})

    def test_visible_entrega_los_textos_y_las_preguntas_con_sus_puntos(self):
        c = SeccionClub.obtener()
        c.visible = True
        c.bloque2_titulo = ''
        c.bloque2_puntos = ''
        c.save()
        r = APIClient().get(reverse('club'))
        self.assertTrue(r.data['visible'])
        self.assertEqual(r.data['titulo'], 'club ingenio blocks')
        self.assertEqual(len(r.data['bloques']), 2)            # la vacía no sale
        self.assertEqual(len(r.data['bloques'][1]['puntos']), 4)
        self.assertIsNone(r.data['imagen_url'])

    def test_el_panel_la_muestra_edita_y_oculta(self):
        admin = User.objects.create_user(username='admin@ib.cl', email='admin@ib.cl', is_staff=True)
        self.client.force_login(admin)
        url = reverse('panel:cfg_club')
        self.assertContains(self.client.get(url), 'Mostrar en la portada')
        datos = {'form': 'club', 'visible': 'on', 'etiqueta': 'nuevo', 'titulo': 'El Club', 'intro': 'Hola',
                 'bloque1_titulo': '¿Quién?', 'bloque1_puntos': 'Uno\nDos', 'bloque2_titulo': '', 'bloque2_puntos': '',
                 'bloque3_titulo': '', 'bloque3_puntos': '', 'boton_texto': 'Ver', 'boton_enlace': '#kits'}
        self.client.post(url, datos)
        c = SeccionClub.obtener()
        self.assertTrue(c.visible)
        self.assertEqual(c.bloques, [{'titulo': '¿Quién?', 'puntos': ['Uno', 'Dos']}])
        datos.pop('visible')
        self.client.post(url, datos)
        self.assertFalse(SeccionClub.obtener().visible)
        self.assertEqual(SeccionClub.obtener().titulo, 'El Club')   # los textos se guardan igual
