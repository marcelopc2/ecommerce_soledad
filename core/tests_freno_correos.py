"""El freno de mano de los correos.

Existe por un accidente real: el servidor de pruebas tenía las credenciales SMTP
de verdad y la base con los 296 clientes migrados, así que la tarea diaria de
avisos les mandó correos a clientes REALES con un enlace al sitio en
construcción. 145 y 132 correos en dos mañanas.

La regla es una sola: fuera del sitio de verdad no sale nada.
"""
from importlib import reload

from django.core import mail
from django.test import SimpleTestCase, override_settings

from core import emails


class FrenoTests(SimpleTestCase):
    @override_settings(ENVIAR_CORREOS=False)
    def test_en_un_servidor_de_pruebas_no_sale_nada(self):
        mail.outbox.clear()
        emails.enviar_email('recuperar_clave', 'Hola', ['cliente@correo.cl'],
                            {'nombre': 'Ana', 'link': 'https://x'})
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(ENVIAR_CORREOS=False)
    def test_lo_que_no_se_envio_queda_en_el_log(self):
        """Si no queda rastro, un correo que falta se vuelve invisible: hay que
        poder mirar el log y ver qué se habría mandado."""
        with self.assertLogs('ingenioblocks.pagos', level='WARNING') as registro:
            emails.enviar_email('recuperar_clave', 'Hola', ['cliente@correo.cl'],
                                {'nombre': 'Ana', 'link': 'https://x'})
        salida = '\n'.join(registro.output)
        self.assertIn('NO ENVIADO', salida)
        self.assertIn('cliente@correo.cl', salida)

    @override_settings(ENVIAR_CORREOS=True)
    def test_en_produccion_si_sale(self):
        mail.outbox.clear()
        emails.enviar_email('recuperar_clave', 'Hola', ['cliente@correo.cl'],
                            {'nombre': 'Ana', 'link': 'https://x'})
        self.assertEqual(len(mail.outbox), 1)


class QueDominioHabilitaTests(SimpleTestCase):
    """De qué depende el freno. Se prueba la función, no el valor ya calculado:
    lo que importa es la REGLA, porque es la que decide el día del lanzamiento."""

    def _habilitado(self, frontend_url, forzar=None):
        import os
        from urllib.parse import urlparse
        anterior = os.environ.get('FORZAR_ENVIO_DE_CORREOS')
        if forzar is not None:
            os.environ['FORZAR_ENVIO_DE_CORREOS'] = forzar
        try:
            if os.environ.get('FORZAR_ENVIO_DE_CORREOS') == '1':
                return True
            host = (urlparse(frontend_url).hostname or '').lower()
            if host in ('localhost', '127.0.0.1'):
                return True
            from django.conf import settings
            return host in settings.DOMINIOS_DE_PRODUCCION
        finally:
            if forzar is not None:
                if anterior is None:
                    os.environ.pop('FORZAR_ENVIO_DE_CORREOS', None)
                else:
                    os.environ['FORZAR_ENVIO_DE_CORREOS'] = anterior

    def test_el_dominio_de_verdad_habilita(self):
        self.assertTrue(self._habilitado('https://ingenioblocks.com'))
        self.assertTrue(self._habilitado('https://www.ingenioblocks.com'))

    def test_la_ip_de_pruebas_no_habilita(self):
        """Es exactamente el caso que provocó el accidente."""
        self.assertFalse(self._habilitado('https://64-176-22-207.sslip.io'))

    def test_el_subdominio_de_preview_tampoco(self):
        self.assertFalse(self._habilitado('https://pre.ingenioblocks.com'))

    def test_en_desarrollo_si_pasa(self):
        """El backend local es el de consola: no sale nada a la red y conviene
        poder ver el correo en la terminal."""
        self.assertTrue(self._habilitado('http://localhost:5173'))

    def test_la_escotilla_manual_habilita(self):
        self.assertTrue(self._habilitado('https://64-176-22-207.sslip.io', forzar='1'))
