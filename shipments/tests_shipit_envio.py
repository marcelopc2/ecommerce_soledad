"""El pedido pagado con despacho va a "Ventas" de Shipit, nunca a "Envíos".

Historia: el 30-09-2026 se usó el endpoint de ENVÍOS (api.shipit.cl/v/shipments)
y Shipit agendó retiros del courier para paquetes de prueba, aunque iban con
`sandbox: true`; la clienta los tuvo que anular. Lo correcto, y lo que hacía el
WordPress, es crear una VENTA (orders.shipit.cl/v/orders): queda en el módulo
Ventas y la tienda decide cuándo convertirla en envío.
"""
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from catalog.models import Product
from payments.models import Order, OrderItem
from shipments.models import AjustesEnvios, Shipment
from shipments.services import enviar_pedido_a_shipit, payload_venta

User = get_user_model()
RESPUESTA_OK = {'id': 55501, 'reference': 'abc', 'state': 1}


def respuesta(status=200, data=RESPUESTA_OK):
    r = MagicMock(status_code=status, text=str(data))
    r.json.return_value = data
    return r


@patch.dict('os.environ', {'SHIPIT_EMAIL': 'tienda@ib.cl', 'SHIPIT_TOKEN': 'token-real'})
class VentaShipitTests(TestCase):
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

    def test_el_formato_es_el_de_ventas(self):
        o = payload_venta(self.envio)['order']
        self.assertLessEqual(len(o['reference']), 15)
        self.assertEqual(o['plaftform'], 2)            # así, con el error de Shipit
        self.assertEqual(o['courier'], {'client': 'spread', 'selected': True, 'payble': False})
        self.assertEqual(o['seller']['status'], 'paid')
        self.assertEqual(o['destiny']['commune_id'], 308)
        self.assertEqual(o['prices']['total'], 5000)
        self.assertEqual(o['insurance']['ticket_amount'], 79490)
        self.assertNotIn('sandbox', o)

    @patch('shipments.services.requests.post', return_value=respuesta())
    def test_va_a_ventas_y_nunca_a_envios(self, post):
        enviar_pedido_a_shipit(self.order)
        url = post.call_args.args[0]
        self.assertEqual(url, 'https://orders.shipit.cl/v/orders')
        self.assertNotIn('shipments', url)
        self.assertEqual(post.call_args.kwargs['headers']['Accept'], 'application/vnd.orders.v1')
        self.envio.refresh_from_db()
        self.assertEqual((self.envio.status, self.envio.shipit_reference), ('CREATED', '55501'))

    def test_ningun_codigo_llama_al_endpoint_de_envios(self):
        import inspect
        from shipments import admin, services
        from panel import views
        import re
        # Solo el código, no los comentarios que explican por qué no se usa.
        for modulo in (services, admin, views):
            codigo = '\n'.join(linea.split('#')[0] for linea in inspect.getsource(modulo).splitlines())
            self.assertIsNone(re.search(r'/v/shipments[\'"]', codigo), modulo.__name__)

    @patch('shipments.services.requests.post', return_value=respuesta())
    def test_no_la_manda_dos_veces(self, post):
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
    def test_si_shipit_la_rechaza_queda_el_error_a_la_vista(self, post):
        enviar_pedido_a_shipit(self.order)
        self.envio.refresh_from_db()
        self.assertEqual(self.envio.status, 'ERROR')
        self.assertIn('comuna inválida', self.envio.error_shipit)

    def test_el_envio_automatico_nace_apagado(self):
        self.assertFalse(AjustesEnvios.obtener().enviar_a_shipit_al_pagar)

    @patch('shipments.services.requests.post', return_value=respuesta())
    @patch('payments.views._send_order_confirmation')
    @patch('payments.views.grant_access_for_order')
    @patch('payments.views.issue_invoice_for_order')
    def test_apagado_no_se_manda_al_pagar(self, _b, _a, _c, post):
        from payments.views import _entregar_compra
        _entregar_compra(self.order)
        post.assert_not_called()

    @patch('shipments.services.requests.post', return_value=respuesta())
    @patch('payments.views._send_order_confirmation')
    @patch('payments.views.grant_access_for_order')
    @patch('payments.views.issue_invoice_for_order')
    def test_prendido_se_manda_al_pagar(self, _b, _a, _c, post):
        from payments.views import _entregar_compra
        AjustesEnvios.objects.update_or_create(pk=1, defaults={'enviar_a_shipit_al_pagar': True})
        _entregar_compra(self.order)
        post.assert_called_once()

    @patch('shipments.services.requests.post', return_value=respuesta())
    def test_el_panel_la_manda_con_su_boton(self, post):
        admin = User.objects.create_user(username='admin@ib.cl', email='admin@ib.cl', is_staff=True)
        self.client.force_login(admin)
        self.assertContains(self.client.get(reverse('panel:order_detail', args=[self.order.pk])),
                            'Mandar a Ventas de Shipit')
        self.client.post(reverse('panel:order_enviar_shipit', args=[self.order.pk]))
        self.envio.refresh_from_db()
        self.assertEqual(self.envio.status, 'CREATED')
