"""Retiro en tienda.

Lo importante acá es que un pedido de retiro NO se comporte como uno de
despacho: no cobra envío, no crea Shipment (si lo creara, aparecería en la cola
de despachos y alguien terminaría mandando por courier algo que el cliente va a
venir a buscar), y no se puede elegir si la tienda lo tiene apagado.
"""
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from catalog.models import Product
from payments.models import Order
from payments.orders import build_order_from_request
from shipments.models import PuntoRetiro, Shipment

User = get_user_model()


def punto_completo(**extra):
    punto = PuntoRetiro.cargar()
    punto.activo = True
    punto.direccion = 'Av. Apoquindo 1234'
    punto.comuna = 'Las Condes'
    punto.horario = 'Lunes a viernes de 10:00 a 18:00'
    for k, v in extra.items():
        setattr(punto, k, v)
    punto.save()
    return punto


def datos_compra(product, **extra):
    base = {
        'product_ids': [product.id],
        'email': 'mama@correo.cl',
        'customer_name': 'Ana Pérez',
        'student_name': 'Beni Pérez',
        'phone': '+56912345678',
    }
    base.update(extra)
    return base


class PuntoRetiroModeloTests(TestCase):
    def test_nace_apagado(self):
        """Ofrecer retiro sin decir dónde es peor que no ofrecerlo."""
        punto = PuntoRetiro.cargar()
        self.assertFalse(punto.activo)
        self.assertFalse(punto.disponible)

    def test_cargar_devuelve_siempre_la_misma_fila(self):
        a = PuntoRetiro.cargar()
        b = PuntoRetiro.cargar()
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(PuntoRetiro.objects.count(), 1)

    def test_encendido_pero_sin_direccion_no_esta_disponible(self):
        punto = PuntoRetiro.cargar()
        punto.activo = True
        punto.horario = 'Lunes a viernes'
        punto.save()
        self.assertFalse(punto.disponible)

    def test_encendido_pero_sin_horario_no_esta_disponible(self):
        """Sin horario la gente llega cuando está cerrado."""
        punto = PuntoRetiro.cargar()
        punto.activo = True
        punto.direccion = 'Av. Apoquindo 1234'
        punto.save()
        self.assertFalse(punto.disponible)

    def test_completo_y_encendido_si_esta_disponible(self):
        self.assertTrue(punto_completo().disponible)

    def test_direccion_completa(self):
        punto = punto_completo()
        self.assertEqual(
            punto.direccion_completa, 'Av. Apoquindo 1234, Las Condes, Santiago',
        )


class PuntoRetiroAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse('shipments-retiro')

    def test_apagado_responde_no_disponible(self):
        r = self.client.get(self.url)
        self.assertFalse(r.data['disponible'])
        # Y no filtra la dirección a medio cargar.
        self.assertNotIn('direccion', r.data)

    def test_disponible_responde_los_datos(self):
        punto_completo(referencia='Piso 2', instrucciones='Trae tu carnet')
        r = self.client.get(self.url)
        self.assertTrue(r.data['disponible'])
        self.assertEqual(r.data['comuna'], 'Las Condes')
        self.assertEqual(r.data['direccion'], 'Av. Apoquindo 1234')
        self.assertEqual(r.data['referencia'], 'Piso 2')


class OrdenConRetiroTests(TestCase):
    def setUp(self):
        self.fisico = Product.objects.create(
            name='Kit Inicial', slug='kit-inicial', price=69490,
            is_active=True, is_digital=False,
        )
        self.digital = Product.objects.create(
            name='Pack Modelos', slug='pack-modelos', price=20000,
            is_active=True, is_digital=True,
        )
        punto_completo()

    def test_retiro_no_cobra_envio(self):
        order, error = build_order_from_request(
            datos_compra(self.fisico, delivery_method='PICKUP'),
        )
        self.assertIsNone(error)
        self.assertEqual(order.total_amount, 69490)
        self.assertEqual(order.delivery_method, Order.RETIRO)

    def test_retiro_no_crea_envio(self):
        """Si creara un Shipment, el pedido caería en la cola de despachos y
        alguien terminaría mandándolo por courier."""
        order, _ = build_order_from_request(
            datos_compra(self.fisico, delivery_method='PICKUP'),
        )
        self.assertEqual(Shipment.objects.count(), 0)
        self.assertIsNone(getattr(order, 'shipment', None))

    def test_retiro_no_pide_direccion(self):
        """Es el punto de todo: se puede comprar sin escribir una dirección."""
        datos = datos_compra(self.fisico, delivery_method='PICKUP')
        self.assertNotIn('shipping', datos)
        order, error = build_order_from_request(datos)
        self.assertIsNone(error)
        self.assertIsNotNone(order)

    def test_con_la_tienda_apagada_se_rechaza(self):
        """Se revalida contra la base: si la tienda cerró el retiro mientras la
        persona llenaba el formulario, no se puede aceptar la compra."""
        punto = PuntoRetiro.cargar()
        punto.activo = False
        punto.save()
        order, error = build_order_from_request(
            datos_compra(self.fisico, delivery_method='PICKUP'),
        )
        self.assertIsNone(order)
        self.assertIn('no está disponible', error)

    def test_sin_metodo_sigue_exigiendo_direccion(self):
        """El camino de siempre no cambia: un pedido físico sin retiro y sin
        datos de envío se sigue rechazando."""
        order, error = build_order_from_request(datos_compra(self.fisico))
        self.assertIsNone(order)
        self.assertIn('envío', error)

    def test_en_compra_digital_el_retiro_se_ignora(self):
        """No hay nada que retirar. Se normaliza en silencio en vez de rechazar:
        el checkout ni siquiera ofrece la opción, así que si llega es ruido."""
        order, error = build_order_from_request(
            datos_compra(self.digital, delivery_method='PICKUP'),
        )
        self.assertIsNone(error)
        self.assertEqual(order.delivery_method, Order.DESPACHO)
        self.assertFalse(order.es_retiro)


class EstadoRetiroTests(TestCase):
    def setUp(self):
        self.order = Order.objects.create(
            customer_email='a@b.cl', total_amount=1000,
            delivery_method=Order.RETIRO, status='PAID',
        )

    def test_arranca_por_preparar(self):
        self.assertEqual(self.order.estado_retiro, 'PREPARANDO')

    def test_tras_avisar_queda_avisado(self):
        from django.utils import timezone
        self.order.pickup_ready_at = timezone.now()
        self.assertEqual(self.order.estado_retiro, 'AVISADO')

    def test_tras_retirar_queda_retirado(self):
        from django.utils import timezone
        self.order.pickup_ready_at = timezone.now()
        self.order.picked_up_at = timezone.now()
        self.assertEqual(self.order.estado_retiro, 'RETIRADO')


class PanelRetiroTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin@ingenioblocks.com', email='admin@ingenioblocks.com',
            password='clave-larga-1234', is_staff=True,
        )
        self.client.force_login(self.admin)
        self.order = Order.objects.create(
            customer_email='mama@correo.cl', customer_name='Ana Pérez',
            total_amount=69490, delivery_method=Order.RETIRO, status='PAID',
        )

    def test_no_se_puede_encender_sin_direccion(self):
        r = self.client.post(reverse('panel:punto_retiro'), {
            'activo': 'on', 'nombre': 'Tienda', 'direccion': '',
            'comuna': 'Las Condes', 'ciudad': 'Santiago',
            'referencia': '', 'horario': 'L a V', 'instrucciones': '', 'mapa_url': '',
        })
        self.assertEqual(r.status_code, 200)           # vuelve al formulario
        self.assertFalse(PuntoRetiro.cargar().activo)

    def test_no_se_puede_encender_sin_horario(self):
        r = self.client.post(reverse('panel:punto_retiro'), {
            'activo': 'on', 'nombre': 'Tienda', 'direccion': 'Apoquindo 1234',
            'comuna': 'Las Condes', 'ciudad': 'Santiago',
            'referencia': '', 'horario': '', 'instrucciones': '', 'mapa_url': '',
        })
        self.assertEqual(r.status_code, 200)
        self.assertFalse(PuntoRetiro.cargar().activo)

    def test_se_enciende_con_todo_cargado(self):
        r = self.client.post(reverse('panel:punto_retiro'), {
            'activo': 'on', 'nombre': 'Tienda Ingenio', 'direccion': 'Apoquindo 1234',
            'comuna': 'Las Condes', 'ciudad': 'Santiago', 'referencia': '',
            'horario': 'Lunes a viernes de 10 a 18', 'instrucciones': '', 'mapa_url': '',
        })
        self.assertEqual(r.status_code, 302)
        self.assertTrue(PuntoRetiro.cargar().disponible)

    def test_avisar_manda_correo_y_deja_la_fecha(self):
        punto_completo()
        self.client.post(reverse('panel:order_pickup_ready', args=[self.order.pk]))
        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.pickup_ready_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('listo para retirar', mail.outbox[0].subject)
        # La dirección tiene que ir EN el correo: es el que la persona abre en
        # el celular parada en la calle.
        self.assertIn('Apoquindo 1234', mail.outbox[0].body)

    def test_no_se_avisa_sin_la_tienda_cargada(self):
        """El correo saldría con el lugar en blanco."""
        self.client.post(reverse('panel:order_pickup_ready', args=[self.order.pk]))
        self.order.refresh_from_db()
        self.assertIsNone(self.order.pickup_ready_at)
        self.assertEqual(len(mail.outbox), 0)

    def test_marcar_retirado(self):
        punto_completo()
        self.client.post(reverse('panel:order_picked_up', args=[self.order.pk]))
        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.picked_up_at)
        self.assertEqual(self.order.estado_retiro, 'RETIRADO')

    def test_retirar_sin_haber_avisado_no_deja_el_estado_a_medias(self):
        """Vino a preguntar y se lo llevó: sin esto quedaba 'retirado' pero
        'preparando' a la vez en los listados."""
        punto_completo()
        self.client.post(reverse('panel:order_picked_up', args=[self.order.pk]))
        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.pickup_ready_at)

    def test_las_acciones_de_retiro_rechazan_un_pedido_con_despacho(self):
        despacho = Order.objects.create(
            customer_email='otro@correo.cl', total_amount=1000, status='PAID',
        )
        punto_completo()
        self.client.post(reverse('panel:order_pickup_ready', args=[despacho.pk]))
        despacho.refresh_from_db()
        self.assertIsNone(despacho.pickup_ready_at)
        self.assertEqual(len(mail.outbox), 0)
