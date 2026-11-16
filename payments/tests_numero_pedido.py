"""N.º de pedido correlativo como en WooCommerce, siguiendo al WordPress (#63704)."""
from django.test import TestCase

from payments.models import ContadorPedidos, Order, asignar_numero
from shipments.models import Shipment
from shipments.services import payload_venta


class NumeroPedidoTests(TestCase):
    def orden(self, **kw):
        return Order.objects.create(customer_email='f@x.cl', customer_name='F', total_amount=8900,
                                    status='PAID', **kw)

    def test_sigue_al_wordpress_y_es_correlativo(self):
        ContadorPedidos.objects.all().delete()
        a, b = self.orden(), self.orden()
        self.assertEqual(asignar_numero(a), 63705)
        self.assertEqual(asignar_numero(b), 63706)
        self.assertEqual(Order.objects.get(pk=b.pk).numero, 63706)

    def test_no_se_renumera(self):
        a = self.orden()
        n = asignar_numero(a)
        self.assertEqual(asignar_numero(Order.objects.get(pk=a.pk)), n)
        self.assertEqual(ContadorPedidos.objects.get().ultimo, n)

    def test_sin_pagar_muestra_el_codigo_corto(self):
        o = Order.objects.create(customer_email='f@x.cl', total_amount=1)
        self.assertEqual(o.numero_pedido, str(o.order_id)[:8])

    def test_shipit_recibe_el_numero(self):
        o = self.orden()
        asignar_numero(o)
        s = Shipment.objects.create(order=o, recipient_name='F', recipient_phone='+56912345678', region='II',
                                    commune='ANTOFAGASTA', commune_id=1, address_street='A', address_number='1',
                                    courier='Chilexpress', courier_code='chilexpress')
        self.assertEqual(payload_venta(s)['order']['reference'], f'#{o.numero}')
