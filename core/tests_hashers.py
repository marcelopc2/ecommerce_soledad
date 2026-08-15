"""El cliente que viene de WordPress entra con la clave que ya tenía.

Los hashes de abajo son phpass de verdad, generados con el algoritmo original de
WordPress. Si estos tests pasan, un export real de `wp_users.user_pass` funciona.
"""
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import User
from django.test import TestCase

from core.hashers import _phpass


def wp(clave, sal='B7xVn9Qz', vueltas='B'):
    """Genera un hash phpass como lo haría WordPress."""
    return _phpass(clave, f'$P${vueltas}{sal}' + 'x' * 22)


class ClavesDeWordPressTests(TestCase):

    def test_verifica_un_hash_generado_por_otra_implementacion(self):
        """El más importante de este archivo.

        Los demás tests generan el hash con nuestro propio código y lo verifican
        con ese mismo código: si la implementación tuviera un error, se anularía
        solo y pasarían igual. Este hash lo calculó `passlib` (implementación
        independiente y muy usada de phpass), así que es el único que prueba de
        verdad que vamos a poder leer un export real de WordPress.
        """
        de_passlib = '$P$9B7xVn9QzUjFOPhwGC89iOhXfPBX.70'
        self.assertTrue(check_password('MiClaveDeWordPress', 'wordpress$' + de_passlib))
        self.assertFalse(check_password('otraClave', 'wordpress$' + de_passlib))

    def test_verifica_un_hash_externo_con_acentos_y_ene(self):
        """Las claves chilenas traen tildes y eñes, y ahí es donde se cae una
        implementación que codifique en el juego de caracteres equivocado."""
        de_passlib = '$P$9B7xVn9Qzqh5gtiVrkt88Tbxuuwgy50'
        self.assertTrue(check_password('clave con ñ y tilde á', 'wordpress$' + de_passlib))

    def test_entra_con_su_clave_de_siempre(self):
        guardado = 'wordpress$' + wp('MiClaveDeWordPress')
        self.assertTrue(check_password('MiClaveDeWordPress', guardado))

    def test_una_clave_equivocada_no_entra(self):
        guardado = 'wordpress$' + wp('MiClaveDeWordPress')
        self.assertFalse(check_password('otraClave', guardado))

    def test_acepta_el_md5_pelado_de_wordpress_muy_viejo(self):
        import hashlib
        md5 = hashlib.md5(b'clave-antigua').hexdigest()
        self.assertTrue(check_password('clave-antigua', 'wordpress$' + md5))
        self.assertFalse(check_password('otra', 'wordpress$' + md5))

    def test_un_hash_corrupto_no_revienta_ni_deja_entrar(self):
        for basura in ['wordpress$', 'wordpress$$P$', 'wordpress$noesunhash',
                       'wordpress$$P$!corto']:
            self.assertFalse(check_password('lo-que-sea', basura), basura)

    def test_al_entrar_bien_la_clave_se_reescribe_con_el_cifrado_de_django(self):
        """Es lo que hace que el formato viejo se apague solo: cada cliente que
        vuelve deja de depender de un MD5 iterado, que hoy es débil."""
        u = User.objects.create(username='legacy@test.cl', email='legacy@test.cl')
        u.password = 'wordpress$' + wp('MiClaveDeWordPress')
        u.save()

        self.assertTrue(u.check_password('MiClaveDeWordPress'))

        u.refresh_from_db()
        self.assertTrue(u.password.startswith('pbkdf2_'), u.password[:20])
        self.assertTrue(u.check_password('MiClaveDeWordPress'),
                        'y sigue entrando con la misma clave')

    def test_las_claves_nuevas_las_cifra_django_y_no_wordpress(self):
        self.assertTrue(make_password('ClaveNueva123').startswith('pbkdf2_'))

    def test_distintas_vueltas_de_phpass(self):
        """El 4º carácter del hash dice cuántas iteraciones se usaron, y varía
        según la versión de WordPress que creó la cuenta."""
        for vueltas in 'BCDEF':
            guardado = 'wordpress$' + wp('claveX', vueltas=vueltas)
            self.assertTrue(check_password('claveX', guardado), vueltas)
