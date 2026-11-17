"""Correos masivos programados: salen solos a la hora elegida.

Todo con el backend de correo de pruebas (mail.outbox): nada sale de verdad.
"""
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from lms.models import Membership

from . import envio as masivos
from .models import DestinatarioMasivo, EnvioMasivo
from .preferencias import NOVEDADES, dar_de_baja

User = get_user_model()


def _alumno(correo):
    u = User.objects.create_user(username=correo, email=correo)
    return Membership.objects.create(user=u, expires_at=timezone.now() + timedelta(days=30))


def _probado():
    e = EnvioMasivo.objects.create(asunto='Novedades', cuerpo='Hola.', audiencia=EnvioMasivo.TODOS)
    e.prueba_enviada_en = timezone.now()
    e.prueba_huella = e.huella()
    e.save()
    return e


def _llego_la_hora(envio):
    EnvioMasivo.objects.filter(pk=envio.pk).update(programado_para=timezone.now() - timedelta(minutes=1))


@override_settings(ENVIAR_CORREOS=True)
class ProgramarTests(TestCase):
    def setUp(self):
        for i in range(3):
            _alumno(f'alumno{i}@correo.cl')
        p = mock.patch('comunicaciones.management.commands.enviar_masivos.avisar')
        self.avisar = p.start()
        self.addCleanup(p.stop)
        mail.outbox.clear()

    def correr(self):
        call_command('enviar_masivos', '--pausa', '0', stdout=StringIO())

    def test_programado_no_sale_antes_de_la_hora(self):
        e = masivos.programar(_probado(), timezone.now() + timedelta(hours=2))
        self.assertEqual(e.estado, EnvioMasivo.PROGRAMADO)
        self.correr()
        e.refresh_from_db()
        self.assertEqual(e.estado, EnvioMasivo.PROGRAMADO)
        self.assertEqual(e.destinatarios.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_a_la_hora_sale_y_avisa(self):
        e = masivos.programar(_probado(), timezone.now() + timedelta(hours=2))
        _llego_la_hora(e)
        self.correr()
        e.refresh_from_db()
        self.assertEqual(e.estado, EnvioMasivo.TERMINADO)
        self.assertEqual(len(mail.outbox), 3)
        textos = ' '.join(c.args[0] for c in self.avisar.call_args_list)
        self.assertIn('Empezó a salir', textos)
        self.assertIn('Terminó de salir', textos)

    def test_la_lista_se_arma_al_salir_no_al_programar(self):
        e = masivos.programar(_probado(), timezone.now() + timedelta(hours=2))
        dar_de_baja('alumno0@correo.cl', NOVEDADES)       # se da de baja después de programado
        _alumno('nuevo@correo.cl')                        # compra después de programado
        _llego_la_hora(e)
        self.correr()
        enviados = {m.to[0] for m in mail.outbox}
        self.assertNotIn('alumno0@correo.cl', enviados)
        self.assertIn('nuevo@correo.cl', enviados)

    def test_con_la_pausa_puesta_espera_y_no_se_pierde(self):
        e = masivos.programar(_probado(), timezone.now() + timedelta(hours=2))
        _llego_la_hora(e)
        with mock.patch('comunicaciones.freno.correos_a_clientes', return_value=False):
            self.correr()
        e.refresh_from_db()
        self.assertEqual(e.estado, EnvioMasivo.PROGRAMADO)
        self.assertEqual(len(mail.outbox), 0)
        self.correr()                                     # quitaron la pausa
        self.assertEqual(len(mail.outbox), 3)

    def test_si_ya_no_cumple_vuelve_a_borrador_y_avisa(self):
        e = masivos.programar(_probado(), timezone.now() + timedelta(hours=2))
        _llego_la_hora(e)
        EnvioMasivo.objects.filter(pk=e.pk).update(asunto='Otro asunto')   # ya no es lo que se probó
        self.correr()
        e.refresh_from_db()
        self.assertEqual(e.estado, EnvioMasivo.BORRADOR)
        self.assertEqual(len(mail.outbox), 0)
        self.assertIn('no salió', self.avisar.call_args.args[0])

    def test_desprogramar_lo_deja_en_borrador(self):
        e = masivos.programar(_probado(), timezone.now() + timedelta(hours=2))
        self.assertTrue(masivos.desprogramar(e))
        e.refresh_from_db()
        self.assertEqual(e.estado, EnvioMasivo.BORRADOR)
        self.assertIsNone(e.programado_para)
        _llego_la_hora(e)
        self.correr()
        self.assertEqual(len(mail.outbox), 0)

    def test_no_se_programa_sin_prueba_ni_en_el_pasado(self):
        sin_prueba = EnvioMasivo.objects.create(asunto='x', cuerpo='y', audiencia=EnvioMasivo.TODOS)
        with self.assertRaises(masivos.NoSePuedeEnviar):
            masivos.programar(sin_prueba, timezone.now() + timedelta(hours=1))
        with self.assertRaises(masivos.NoSePuedeEnviar):
            masivos.programar(_probado(), timezone.now() - timedelta(hours=1))
        with self.assertRaises(masivos.NoSePuedeEnviar):
            masivos.programar(_probado(), timezone.now() + timedelta(days=200))

    def test_un_programado_no_se_puede_editar(self):
        e = masivos.programar(_probado(), timezone.now() + timedelta(hours=2))
        self.assertFalse(e.editable)


@override_settings(ENVIAR_CORREOS=True)
class PanelProgramarTests(TestCase):
    def setUp(self):
        self.jefa = User.objects.create_user(username='jefa@ib.cl', email='jefa@ib.cl', is_staff=True)
        self.client.force_login(self.jefa)
        for i in range(3):
            _alumno(f'alumno{i}@correo.cl')
        mail.outbox.clear()

    def confirmar(self, e, **datos):
        return self.client.post(reverse('panel:correo_confirmar', args=[e.pk]), {'confirmacion': '3', **datos})

    def test_programar_desde_el_panel(self):
        e = _probado()
        cuando = timezone.localtime(timezone.now() + timedelta(days=1)).replace(second=0, microsecond=0)
        r = self.confirmar(e, accion='programar', cuando=cuando.strftime('%Y-%m-%dT%H:%M'))
        self.assertRedirects(r, reverse('panel:correo_detalle', args=[e.pk]), fetch_redirect_response=False)
        e.refresh_from_db()
        self.assertEqual(e.estado, EnvioMasivo.PROGRAMADO)
        self.assertEqual(e.programado_para, cuando)
        self.assertEqual(len(mail.outbox), 0)
        self.assertContains(self.client.get(reverse('panel:correo_detalle', args=[e.pk])), 'Cancelar programación')
        self.assertContains(self.client.get(reverse('panel:correos')), 'Programado')

    def test_programar_sin_fecha_no_manda_nada(self):
        e = _probado()
        r = self.confirmar(e, accion='programar', cuando='')
        self.assertEqual(r.status_code, 200)
        e.refresh_from_db()
        self.assertEqual(e.estado, EnvioMasivo.BORRADOR)
        self.assertEqual(e.destinatarios.count(), 0)

    def test_programar_igual_pide_el_numero_exacto(self):
        e = _probado()
        cuando = (timezone.localtime() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
        self.client.post(reverse('panel:correo_confirmar', args=[e.pk]),
                         {'confirmacion': '2', 'accion': 'programar', 'cuando': cuando})
        e.refresh_from_db()
        self.assertEqual(e.estado, EnvioMasivo.BORRADOR)

    def test_enviar_ahora_sigue_igual(self):
        e = _probado()
        self.confirmar(e, accion='ahora')
        e.refresh_from_db()
        self.assertEqual(e.estado, EnvioMasivo.EN_COLA)

    def test_cancelar_programacion(self):
        e = masivos.programar(_probado(), timezone.now() + timedelta(hours=3))
        r = self.client.post(reverse('panel:correo_desprogramar', args=[e.pk]))
        self.assertRedirects(r, reverse('panel:correo_edit', args=[e.pk]), fetch_redirect_response=False)
        e.refresh_from_db()
        self.assertEqual(e.estado, EnvioMasivo.BORRADOR)
        self.assertFalse(DestinatarioMasivo.objects.exists())

    def test_boton_programar_del_editor_lleva_a_programar(self):
        e = _probado()
        r = self.client.post(reverse('panel:correo_edit', args=[e.pk]), {
            'asunto': e.asunto, 'cuerpo_html': '<p>Hola.</p>', 'audiencia': 'TODOS',
            'boton_texto': '', 'boton_url': '', 'accion': 'programar'})
        self.assertRedirects(r, reverse('panel:correo_confirmar', args=[e.pk]) + '?programar=1',
                             fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 0)

    def test_programar_una_prueba_no_manda_nada(self):
        e = _probado()
        r = self.client.post(reverse('panel:correo_edit', args=[e.pk]), {
            'asunto': e.asunto, 'cuerpo_html': '<p>Hola.</p>', 'audiencia': 'PRUEBA',
            'boton_texto': '', 'boton_url': '', 'accion': 'programar'})
        self.assertRedirects(r, reverse('panel:correo_edit', args=[e.pk]), fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 0)
        e.refresh_from_db()
        self.assertEqual(e.estado, EnvioMasivo.BORRADOR)

    def test_la_lista_deja_borrar_borradores(self):
        e = _probado()
        r = self.client.get(reverse('panel:correos'))
        self.assertContains(r, reverse('panel:correo_eliminar', args=[e.pk]))
        self.client.post(reverse('panel:correo_eliminar', args=[e.pk]))
        self.assertFalse(EnvioMasivo.objects.filter(pk=e.pk).exists())
