"""Transbank Oneclick: compra con tarjeta inscrita y suscripciones.

Transbank va simulado: lo que se prueba es qué hace la tienda con cada
respuesta. Lo más importante es la plata: nunca cobrar dos veces, no dar por
pagado lo que no se cobró y no dar por perdido lo que quizás sí se cobró.
"""
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from catalog.models import Product
from payments import oneclick
from payments.models import Coupon, Order, Suscripcion, TarjetaOneclick

User = get_user_model()

INSCRITA = {'response_code': 0, 'tbk_user': 'tbk-abc', 'card_type': 'Visa',
            'card_number': 'XXXXXXXXXXXX6623', 'authorization_code': '1213'}
AUTORIZADA = {'details': [{'status': 'AUTHORIZED', 'response_code': 0, 'amount': 1}]}
RECHAZADA = {'details': [{'status': 'FAILED', 'response_code': -1, 'amount': 1}]}


def datos(product, **extra):
    base = {
        'product_ids': [product.id], 'email': 'mama@correo.cl',
        'customer_name': 'Ana Pérez', 'student_name': 'Beni', 'phone': '+56912345678',
    }
    base.update(extra)
    return base


class Base(TestCase):
    def setUp(self):
        # Los topes de intentos (throttle) viven en la caché y sobreviven de un
        # test al otro: sin limpiarla, los últimos tests reciben 429.
        cache.clear()
        self.api = APIClient()
        self.pack = Product.objects.create(
            name='Pack', slug='pack', price=13490, is_active=True, is_digital=True,
        )
        self.mensual = Product.objects.create(
            name='Membresía', slug='membresia', price=4990, is_active=True,
            is_digital=True, es_suscripcion=True, access_months=1,
        )
        p = patch('payments.oneclick.MallInscription')
        self.Inscripcion = p.start()
        self.addCleanup(p.stop)
        p = patch('payments.oneclick.MallTransaction')
        self.Transaccion = p.start()
        self.addCleanup(p.stop)
        p = patch('payments.views._entregar_compra')
        self.entregar = p.start()
        self.addCleanup(p.stop)
        self.Inscripcion.return_value.start.return_value = {'token': 'tok-1', 'url_webpay': 'https://tbk/inscribir'}
        self.Inscripcion.return_value.finish.return_value = INSCRITA
        self.Transaccion.return_value.authorize.return_value = AUTORIZADA

    def iniciar(self, product, **extra):
        return self.api.post(reverse('oneclick-create'), datos(product, **extra), format='json')

    def volver(self, token='tok-1'):
        return self.api.post(reverse('oneclick-finish'), {'TBK_TOKEN': token})


class CompraTests(Base):
    def test_iniciar_devuelve_la_pagina_de_transbank(self):
        r = self.iniciar(self.pack)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data, {'url': 'https://tbk/inscribir', 'token': 'tok-1'})
        o = Order.objects.get()
        self.assertEqual((o.pasarela, o.tbk_token, o.status), (Order.ONECLICK, 'tok-1', 'PENDING'))

    def test_al_volver_inscribe_cobra_y_entrega(self):
        self.iniciar(self.pack)
        r = self.volver()
        o = Order.objects.get()
        self.assertEqual(o.status, 'PAID')
        self.assertIn('/checkout/success', r['Location'])
        t = TarjetaOneclick.objects.get()
        self.assertEqual((t.tbk_user, t.ultimos4, t.email), ('tbk-abc', '6623', 'mama@correo.cl'))
        self.entregar.assert_called_once()
        monto = self.Transaccion.return_value.authorize.call_args.args[3].details[0].amount
        self.assertEqual(monto, 13490)
        self.assertFalse(Suscripcion.objects.exists())   # un pack no es suscripción

    def test_volver_dos_veces_no_cobra_dos_veces(self):
        self.iniciar(self.pack)
        self.volver()
        r = self.volver()
        self.assertEqual(self.Transaccion.return_value.authorize.call_count, 1)
        self.assertIn('/checkout/success', r['Location'])

    def test_tarjeta_no_inscrita_no_cobra(self):
        self.Inscripcion.return_value.finish.return_value = {'response_code': -96}
        self.iniciar(self.pack)
        r = self.volver()
        self.assertEqual(Order.objects.get().status, 'FAILED')
        self.assertIn('reason=card', r['Location'])
        self.Transaccion.return_value.authorize.assert_not_called()

    def test_cobro_rechazado(self):
        self.Transaccion.return_value.authorize.return_value = RECHAZADA
        self.iniciar(self.pack)
        r = self.volver()
        self.assertEqual(Order.objects.get().status, 'FAILED')
        self.assertIn('reason=rejected', r['Location'])
        self.entregar.assert_not_called()

    def test_si_se_corta_la_red_se_pregunta_como_quedo(self):
        """Transbank cobró pero la respuesta no llegó: se consulta y se da por pagada."""
        self.Transaccion.return_value.authorize.side_effect = Exception('timeout')
        self.Transaccion.return_value.status.return_value = AUTORIZADA
        self.iniciar(self.pack)
        self.volver()
        self.assertEqual(Order.objects.get().status, 'PAID')

    def test_si_no_se_sabe_queda_para_revisar_y_no_se_entrega(self):
        self.Transaccion.return_value.authorize.side_effect = Exception('timeout')
        self.Transaccion.return_value.status.side_effect = Exception('sin red')
        self.iniciar(self.pack)
        self.volver()
        self.assertEqual(Order.objects.get().status, 'REVIEW')
        self.entregar.assert_not_called()

    def test_sin_token_es_que_cancelo(self):
        r = self.api.post(reverse('oneclick-finish'), {})
        self.assertIn('reason=aborted', r['Location'])

    def test_username_cabe_en_transbank_y_es_estable(self):
        largo = 'una.direccion.de.correo.muy.muy.larga@dominio-larguisimo.cl'
        self.assertLessEqual(len(oneclick.username_de(largo)), 40)
        self.assertEqual(oneclick.username_de(largo), oneclick.username_de(largo.upper()))


class SuscripcionTests(Base):
    def test_hay_que_aceptar_el_cobro_automatico(self):
        r = self.iniciar(self.mensual)
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Order.objects.exists())

    def test_mercadopago_no_puede_partir_una_suscripcion(self):
        r = self.api.post(reverse('mp-create'), datos(self.mensual), format='json')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Order.objects.exists())

    def test_el_primer_pago_deja_la_suscripcion_andando(self):
        Coupon.objects.create(code='MITAD', discount_type=Coupon.PORCENTAJE, value=50)
        self.iniciar(self.mensual, acepta_cobro_automatico=True, coupon_code='MITAD')
        self.volver()
        s = Suscripcion.objects.get()
        self.assertEqual(Order.objects.get().total_amount, 2495)   # el cupón, solo en el primero
        self.assertEqual(s.monto, 4990)
        self.assertEqual(s.proximo_cobro, timezone.localdate() + relativedelta(months=1))
        self.assertEqual(s.estado, Suscripcion.ACTIVA)

    def test_no_se_contrata_dos_veces(self):
        self.iniciar(self.mensual, acepta_cobro_automatico=True)
        self.volver()
        r = self.iniciar(self.mensual, acepta_cobro_automatico=True)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Suscripcion.objects.count(), 1)


class CobroMensualTests(Base):
    def setUp(self):
        super().setUp()
        self.iniciar(self.mensual, acepta_cobro_automatico=True)
        self.volver()
        self.s = Suscripcion.objects.get()
        self.s.proximo_cobro = timezone.localdate()
        self.s.save()
        self.entregar.reset_mock()
        self.Transaccion.return_value.authorize.reset_mock()

    def cobrar(self, *args):
        call_command('cobrar_suscripciones', *args, stdout=StringIO())
        self.s.refresh_from_db()

    def test_cobra_crea_la_orden_y_entrega(self):
        self.cobrar()
        o = Order.objects.filter(suscripcion=self.s).get()
        self.assertEqual((o.status, int(o.total_amount), o.pasarela), ('PAID', 4990, Order.ONECLICK))
        self.assertEqual(o.items.get().subtotal, 4990)
        self.entregar.assert_called_once_with(o)
        self.assertEqual(self.s.proximo_cobro, timezone.localdate() + relativedelta(months=1))

    def test_simular_no_cobra(self):
        self.cobrar('--simular')
        self.Transaccion.return_value.authorize.assert_not_called()
        self.assertFalse(Order.objects.filter(suscripcion=self.s).exists())

    def test_no_cobra_antes_de_tiempo_ni_canceladas(self):
        self.s.proximo_cobro = timezone.localdate() + timedelta(days=1)
        self.s.save()
        self.cobrar()
        self.s.proximo_cobro = timezone.localdate()
        self.s.estado = Suscripcion.CANCELADA
        self.s.save()
        self.cobrar()
        self.Transaccion.return_value.authorize.assert_not_called()

    def test_rechazos_seguidos_la_suspenden(self):
        self.Transaccion.return_value.authorize.return_value = RECHAZADA
        for _ in range(Suscripcion.INTENTOS_MAXIMOS):
            self.cobrar()
            self.assertGreater(self.s.proximo_cobro, timezone.localdate() - timedelta(days=1))
            self.s.proximo_cobro = timezone.localdate()
            if self.s.estado == Suscripcion.ACTIVA:
                self.s.save()
        self.assertEqual(self.s.estado, Suscripcion.SUSPENDIDA)
        self.entregar.assert_not_called()

    def test_un_cobro_dudoso_suspende_para_no_cobrar_doble(self):
        self.Transaccion.return_value.authorize.side_effect = Exception('timeout')
        self.Transaccion.return_value.status.side_effect = Exception('sin red')
        self.cobrar()
        self.assertEqual(self.s.estado, Suscripcion.SUSPENDIDA)
        self.assertEqual(Order.objects.filter(suscripcion=self.s).get().status, 'REVIEW')


class CancelarTests(Base):
    def setUp(self):
        super().setUp()
        self.iniciar(self.mensual, acepta_cobro_automatico=True)
        self.volver()
        self.s = Suscripcion.objects.get()

    def test_la_duena_la_ve_y_la_cancela(self):
        u = User.objects.create_user(username='mama@correo.cl', email='mama@correo.cl')
        self.api.force_authenticate(u)
        r = self.api.get(reverse('mis-suscripciones'))
        self.assertEqual(r.data[0]['tarjeta'], 'Visa terminada en 6623')
        r = self.api.post(reverse('suscripcion-cancelar', args=[self.s.pk]))
        self.assertEqual(r.data['estado'], Suscripcion.CANCELADA)
        self.s.refresh_from_db()
        self.assertIsNotNone(self.s.cancelada_en)

    def test_otra_persona_no_puede(self):
        u = User.objects.create_user(username='otra@correo.cl', email='otra@correo.cl')
        self.api.force_authenticate(u)
        self.assertEqual(self.api.get(reverse('mis-suscripciones')).data, [])
        r = self.api.post(reverse('suscripcion-cancelar', args=[self.s.pk]))
        self.assertEqual(r.status_code, 404)
        self.s.refresh_from_db()
        self.assertEqual(self.s.estado, Suscripcion.ACTIVA)

    def test_el_panel_la_lista_y_la_cancela(self):
        admin = User.objects.create_user(username='admin@ib.cl', email='admin@ib.cl', is_staff=True)
        self.client.force_login(admin)
        r = self.client.get(reverse('panel:suscripciones'))
        self.assertContains(r, 'mama@correo.cl')
        self.client.post(reverse('panel:suscripcion_cancelar', args=[self.s.pk]))
        self.s.refresh_from_db()
        self.assertEqual(self.s.estado, Suscripcion.CANCELADA)


class ConfiguracionTests(TestCase):
    def test_en_produccion_sin_tienda_hija_no_cobra_a_la_de_pruebas(self):
        from django.core.exceptions import ImproperlyConfigured
        with patch.dict('os.environ', {'TBK_ENVIRONMENT': 'PRODUCCION', 'TBK_ONECLICK_TIENDA': ''}):
            with self.assertRaises(ImproperlyConfigured):
                oneclick.codigo_tienda()
        with patch.dict('os.environ', {'TBK_ENVIRONMENT': 'PRODUCCION', 'TBK_ONECLICK_TIENDA': '597000000001'}):
            self.assertEqual(oneclick.codigo_tienda(), '597000000001')


class FormularioProductoTests(TestCase):
    def test_una_suscripcion_tiene_que_ser_digital_y_tener_meses(self):
        from panel.forms import ProductForm
        f = ProductForm(data={
            'name': 'Kit', 'description': 'x', 'price': 1000,
            'es_suscripcion': True, 'is_digital': False, 'access_months': '',
            'weight_kg': 1, 'width_cm': 1, 'height_cm': 1, 'length_cm': 1,
        })
        self.assertFalse(f.is_valid())
        self.assertIn('es_suscripcion', f.errors)
        self.assertIn('access_months', f.errors)
