"""Boletas con productos exentos de IVA.

La empresa es de servicios educativos y sus productos van EXENTOS; el despacho
no, porque es un servicio del courier. Una boleta con envío lleva las dos cosas
a la vez.

Los números de `BoletaIgualALaDeLaClientaTests` salen de una boleta REAL que la
clienta emite hoy a mano (DTE 39, folio 161): si nuestro cálculo no da esos
mismos totales, el documento que emitimos no es el que ella espera.
"""
from django.test import TestCase

from catalog.models import Category, Product
from invoicing.services import _build_boleta_payload
from payments.models import Order, OrderItem
from shipments.models import Shipment


def _sin_red(monkey_target=None):
    """get_organization() llama a OpenFactura por HTTP; en los tests no."""
    import invoicing.services as srv
    srv._ORG_CACHE = {
        'rut': '77915902-7',
        'razonSocial': 'SERVICIOS EDUCATIVOS Y DE CAPACITACION INGENIO BLOCKS SPA',
        'glosaDescriptiva': 'SERVICIOS EDUCATIVOS Y DE CAPACITACION',
        'direccion': 'EL TORRENTE 8973 LT 39 A',
        'comuna': 'Las Condes',
    }


class BaseBoleta(TestCase):
    def setUp(self):
        _sin_red()
        self.categoria = Category.objects.create(name='Kits', slug='kits')

    def _producto(self, nombre='Plan Individual - Solo kit', precio=69490, exento=True,
                  digital=False):
        return Product.objects.create(
            name=nombre, slug=nombre.lower().replace(' ', '-')[:40], price=precio,
            category=self.categoria, is_active=True, is_digital=digital,
            exento_iva=exento,
        )

    def _orden(self, producto, total, envio=0, courier='starken'):
        order = Order.objects.create(
            customer_email='mama@correo.cl', total_amount=total, status='PAID',
        )
        order.products.set([producto])
        OrderItem.objects.create(
            order=order, product=producto, name=producto.name,
            unit_price=int(producto.price), quantity=1,
        )
        if envio:
            Shipment.objects.create(
                order=order, recipient_name='Ana', recipient_phone='+56911111111',
                region='Metropolitana', commune='Las Condes',
                address_street='Calle', address_number='1',
                courier=courier, shipping_cost=envio,
            )
        return order


class BoletaIgualALaDeLaClientaTests(BaseBoleta):
    """Reproduce la boleta real: kit $69.490 exento + despacho Starken $5.325."""

    def setUp(self):
        super().setUp()
        producto = self._producto()
        self.order = self._orden(producto, total=69490 + 5325, envio=5325)
        self.totales = _build_boleta_payload(self.order)['dte']['Encabezado']['Totales']

    def test_monto_exento(self):
        self.assertEqual(self.totales['MntExe'], 69490)

    def test_monto_neto(self):
        """Solo el despacho: 5325 / 1,19 = 4.475."""
        self.assertEqual(self.totales['MntNeto'], 4475)

    def test_iva(self):
        """19% del despacho y de nada más."""
        self.assertEqual(self.totales['IVA'], 850)

    def test_monto_total(self):
        self.assertEqual(self.totales['MntTotal'], 74815)

    def test_los_totales_cuadran_entre_si(self):
        t = self.totales
        self.assertEqual(t['MntExe'] + t['MntNeto'] + t['IVA'], t['MntTotal'])

    def test_la_linea_del_producto_va_marcada_exenta(self):
        """IndExe 1 es lo que imprime "**Producto o servicio es exento o no
        afecto" bajo el nombre en el PDF."""
        detalle = _build_boleta_payload(self.order)['dte']['Detalle']
        self.assertEqual(detalle[0]['IndExe'], 1)

    def test_la_linea_del_despacho_NO_va_exenta(self):
        detalle = _build_boleta_payload(self.order)['dte']['Detalle']
        self.assertNotIn('IndExe', detalle[1])
        self.assertEqual(detalle[1]['MontoItem'], 5325)

    def test_el_detalle_suma_el_total(self):
        """Condición que el SII exige para que el documento sea válido."""
        payload = _build_boleta_payload(self.order)
        suma = sum(d['MontoItem'] for d in payload['dte']['Detalle'])
        self.assertEqual(suma, payload['dte']['Encabezado']['Totales']['MntTotal'])

    def test_lleva_la_referencia_al_pedido(self):
        payload = _build_boleta_payload(self.order)
        razon = payload['dte']['Referencia'][0]['RazonRef']
        self.assertIn('Orden de compra', razon)
        self.assertIn(str(self.order.order_id)[:8], razon)


class CompraDigitalTests(BaseBoleta):
    """Un plan sin despacho es 100% exento: no lleva neto ni IVA."""

    def setUp(self):
        super().setUp()
        producto = self._producto('Pack de modelos', 20000, digital=True)
        self.order = self._orden(producto, total=20000)
        self.totales = _build_boleta_payload(self.order)['dte']['Encabezado']['Totales']

    def test_todo_va_a_exento(self):
        self.assertEqual(self.totales['MntExe'], 20000)
        self.assertEqual(self.totales['MntTotal'], 20000)

    def test_no_se_manda_neto_ni_iva_en_cero(self):
        """Mandarlos en 0 no es lo mismo que omitirlos: el SII lo lee como
        "hay una parte afecta que suma cero", que es otra cosa."""
        self.assertNotIn('MntNeto', self.totales)
        self.assertNotIn('IVA', self.totales)


class ProductoAfectoTests(BaseBoleta):
    """Si algún día venden algo que SÍ paga IVA, se desmarca y funciona."""

    def test_un_producto_afecto_paga_iva(self):
        producto = self._producto('Repuesto', 11900, exento=False, digital=True)
        order = self._orden(producto, total=11900)
        t = _build_boleta_payload(order)['dte']['Encabezado']['Totales']
        self.assertNotIn('MntExe', t)
        self.assertEqual(t['MntNeto'], 10000)
        self.assertEqual(t['IVA'], 1900)
        self.assertEqual(t['MntTotal'], 11900)

    def test_la_linea_afecta_no_lleva_la_marca(self):
        producto = self._producto('Repuesto', 11900, exento=False, digital=True)
        order = self._orden(producto, total=11900)
        detalle = _build_boleta_payload(order)['dte']['Detalle']
        self.assertNotIn('IndExe', detalle[0])


class RedondeoTests(BaseBoleta):
    """Neto + IVA tiene que dar EXACTO lo cobrado, o el documento se cae."""

    def test_el_iva_se_calcula_por_resta(self):
        producto = self._producto()
        for envio in (2990, 3333, 4999, 5325, 7777, 12345):
            with self.subTest(envio=envio):
                order = self._orden(producto, total=69490 + envio, envio=envio)
                t = _build_boleta_payload(order)['dte']['Encabezado']['Totales']
                self.assertEqual(t['MntNeto'] + t['IVA'], envio)
                self.assertEqual(t['MntExe'] + t['MntNeto'] + t['IVA'], t['MntTotal'])


class NombreDelArchivoTests(TestCase):
    """El PDF se llama igual que los que la clienta ya tiene guardados."""

    def setUp(self):
        _sin_red()

    def test_formato_identico_al_de_la_clienta(self):
        from invoicing.models import Invoice
        from panel.views import _nombre_de_boleta

        order = Order.objects.create(
            customer_email='a@b.cl', total_amount=1000, status='PAID',
        )
        invoice = Invoice.objects.create(order=order, folio='161', dte_type=39)
        self.assertEqual(
            _nombre_de_boleta(invoice),
            'DTE 39- Empresa 77915902 - Folio Nº 161.pdf',
        )
