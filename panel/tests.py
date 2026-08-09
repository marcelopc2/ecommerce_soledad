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


@override_settings(AXES_ENABLED=False)
class IpDelVisitanteTests(TestCase):
    """La IP guardada tiene que ser la del visitante, no la de nginx.

    Estaba mal: con un proxy declarado se pasaba ese número a django-ipware,
    que entiende proxy_count como "cuántas IP de proxy vienen DESPUÉS de la del
    cliente" y por lo tanto espera la cadena completa. Nuestro nginx sobrescribe
    X-Forwarded-For con UNA sola IP, así que ipware no reconocía el formato y
    caía a REMOTE_ADDR: todos los accesos quedaban anotados como 127.0.0.1 y el
    registro no servía para auditar nada.
    """

    def _ip_vista(self, **extra):
        from django.test import RequestFactory
        from panel.registro import ip_del_request
        return ip_del_request(RequestFactory().get('/', **extra))

    @override_settings(NUM_PROXIES=1)
    def test_detras_de_nginx_se_usa_la_ip_reenviada(self):
        self.assertEqual(
            self._ip_vista(HTTP_X_FORWARDED_FOR='2.155.71.177', REMOTE_ADDR='127.0.0.1'),
            '2.155.71.177',
        )

    @override_settings(NUM_PROXIES=1)
    def test_si_llegan_varias_se_toma_la_primera(self):
        """Si algún día se encadenaran IPs, la del cliente es la primera."""
        self.assertEqual(
            self._ip_vista(
                HTTP_X_FORWARDED_FOR='2.155.71.177, 10.0.0.1', REMOTE_ADDR='127.0.0.1',
            ),
            '2.155.71.177',
        )

    @override_settings(NUM_PROXIES=0)
    def test_sin_proxy_declarado_se_ignora_el_encabezado(self):
        """Sin proxy delante, X-Forwarded-For lo escribe cualquiera: creerle
        permitiría falsear el origen de cada intento y anular el bloqueo."""
        self.assertEqual(
            self._ip_vista(HTTP_X_FORWARDED_FOR='1.2.3.4', REMOTE_ADDR='9.9.9.9'),
            '9.9.9.9',
        )


@override_settings(AXES_ENABLED=False)
class RegistroDeAccesosTests(TestCase):
    """Entradas e intentos fallidos quedan anotados y sobreviven al borrado."""

    CLAVE = 'UnaClaveLarga123'

    def setUp(self):
        self.user = User.objects.create_user(
            username='ayudante@ingenioblocks.com', email='ayudante@ingenioblocks.com',
            password=self.CLAVE, is_staff=True,
        )

    def test_entrar_al_panel_queda_registrado(self):
        from panel.models import RegistroAcceso
        self.client.post(
            reverse('panel:login'), {'email': self.user.email, 'password': self.CLAVE},
        )
        acceso = RegistroAcceso.objects.filter(tipo=RegistroAcceso.ENTRADA).first()
        self.assertIsNotNone(acceso)
        self.assertEqual(acceso.email, self.user.email)
        self.assertEqual(acceso.zona, RegistroAcceso.PANEL)

    def test_intento_fallido_queda_registrado_sin_guardar_la_clave(self):
        from panel.models import RegistroAcceso
        self.client.post(
            reverse('panel:login'),
            {'email': self.user.email, 'password': 'claveEquivocada'},
        )
        fallido = RegistroAcceso.objects.filter(tipo=RegistroAcceso.FALLIDO).first()
        self.assertIsNotNone(fallido)
        self.assertEqual(fallido.email, self.user.email)
        # La contraseña tecleada NUNCA debe terminar en la base de datos.
        self.assertNotIn('claveEquivocada', fallido.email)
        self.assertNotIn('claveEquivocada', fallido.dispositivo or '')

    def test_el_registro_sobrevive_al_borrado_de_la_cuenta(self):
        from panel.models import RegistroAcceso
        self.client.post(
            reverse('panel:login'), {'email': self.user.email, 'password': self.CLAVE},
        )
        self.user.delete()
        acceso = RegistroAcceso.objects.filter(tipo=RegistroAcceso.ENTRADA).first()
        self.assertIsNotNone(acceso, 'el acceso no puede irse con la cuenta')
        self.assertEqual(acceso.email, 'ayudante@ingenioblocks.com')
        self.assertIsNone(acceso.usuario)


@override_settings(AXES_ENABLED=False)
class ContadorDeVisitasTests(TestCase):
    """Suma vistas y personas, y descarta robots."""

    URL = '/api/metricas/visita/'
    NAVEGADOR = 'Mozilla/5.0 (iPhone) Safari/604'

    def test_una_visita_suma_una_vista_y_una_persona(self):
        from panel.models import VisitaDiaria, VisitanteDiario
        self.client.post(self.URL, {'ruta': '/'}, HTTP_USER_AGENT=self.NAVEGADOR)
        self.assertEqual(VisitaDiaria.objects.get(ruta='/').vistas, 1)
        self.assertEqual(VisitanteDiario.objects.count(), 1)

    def test_la_misma_persona_navegando_suma_vistas_pero_no_personas(self):
        from panel.models import VisitaDiaria, VisitanteDiario
        for ruta in ('/', '/checkout', '/'):
            self.client.post(self.URL, {'ruta': ruta}, HTTP_USER_AGENT=self.NAVEGADOR)
        self.assertEqual(VisitaDiaria.objects.get(ruta='/').vistas, 2)
        self.assertEqual(
            VisitanteDiario.objects.count(), 1,
            'quien navega varias páginas sigue siendo una sola persona',
        )

    def test_los_robots_no_se_cuentan(self):
        from panel.models import VisitaDiaria
        self.client.post(self.URL, {'ruta': '/'}, HTTP_USER_AGENT='Googlebot/2.1')
        self.assertEqual(VisitaDiaria.objects.count(), 0)

    def test_responde_sin_error_aunque_falte_la_ruta(self):
        respuesta = self.client.post(self.URL, {}, HTTP_USER_AGENT=self.NAVEGADOR)
        self.assertEqual(respuesta.status_code, 204)


@override_settings(AXES_ENABLED=False)
class MiClaveTests(TestCase):
    """Cualquier cuenta de gestión puede cambiar SU propia contraseña.

    Antes no había forma: la pantalla de cuentas es solo para superusuarios y,
    a propósito, no deja tocarse a uno mismo. Un ayudante quedaba atado a la
    clave que le dictaron.
    """

    CLAVE = 'UnaClaveLarga123'
    NUEVA = 'OtraClaveDistinta456'

    def setUp(self):
        self.user = User.objects.create_user(
            username='ayudante@ingenioblocks.com', email='ayudante@ingenioblocks.com',
            password=self.CLAVE, is_staff=True,
        )
        self.client.force_login(self.user)

    def _cambiar(self, actual, nueva, repetir):
        return self.client.post(reverse('panel:mi_clave'), {
            'actual': actual, 'nueva': nueva, 'repetir': repetir,
        })

    def test_un_staff_normal_puede_cambiar_su_clave(self):
        self._cambiar(self.CLAVE, self.NUEVA, self.NUEVA)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.NUEVA))

    def test_no_cambia_si_la_actual_esta_mala(self):
        self._cambiar('noEsMiClave', self.NUEVA, self.NUEVA)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.CLAVE))

    def test_no_cambia_si_las_nuevas_no_coinciden(self):
        self._cambiar(self.CLAVE, self.NUEVA, 'otraCosa789')
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.CLAVE))

    def test_la_sesion_sigue_abierta_despues_de_cambiarla(self):
        """Sin update_session_auth_hash, cambiar la clave expulsa al instante."""
        self._cambiar(self.CLAVE, self.NUEVA, self.NUEVA)
        self.assertEqual(self.client.get(reverse('panel:dashboard')).status_code, 200)


@override_settings(AXES_ENABLED=False)
class PermisosDeCuentasTests(TestCase):
    """La cuenta principal no se puede borrar, pero sí puede crear otras."""

    CLAVE = 'UnaClaveLarga123'

    def setUp(self):
        self.dueno = User.objects.create_superuser(
            username='dueno@ingenioblocks.com', email='dueno@ingenioblocks.com',
            password=self.CLAVE,
        )
        self.socio = User.objects.create_superuser(
            username='socio@ingenioblocks.com', email='socio@ingenioblocks.com',
            password=self.CLAVE,
        )
        self.ayudante = User.objects.create_user(
            username='ayudante@ingenioblocks.com', email='ayudante@ingenioblocks.com',
            password=self.CLAVE, is_staff=True,
        )

    def test_el_dueno_no_puede_borrarse_a_si_mismo(self):
        self.client.force_login(self.dueno)
        self.client.post(reverse('panel:staff_user_delete', args=[self.dueno.pk]))
        self.assertTrue(User.objects.filter(pk=self.dueno.pk).exists())

    def test_un_dueno_no_puede_borrar_a_otro_dueno(self):
        self.client.force_login(self.dueno)
        self.client.post(reverse('panel:staff_user_delete', args=[self.socio.pk]))
        self.assertTrue(User.objects.filter(pk=self.socio.pk).exists())

    def test_el_dueno_si_puede_crear_cuentas_de_gestion(self):
        self.client.force_login(self.dueno)
        self.client.post(reverse('panel:staff_users'), {
            'nombre': 'Nueva Persona',
            'email': 'nueva@ingenioblocks.com',
            'password': 'ClaveParaElla789',
        })
        creada = User.objects.filter(email='nueva@ingenioblocks.com').first()
        self.assertIsNotNone(creada)
        self.assertTrue(creada.is_staff)
        self.assertFalse(
            creada.is_superuser,
            'una cuenta de gestión no debe poder crear más cuentas',
        )

    def test_un_ayudante_no_entra_a_administrar_cuentas(self):
        self.client.force_login(self.ayudante)
        self.assertEqual(
            self.client.get(reverse('panel:staff_users')).status_code, 302,
        )
