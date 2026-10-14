"""Webpay Plus: los cuatro regresos que exige la validación de Transbank.

Del manual de validación (octubre 2026):
- solo token_ws: pago terminado -> se confirma.
- solo TBK_TOKEN: el cliente anuló -> NO se confirma.
- token_ws y TBK_TOKEN: error en el formulario -> NO se confirma.
- sin token, solo TBK_ORDEN_COMPRA y TBK_ID_SESION: tiempo agotado -> NO se confirma.
"""
from unittest.mock import patch

from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from catalog.models import Product
from payments.models import Order

AUTORIZADA = {'status': 'AUTHORIZED', 'response_code': 0}
RECHAZADA = {'status': 'FAILED', 'response_code': -1}


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.api = APIClient()
        self.kit = Product.objects.create(name='Kit', slug='kit', price=15990, is_active=True, is_digital=True)
        self.mensual = Product.objects.create(name='Membresía', slug='m', price=4990, is_active=True,
                                              is_digital=True, es_suscripcion=True, access_months=1)
        p = patch('payments.views.create_webpay_transaction',
                  return_value={'token': 'tok-ws', 'url': 'https://webpay3g.transbank.cl/x'})
        self.crear = p.start()
        self.addCleanup(p.stop)
        p = patch('payments.views.commit_webpay_transaction', return_value=AUTORIZADA)
        self.commit = p.start()
        self.addCleanup(p.stop)
        p = patch('payments.views._entregar_compra')
        self.entregar = p.start()
        self.addCleanup(p.stop)

    def pagar(self, producto):
        return self.api.post(reverse('webpay-create'), {
            'product_ids': [producto.id], 'email': 'mama@correo.cl', 'customer_name': 'Ana',
            'student_name': 'Beni', 'phone': '+56912345678'}, format='json')

    def volver(self, **datos):
        return self.client.post(reverse('webpay-commit'), datos)


class RegresosTests(Base):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.pagar(self.kit).status_code, 200)
        self.order = Order.objects.get()

    def test_pago_terminado_se_confirma_y_entrega(self):
        r = self.volver(token_ws='tok-ws')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'PAID')
        self.assertIn('/checkout/success', r['Location'])
        self.entregar.assert_called_once()

    def test_volver_dos_veces_no_confirma_dos_veces(self):
        self.volver(token_ws='tok-ws')
        r = self.volver(token_ws='tok-ws')
        self.assertEqual(self.commit.call_count, 1)
        self.assertIn('/checkout/success', r['Location'])

    def test_rechazado(self):
        self.commit.return_value = RECHAZADA
        r = self.volver(token_ws='tok-ws')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'FAILED')
        self.assertIn('reason=rejected', r['Location'])

    def test_anulado_por_el_cliente_no_se_confirma(self):
        r = self.volver(TBK_TOKEN='tok-ws', TBK_ORDEN_COMPRA='x', TBK_ID_SESION=str(self.order.pk))
        self.commit.assert_not_called()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'FAILED')
        self.assertIn('reason=aborted', r['Location'])

    def test_error_en_el_formulario_no_se_confirma(self):
        r = self.volver(token_ws='tok-ws', TBK_TOKEN='tok-ws', TBK_ORDEN_COMPRA='x', TBK_ID_SESION='1')
        self.commit.assert_not_called()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'FAILED')
        self.assertIn('reason=error', r['Location'])

    def test_tiempo_agotado_ubica_la_orden_por_la_sesion(self):
        r = self.volver(TBK_ORDEN_COMPRA=str(self.order.order_id)[:26], TBK_ID_SESION=str(self.order.pk))
        self.commit.assert_not_called()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'FAILED')
        self.assertIn('reason=aborted', r['Location'])

    def test_tiempo_agotado_con_una_orden_de_compra_ajena_no_toca_nada(self):
        self.volver(TBK_ORDEN_COMPRA='otra-orden', TBK_ID_SESION=str(self.order.pk))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'PENDING')


class ReglasTests(Base):
    def test_una_suscripcion_no_va_por_webpay_plus(self):
        r = self.pagar(self.mensual)
        self.assertEqual(r.status_code, 400)
        self.crear.assert_not_called()


class ConfiguracionTests(TestCase):
    def test_en_produccion_usa_sus_propias_credenciales_y_no_las_de_oneclick(self):
        from payments.services import get_webpay_transaction
        env = {'TBK_ENVIRONMENT': 'PRODUCCION', 'TBK_API_KEY_ID': 'oneclick', 'TBK_API_KEY_SECRET': 'x',
               'TBK_WEBPAY_CODIGO': '', 'TBK_WEBPAY_LLAVE': ''}
        with patch.dict('os.environ', env):
            with self.assertRaises(ImproperlyConfigured):
                get_webpay_transaction()
        env.update(TBK_WEBPAY_CODIGO='597000000000', TBK_WEBPAY_LLAVE='llave')
        with patch.dict('os.environ', env):
            self.assertEqual(get_webpay_transaction().options.commerce_code, '597000000000')
