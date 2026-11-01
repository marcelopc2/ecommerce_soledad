"""Suscripciones con Mercado Pago (preapproval).

Mercado Pago va simulado. Lo que importa es la plata: cada cobro que Mercado
Pago hace se entrega UNA vez (boleta, acceso, correo) aunque avise por tres
caminos, nada se da por pagado sin que la API lo diga, y nuestros cobros
automáticos (Oneclick) nunca tocan una suscripción de Mercado Pago.
"""
from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from catalog.models import Product
from payments.models import AjustesCobros, Order, Suscripcion

PRE_ID = 'pre-123'


def datos(product, **extra):
    base = {
        'product_ids': [product.id], 'email': 'mama@correo.cl',
        'customer_name': 'Ana Pérez', 'student_name': 'Beni', 'phone': '+56912345678',
        'acepta_cobro_automatico': True,
    }
    base.update(extra)
    return base


class SdkFalso:
    """Lo mínimo del SDK de Mercado Pago que usa payments.mp_suscripciones."""

    def __init__(self):
        self.preapprovals = {}
        self.cobros = {}          # id de authorized_payment -> dict
        self.creado = None
        self.error_crear = None
        self.estados_pedidos = []
        pre = MagicMock()
        pre.create.side_effect = self._crear
        pre.get.side_effect = lambda i: {'status': 200, 'response': self.preapprovals[i]}
        pre.update.side_effect = self._actualizar
        self._pre = pre
        inv = MagicMock()
        inv.get.side_effect = lambda i: {'status': 200, 'response': self.cobros[i]}
        inv.search.side_effect = lambda filters=None: {'status': 200, 'response': {'results': [
            c for c in self.cobros.values() if c['preapproval_id'] == filters['preapproval_id']]}}
        self._inv = inv

    def preapproval(self):
        return self._pre

    def invoice(self):
        return self._inv

    def _crear(self, cuerpo):
        if self.error_crear:
            return {'status': 400, 'response': {'message': self.error_crear}}
        self.creado = cuerpo
        self.preapprovals[PRE_ID] = {
            'id': PRE_ID, 'status': 'pending', 'external_reference': cuerpo['external_reference'],
            'next_payment_date': None,
        }
        return {'status': 201, 'response': {
            'id': PRE_ID, 'init_point': 'https://www.mercadopago.cl/subscriptions/checkout?preapproval_id=pre-123'}}

    def _actualizar(self, i, cuerpo):
        self.estados_pedidos.append(cuerpo['status'])
        self.preapprovals[i]['status'] = cuerpo['status']
        return {'status': 200, 'response': self.preapprovals[i]}


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.api = APIClient()
        self.mensual = Product.objects.create(
            name='Membresía', slug='membresia', price=4990, is_active=True,
            is_digital=True, es_suscripcion=True, access_months=1,
        )
        self.sdk = SdkFalso()
        self.pagos = {}
        for destino in ('payments.mp_suscripciones.get_mercadopago_sdk',):
            p = patch(destino, return_value=self.sdk)
            p.start()
            self.addCleanup(p.stop)
        for destino in ('payments.mp_suscripciones.get_mercadopago_payment',
                        'payments.views.get_mercadopago_payment'):
            p = patch(destino, side_effect=lambda i: self.pagos[str(i)])
            p.start()
            self.addCleanup(p.stop)
        p = patch('payments.views._entregar_compra')
        self.entregar = p.start()
        self.addCleanup(p.stop)

    def suscribir(self, **extra):
        return self.api.post(reverse('mp-suscribir'), datos(self.mensual, **extra), format='json')

    def mp_cobra(self, pago_id, estado='approved', monto=4990, proxima='2026-12-01T10:00:00.000-03:00'):
        """Mercado Pago hace un cobro de la suscripción (y lo deja consultable)."""
        self.sdk.preapprovals[PRE_ID].update(status='authorized', next_payment_date=proxima)
        self.pagos[str(pago_id)] = {'id': pago_id, 'status': estado, 'transaction_amount': monto,
                                    'external_reference': self.sdk.creado['external_reference']}
        self.sdk.cobros[f'ap-{pago_id}'] = {'id': f'ap-{pago_id}', 'preapproval_id': PRE_ID,
                                            'payment': {'id': pago_id, 'status': estado}}

    def webhook(self, tipo, recurso):
        return self.api.post(f"{reverse('mp-webhook')}?type={tipo}", {'type': tipo, 'data': {'id': recurso}},
                             format='json')


class ContratarTests(Base):
    def test_crea_la_suscripcion_en_mercado_pago_y_devuelve_su_pagina(self):
        r = self.suscribir()
        self.assertEqual(r.status_code, 200)
        self.assertIn('mercadopago.cl/subscriptions', r.data['url'])
        o = Order.objects.get()
        self.assertEqual((o.status, o.pasarela, o.mp_preapproval_id), ('PENDING', Order.MERCADOPAGO, PRE_ID))
        c = self.sdk.creado
        self.assertEqual(c['external_reference'], str(o.order_id))
        self.assertEqual(c['payer_email'], 'mama@correo.cl')
        self.assertEqual(c['auto_recurring'], {'frequency': 1, 'frequency_type': 'months',
                                               'transaction_amount': 4990, 'currency_id': 'CLP'})
        self.assertIn(str(o.order_id), c['back_url'])
        # Todavía no hay suscripción: nace con el primer cobro aprobado.
        self.assertFalse(Suscripcion.objects.exists())

    def test_sin_aceptar_el_cobro_automatico_no_se_crea(self):
        r = self.suscribir(acepta_cobro_automatico=False)
        self.assertEqual(r.status_code, 400)
        self.assertIsNone(self.sdk.creado)

    def test_con_cupon_no_se_puede(self):
        r = self.suscribir(coupon_code='PROMO')
        self.assertEqual(r.status_code, 400)
        self.assertIsNone(self.sdk.creado)

    def test_un_producto_que_no_es_suscripcion_no_entra_por_aca(self):
        pack = Product.objects.create(name='Pack', slug='pack', price=13490, is_active=True, is_digital=True)
        r = self.api.post(reverse('mp-suscribir'), datos(pack), format='json')
        self.assertEqual(r.status_code, 400)

    def test_correo_sin_cuenta_de_mercado_pago_pide_el_de_la_cuenta(self):
        self.sdk.error_crear = 'Both payer and collector must be real or test users'
        r = self.suscribir()
        self.assertEqual(r.status_code, 400)
        self.assertTrue(r.data['pedir_correo_mp'])
        self.assertEqual(Order.objects.get().status, 'FAILED')

    def test_se_puede_usar_otro_correo_para_mercado_pago(self):
        self.suscribir(mp_email='Cuenta@MP.cl')
        self.assertEqual(self.sdk.creado['payer_email'], 'cuenta@mp.cl')
        # La compra y el acceso siguen con el correo de la tienda.
        self.assertEqual(Order.objects.get().customer_email, 'mama@correo.cl')

    def test_si_ya_tiene_la_suscripcion_activa_no_crea_otra(self):
        self.suscribir()
        self.mp_cobra(1001)
        self.webhook('subscription_authorized_payment', 'ap-1001')
        self.sdk.creado = None
        r = self.suscribir()
        self.assertEqual(r.status_code, 400)
        self.assertIsNone(self.sdk.creado)


class CobrosTests(Base):
    def setUp(self):
        super().setUp()
        self.suscribir()
        self.inicial = Order.objects.get()

    def test_primer_cobro_paga_la_orden_y_crea_la_suscripcion(self):
        self.mp_cobra(1001)
        self.webhook('subscription_authorized_payment', 'ap-1001')
        self.inicial.refresh_from_db()
        self.assertEqual((self.inicial.status, self.inicial.mp_payment_id), ('PAID', '1001'))
        s = Suscripcion.objects.get()
        self.assertEqual((s.pasarela, s.mp_preapproval_id, s.monto, s.estado, s.tarjeta),
                         (Suscripcion.MERCADOPAGO, PRE_ID, 4990, Suscripcion.ACTIVA, None))
        self.assertEqual(s.orden_inicial, self.inicial)
        self.assertEqual(str(s.proximo_cobro), '2026-12-01')
        self.entregar.assert_called_once_with(self.inicial)

    def test_el_mismo_cobro_por_tres_caminos_se_entrega_una_vez(self):
        self.mp_cobra(1001)
        self.webhook('subscription_authorized_payment', 'ap-1001')
        self.webhook('payment', 1001)
        self.api.get(f"{reverse('mp-suscripcion-vuelta')}?orden={self.inicial.order_id}")
        call_command('sincronizar_suscripciones_mp', stdout=StringIO())
        self.assertEqual(self.entregar.call_count, 1)
        self.assertEqual(Order.objects.filter(status='PAID').count(), 1)

    def test_el_tope_normal_de_pagos_tambien_registra_el_primer_cobro(self):
        # Si el aviso llega solo por el tópico "payment" (con la referencia de
        # la orden inicial), igual se registra como cobro de la suscripción.
        self.mp_cobra(1001)
        self.webhook('payment', 1001)
        self.assertEqual(Suscripcion.objects.get().mp_preapproval_id, PRE_ID)
        self.entregar.assert_called_once()

    def test_cada_cobro_siguiente_es_una_orden_nueva(self):
        self.mp_cobra(1001)
        self.webhook('subscription_authorized_payment', 'ap-1001')
        self.mp_cobra(1002, proxima='2027-01-01T10:00:00.000-03:00')
        self.webhook('subscription_authorized_payment', 'ap-1002')
        self.webhook('payment', 1002)  # el mismo cobro otra vez
        s = Suscripcion.objects.get()
        renov = Order.objects.get(suscripcion=s)
        self.assertEqual((renov.status, renov.pasarela, renov.mp_payment_id, int(renov.total_amount)),
                         ('PAID', Order.MERCADOPAGO, '1002', 4990))
        self.assertEqual(renov.student_name, 'Beni')
        self.assertEqual(str(s.proximo_cobro), '2027-01-01')
        self.assertEqual(self.entregar.call_count, 2)

    def test_cobro_rechazado_no_entrega_nada(self):
        self.mp_cobra(1001, estado='rejected')
        self.webhook('subscription_authorized_payment', 'ap-1001')
        self.inicial.refresh_from_db()
        self.assertEqual(self.inicial.status, 'PENDING')
        self.assertFalse(Suscripcion.objects.exists())
        self.entregar.assert_not_called()

    def test_monto_distinto_no_se_da_por_pagado(self):
        self.mp_cobra(1001, monto=10)
        self.webhook('subscription_authorized_payment', 'ap-1001')
        self.inicial.refresh_from_db()
        self.assertEqual(self.inicial.status, 'PENDING')
        self.entregar.assert_not_called()

    def test_un_cobro_de_otra_suscripcion_se_ignora(self):
        self.sdk.preapprovals['ajena'] = {'id': 'ajena', 'status': 'authorized'}
        self.pagos['9'] = {'id': 9, 'status': 'approved', 'transaction_amount': 4990}
        self.sdk.cobros['ap-9'] = {'id': 'ap-9', 'preapproval_id': 'ajena', 'payment': {'id': 9}}
        self.webhook('subscription_authorized_payment', 'ap-9')
        self.entregar.assert_not_called()

    def test_la_vuelta_con_el_cobro_aprobado_va_al_exito(self):
        self.mp_cobra(1001)
        r = self.api.get(f"{reverse('mp-suscripcion-vuelta')}?orden={self.inicial.order_id}")
        self.assertIn(f'/checkout/success?order={self.inicial.order_id}', r.url)
        self.assertNotIn('confirmando', r.url)
        self.entregar.assert_called_once()

    def test_la_vuelta_autorizada_sin_cobro_todavia_avisa_que_se_confirma(self):
        self.sdk.preapprovals[PRE_ID]['status'] = 'authorized'
        r = self.api.get(f"{reverse('mp-suscripcion-vuelta')}?orden={self.inicial.order_id}")
        self.assertIn('confirmando=1', r.url)
        self.entregar.assert_not_called()

    def test_la_vuelta_sin_autorizar_va_al_fallo(self):
        r = self.api.get(f"{reverse('mp-suscripcion-vuelta')}?orden={self.inicial.order_id}")
        self.assertIn('/checkout/failed', r.url)

    def test_la_vuelta_con_orden_inventada_va_al_fallo(self):
        r = self.api.get(f"{reverse('mp-suscripcion-vuelta')}?orden=no-es-un-uuid")
        self.assertIn('/checkout/failed', r.url)


class EstadoTests(Base):
    def setUp(self):
        super().setUp()
        self.suscribir()
        self.mp_cobra(1001)
        self.webhook('subscription_authorized_payment', 'ap-1001')
        self.s = Suscripcion.objects.get()

    def test_si_la_cancela_en_la_app_de_mercado_pago_queda_cancelada(self):
        self.sdk.preapprovals[PRE_ID]['status'] = 'cancelled'
        self.webhook('subscription_preapproval', PRE_ID)
        self.s.refresh_from_db()
        self.assertEqual(self.s.estado, Suscripcion.CANCELADA)
        self.assertIsNotNone(self.s.cancelada_en)

    def test_cancelar_desde_el_perfil_la_cancela_en_mercado_pago(self):
        from django.contrib.auth import get_user_model
        u = get_user_model().objects.create_user('mama@correo.cl', email='mama@correo.cl', password='x')
        self.api.force_authenticate(u)
        r = self.api.post(reverse('suscripcion-cancelar', args=[self.s.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.sdk.estados_pedidos, ['cancelled'])
        self.s.refresh_from_db()
        self.assertEqual(self.s.estado, Suscripcion.CANCELADA)
        self.assertEqual(r.data['tarjeta'], 'Mercado Pago')

    def test_si_mercado_pago_no_responde_no_se_marca_cancelada(self):
        from payments.views import cancelar_suscripcion
        self.sdk.preapproval().update.side_effect = None
        self.sdk.preapproval().update.return_value = {'status': 500, 'response': {'message': 'caído'}}
        with self.assertRaises(Exception):
            cancelar_suscripcion(self.s, por='prueba')
        self.s.refresh_from_db()
        self.assertEqual(self.s.estado, Suscripcion.ACTIVA)

    @override_settings(COBROS_AUTOMATICOS=True)
    def test_nuestros_cobros_automaticos_no_la_tocan(self):
        AjustesCobros.objects.update_or_create(pk=1, defaults={'cobros_automaticos': True, 'cobrar_wordpress': True})
        Suscripcion.objects.filter(pk=self.s.pk).update(proximo_cobro=timezone.localdate())
        with patch('payments.oneclick.cobrar_suscripcion') as cobrar:
            call_command('cobrar_suscripciones', stdout=StringIO())
        cobrar.assert_not_called()

    def test_el_panel_pausa_y_reanuda_tambien_en_mercado_pago(self):
        from django.contrib.auth import get_user_model
        staff = get_user_model().objects.create_user('staff', email='s@ib.cl', password='x',
                                                     is_staff=True, is_superuser=True)
        self.client.force_login(staff)
        self.client.post(reverse('panel:suscripcion_pausar', args=[self.s.pk]))
        self.client.post(reverse('panel:suscripcion_reanudar', args=[self.s.pk]))
        self.assertEqual(self.sdk.estados_pedidos, ['paused', 'authorized'])
        self.s.refresh_from_db()
        self.assertEqual(self.s.estado, Suscripcion.ACTIVA)

    def test_el_panel_muestra_que_es_de_mercado_pago(self):
        from django.contrib.auth import get_user_model
        staff = get_user_model().objects.create_user('staff', email='s@ib.cl', password='x',
                                                     is_staff=True, is_superuser=True)
        self.client.force_login(staff)
        r = self.client.get(reverse('panel:suscripcion_detalle', args=[self.s.pk]))
        self.assertContains(r, 'Mercado Pago')
        self.assertNotContains(r, 'name="proximo_cobro"')
        r = self.client.get(reverse('panel:suscripciones'))
        self.assertContains(r, 'Mercado Pago')
