"""El pedido pagado con despacho llega solo a Shipit.

Pasó en la primera compra de prueba real (30-09-2026): Shipit cotizó bien, se
pagó, y el envío nunca llegó a Shipit. Crearlo solo existía en el admin técnico
de Django y además con un formato que Shipit no acepta (sin destiny/sizes/
courier, referencia de 26 caracteres cuando el máximo es 15).
"""
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from catalog.models import Product
from payments.models import Order, OrderItem
from shipments.models import AjustesEnvios, Shipment
from shipments.services import enviar_pedido_a_shipit, payload_shipit

User = get_user_model()
RESPUESTA_OK = {'id': 99887, 'tracking_number': 'SP123', 'ticket_url': 'https://shipit/etiqueta.pdf'}


def respuesta(status=200, data=RESPUESTA_OK):
    r = MagicMock(status_code=status, text=str(data))
    r.json.return_value = data
    return r


@patch.dict('os.environ', {'SHIPIT_EMAIL': 'tienda@ib.cl', 'SHIPIT_TOKEN': 'token-real'})
class EnvioShipitTests(TestCase):
    def setUp(self):
        kit = Product.objects.create(name='Kit Inicial', slug='kit', price=79490, is_active=True)
        self.order = Order.objects.create(customer_email='mama@correo.cl', total_amount=84490, status='PAID')
        self.order.products.set([kit])
        OrderItem.objects.create(order=self.order, product=kit, name='Kit Inicial', unit_price=79490)
        self.envio = Shipment.objects.create(
            order=self.order, recipient_name='Ana Pérez', recipient_phone='+56912345678',
            region='RM', commune='LAS CONDES', commune_id=308, address_street='Av. Apoquindo',
            address_number='1234', address_detail='Depto 5', courier='Spread', courier_code='spread',
            shipping_cost=5000,
        )

    def test_el_formato_es_el_de_la_api_v4(self):
        p = payload_shipit(self.envio)['shipment']
        self.assertLessEqual(len(p['reference']), 15)
        self.assertEqual(p['courier'], {'client': 'spread', 'selected': True, 'payable': False})
        self.assertEqual(p['destiny']['commune_id'], 308)
        self.assertEqual(p['destiny']['kind'], 'home_delivery')
        self.assertEqual(p['destiny']['email'], 'mama@correo.cl')
        self.assertEqual(p['insurance']['ticket_amount'], 79490)   # sin el despacho
        self.assertFalse(p['sandbox'])
        self.assertTrue(payload_shipit(self.envio, prueba=True)['shipment']['sandbox'])

    def test_un_envio_viejo_sin_codigo_usa_el_nombre_en_minuscula(self):
        self.envio.courier_code = ''
        self.assertEqual(payload_shipit(self.envio)['shipment']['courier']['client'], 'spread')

    @patch('shipments.services.requests.post', return_value=respuesta())
    def test_crea_el_envio_con_la_version_4_y_guarda_lo_que_devuelve(self, post):
        enviar_pedido_a_shipit(self.order)
        self.assertEqual(post.call_args.kwargs['headers']['Accept'], 'application/vnd.shipit.v4')
        self.envio.refresh_from_db()
        self.assertEqual((self.envio.status, self.envio.shipit_reference, self.envio.tracking_number),
                         ('CREATED', '99887', 'SP123'))

    @patch('shipments.services.requests.post', return_value=respuesta())
    def test_no_lo_crea_dos_veces(self, post):
        enviar_pedido_a_shipit(self.order)
        enviar_pedido_a_shipit(self.order)
        self.assertEqual(post.call_count, 1)

    @patch('shipments.services.requests.post', return_value=respuesta())
    def test_un_pedido_sin_pagar_no_se_manda(self, post):
        self.order.status = 'PENDING'
        self.order.save()
        enviar_pedido_a_shipit(self.order)
        post.assert_not_called()

    @patch('shipments.services.requests.post', return_value=respuesta(422, {'error': 'comuna inválida'}))
    def test_si_shipit_lo_rechaza_queda_el_error_a_la_vista(self, post):
        enviar_pedido_a_shipit(self.order)
        self.envio.refresh_from_db()
        self.assertEqual(self.envio.status, 'ERROR')
        self.assertIn('comuna inválida', self.envio.error_shipit)

    @patch('shipments.services.requests.post', return_value=respuesta())
    @patch('payments.views._send_order_confirmation')
    @patch('payments.views.grant_access_for_order')
    @patch('payments.views.issue_invoice_for_order')
    def test_al_pagarse_se_manda_solo(self, _boleta, _acceso, _correo, post):
        from payments.views import _entregar_compra
        _entregar_compra(self.order)
        post.assert_called_once()

    @patch('shipments.services.requests.post', return_value=respuesta())
    @patch('payments.views._send_order_confirmation')
    @patch('payments.views.grant_access_for_order')
    @patch('payments.views.issue_invoice_for_order')
    def test_con_el_interruptor_apagado_no(self, _boleta, _acceso, _correo, post):
        from payments.views import _entregar_compra
        AjustesEnvios.objects.update_or_create(pk=1, defaults={'enviar_a_shipit_al_pagar': False})
        _entregar_compra(self.order)
        post.assert_not_called()

    @patch('shipments.services.requests.post', return_value=respuesta())
    def test_el_panel_lo_manda_y_el_interruptor_se_cambia(self, post):
        admin = User.objects.create_user(username='admin@ib.cl', email='admin@ib.cl', is_staff=True)
        self.client.force_login(admin)
        self.assertContains(self.client.get(reverse('panel:order_detail', args=[self.order.pk])), 'Enviar a Shipit')
        self.client.post(reverse('panel:order_enviar_shipit', args=[self.order.pk]))
        self.envio.refresh_from_db()
        self.assertEqual(self.envio.status, 'CREATED')
        self.assertContains(self.client.get(reverse('panel:orders')), 'Mandar los despachos a Shipit')
        self.client.post(reverse('panel:envios_ajustes'), {'valor': '0'})
        self.assertFalse(AjustesEnvios.obtener().enviar_a_shipit_al_pagar)
