from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse


# django-axes bloquea por usuario+IP y guarda los intentos en la base: sin
# desactivarlo, los logins fallidos a propósito de estos tests se acumulan y
# terminan bloqueando a los que corren después.
@override_settings(AXES_ENABLED=False)
class LoginDelPanelTests(TestCase):
    """El login del panel pide el CORREO, pero Django autentica por `username`.

    Cuando no coinciden -toda cuenta creada con `createsuperuser`- la clave
    correcta era rechazada con "credenciales incorrectas" y no había manera de
    entrar. Estos tests fijan que se pueda entrar con el correo sin importar qué
    username tenga la cuenta detrás.
    """

    CLAVE = 'UnaClaveLarga123'

    def setUp(self):
        # username != email: es el caso que estaba roto
        self.admin = User.objects.create_user(
            username='admin', email='admin@ingenioblocks.com',
            password=self.CLAVE, is_staff=True,
        )
        # username == email: el caso que ya funcionaba, no debe romperse
        self.clienta = User.objects.create_user(
            username='clienta@ingenioblocks.cl', email='clienta@ingenioblocks.cl',
            password=self.CLAVE, is_staff=True,
        )
        self.url = reverse('panel:login')

    def _entrar(self, email, clave):
        return self.client.post(self.url, {'email': email, 'password': clave})

    def test_entra_aunque_el_username_no_sea_el_correo(self):
        respuesta = self._entrar('admin@ingenioblocks.com', self.CLAVE)
        self.assertRedirects(respuesta, reverse('panel:dashboard'))
        self.assertEqual(self.client.session['_auth_user_id'], str(self.admin.pk))

    def test_entra_cuando_el_username_es_el_correo(self):
        respuesta = self._entrar('clienta@ingenioblocks.cl', self.CLAVE)
        self.assertRedirects(respuesta, reverse('panel:dashboard'))

    def test_el_correo_no_distingue_mayusculas(self):
        respuesta = self._entrar('Admin@IngenioBlocks.com', self.CLAVE)
        self.assertRedirects(respuesta, reverse('panel:dashboard'))

    def test_clave_incorrecta_sigue_siendo_rechazada(self):
        respuesta = self._entrar('admin@ingenioblocks.com', 'otra-clave')
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_correo_inexistente_no_entra(self):
        respuesta = self._entrar('nadie@ingenioblocks.com', self.CLAVE)
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_una_cuenta_sin_permisos_de_gestion_no_entra(self):
        User.objects.create_user(
            username='apoderado', email='apoderado@correo.cl',
            password=self.CLAVE, is_staff=False,
        )
        respuesta = self._entrar('apoderado@correo.cl', self.CLAVE)
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)
