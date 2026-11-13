"""Un correo a un cliente que no sale no se pierde: se guarda y se reintenta.

Caso real: el 11-11-2026 Gmail demoró al cobrar una renovación y los dos
correos de la familia (acceso extendido y confirmación) nunca le llegaron.
"""
import smtplib
from io import StringIO
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings

from comunicaciones.models import CorreoPendiente
from core.emails import enviar_email


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ReintentoTests(TestCase):
    def setUp(self):
        p = patch('comunicaciones.freno.correos_a_clientes', return_value=True)
        p.start()
        self.addCleanup(p.stop)
        p = patch('comunicaciones.management.commands.reintentar_correos.avisar')
        self.avisar = p.start()
        self.addCleanup(p.stop)

    def mandar(self):
        enviar_email('recuperar_clave', asunto='Recupera tu clave', destinatarios=['familia@correo.cl'],
                     contexto={'link': 'https://ingenioblocks.com/x'})

    def test_si_gmail_falla_queda_guardado(self):
        with patch('django.core.mail.EmailMultiAlternatives.send', side_effect=smtplib.SMTPServerDisconnected('timeout')):
            self.mandar()
        p = CorreoPendiente.objects.get()
        self.assertEqual(p.destinatarios, ['familia@correo.cl'])
        self.assertEqual(p.asunto, 'Recupera tu clave')
        self.assertIn('SMTPServerDisconnected', p.ultimo_error)
        self.assertIn('ingenioblocks.com/x', p.html)

    def test_el_reintento_lo_manda_una_vez(self):
        with patch('django.core.mail.EmailMultiAlternatives.send', side_effect=smtplib.SMTPServerDisconnected('timeout')):
            self.mandar()
        mail.outbox = []
        call_command('reintentar_correos', stdout=StringIO())
        call_command('reintentar_correos', stdout=StringIO())   # 10 min después: no repite
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['familia@correo.cl'])
        self.assertEqual(mail.outbox[0].subject, 'Recupera tu clave')
        self.assertIsNotNone(CorreoPendiente.objects.get().enviado_en)
        self.avisar.assert_called_once()

    def test_despues_de_6_intentos_deja_de_insistir(self):
        CorreoPendiente.objects.create(destinatarios=['x@y.cl'], asunto='a', texto='t', html='<p>h</p>',
                                       intentos=CorreoPendiente.INTENTOS_MAXIMOS)
        call_command('reintentar_correos', stdout=StringIO())
        self.assertEqual(len(mail.outbox), 0)

    def test_un_correo_que_sale_no_queda_pendiente(self):
        self.mandar()
        self.assertEqual(len(mail.outbox), 1)
        self.assertFalse(CorreoPendiente.objects.exists())
