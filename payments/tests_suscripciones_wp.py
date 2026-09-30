"""Suscripciones traídas de WordPress, tarjeta guardada y aviso de cobro rechazado.

Lo que más importa acá: que nada se cobre dos veces. Las suscripciones del
WordPress las sigue cobrando el WordPress hasta que se apague, y el sitio de
revisión tiene las credenciales de producción.
"""
import os
import tempfile
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from catalog.models import Product
from lms.models import CourseCategory, Membership
from payments import oneclick
from payments.models import Order, Suscripcion, TarjetaOneclick

User = get_user_model()

AUTORIZADA = {'details': [{'status': 'AUTHORIZED', 'response_code': 0}]}
RECHAZADA = {'details': [{'status': 'FAILED', 'response_code': -1}]}

VOLCADO = """
INSERT INTO `wp_users` (`ID`, `user_login`, `user_email`) VALUES
(7, 'mama', 'Mama@Correo.cl'),
(8, 'papa', 'papa@correo.cl');

INSERT INTO `wp_wc_orders` (`id`, `status`, `type`, `total_amount`, `customer_id`, `billing_email`, `payment_method`) VALUES
(100, 'wc-active', 'shop_subscription', '8900.00000000', 7, 'mama@correo.cl', 'transbank_oneclick_mall_rest'),
(101, 'wc-active', 'shop_subscription', '58900.00000000', 8, 'papa@correo.cl', 'transbank_oneclick_mall_rest'),
(102, 'wc-cancelled', 'shop_subscription', '8900.00000000', 8, 'papa@correo.cl', 'transbank_oneclick_mall_rest');

INSERT INTO `wp_wc_orders_meta` (`id`, `order_id`, `meta_key`, `meta_value`) VALUES
(1, 100, '_billing_period', 'month'),
(2, 100, '_billing_interval', '3'),
(3, 100, '_schedule_next_payment', '2026-11-07 15:00:00'),
(4, 101, '_billing_period', 'month'),
(5, 101, '_billing_interval', '6'),
(6, 101, '_schedule_next_payment', '0');

INSERT INTO `wp_woocommerce_order_items` (`order_item_id`, `order_item_name`, `order_item_type`, `order_id`) VALUES
(1, 'Plan Individual<span> - </span>Trimestral', 'line_item', 100);

INSERT INTO `wp_woocommerce_payment_tokens` (`token_id`, `gateway_id`, `token`, `user_id`, `type`, `is_default`) VALUES
(1, 'transbank_oneclick_mall_rest', 'tbk-vieja-de-prueba', 7, 'Oneclick', '0'),
(2, 'transbank_oneclick_mall_rest', 'tbk-mama-real', 7, 'Oneclick', '1'),
(3, 'transbank_oneclick_mall_rest', 'tbk-papa', 8, 'Oneclick', '1');

INSERT INTO `wp_woocommerce_payment_tokenmeta` (`meta_id`, `payment_token_id`, `meta_key`, `meta_value`) VALUES
(1, 1, 'environment', 'TEST'),
(2, 1, 'username', 'mama'),
(3, 2, 'environment', 'LIVE'),
(4, 2, 'username', 'mama'),
(5, 2, 'last4', '6623'),
(6, 2, 'card_type', 'Visa'),
(7, 3, 'environment', 'LIVE'),
(8, 3, 'username', 'papa'),
(9, 3, 'last4', '1111'),
(10, 3, 'card_type', 'Mastercard');
"""


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.producto = Product.objects.create(
            name='Membresía Familiar', slug='membresia-familiar', price=4990, is_active=True,
            is_digital=True, es_suscripcion=True, access_months=1,
        )
        self.producto.categories.add(CourseCategory.objects.create(nombre='General', slug='general'))
        p = patch('payments.oneclick.MallTransaction')
        self.Transaccion = p.start()
        self.addCleanup(p.stop)
        self.Transaccion.return_value.authorize.return_value = AUTORIZADA

    def importar(self, *args):
        with tempfile.NamedTemporaryFile('w', suffix='.sql', delete=False, encoding='utf-8') as f:
            f.write(VOLCADO)
        self.addCleanup(os.unlink, f.name)
        out = StringIO()
        call_command('importar_suscripciones_wordpress', '--dump', f.name, *args, stdout=out)
        return out.getvalue()


class ImportarTests(Base):
    def test_ensayo_no_guarda(self):
        out = self.importar()
        self.assertIn('1 suscripción(es) activas', out)
        self.assertFalse(Suscripcion.objects.exists())
        self.assertFalse(TarjetaOneclick.objects.exists())

    def test_trae_solo_las_que_se_cobran_solas_y_las_tarjetas_de_produccion(self):
        self.importar('--aplicar')
        s = Suscripcion.objects.get()
        self.assertEqual((s.wp_id, s.email, s.monto, s.cada_meses), (100, 'mama@correo.cl', 8900, 3))
        self.assertEqual(str(s.proximo_cobro), '2026-11-07')
        self.assertEqual(s.nombre, 'Plan Individual - Trimestral')
        self.assertEqual(s.origen, Suscripcion.WORDPRESS)
        self.assertEqual((s.tarjeta.tbk_user, s.tarjeta.username, s.tarjeta.ultimos4),
                         ('tbk-mama-real', 'mama', '6623'))
        # La de TEST no se trae; la de papá sí, aunque su suscripción no se cobre sola.
        self.assertEqual(set(TarjetaOneclick.objects.values_list('tbk_user', flat=True)),
                         {'tbk-mama-real', 'tbk-papa'})

    def test_volver_a_importar_actualiza_sin_duplicar_y_respeta_la_cancelacion(self):
        self.importar('--aplicar')
        s = Suscripcion.objects.get()
        s.estado = Suscripcion.CANCELADA
        s.save()
        self.importar('--aplicar')
        self.assertEqual(Suscripcion.objects.count(), 1)
        self.assertEqual(Suscripcion.objects.get().estado, Suscripcion.CANCELADA)
        self.assertEqual(TarjetaOneclick.objects.count(), 2)


@override_settings(COBROS_AUTOMATICOS=True)
class NoCobrarDobleTests(Base):
    def setUp(self):
        super().setUp()
        self.importar('--aplicar')
        Suscripcion.objects.update(proximo_cobro=timezone.localdate())

    def cobrar(self):
        with patch('payments.views._entregar_compra'):
            call_command('cobrar_suscripciones', stdout=StringIO())

    def test_las_de_wordpress_no_se_cobran_mientras_el_wordpress_cobre(self):
        self.cobrar()
        self.Transaccion.return_value.authorize.assert_not_called()

    @override_settings(COBRAR_SUSCRIPCIONES_WORDPRESS=True)
    def test_con_el_interruptor_prendido_si_se_cobran_con_el_usuario_del_wordpress(self):
        self.cobrar()
        args = self.Transaccion.return_value.authorize.call_args.args
        self.assertEqual((args[0], args[1]), ('mama', 'tbk-mama-real'))
        o = Order.objects.get(suscripcion__isnull=False)
        self.assertEqual((o.status, int(o.total_amount)), ('PAID', 8900))
        self.assertEqual(o.items.get().name, 'Plan Individual - Trimestral')

    @override_settings(COBROS_AUTOMATICOS=False, COBRAR_SUSCRIPCIONES_WORDPRESS=True)
    def test_en_el_sitio_de_revision_no_se_cobra_nada(self):
        self.cobrar()
        self.Transaccion.return_value.authorize.assert_not_called()


class MesesDelCobroTests(Base):
    @override_settings(COBROS_AUTOMATICOS=True, COBRAR_SUSCRIPCIONES_WORDPRESS=True)
    def test_un_cobro_trimestral_da_tres_meses_aunque_el_producto_sea_mensual(self):
        from lms.services import grant_access_for_order
        self.importar('--aplicar')
        s = Suscripcion.objects.get()
        with patch('lms.services._send_welcome_email'), patch('lms.services._send_extended_email'):
            order, _ = oneclick.cobrar_suscripcion(s, entregar=grant_access_for_order)
        m = Membership.objects.get(user__email='mama@correo.cl')
        dias = (m.expires_at - timezone.now()).days
        self.assertTrue(85 <= dias <= 93, dias)


class TarjetaGuardadaTests(Base):
    def setUp(self):
        super().setUp()
        self.importar('--aplicar')
        self.pack = Product.objects.create(name='Pack', slug='pack', price=13490, is_active=True, is_digital=True)
        self.api = APIClient()
        self.mama = User.objects.create_user(username='mama@correo.cl', email='mama@correo.cl')
        self.tarjeta = TarjetaOneclick.objects.get(tbk_user='tbk-mama-real')
        p = patch('payments.views._entregar_compra')
        self.entregar = p.start()
        self.addCleanup(p.stop)

    def pagar(self, tarjeta_id, producto=None, **extra):
        datos = {'product_ids': [(producto or self.pack).id], 'email': extra.pop('email', 'mama@correo.cl'),
                 'customer_name': 'Ana', 'student_name': 'Beni', 'phone': '+56912345678',
                 'tarjeta_id': tarjeta_id}
        datos.update(extra)
        return self.api.post(reverse('oneclick-guardada'), datos, format='json')

    def test_la_duena_ve_su_tarjeta_y_paga_sin_pasar_por_transbank(self):
        self.api.force_authenticate(self.mama)
        r = self.api.get(reverse('mis-tarjetas'))
        self.assertEqual(r.data, [{'id': self.tarjeta.pk, 'texto': 'Visa terminada en 6623'}])
        r = self.pagar(self.tarjeta.pk)
        self.assertIn('/checkout/success', r.data['url'])
        self.assertEqual(Order.objects.get().status, 'PAID')
        self.entregar.assert_called_once()

    def test_no_se_puede_usar_la_tarjeta_de_otro(self):
        otro = User.objects.create_user(username='otro@correo.cl', email='otro@correo.cl')
        self.api.force_authenticate(otro)
        self.assertEqual(self.api.get(reverse('mis-tarjetas')).data, [])
        r = self.pagar(self.tarjeta.pk)
        self.assertEqual(r.status_code, 400)
        self.Transaccion.return_value.authorize.assert_not_called()

    def test_sin_sesion_no(self):
        r = self.pagar(self.tarjeta.pk)
        self.assertEqual(r.status_code, 401)
        self.Transaccion.return_value.authorize.assert_not_called()

    def test_doble_clic_no_cobra_dos_veces(self):
        self.api.force_authenticate(self.mama)
        self.pagar(self.tarjeta.pk)
        r = self.pagar(self.tarjeta.pk)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.Transaccion.return_value.authorize.call_count, 1)

    def test_suscribirse_con_la_tarjeta_guardada(self):
        papa = User.objects.create_user(username='papa@correo.cl', email='papa@correo.cl')
        tarjeta = TarjetaOneclick.objects.get(tbk_user='tbk-papa')
        self.api.force_authenticate(papa)
        datos = {'producto': self.producto, 'email': 'papa@correo.cl'}
        self.assertEqual(self.pagar(tarjeta.pk, **datos).status_code, 400)  # falta aceptar
        self.pagar(tarjeta.pk, acepta_cobro_automatico=True, **datos)
        s = Suscripcion.objects.get(origen=Suscripcion.TIENDA)
        self.assertEqual((s.tarjeta, s.monto), (tarjeta, 4990))

    def test_quien_ya_tiene_la_suscripcion_de_wordpress_no_la_contrata_de_nuevo(self):
        self.api.force_authenticate(self.mama)
        r = self.pagar(self.tarjeta.pk, producto=self.producto, acepta_cobro_automatico=True)
        self.assertEqual(r.status_code, 400)
        self.Transaccion.return_value.authorize.assert_not_called()

    def test_rechazada(self):
        self.Transaccion.return_value.authorize.return_value = RECHAZADA
        self.api.force_authenticate(self.mama)
        r = self.pagar(self.tarjeta.pk)
        self.assertIn('reason=rejected', r.data['url'])
        self.entregar.assert_not_called()


class AvisoDeRechazoTests(Base):
    def setUp(self):
        super().setUp()
        self.importar('--aplicar')
        self.s = Suscripcion.objects.get()
        self.Transaccion.return_value.authorize.return_value = RECHAZADA

    @override_settings(ENVIAR_CORREOS=True)
    def test_avisa_el_rechazo_y_despues_la_suspension(self):
        oneclick.cobrar_suscripcion(self.s, entregar=lambda o: None)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['mama@correo.cl'])
        self.assertIn('No pudimos cobrar', mail.outbox[0].subject)
        self.assertIn('Visa terminada en 6623', mail.outbox[0].body)
        for _ in range(Suscripcion.INTENTOS_MAXIMOS - 1):
            oneclick.cobrar_suscripcion(self.s, entregar=lambda o: None)
        self.assertIn('suspendida', mail.outbox[-1].subject)

    @override_settings(ENVIAR_CORREOS=False)
    def test_con_el_freno_puesto_no_le_llega_al_cliente(self):
        oneclick.cobrar_suscripcion(self.s, entregar=lambda o: None)
        self.assertEqual([m for m in mail.outbox if 'mama@correo.cl' in m.to], [])
