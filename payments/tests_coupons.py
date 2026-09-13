"""Cupones de descuento.

Lo que se prueba acá es la plata: que el descuento sea el que corresponde, que
los límites se respeten, y sobre todo que las líneas del pedido sigan sumando
exactamente el total cobrado. Ese último punto no es cosmético: la boleta
electrónica se niega a emitirse si el detalle no cuadra (invoicing/services.py),
así que un error ahí deja la venta hecha y sin documento tributario.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from catalog.models import Product
from payments import coupons
from payments.models import Coupon, Order
from payments.orders import build_order_from_request

User = get_user_model()


def datos_compra(product, **extra):
    """Payload mínimo válido de checkout para un producto digital."""
    base = {
        'product_ids': [product.id],
        'email': 'mama@correo.cl',
        'customer_name': 'Ana Pérez',
        'student_name': 'Beni Pérez',
        'phone': '+56912345678',
    }
    base.update(extra)
    return base


class CuponBaseTests(TestCase):
    """El cálculo del descuento, sin tocar la base de datos de órdenes."""

    def test_porcentaje(self):
        c = Coupon(discount_type=Coupon.PORCENTAJE, value=25)
        self.assertEqual(c.descuento_sobre(40000), 10000)

    def test_monto_fijo(self):
        c = Coupon(discount_type=Coupon.MONTO, value=5000)
        self.assertEqual(c.descuento_sobre(40000), 5000)

    def test_el_monto_fijo_nunca_pasa_del_subtotal(self):
        """Un cupón de $10.000 sobre una compra de $6.000 descuenta $6.000.

        Si no, el total quedaba negativo y se le terminaba pagando al cliente.
        """
        c = Coupon(discount_type=Coupon.MONTO, value=10000)
        self.assertEqual(c.descuento_sobre(6000), 6000)

    def test_el_porcentaje_redondea_hacia_abajo(self):
        """A favor de la tienda, y siempre un número entero: el CLP no tiene
        decimales y un total con coma lo rechaza la pasarela."""
        c = Coupon(discount_type=Coupon.PORCENTAJE, value=33)
        self.assertEqual(c.descuento_sobre(10000), 3300)
        self.assertEqual(c.descuento_sobre(9999), 3299)

    def test_el_codigo_se_guarda_en_mayusculas(self):
        c = Coupon.objects.create(code='  cyber2026 ', discount_type=Coupon.PORCENTAJE, value=10)
        self.assertEqual(c.code, 'CYBER2026')

    def test_buscar_ignora_mayusculas_y_espacios(self):
        """La gente copia y pega el código de un mail y se trae espacios."""
        Coupon.objects.create(code='CYBER2026', discount_type=Coupon.PORCENTAJE, value=10)
        self.assertIsNotNone(coupons.buscar('  cyber2026  '))
        self.assertIsNone(coupons.buscar('CYBER2025'))


class RepartirTests(TestCase):
    """El descuento se reparte entre las líneas y la suma tiene que dar EXACTA."""

    def test_una_sola_linea(self):
        self.assertEqual(coupons.repartir([40000], 10000), [30000])

    def test_varias_lineas_a_prorrata(self):
        self.assertEqual(coupons.repartir([30000, 10000], 8000), [24000, 8000])

    def test_el_redondeo_lo_absorbe_la_ultima_linea(self):
        """Tres líneas iguales y un descuento que no divide en tres: el peso
        suelto tiene que quedar en alguna parte, no evaporarse."""
        precios = [1000, 1000, 1000]
        rebajados = coupons.repartir(precios, 100)
        self.assertEqual(sum(precios) - sum(rebajados), 100)

    def test_sin_descuento_no_toca_nada(self):
        self.assertEqual(coupons.repartir([1000, 2000], 0), [1000, 2000])


class LimitesTests(TestCase):
    def setUp(self):
        self.cupon = Coupon.objects.create(
            code='CYBER', discount_type=Coupon.PORCENTAJE, value=20,
        )

    def test_apagado_no_sirve(self):
        self.cupon.is_active = False
        self.cupon.save()
        _, error = coupons.revisar(self.cupon, 10000)
        self.assertIn('no está disponible', error)

    def test_vencido_no_sirve(self):
        self.cupon.ends_at = timezone.now() - timedelta(hours=1)
        self.cupon.save()
        _, error = coupons.revisar(self.cupon, 10000)
        self.assertIn('venció', error)

    def test_todavia_no_empieza(self):
        self.cupon.starts_at = timezone.now() + timedelta(days=1)
        self.cupon.save()
        _, error = coupons.revisar(self.cupon, 10000)
        self.assertIn('todavía no', error)

    def test_dentro_de_la_ventana_si_sirve(self):
        self.cupon.starts_at = timezone.now() - timedelta(hours=1)
        self.cupon.ends_at = timezone.now() + timedelta(hours=1)
        self.cupon.save()
        descuento, error = coupons.revisar(self.cupon, 10000)
        self.assertIsNone(error)
        self.assertEqual(descuento, 2000)

    def test_compra_minima(self):
        self.cupon.min_purchase = 50000
        self.cupon.save()
        _, error = coupons.revisar(self.cupon, 20000)
        self.assertIn('50.000', error)

        descuento, error = coupons.revisar(self.cupon, 50000)
        self.assertIsNone(error)
        self.assertEqual(descuento, 10000)


class UsosTests(TestCase):
    """El tope de usos y el "un uso por persona" se miden sobre compras PAGADAS."""

    def setUp(self):
        self.cupon = Coupon.objects.create(
            code='CYBER', discount_type=Coupon.MONTO, value=1000, max_uses=1,
        )

    def _orden(self, status, email='mama@correo.cl'):
        return Order.objects.create(
            customer_email=email, total_amount=9000,
            coupon=self.cupon, discount_amount=1000, status=status,
        )

    def test_una_orden_pendiente_no_gasta_el_cupon(self):
        """Quien abandona el pago a medio camino no puede agotarle el cupón al
        resto: si no, bastaba abrir el checkout para quemar la promoción."""
        self._orden('PENDING')
        descuento, error = coupons.revisar(self.cupon, 10000)
        self.assertIsNone(error)
        self.assertEqual(descuento, 1000)

    def test_una_orden_pagada_si_lo_gasta(self):
        self._orden('PAID')
        _, error = coupons.revisar(self.cupon, 10000)
        self.assertIn('agotó', error)

    def test_un_uso_por_correo(self):
        self.cupon.max_uses = None
        self.cupon.once_per_email = True
        self.cupon.save()
        self._orden('PAID', email='mama@correo.cl')

        _, error = coupons.revisar(self.cupon, 10000, 'MAMA@correo.cl')
        self.assertIn('ya lo usaste', error)

        # Otra persona sí puede usarlo.
        descuento, error = coupons.revisar(self.cupon, 10000, 'otra@correo.cl')
        self.assertIsNone(error)
        self.assertEqual(descuento, 1000)


class OrdenConCuponTests(TestCase):
    """El camino completo: crear la orden con un cupón."""

    def setUp(self):
        self.product = Product.objects.create(
            name='Kit Ingenio', slug='kit-ingenio', price=40000,
            is_active=True, is_digital=True,
        )
        self.cupon = Coupon.objects.create(
            code='CYBER', discount_type=Coupon.PORCENTAJE, value=25,
        )

    def test_sin_cupon_cobra_el_precio_de_lista(self):
        order, error = build_order_from_request(datos_compra(self.product))
        self.assertIsNone(error)
        self.assertEqual(order.total_amount, 40000)
        self.assertEqual(order.discount_amount, 0)
        self.assertIsNone(order.coupon)

    def test_con_cupon_descuenta_y_deja_el_rastro(self):
        order, error = build_order_from_request(
            datos_compra(self.product, coupon_code='cyber'),
        )
        self.assertIsNone(error)
        self.assertEqual(order.total_amount, 30000)
        self.assertEqual(order.discount_amount, 10000)
        self.assertEqual(order.coupon, self.cupon)

    def test_las_lineas_suman_exactamente_el_total(self):
        """Es la condición que la boleta electrónica exige para poder emitirse.

        Si el descuento se guardara solo en el total y la línea quedara a precio
        de lista, toda compra con cupón se quedaría sin boleta.
        """
        order, _ = build_order_from_request(
            datos_compra(self.product, coupon_code='CYBER'),
        )
        suma = sum(i.subtotal for i in order.items.all())
        self.assertEqual(suma, order.total_amount)

    def test_un_cupon_inexistente_no_crea_la_orden(self):
        order, error = build_order_from_request(
            datos_compra(self.product, coupon_code='NOEXISTE'),
        )
        self.assertIsNone(order)
        self.assertIn('no existe', error)
        self.assertEqual(Order.objects.count(), 0)

    def test_un_cupon_vencido_no_crea_la_orden(self):
        self.cupon.ends_at = timezone.now() - timedelta(days=1)
        self.cupon.save()
        order, error = build_order_from_request(
            datos_compra(self.product, coupon_code='CYBER'),
        )
        self.assertIsNone(order)
        self.assertIn('venció', error)

    def test_un_cupon_que_deja_el_total_en_cero_se_rechaza(self):
        """Ni Webpay ni MercadoPago aceptan cobrar $0."""
        self.cupon.value = 100
        self.cupon.save()
        order, error = build_order_from_request(
            datos_compra(self.product, coupon_code='CYBER'),
        )
        self.assertIsNone(order)
        self.assertIn('$0', error)

    def test_el_codigo_vacio_se_ignora(self):
        """El campo llega siempre desde el frontend, casi siempre vacío."""
        order, error = build_order_from_request(
            datos_compra(self.product, coupon_code=''),
        )
        self.assertIsNone(error)
        self.assertEqual(order.total_amount, 40000)


class ValidarCuponAPITests(TestCase):
    """El endpoint que revisa el cupón antes de pagar."""

    def setUp(self):
        self.client = APIClient()
        self.url = reverse('cupon-validar')
        self.product = Product.objects.create(
            name='Kit Ingenio', slug='kit-ingenio', price=40000,
            is_active=True, is_digital=True,
        )
        Coupon.objects.create(code='CYBER', discount_type=Coupon.PORCENTAJE, value=25)

    def test_cupon_valido(self):
        r = self.client.post(self.url, {
            'code': 'cyber', 'product_ids': [self.product.id],
        }, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data['ok'])
        self.assertEqual(r.data['discount'], 10000)
        self.assertEqual(r.data['code'], 'CYBER')
        self.assertEqual(r.data['label'], '25%')

    def test_cupon_inexistente(self):
        r = self.client.post(self.url, {
            'code': 'NADA', 'product_ids': [self.product.id],
        }, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data['ok'])

    def test_un_cupon_apagado_responde_igual_que_uno_inexistente(self):
        """A propósito: distinguirlos le confirma a quien prueba códigos al
        azar cuáles acertó, y esos códigos se reutilizan entre campañas."""
        Coupon.objects.create(
            code='APAGADO', discount_type=Coupon.PORCENTAJE, value=50, is_active=False,
        )
        inexistente = self.client.post(self.url, {
            'code': 'NOEXISTE', 'product_ids': [self.product.id],
        }, format='json')
        apagado = self.client.post(self.url, {
            'code': 'APAGADO', 'product_ids': [self.product.id],
        }, format='json')
        self.assertEqual(inexistente.data['error'], apagado.data['error'])

    def test_no_cobra_ni_deja_orden(self):
        self.client.post(self.url, {
            'code': 'CYBER', 'product_ids': [self.product.id],
        }, format='json')
        self.assertEqual(Order.objects.count(), 0)


class PanelCuponesTests(TestCase):
    """La sección del CMS."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin@ingenioblocks.com', email='admin@ingenioblocks.com',
            password='clave-larga-1234', is_staff=True,
        )
        self.client.force_login(self.admin)

    def test_crear_un_cupon(self):
        r = self.client.post(reverse('panel:coupon_new'), {
            'code': 'cyber2026', 'description': 'CyberMonday',
            'discount_type': Coupon.PORCENTAJE, 'value': 30,
            'min_purchase': 0, 'starts_at': '', 'ends_at': '', 'max_uses': '',
        })
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Coupon.objects.filter(code='CYBER2026').exists())

    def test_un_porcentaje_sobre_100_se_rechaza(self):
        r = self.client.post(reverse('panel:coupon_new'), {
            'code': 'MALO', 'discount_type': Coupon.PORCENTAJE, 'value': 150,
            'min_purchase': 0, 'starts_at': '', 'ends_at': '', 'max_uses': '',
        })
        self.assertEqual(r.status_code, 200)          # vuelve al formulario
        self.assertFalse(Coupon.objects.filter(code='MALO').exists())

    def test_un_codigo_con_espacios_se_rechaza(self):
        """El cliente lo escribe a mano: un espacio lo deja inservible."""
        r = self.client.post(reverse('panel:coupon_new'), {
            'code': 'CYBER 2026', 'discount_type': Coupon.PORCENTAJE, 'value': 10,
            'min_purchase': 0, 'starts_at': '', 'ends_at': '', 'max_uses': '',
        })
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Coupon.objects.filter(description='').exclude(code='').exists())

    def test_la_fecha_de_termino_no_puede_ser_anterior_a_la_de_inicio(self):
        r = self.client.post(reverse('panel:coupon_new'), {
            'code': 'ALREVES', 'discount_type': Coupon.PORCENTAJE, 'value': 10,
            'min_purchase': 0, 'max_uses': '',
            'starts_at': '2026-11-30T10:00', 'ends_at': '2026-11-29T10:00',
        })
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Coupon.objects.filter(code='ALREVES').exists())

    def test_apagar_un_cupon_desde_la_lista(self):
        c = Coupon.objects.create(code='CYBER', discount_type=Coupon.PORCENTAJE, value=10)
        self.client.post(reverse('panel:coupon_toggle_active', args=[c.pk]))
        c.refresh_from_db()
        self.assertFalse(c.is_active)

    def test_no_se_puede_borrar_un_cupon_ya_usado(self):
        """Borrarlo dejaría pedidos con un descuento sin poder decir de dónde
        salió, y la boleta de esa venta sin respaldo."""
        c = Coupon.objects.create(code='CYBER', discount_type=Coupon.PORCENTAJE, value=10)
        Order.objects.create(
            customer_email='a@b.cl', total_amount=1000, coupon=c,
            discount_amount=100, status='PAID',
        )
        self.client.post(reverse('panel:coupon_delete', args=[c.pk]))
        self.assertTrue(Coupon.objects.filter(pk=c.pk).exists())

    def test_un_cupon_sin_usar_si_se_borra(self):
        c = Coupon.objects.create(code='CYBER', discount_type=Coupon.PORCENTAJE, value=10)
        self.client.post(reverse('panel:coupon_delete', args=[c.pk]))
        self.assertFalse(Coupon.objects.filter(pk=c.pk).exists())

    def _consultas_del_listado(self, cuantos):
        Coupon.objects.all().delete()
        for i in range(cuantos):
            Coupon.objects.create(
                code=f'CUPON{i}', discount_type=Coupon.PORCENTAJE, value=10, max_uses=10,
            )
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(reverse('panel:coupons'))
        return len(ctx)

    def test_la_lista_no_hace_una_consulta_por_fila(self):
        """El conteo de usos viene anotado, y la columna "Estado" lo reusa.

        Se compara 3 contra 30 en vez de fijar un número: el número exacto
        depende de la sesión y de axes, y un test que lo fija se rompe cada vez
        que se toca algo que no tiene nada que ver. Lo que importa es que no
        crezca con la cantidad de cupones.
        """
        pocos = self._consultas_del_listado(3)
        muchos = self._consultas_del_listado(30)
        self.assertEqual(pocos, muchos)
