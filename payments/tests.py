"""Tests del camino del dinero.

No buscan cobertura: cubren los puntos donde un error se traduce en plata
perdida o en un cliente que pagó y no recibió nada. Son los que permiten tocar
el resto del código sin miedo.
"""
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from catalog.models import Product
from lms.models import Course, Membership
from lms.services import grant_access_for_order
from payments.models import Order
from payments.orders import build_order_from_request
from shipments.services import CotizacionNoDisponible


DATOS_BASE = {
    'email': 'apoderado@test.cl',
    'customer_name': 'Ana Pérez',
    'student_name': 'Tomás Pérez',
    'phone': '+56912345678',
}


class PrecioAutoritativoTests(TestCase):
    """El total lo decide el servidor, nunca lo que manda el navegador."""

    def setUp(self):
        self.producto = Product.objects.create(
            name='Kit Inicial', slug='kit-inicial', price=69490,
            is_active=True, is_digital=True, access_months=6,
        )

    def test_ignora_el_precio_que_manda_el_cliente(self):
        orden, error = build_order_from_request({
            **DATOS_BASE,
            'product_ids': [self.producto.id],
            # Un atacante manipulando el formulario:
            'total_amount': 1,
            'price': 1,
        })
        self.assertIsNone(error)
        self.assertEqual(int(orden.total_amount), 69490)

    def test_usa_el_precio_de_oferta_cuando_corresponde(self):
        self.producto.is_on_sale = True
        self.producto.sale_price = 49990
        self.producto.save()

        orden, error = build_order_from_request({
            **DATOS_BASE, 'product_ids': [self.producto.id],
        })
        self.assertIsNone(error)
        # effective_price y no price: es lo que se muestra en el checkout.
        self.assertEqual(int(orden.total_amount), 49990)

    def test_no_deja_comprar_un_producto_proximamente(self):
        self.producto.is_coming_soon = True
        self.producto.save()
        orden, error = build_order_from_request({
            **DATOS_BASE, 'product_ids': [self.producto.id],
        })
        self.assertIsNone(orden)
        self.assertIsNotNone(error)

    def test_no_deja_comprar_un_producto_inactivo(self):
        self.producto.is_active = False
        self.producto.save()
        orden, error = build_order_from_request({
            **DATOS_BASE, 'product_ids': [self.producto.id],
        })
        self.assertIsNone(orden)
        self.assertIsNotNone(error)

    def test_el_orderitem_congela_el_precio_aunque_el_producto_cambie(self):
        orden, _ = build_order_from_request({
            **DATOS_BASE, 'product_ids': [self.producto.id],
        })
        # El precio del producto sube DESPUÉS de la compra.
        self.producto.price = 99990
        self.producto.save()

        item = orden.items.get()
        self.assertEqual(int(item.unit_price), 69490)   # el que se cobró
        self.assertEqual(item.name, 'Kit Inicial')

    def test_no_se_puede_borrar_un_producto_ya_vendido(self):
        """OrderItem.product es PROTECT: ni el admin ni un delete directo pueden
        vaciar los pedidos históricos."""
        from django.db.models import ProtectedError
        build_order_from_request({
            **DATOS_BASE, 'product_ids': [self.producto.id],
        })
        with self.assertRaises(ProtectedError):
            self.producto.delete()


class SoloParaAlumnosTests(TestCase):
    """requires_login: los packs y planes no se compran sin haber comprado el kit."""

    def setUp(self):
        self.plan = Product.objects.create(
            name='Ingenio Plus', slug='ingenio-plus', price=12900,
            is_active=True, is_digital=True, requires_login=True, access_months=1,
        )

    def test_sin_sesion_se_rechaza(self):
        orden, error = build_order_from_request({
            **DATOS_BASE, 'product_ids': [self.plan.id],
        }, user=None)
        self.assertIsNone(orden)
        self.assertIn('alumnos', error.lower())

    def test_con_sesion_la_compra_se_ancla_al_correo_de_la_cuenta(self):
        usuario = User.objects.create_user(
            username='alumna@test.cl', email='alumna@test.cl', password='clave-de-prueba')

        orden, error = build_order_from_request({
            **DATOS_BASE,
            'product_ids': [self.plan.id],
            # Aunque mande otro correo, manda el de la sesión: si no, se le
            # podría regalar el acceso a una cuenta ajena.
            'email': 'otra.persona@test.cl',
        }, user=usuario)

        self.assertIsNone(error)
        self.assertEqual(orden.customer_email, 'alumna@test.cl')


class EnvioTests(TestCase):
    """El costo de despacho se recotiza en el servidor, y nunca se inventa."""

    def setUp(self):
        self.kit = Product.objects.create(
            name='Kit físico', slug='kit-fisico', price=69490,
            is_active=True, is_digital=False, weight_kg=2,
        )
        self.envio = {
            'commune': 'Providencia', 'commune_id': 308,
            'courier': 'Chilexpress', 'service_name': 'Normal',
            'address_street': 'Av. Siempre Viva', 'address_number': '742',
            'region': 'Metropolitana',
        }

    @patch('payments.orders.get_shipping_quotes')
    def test_ignora_el_costo_de_envio_que_manda_el_cliente(self, cotizar):
        cotizar.return_value = [
            {'courier': 'Chilexpress', 'service': 'Normal', 'price': 4500, 'days': '2-3'},
        ]
        orden, error = build_order_from_request({
            **DATOS_BASE,
            'product_ids': [self.kit.id],
            'shipping': {**self.envio, 'shipping_cost': 1},   # ← manipulado
        })
        self.assertIsNone(error)
        # 69490 + 4500 de la cotización del servidor, no el 1 del cliente.
        self.assertEqual(int(orden.total_amount), 73990)

    @patch('payments.orders.get_shipping_quotes')
    def test_si_no_hay_cotizacion_real_no_se_vende(self, cotizar):
        """Antes cualquier fallo de Shipit caía a un mock y se cobraba una
        tarifa inventada, que la tienda terminaba absorbiendo en silencio."""
        cotizar.side_effect = CotizacionNoDisponible('No pudimos calcular el despacho.')

        orden, error = build_order_from_request({
            **DATOS_BASE, 'product_ids': [self.kit.id], 'shipping': self.envio,
        })
        self.assertIsNone(orden)
        self.assertIn('despacho', error.lower())

    @patch('payments.orders.get_shipping_quotes')
    def test_rechaza_un_courier_que_no_esta_en_la_cotizacion(self, cotizar):
        cotizar.return_value = [
            {'courier': 'Chilexpress', 'service': 'Normal', 'price': 4500, 'days': '2-3'},
        ]
        orden, error = build_order_from_request({
            **DATOS_BASE,
            'product_ids': [self.kit.id],
            'shipping': {**self.envio, 'courier': 'Courier Inventado', 'service_name': 'Gratis'},
        })
        self.assertIsNone(orden)
        self.assertIsNotNone(error)


class ValidacionDeDatosTests(TestCase):
    def setUp(self):
        self.producto = Product.objects.create(
            name='Kit', slug='kit', price=1000, is_active=True, is_digital=True)

    def test_el_nombre_del_nino_es_obligatorio(self):
        """Va impreso en el diploma: sin él la compra no sirve."""
        datos = {**DATOS_BASE, 'product_ids': [self.producto.id]}
        del datos['student_name']
        orden, error = build_order_from_request(datos)
        self.assertIsNone(orden)
        self.assertIsNotNone(error)

    def test_rechaza_correo_invalido(self):
        orden, error = build_order_from_request({
            **DATOS_BASE, 'product_ids': [self.producto.id], 'email': 'no-es-un-correo',
        })
        self.assertIsNone(orden)
        self.assertIsNotNone(error)

    def test_rechaza_telefono_que_no_es_chileno(self):
        orden, error = build_order_from_request({
            **DATOS_BASE, 'product_ids': [self.producto.id], 'phone': '123',
        })
        self.assertIsNone(orden)
        self.assertIsNotNone(error)


class OtorgarAccesoTests(TestCase):
    """grant_access_for_order tiene que ser idempotente: el webhook de
    MercadoPago y el retorno del navegador llegan casi a la vez y los dos
    ejecutan esto."""

    def setUp(self):
        self.curso = Course.objects.create(title='Modelo 1', slug='modelo-1', order=1)
        self.producto = Product.objects.create(
            name='Kit', slug='kit', price=69490,
            is_active=True, is_digital=True, access_months=6,
        )
        self.producto.courses.add(self.curso)

        self.orden = Order.objects.create(
            customer_email='apoderado@test.cl',
            customer_name='Ana Pérez', student_name='Tomás Pérez',
            total_amount=69490, status='PAID',
        )
        self.orden.products.set([self.producto])

    def test_crea_la_membresia_y_copia_el_nombre_del_nino(self):
        membresia = grant_access_for_order(self.orden)

        self.assertIsNotNone(membresia)
        self.assertTrue(membresia.is_active)
        self.assertIn(self.curso, membresia.courses.all())
        # El diploma sale a nombre del niño, no del apoderado.
        self.assertEqual(membresia.student_name, 'Tomás Pérez')

    def test_aplicar_la_misma_orden_dos_veces_no_duplica_los_meses(self):
        primera = grant_access_for_order(self.orden)
        vence_primera = primera.expires_at

        segunda = grant_access_for_order(self.orden)

        self.assertEqual(primera.pk, segunda.pk)
        self.assertEqual(vence_primera, segunda.expires_at)
        self.assertEqual(Membership.objects.count(), 1)

    def test_una_orden_sin_cursos_no_crea_membresia(self):
        self.producto.courses.clear()
        self.assertIsNone(grant_access_for_order(self.orden))
        self.assertEqual(Membership.objects.count(), 0)
