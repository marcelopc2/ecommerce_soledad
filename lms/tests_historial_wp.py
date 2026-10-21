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
