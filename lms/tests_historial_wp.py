"""Historial de compras y accesos traído del volcado de WordPress."""
import os
import tempfile
from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from lms.models import HistorialWordPress as H, Membership

User = get_user_model()

VOLCADO = """
INSERT INTO `wp_users` (`ID`, `user_login`, `user_email`) VALUES
(10, 'ana', 'Ana@Correo.cl'),
(11, 'beto', 'beto@correo.cl');

INSERT INTO `wp_wc_orders` (`id`, `status`, `type`, `total_amount`, `customer_id`, `billing_email`, `date_created_gmt`, `parent_order_id`, `payment_method_title`) VALUES
(100, 'wc-completed', 'shop_order', 58900.00000000, 10, 'ana@correo.cl', '2025-07-01 12:00:00', 0, 'Webpay Oneclick'),
(101, 'wc-active', 'shop_subscription', 8900.00000000, 10, 'ana@correo.cl', '2025-07-01 12:00:00', 100, 'Webpay Oneclick'),
(102, 'wc-completed', 'shop_order', 8900.00000000, 10, 'ana@correo.cl', '2025-08-01 12:00:00', 0, 'Webpay Oneclick'),
(103, 'wc-failed', 'shop_order', 8900.00000000, 10, 'ana@correo.cl', '2025-09-01 12:00:00', 0, 'Webpay Oneclick'),
(104, 'trash', 'shop_order', 8900.00000000, 10, 'ana@correo.cl', '2025-09-02 12:00:00', 0, ''),
(105, 'wc-delivered', 'shop_order', 12900.00000000, 0, 'beto@correo.cl', '2025-10-01 12:00:00', 0, 'Mercado Pago');

INSERT INTO `wp_wc_orders_meta` (`id`, `order_id`, `meta_key`, `meta_value`) VALUES
(1, 100, '_alumno_nombre', 'Isidora'),
(2, 100, '_alumno_apellido', 'Pérez'),
(3, 101, '_schedule_start', '2025-07-01 12:00:00'),
(4, 101, '_schedule_end', '0'),
(5, 101, '_billing_interval', '1'),
(6, 101, '_billing_period', 'month'),
(7, 102, '_subscription_renewal', '101'),
(8, 103, '_subscription_renewal', '101'),
(9, 105, '_alumno_nombre', 'Tomás');

INSERT INTO `wp_woocommerce_order_items` (`order_item_id`, `order_item_name`, `order_item_type`, `order_id`) VALUES
(1, 'Plan Individual<span> - </span>Promo', 'line_item', 100),
(2, 'Envío', 'shipping', 100),
(3, 'Plan Individual<span> - </span>Promo', 'line_item', 101),
(4, 'Pack 8 modelos', 'line_item', 105);

INSERT INTO `wp_pmpro_membership_levels` (`id`, `name`) VALUES
(6, 'PLAN INDIVIDUAL');

INSERT INTO `wp_pmpro_memberships_users` (`id`, `user_id`, `membership_id`, `status`, `startdate`, `enddate`) VALUES
(1, 10, 6, 'changed', '2025-01-01 00:00:00', '2025-03-01 00:00:00'),
(2, 10, 6, 'expired', '2025-03-01 00:00:00', '2025-05-01 00:00:00'),
(3, 10, 6, 'active', '2025-07-01 12:00:00', '0000-00-00 00:00:00');
"""


class HistorialWordPressTests(TestCase):
    def setUp(self):
        fd, self.ruta = tempfile.mkstemp(suffix='.sql')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(VOLCADO)
        self.addCleanup(os.remove, self.ruta)
        ana = User.objects.create_user(username='ana@correo.cl', email='ana@correo.cl')
        self.m = Membership.objects.create(user=ana, expires_at=timezone.now() + timedelta(days=30))
        beto = User.objects.create_user(username='beto@correo.cl', email='beto@correo.cl')
        self.m_beto = Membership.objects.create(user=beto, student_name='Tomasito',
                                                expires_at=timezone.now() + timedelta(days=30))

    def _correr(self, aplicar=True):
        call_command('historial_desde_wordpress', dump=self.ruta, aplicar=aplicar, stdout=StringIO())

    def test_sin_aplicar_no_guarda(self):
        self._correr(aplicar=False)
        self.assertFalse(H.objects.exists())

    def test_trae_compras_renovaciones_suscripciones_y_periodos(self):
        self._correr()
        ana = H.objects.filter(email='ana@correo.cl')
        self.assertEqual(ana.filter(tipo=H.COMPRA).count(), 1)
        self.assertEqual(ana.filter(tipo=H.RENOVACION).count(), 2)          # la pagada y la fallida
        self.assertEqual(ana.filter(tipo=H.SUSCRIPCION).get().detalle, 'Plan Individual – Promo · cada 1 mes')
        self.assertEqual(ana.filter(tipo=H.PERIODO).count(), 3)
        self.assertFalse(H.objects.filter(wp_id=104).exists())             # la papelera no es una compra
        compra = ana.get(tipo=H.COMPRA)
        self.assertTrue(compra.pagado)
        self.assertEqual(compra.monto, 58900)
        self.assertEqual(compra.detalle, 'Plan Individual – Promo')        # sin el envío
        self.assertFalse(ana.get(wp_id=103).pagado)
        # Sin cliente en el pedido, se usa el correo de facturación.
        self.assertTrue(H.objects.filter(email='beto@correo.cl', wp_id=105, pagado=True).exists())

    def test_rellena_el_nombre_del_alumno_solo_si_esta_vacio(self):
        self._correr()
        self.m.refresh_from_db()
        self.m_beto.refresh_from_db()
        self.assertEqual(self.m.student_name, 'Isidora Pérez')
        self.assertEqual(self.m_beto.student_name, 'Tomasito')

    def test_se_puede_correr_dos_veces(self):
        self._correr()
        n = H.objects.count()
        self._correr()
        self.assertEqual(H.objects.count(), n)

    def test_la_ficha_muestra_el_resumen(self):
        self._correr()
        admin = User.objects.create_user(username='admin@ib.cl', email='admin@ib.cl', is_staff=True)
        self.client.force_login(admin)
        r = self.client.get(reverse('panel:membership_detail', args=[self.m.pk]))
        h = r.context['historial_wp']
        self.assertEqual(h['compras'], 2)            # la compra y la renovación pagada
        self.assertEqual(h['total'], 58900 + 8900)
        self.assertEqual(h['renovaciones'], 1)
        self.assertEqual(h['fallidas'], 1)
        # Ene-Mar (cambio de plan) + Mar-May seguidos son UN tramo; julio es otro.
        self.assertEqual(h['cortes'], 1)
        self.assertEqual(h['reactivaciones'], 1)
        self.assertContains(r, 'Historial en la página anterior')

    def test_renovar_todos_los_meses_no_cuenta_como_cortes(self):
        """PMPro abre un periodo por cada renovación: 12 meses pagados seguidos
        son 12 filas, pero el acceso nunca se cortó."""
        from panel.views import _historial_wp
        inicio = timezone.now() - timedelta(days=360)
        for i in range(12):
            H.objects.create(tipo=H.PERIODO, wp_id=900 + i, email='beto@correo.cl', estado='Terminó',
                             fecha=inicio + timedelta(days=30 * i),
                             fecha_fin=inicio + timedelta(days=30 * (i + 1)) if i < 11 else None)
        h = _historial_wp(self.m_beto)
        self.assertEqual((h['cortes'], h['reactivaciones']), (0, 0))
        self.assertEqual(h['meses'], 12)

    def test_sin_historial_no_aparece(self):
        admin = User.objects.create_user(username='admin@ib.cl', email='admin@ib.cl', is_staff=True)
        self.client.force_login(admin)
        r = self.client.get(reverse('panel:membership_detail', args=[self.m.pk]))
        self.assertNotContains(r, 'Historial en la página anterior')


VOLCADO_EXTRAS = VOLCADO + """
INSERT INTO `wp_comments` (`comment_ID`, `comment_post_ID`, `comment_date`, `comment_content`, `comment_type`) VALUES
(1, 100, '2025-07-01 12:05:00', '<div class=''x''>Pago <b>aprobado</b></div>', 'order_note'),
(2, 100, '2025-07-02 09:00:00', 'El pedido se ha enviado a Shipit correctamente', 'order_note');

INSERT INTO `wp_transbank_execution_error_log` (`id`, `order_id`, `error`, `custom_error`, `created_at`) VALUES
(1, 103, 'x', 'Tarjeta rechazada', '2025-09-01 12:01:00');

INSERT INTO `wp_usermeta` (`umeta_id`, `user_id`, `meta_key`, `meta_value`) VALUES
(1, 10, 'billing_first_name', 'Ana'),
(2, 10, 'billing_address_1', 'Calle Falsa 123'),
(3, 10, 'billing_city', 'Ñuñoa'),
(4, 10, 'pmpro_logins', 'a:2:{s:4:"last";s:15:"October 9, 2026";s:7:"alltime";i:42;}'),
(5, 10, 'wc_last_active', '1792454400');

INSERT INTO `wp_wpmailsmtp_emails_log` (`id`, `subject`, `people`, `status`, `date_sent`) VALUES
(7, 'Tu pedido ya está completo', '{"to":["ana@correo.cl"]}', '1', '2025-07-01 12:10:00'),
(8, 'Nuevo modelo disponible', '{"to":["ana@correo.cl"]}', '0', '2025-07-08 12:10:00');

INSERT INTO `wp_e_submissions` (`id`, `form_name`, `referer`, `created_at_gmt`, `created_at`) VALUES
(5, 'New Form', 'https://ingenioblocks.com/', '2025-05-01 10:00:00', '2025-05-01 06:00:00');

INSERT INTO `wp_e_submissions_values` (`id`, `submission_id`, `key`, `value`) VALUES
(1, 5, 'name', 'Pedro'),
(2, 5, 'email', 'pedro@correo.cl'),
(3, 5, 'field_16509eb', '+56912345678'),
(4, 5, 'field_8ac25fa', '¿Tienen envío a regiones?');

INSERT INTO `wp_posts` (`ID`, `post_title`, `post_type`, `post_status`) VALUES
(900, 'niño26', 'shop_coupon', 'publish');

INSERT INTO `wp_postmeta` (`meta_id`, `post_id`, `meta_key`, `meta_value`) VALUES
(1, 900, 'discount_type', 'fixed_cart'),
(2, 900, 'coupon_amount', '10490'),
(3, 900, 'usage_limit', '2');
"""


class DatosExtraWordPressTests(TestCase):
    def setUp(self):
        fd, self.ruta = tempfile.mkstemp(suffix='.sql')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(VOLCADO_EXTRAS)
        self.addCleanup(os.remove, self.ruta)
        ana = User.objects.create_user(username='ana@correo.cl', email='ana@correo.cl')
        self.m = Membership.objects.create(user=ana, expires_at=timezone.now() + timedelta(days=30))

    def _correr(self):
        call_command('historial_desde_wordpress', dump=self.ruta, aplicar=True, stdout=StringIO())

    def test_trae_notas_correos_perfil_mensajes_y_cupones(self):
        from catalog.models import MensajeContacto
        from lms.models import PerfilWordPress
        from payments.models import Coupon
        self._correr()
        self._correr()   # repetirlo no duplica nada
        compra = H.objects.get(tipo=H.COMPRA, wp_id=100)
        self.assertEqual([t for _, t in compra.notas], ['Pago aprobado',
                                                         'El pedido se ha enviado a Shipit correctamente'])
        self.assertIn('Transbank: Tarjeta rechazada', [t for _, t in H.objects.get(wp_id=103).notas])
        correos = H.objects.filter(tipo=H.CORREO, email='ana@correo.cl')
        self.assertEqual(correos.count(), 2)
        self.assertEqual(correos.get(detalle='Nuevo modelo disponible').estado, 'No salió')
        datos = PerfilWordPress.objects.get(email='ana@correo.cl').datos
        self.assertEqual(datos['ingresos'], 42)
        self.assertEqual(datos['facturacion']['city'], 'Ñuñoa')
        self.assertIn('ultima_actividad', datos)
        msj = MensajeContacto.objects.get()
        self.assertEqual((msj.nombre, msj.telefono, msj.leido), ('Pedro', '+56912345678', True))
        cupon = Coupon.objects.get()
        self.assertEqual((cupon.code, cupon.discount_type, cupon.value, cupon.max_uses, cupon.is_active),
                         ('NIÑO26', 'AMOUNT', 10490, 2, False))

    def test_la_ficha_muestra_perfil_notas_y_correos(self):
        self._correr()
        admin = User.objects.create_user(username='admin@ib.cl', email='admin@ib.cl', is_staff=True)
        self.client.force_login(admin)
        r = self.client.get(reverse('panel:membership_detail', args=[self.m.pk]))
        self.assertContains(r, 'Calle Falsa 123')
        self.assertContains(r, 'Correos que recibió')
        self.assertContains(r, 'notas del pedido')
        self.assertNotContains(r, 'Correo enviado</span>')   # los correos no van en la tabla de compras
