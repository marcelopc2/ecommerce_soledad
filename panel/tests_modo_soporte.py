"""Panel: entrar al Aula como un alumno (modo soporte), solo para mirar."""
from datetime import timedelta
from urllib.parse import unquote

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from lms.models import Membership
from panel.models import RegistroAcceso

User = get_user_model()


@override_settings(FRONTEND_URL='https://aula.test')
class ModoSoporteTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin@ib.cl', email='admin@ib.cl', is_staff=True)
        self.client.force_login(self.admin)
        self.alumno = User.objects.create_user(username='a@b.cl', email='a@b.cl', password='clave-vieja-123')
        self.m = Membership.objects.create(user=self.alumno, student_name='Isidora',
                                           expires_at=timezone.now() + timedelta(days=90))

    def _entrar(self):
        r = self.client.post(reverse('panel:membership_soporte', args=[self.m.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r['Location'].startswith('https://aula.test/soporte#t='))
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION='Bearer ' + unquote(r['Location'].split('#t=', 1)[1]))
        return api

    def test_entra_como_el_alumno_y_el_aula_lo_sabe(self):
        r = self._entrar().get(reverse('auth-me'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['email'], 'a@b.cl')
        self.assertEqual(r.data['soporte']['por'], 'admin@ib.cl')

    def test_el_login_normal_no_esta_en_modo_soporte(self):
        api = APIClient()
        api.force_authenticate(self.alumno)
        self.assertIsNone(api.get(reverse('auth-me')).data['soporte'])

    def test_solo_lectura(self):
        api = self._entrar()
        self.assertEqual(api.get(reverse('lms-my-courses')).status_code, 200)
        r = api.post(reverse('auth-change-password'),
                     {'current_password': 'clave-vieja-123', 'new_password': 'otra-clave-456'}, format='json')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(api.patch(reverse('auth-profile'), {'student_name': 'X'}, format='json').status_code, 403)
        self.alumno.refresh_from_db()
        self.assertTrue(self.alumno.check_password('clave-vieja-123'))
        self.m.refresh_from_db()
        self.assertEqual(self.m.student_name, 'Isidora')

    def test_queda_registrado(self):
        self._entrar()
        reg = RegistroAcceso.objects.get(tipo=RegistroAcceso.SOPORTE)
        self.assertEqual(reg.usuario, self.alumno)
        self.assertEqual(reg.soporte_por, 'admin@ib.cl')
        self.assertEqual(reg.zona, RegistroAcceso.SITIO)
        r = self.client.get(reverse('panel:accesos') + '?tipo=SOPORTE')
        self.assertContains(r, 'entró admin@ib.cl')

    def test_si_el_staff_pierde_el_acceso_el_token_deja_de_servir(self):
        api = self._entrar()
        self.admin.is_staff = False
        self.admin.save()
        self.assertEqual(api.get(reverse('auth-me')).status_code, 401)

    def test_vence_a_los_30_minutos(self):
        from rest_framework_simplejwt.tokens import AccessToken
        from lms.soporte import token_de_soporte
        token = AccessToken(token_de_soporte(self.alumno, self.admin))
        restante = token['exp'] - timezone.now().timestamp()
        self.assertTrue(25 * 60 < restante <= 30 * 60)

    def test_no_abre_cuentas_de_gestion(self):
        otro = User.objects.create_user(username='c@ib.cl', email='c@ib.cl', is_staff=True)
        mm = Membership.objects.create(user=otro, expires_at=timezone.now() + timedelta(days=9))
        r = self.client.post(reverse('panel:membership_soporte', args=[mm.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertNotIn('#t=', r['Location'])
        self.assertFalse(RegistroAcceso.objects.filter(tipo=RegistroAcceso.SOPORTE).exists())

    def test_solo_por_post_y_solo_staff(self):
        url = reverse('panel:membership_soporte', args=[self.m.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.logout()
        r = self.client.post(url)
        self.assertNotIn('#t=', r.get('Location', ''))

    def test_boton_en_la_ficha(self):
        r = self.client.get(reverse('panel:membership_detail', args=[self.m.pk]))
        self.assertContains(r, 'Entrar como este alumno')
