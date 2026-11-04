"""El correo que le llega a la tienda por cada compra y cada renovación.

Lo pidió la clienta: con WooCommerce les llegaba un "Nuevo pedido" por cada
venta, y es como se enteran sin tener el panel abierto.
"""
from datetime import date
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings

from catalog.models import Product
from payments.models import Order, OrderItem, Suscripcion, TarjetaOneclick
from payments.views import _entregar_compra


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   CONTACT_EMAIL='tienda@ib.cl', ENVIAR_CORREOS=True)
class AvisoATiendaTests(TestCase):
    def setUp(self):
        self.kit = Product.objects.create(name='Kit Inicial', slug='kit', price=58900, is_active=True)
        for destino in ('payments.views.issue_invoice_for_order', 'payments.views.grant_access_for_order'):
            p = patch(destino, return_value=None)
            p.start()
            self.addCleanup(p.stop)
        p = patch('comunicaciones.freno.correos_a_clientes', return_value=True)
        p.start()
        self.addCleanup(p.stop)

    def orden(self, **extra):
        datos = dict(customer_email='cliente@correo.cl', customer_name='Cristian Álvarez',
                     student_name='Tomás', customer_phone='+56911112222', total_amount=58900,
                     status='PAID', pasarela=Order.MERCADOPAGO)
        datos.update(extra)
        o = Order.objects.create(**datos)
        o.products.set([self.kit])
        OrderItem.objects.create(order=o, product=self.kit, name='Kit Inicial', unit_price=58900)
        return o

    def a_la_tienda(self):
        return [m for m in mail.outbox if m.to == ['tienda@ib.cl']]

    def test_compra_avisa_a_la_tienda_con_el_detalle(self):
        _entregar_compra(self.orden(delivery_method=Order.RETIRO))
        [m] = self.a_la_tienda()
        self.assertIn('Nueva compra', m.subject)
        self.assertIn('Cristian Álvarez', m.subject)
        self.assertIn('$58.900', m.subject)
        self.assertEqual(m.reply_to, ['cliente@correo.cl'])
        for dato in ('Kit Inicial', 'Retiro en tienda', 'MercadoPago', 'Tomás', '+56911112222'):
            self.assertIn(dato, m.body)

    def test_renovacion_avisa_como_renovacion(self):
        tarjeta = TarjetaOneclick.objects.create(email='cliente@correo.cl', username='u', tbk_user='t',
                                                 tipo='Visa', ultimos4='1234')
        s = Suscripcion.objects.create(email='cliente@correo.cl', producto=self.kit, tarjeta=tarjeta,
                                       monto=8900, cada_meses=1, proximo_cobro=date(2026, 12, 3))
        _entregar_compra(self.orden(total_amount=8900, suscripcion=s, pasarela=Order.ONECLICK))
        [m] = self.a_la_tienda()
        self.assertIn('Renovación automática', m.subject)
        self.assertIn('Próximo cobro: 03-12-2026', m.body)
        self.assertIn('Visa terminada en 1234', m.body)

    def test_si_falla_el_aviso_la_compra_sigue(self):
        with patch('payments.views._avisar_a_la_tienda', side_effect=RuntimeError('smtp')):
            _entregar_compra(self.orden())   # no lanza
