"""Correos masivos y preferencias de correo.

Lo que se cuida acá, en orden de gravedad:

1. Que una baja se respete SIEMPRE -la ley lo exige- y que sobreviva a la
   importación, que borra y recrea a los alumnos.
2. Que darse de baja de novedades no deje a nadie sin la confirmación de su
   compra.
3. Que abrir el enlace del correo no dé de baja: el escáner de Gmail los abre
   solo.
4. Que un masivo no salga sin prueba, ni dos veces a la misma persona.
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

from core.emails import enviar_email
from lms.models import Membership
from payments.models import Order

from . import envio as masivos
from .models import BajaDeCorreo, DestinatarioMasivo, EnvioMasivo
from .preferencias import (
    AULA, NOVEDADES, dar_de_baja, esta_de_baja, token_de, url_baja_un_clic,
    url_preferencias)

User = get_user_model()

AVISO_CTX = {'saludo': 'Hola', 'numero': 3, 'curso_titulo': 'Carrusel',
             'curso_descripcion': '', 'link': 'https://x'}
CLAVE_CTX = {'nombre': 'Ana', 'link': 'https://x'}


def _alumno(correo, vigente=True):
    u = User.objects.create_user(username=correo, email=correo)
    vence = timezone.now() + timedelta(days=30 if vigente else -30)
    return Membership.objects.create(user=u, expires_at=vence)


def _equipo(correo='jefa@ib.cl'):
    return User.objects.create_user(username=correo, email=correo, is_staff=True)


# ---------------------------------------------------------------------------
# 1. La regla de las categorías, en el único punto por donde salen los correos
# ---------------------------------------------------------------------------

@override_settings(ENVIAR_CORREOS=True)
class CategoriasTests(TestCase):

    def setUp(self):
        mail.outbox.clear()

    def test_los_correos_del_servicio_llegan_aunque_se_haya_dado_de_baja_de_todo(self):
        """Nadie puede quedarse sin su confirmación de compra o su cambio de
        clave por haberse dado de baja de las novedades."""
        dar_de_baja('ana@correo.cl', NOVEDADES)
        dar_de_baja('ana@correo.cl', AULA)
        enviar_email('recuperar_clave', 'Clave', ['ana@correo.cl'], CLAVE_CTX)
        self.assertEqual(len(mail.outbox), 1)

    def test_el_aviso_del_aula_respeta_su_baja(self):
        dar_de_baja('ana@correo.cl', AULA)
        enviar_email('curso_desbloqueado', 'Nuevo', ['ana@correo.cl'], AVISO_CTX)
        self.assertEqual(len(mail.outbox), 0)

    def test_las_bajas_no_se_pisan_entre_categorias(self):
        """Salirse de las novedades no apaga los avisos de modelos nuevos."""
        dar_de_baja('ana@correo.cl', NOVEDADES)
        enviar_email('curso_desbloqueado', 'Nuevo', ['ana@correo.cl'], AVISO_CTX)
        self.assertEqual(len(mail.outbox), 1)

    def test_la_baja_no_distingue_mayusculas(self):
        dar_de_baja('Ana@Correo.CL', AULA)
        enviar_email('curso_desbloqueado', 'Nuevo', ['ana@correo.cl'], AVISO_CTX)
        self.assertEqual(len(mail.outbox), 0)

    def test_cada_uno_recibe_su_propio_enlace(self):
        """Un enlace compartido le permitiría a uno dar de baja al otro."""
        enviar_email('curso_desbloqueado', 'Nuevo', ['a@x.cl', 'b@x.cl'], AVISO_CTX)
        self.assertEqual(len(mail.outbox), 2)
        cuerpos = [m.body for m in mail.outbox]
        self.assertIn(url_preferencias('a@x.cl', AULA), cuerpos[0])
        self.assertIn(url_preferencias('b@x.cl', AULA), cuerpos[1])
        self.assertNotIn(url_preferencias('b@x.cl', AULA), cuerpos[0])

    def test_lleva_la_cabecera_estandar_de_baja(self):
        """La que hace que Gmail muestre su botón "Cancelar suscripción"."""
        enviar_email('curso_desbloqueado', 'Nuevo', ['a@x.cl'], AVISO_CTX)
        m = mail.outbox[0]
        self.assertEqual(m.extra_headers['List-Unsubscribe'],
                         '<%s>' % url_baja_un_clic('a@x.cl', AULA))
        self.assertEqual(m.extra_headers['List-Unsubscribe-Post'], 'List-Unsubscribe=One-Click')

    def test_el_enlace_va_tambien_en_el_html(self):
        enviar_email('curso_desbloqueado', 'Nuevo', ['a@x.cl'], AVISO_CTX)
        html = mail.outbox[0].alternatives[0][0]
        self.assertIn(url_preferencias('a@x.cl', AULA), html)
        self.assertIn('Darte de baja', html)

    def test_los_del_servicio_no_llevan_enlace_de_baja(self):
        enviar_email('recuperar_clave', 'Clave', ['a@x.cl'], CLAVE_CTX)
        m = mail.outbox[0]
        self.assertNotIn('List-Unsubscribe', m.extra_headers)
        self.assertNotIn('Darte de baja', m.alternatives[0][0])

    def test_las_novedades_salen_con_su_propio_nombre(self):
        """Se distinguen de un vistazo de los correos de una compra."""
        enviar_email('novedades', 'Hola', ['a@x.cl'],
                     {'titulo': 'Hola', 'parrafos': ['Texto'], 'preheader': 'x'})
        self.assertIn('Novedades', mail.outbox[0].from_email)

    def test_la_prueba_llega_aunque_esa_persona_se_haya_dado_de_baja(self):
        dar_de_baja('jefa@ib.cl', NOVEDADES)
        enviar_email('novedades', 'Hola', ['jefa@ib.cl'],
                     {'titulo': 'Hola', 'parrafos': ['x']}, es_prueba=True)
        self.assertEqual(len(mail.outbox), 1)


class LaBajaSobreviveALaImportacionTests(TestCase):
    """El motivo de guardar las bajas por dirección y no en la ficha."""

    @override_settings(ENVIAR_CORREOS=True)
    def test_borrar_al_alumno_no_borra_su_baja(self):
        m = _alumno('ana@correo.cl')
        dar_de_baja('ana@correo.cl', NOVEDADES)
        m.user.delete()                     # lo que hace la importación
        _alumno('ana@correo.cl')            # ...y lo vuelve a crear
        self.assertTrue(esta_de_baja('ana@correo.cl', NOVEDADES))
        mail.outbox.clear()
        enviar_email('novedades', 'Hola', ['ana@correo.cl'], {'titulo': 'x', 'parrafos': ['x']})
        self.assertEqual(len(mail.outbox), 0)


# ---------------------------------------------------------------------------
# 2. La página de preferencias y la baja de un clic
# ---------------------------------------------------------------------------

class PaginaDePreferenciasTests(TestCase):

    def _url(self, categoria=NOVEDADES, correo='ana@correo.cl'):
        return reverse('correos_preferencias', args=[token_de(correo, categoria)])

    def test_abrir_el_enlace_NO_da_de_baja(self):
        """El escáner de Gmail abre los enlaces de los correos solo. Si abrirlo
        diera de baja, daría de baja a la gente sin que tocara nada."""
        r = self.client.get(self._url())
        self.assertEqual(r.status_code, 200)
        self.assertFalse(BajaDeCorreo.objects.exists())

    def test_el_boton_da_de_baja_solo_esa_categoria(self):
        self.client.post(self._url(NOVEDADES), {'accion': 'baja_rapida'})
        self.assertTrue(esta_de_baja('ana@correo.cl', NOVEDADES))
        self.assertFalse(esta_de_baja('ana@correo.cl', AULA))

    def test_los_interruptores_guardan_cada_categoria(self):
        self.client.post(self._url(), {AULA: 'on'})          # novedades apagado
        self.assertTrue(esta_de_baja('ana@correo.cl', NOVEDADES))
        self.assertFalse(esta_de_baja('ana@correo.cl', AULA))

    def test_se_puede_volver_a_suscribir(self):
        dar_de_baja('ana@correo.cl', NOVEDADES)
        self.client.post(self._url(), {NOVEDADES: 'on', AULA: 'on'})
        self.assertFalse(esta_de_baja('ana@correo.cl', NOVEDADES))

    def test_despues_de_guardar_redirige(self):
        """Sin redirigir, recargar la página volvía a mandar el formulario."""
        r = self.client.post(self._url(), {'accion': 'baja_rapida'})
        self.assertEqual(r.status_code, 302)
        self.assertIn('guardado=1', r['Location'])

    def test_un_enlace_alterado_no_sirve(self):
        token = token_de('ana@correo.cl', NOVEDADES)
        r = self.client.get(reverse('correos_preferencias', args=[token[:-3] + 'abc']))
        self.assertEqual(r.status_code, 404)

    def test_no_se_puede_fabricar_el_enlace_de_otra_persona(self):
        """El ataque concreto: tomar el enlace propio, cambiarle el correo por el
        de otra persona y reusar la firma. El correo va legible en el enlace
        -firmado, no cifrado-, así que cambiarlo es trivial; lo que lo impide
        es que la firma deja de calzar."""
        import base64
        import json
        datos, sello, firma = token_de('ana@correo.cl', NOVEDADES).split(':')
        ajeno = base64.urlsafe_b64encode(
            json.dumps({'e': 'victima@correo.cl', 'c': NOVEDADES},
                       separators=(',', ':')).encode()).decode().rstrip('=')
        falso = ':'.join([ajeno, sello, firma])
        r = self.client.post(reverse('correos_preferencias', args=[falso]),
                             {'accion': 'baja_rapida'})
        self.assertEqual(r.status_code, 404)
        self.assertFalse(esta_de_baja('victima@correo.cl', NOVEDADES))

    def test_la_pagina_aclara_que_las_compras_llegan_siempre(self):
        self.assertContains(self.client.get(self._url()), 'tus compras y tu cuenta')


class BajaDeUnClicTests(TestCase):

    def _url(self):
        return reverse('correos_baja', args=[token_de('ana@correo.cl', NOVEDADES)])

    def test_el_post_de_gmail_da_de_baja_sin_csrf(self):
        """Gmail lo manda sin cookies ni formulario (RFC 8058)."""
        cliente = self.client_class(enforce_csrf_checks=True)
        r = cliente.post(self._url(), {'List-Unsubscribe': 'One-Click'})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(esta_de_baja('ana@correo.cl', NOVEDADES))

    def test_abrirlo_en_el_navegador_no_da_de_baja(self):
        r = self.client.get(self._url())
        self.assertEqual(r.status_code, 302)
        self.assertFalse(BajaDeCorreo.objects.exists())


class EnlaceDesdeMiCuentaTests(TestCase):

    def test_pide_sesion(self):
        self.assertEqual(self.client.get('/api/correos/mi-enlace/').status_code, 401)

    def test_devuelve_el_enlace_de_la_persona(self):
        m = _alumno('ana@correo.cl')
        self.client.force_login(m.user)
        from rest_framework.test import APIClient
        api = APIClient()
        api.force_authenticate(m.user)
        r = api.get('/api/correos/mi-enlace/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['url'], url_preferencias('ana@correo.cl', NOVEDADES))


# ---------------------------------------------------------------------------
# 3. El correo masivo: prueba, cola y envío de a poco
# ---------------------------------------------------------------------------

def _envio(**extra):
    datos = {'asunto': 'Estrenamos página', 'cuerpo': 'Hola.\n\nTe contamos...',
             'audiencia': EnvioMasivo.TODOS}
    datos.update(extra)
    return EnvioMasivo.objects.create(**datos)


class PruebaTests(TestCase):

    @override_settings(ENVIAR_CORREOS=True)
    def test_la_prueba_va_solo_al_equipo(self):
        _equipo('jefa@ib.cl')
        _alumno('cliente@correo.cl')
        mail.outbox.clear()
        masivos.enviar_prueba(_envio())
        self.assertEqual([m.to for m in mail.outbox], [['jefa@ib.cl']])
        self.assertTrue(mail.outbox[0].subject.startswith('[PRUEBA]'))

    @override_settings(ENVIAR_CORREOS=False)
    def test_la_prueba_funciona_con_el_freno_puesto(self):
        """Es lo que permite probarlo antes del lanzamiento."""
        _equipo('jefa@ib.cl')
        mail.outbox.clear()
        masivos.enviar_prueba(_envio())
        self.assertEqual(len(mail.outbox), 1)

    def test_cambiar_el_contenido_invalida_la_prueba(self):
        e = _envio()
        e.prueba_huella = e.huella()
        e.prueba_enviada_en = timezone.now()
        e.save()
        self.assertTrue(e.prueba_al_dia)
        e.cuerpo += ' Una coma más,'
        self.assertFalse(e.prueba_al_dia)

    def test_cambiar_a_quien_se_manda_no_invalida_la_prueba(self):
        """Lo que se probó es lo que se ve, no a quién le llega."""
        e = _envio()
        e.prueba_huella = e.huella()
        e.audiencia = EnvioMasivo.VIGENTES
        self.assertTrue(e.prueba_al_dia)


class MotivoParaNoEnviarTests(TestCase):

    def _probado(self):
        e = _envio()
        e.prueba_enviada_en = timezone.now()
        e.prueba_huella = e.huella()
        e.save()
        return e

    @override_settings(ENVIAR_CORREOS=False)
    def test_con_el_freno_no_se_envia_a_todos(self):
        self.assertIn('dominio', masivos.motivo_para_no_enviar(self._probado()))

    @override_settings(ENVIAR_CORREOS=True)
    def test_sin_prueba_no(self):
        self.assertIn('prueba', masivos.motivo_para_no_enviar(_envio()))

    @override_settings(ENVIAR_CORREOS=True)
    def test_con_prueba_vieja_no(self):
        e = self._probado()
        e.asunto = 'Otro asunto'
        self.assertIn('Cambiaste', masivos.motivo_para_no_enviar(e))

    @override_settings(ENVIAR_CORREOS=True)
    def test_con_prueba_al_dia_si(self):
        self.assertIsNone(masivos.motivo_para_no_enviar(self._probado()))


class AudienciaTests(TestCase):

    def test_sin_repetidos_ni_mayusculas(self):
        _alumno('ana@correo.cl')
        Order.objects.create(customer_email='ANA@correo.cl', total_amount=1000, status='PAID')
        self.assertEqual(masivos.correos_de_la_audiencia(EnvioMasivo.TODOS), ['ana@correo.cl'])

    def test_el_equipo_no_entra(self):
        """Ya recibió la prueba."""
        _equipo('jefa@ib.cl')
        Order.objects.create(customer_email='jefa@ib.cl', total_amount=1000, status='PAID')
        self.assertEqual(masivos.correos_de_la_audiencia(EnvioMasivo.TODOS), [])

    def test_todos_incluye_a_quien_compro_sin_aula(self):
        Order.objects.create(customer_email='kit@correo.cl', total_amount=1000, status='PAID')
        self.assertIn('kit@correo.cl', masivos.correos_de_la_audiencia(EnvioMasivo.TODOS))

    def test_un_pedido_que_no_se_pago_no_cuenta(self):
        Order.objects.create(customer_email='nopago@correo.cl', total_amount=1000, status='PENDING')
        self.assertNotIn('nopago@correo.cl', masivos.correos_de_la_audiencia(EnvioMasivo.TODOS))

    def test_vigentes_deja_fuera_a_los_vencidos(self):
        _alumno('al_dia@correo.cl', vigente=True)
        _alumno('vencido@correo.cl', vigente=False)
        self.assertEqual(masivos.correos_de_la_audiencia(EnvioMasivo.VIGENTES), ['al_dia@correo.cl'])

    def test_la_cuenta_descuenta_las_bajas(self):
        _alumno('a@correo.cl')
        _alumno('b@correo.cl')
        dar_de_baja('b@correo.cl', NOVEDADES)
        self.assertEqual(masivos.cuantos(EnvioMasivo.TODOS),
                         {'total': 2, 'de_baja': 1, 'a_enviar': 1})


@override_settings(ENVIAR_CORREOS=True)
class ColaYEnvioTests(TestCase):

    def setUp(self):
        for i in range(5):
            _alumno('alumno%d@correo.cl' % i)
        self.envio = _envio()
        self.envio.prueba_enviada_en = timezone.now()
        self.envio.prueba_huella = self.envio.huella()
        self.envio.save()
        mail.outbox.clear()

    def _procesar(self, lote=25):
        return masivos.procesar(lote=lote, pausa=0, dormir=lambda s: None)

    def test_encolar_arma_la_lista_y_no_manda_nada_todavia(self):
        masivos.encolar(self.envio)
        self.envio.refresh_from_db()
        self.assertEqual(self.envio.estado, EnvioMasivo.EN_COLA)
        self.assertEqual(self.envio.destinatarios.count(), 5)
        self.assertEqual(len(mail.outbox), 0)

    def test_los_que_ya_se_dieron_de_baja_quedan_anotados_como_omitidos(self):
        dar_de_baja('alumno0@correo.cl', NOVEDADES)
        masivos.encolar(self.envio)
        d = self.envio.destinatarios.get(email='alumno0@correo.cl')
        self.assertEqual(d.estado, DestinatarioMasivo.OMITIDO)

    def test_no_se_puede_encolar_dos_veces(self):
        """Dos clics seguidos no pueden mandar el correo dos veces."""
        masivos.encolar(self.envio)
        with self.assertRaises(masivos.NoSePuedeEnviar):
            masivos.encolar(EnvioMasivo.objects.get(pk=self.envio.pk))

    def test_sale_de_a_poco(self):
        masivos.encolar(self.envio)
        self._procesar(lote=2)
        self.assertEqual(len(mail.outbox), 2)
        self.envio.refresh_from_db()
        self.assertEqual(self.envio.estado, EnvioMasivo.EN_COLA)

    def test_al_terminar_queda_como_enviado(self):
        masivos.encolar(self.envio)
        self._procesar()
        self.envio.refresh_from_db()
        self.assertEqual(self.envio.estado, EnvioMasivo.TERMINADO)
        self.assertEqual(self.envio.contadores()['ENVIADO'], 5)
        self.assertEqual(len(mail.outbox), 5)

    def test_una_falla_se_anota_y_el_resto_sigue(self):
        masivos.encolar(self.envio)
        original = masivos.enviar_a

        def falla_uno(envio, email, prueba=False):
            if email == 'alumno2@correo.cl':
                raise ConnectionError('SMTP caído')
            return original(envio, email, prueba)

        with mock.patch.object(masivos, 'enviar_a', side_effect=falla_uno):
            self._procesar()
        d = self.envio.destinatarios.get(email='alumno2@correo.cl')
        self.assertEqual(d.estado, DestinatarioMasivo.FALLIDO)
        self.assertIn('SMTP', d.error)
        self.assertEqual(len(mail.outbox), 4)

    def test_quien_se_da_de_baja_a_mitad_del_envio_no_lo_recibe(self):
        masivos.encolar(self.envio)
        dar_de_baja('alumno4@correo.cl', NOVEDADES)
        self._procesar()
        self.assertEqual(self.envio.destinatarios.get(email='alumno4@correo.cl').estado,
                         DestinatarioMasivo.OMITIDO)
        self.assertNotIn(['alumno4@correo.cl'], [m.to for m in mail.outbox])

    def test_cancelar_frena_el_envio(self):
        masivos.encolar(self.envio)
        EnvioMasivo.objects.filter(pk=self.envio.pk).update(estado=EnvioMasivo.CANCELADO)
        self._procesar()
        self.assertEqual(len(mail.outbox), 0)

    def test_nadie_lo_recibe_dos_veces(self):
        """Si una fila ya la tomó otro proceso, este la salta."""
        masivos.encolar(self.envio)
        self.envio.destinatarios.filter(email='alumno0@correo.cl').update(
            estado=DestinatarioMasivo.ENVIANDO, enviado_en=timezone.now())
        self._procesar()
        self.assertNotIn(['alumno0@correo.cl'], [m.to for m in mail.outbox])

    def test_un_envio_cortado_a_la_mitad_no_se_reintenta(self):
        """Mandar el mismo correo dos veces es peor que perder uno."""
        masivos.encolar(self.envio)
        self.envio.destinatarios.filter(email='alumno0@correo.cl').update(
            estado=DestinatarioMasivo.ENVIANDO,
            enviado_en=timezone.now() - timedelta(minutes=30))
        self._procesar()
        d = self.envio.destinatarios.get(email='alumno0@correo.cl')
        self.assertEqual(d.estado, DestinatarioMasivo.FALLIDO)
        self.assertNotIn(['alumno0@correo.cl'], [m.to for m in mail.outbox])

    @override_settings(ENVIAR_CORREOS=False)
    def test_el_comando_no_hace_nada_con_el_freno_puesto(self):
        EnvioMasivo.objects.filter(pk=self.envio.pk).update(estado=EnvioMasivo.EN_COLA)
        DestinatarioMasivo.objects.create(envio=self.envio, email='alumno0@correo.cl')
        salida = StringIO()
        call_command('enviar_masivos', stdout=salida)
        self.assertIn('Freno', salida.getvalue())
        self.assertEqual(len(mail.outbox), 0)


# ---------------------------------------------------------------------------
# 4. Las pantallas del panel
# ---------------------------------------------------------------------------

@override_settings(ENVIAR_CORREOS=True)
class PanelTests(TestCase):

    def setUp(self):
        self.jefa = User.objects.create_user(username='jefa@ib.cl', email='jefa@ib.cl',
                                             password='clave-larga-1234', is_staff=True)
        self.client.force_login(self.jefa)
        for i in range(3):
            _alumno('alumno%d@correo.cl' % i)

    def _probado(self):
        e = _envio()
        e.prueba_enviada_en = timezone.now()
        e.prueba_huella = e.huella()
        e.save()
        return e

    def test_solo_el_equipo_entra(self):
        self.client.logout()
        r = self.client.get(reverse('panel:correos'))
        self.assertEqual(r.status_code, 302)

    def test_se_puede_crear_un_borrador(self):
        r = self.client.post(reverse('panel:correo_new'), {
            'asunto': 'Hola', 'cuerpo': 'Texto', 'audiencia': 'TODOS',
            'boton_texto': '', 'boton_url': ''})
        self.assertEqual(r.status_code, 302)
        e = EnvioMasivo.objects.get()
        self.assertEqual(e.creado_por, self.jefa)
        self.assertEqual(e.estado, EnvioMasivo.BORRADOR)

    def test_un_boton_a_medias_no_se_acepta(self):
        r = self.client.post(reverse('panel:correo_new'), {
            'asunto': 'Hola', 'cuerpo': 'Texto', 'audiencia': 'TODOS',
            'boton_texto': 'Ver', 'boton_url': ''})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(EnvioMasivo.objects.exists())

    def test_hay_que_escribir_el_numero_exacto(self):
        e = self._probado()
        r = self.client.post(reverse('panel:correo_confirmar', args=[e.pk]), {'confirmacion': '2'})
        self.assertEqual(r.status_code, 200)
        e.refresh_from_db()
        self.assertEqual(e.estado, EnvioMasivo.BORRADOR)

    def test_con_el_numero_exacto_sale(self):
        e = self._probado()
        r = self.client.post(reverse('panel:correo_confirmar', args=[e.pk]), {'confirmacion': '3'})
        self.assertRedirects(r, reverse('panel:correo_detalle', args=[e.pk]), fetch_redirect_response=False)
        e.refresh_from_db()
        self.assertEqual(e.estado, EnvioMasivo.EN_COLA)

    def test_sin_prueba_ni_escribiendo_el_numero(self):
        e = _envio()
        self.client.post(reverse('panel:correo_confirmar', args=[e.pk]), {'confirmacion': '3'})
        e.refresh_from_db()
        self.assertEqual(e.estado, EnvioMasivo.BORRADOR)

    def test_lo_enviado_ya_no_se_puede_editar(self):
        e = self._probado()
        masivos.encolar(e)
        r = self.client.get(reverse('panel:correo_edit', args=[e.pk]))
        self.assertRedirects(r, reverse('panel:correo_detalle', args=[e.pk]), fetch_redirect_response=False)

    def test_la_vista_previa_muestra_el_correo(self):
        e = _envio(cuerpo='Hola.\n\nVisita https://ingenioblocks.com')
        r = self.client.get(reverse('panel:correo_vista_previa', args=[e.pk]))
        self.assertContains(r, 'Estrenamos página')
        self.assertContains(r, 'href="https://ingenioblocks.com"')   # urlize

    def test_lo_que_se_escribe_no_se_ejecuta_como_codigo(self):
        e = _envio(cuerpo='<script>alert(1)</script>')
        r = self.client.get(reverse('panel:correo_vista_previa', args=[e.pk]))
        self.assertNotContains(r, '<script>alert(1)</script>')
