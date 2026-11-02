"""Alertas por Telegram a quien mantiene el sitio (core/alertas.py).

Telegram va simulado. Lo que importa: que los problemas y los mensajes de
clientes lleguen, que el mismo problema no inunde el celular, que sin
configuración no salga nada, y que una alerta nunca rompa lo que la provocó.
"""
import logging
from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.cache import caches
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.alertas import avisar

CONFIG = dict(
    TELEGRAM_BOT_TOKEN='123:abc', TELEGRAM_CHAT_ID='999',
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
            'alertas': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'alertas-tests'}},
)


@override_settings(**CONFIG)
class Base(TestCase):
    def setUp(self):
        caches['alertas'].clear()
        p = patch('core.alertas.requests.post', return_value=MagicMock(ok=True))
        self.post = p.start()
        self.addCleanup(p.stop)

    def textos(self):
        return [c.kwargs['data']['text'] for c in self.post.call_args_list]


class AvisarTests(Base):
    def test_manda_al_chat_configurado(self):
        self.assertTrue(avisar('hola'))
        self.assertIn('bot123:abc/sendMessage', self.post.call_args.args[0])
        self.assertEqual(self.post.call_args.kwargs['data']['chat_id'], '999')

    def test_el_mismo_problema_se_avisa_una_vez(self):
        avisar('falla x', firma='x')
        avisar('falla x', firma='x')
        avisar('falla y', firma='y')
        self.assertEqual(self.textos(), ['falla x', 'falla y'])

    @override_settings(TELEGRAM_BOT_TOKEN='')
    def test_sin_configurar_no_sale_nada(self):
        self.assertFalse(avisar('hola'))
        self.post.assert_not_called()

    def test_si_telegram_falla_no_rompe_nada(self):
        self.post.side_effect = ConnectionError('sin internet')
        self.assertFalse(avisar('hola'))


class ErroresTests(Base):
    def test_un_error_registrado_llega_por_telegram(self):
        logging.getLogger('ingenioblocks.pagos').error('Falló la emisión de boleta de la orden 123')
        self.assertTrue(any('Falló la emisión de boleta' in t for t in self.textos()))

    def test_los_robots_de_django_security_no_avisan(self):
        logging.getLogger('django.security.DisallowedHost').error('Invalid HTTP_HOST header')
        self.post.assert_not_called()

    def test_un_correo_que_no_sale_se_avisa(self):
        from core.emails import enviar_email
        with patch('django.core.mail.EmailMultiAlternatives.send', return_value=0):
            enviar_email('recuperar_clave', asunto='x', destinatarios=['staff@ib.cl'],
                         contexto={'link': 'https://x'})
        self.assertTrue(any('CORREO NO SALIÓ' in t for t in self.textos()))


class MensajeDeClienteTests(Base):
    def test_un_mensaje_del_formulario_llega_con_su_texto(self):
        with patch('catalog.views.enviar_email'):
            r = APIClient().post('/api/catalog/contacto/', {
                'nombre': 'Ana', 'apellido': 'Pérez', 'email': 'ana@correo.cl',
                'telefono': '+56911112222', 'comentarios': '¿Tienen despacho a Puerto Montt?',
            }, format='json')
        self.assertEqual(r.status_code, 200)
        texto = self.textos()[-1]
        self.assertIn('Ana Pérez', texto)
        self.assertIn('ana@correo.cl', texto)
        self.assertIn('Puerto Montt', texto)


class VigilarTests(Base):
    def test_avisa_si_el_sitio_no_responde_y_cuando_vuelve(self):
        with patch('comunicaciones.management.commands.vigilar_sitio.requests.get',
                   side_effect=ConnectionError), \
                patch('comunicaciones.management.commands.vigilar_sitio.revisar_certificado', return_value=None):
            call_command('vigilar_sitio', stdout=StringIO())
            call_command('vigilar_sitio', stdout=StringIO())   # 10 min después: no repite
        with patch('comunicaciones.management.commands.vigilar_sitio.requests.get',
                   return_value=MagicMock(status_code=200)), \
                patch('comunicaciones.management.commands.vigilar_sitio.revisar_certificado', return_value=None):
            call_command('vigilar_sitio', stdout=StringIO())
        textos = self.textos()
        self.assertEqual(sum('no responde' in t for t in textos), 1)
        self.assertTrue(any('Resuelto' in t and 'sitio' in t for t in textos))


class ResumenTests(Base):
    def test_el_resumen_sale_con_sus_secciones(self):
        call_command('resumen_diario', stdout=StringIO())
        texto = self.textos()[-1]
        for parte in ('Resumen', 'Ventas', 'Pendientes', 'Chequeos'):
            self.assertIn(parte, texto)

    def test_probar_manda_un_saludo(self):
        call_command('resumen_diario', '--probar', stdout=StringIO())
        self.assertIn('quedaron funcionando', self.textos()[-1])
