"""Borrar una compra de prueba desde el panel.

Es la acción más destructiva del CMS: no tiene deshacer y se lleva la boleta, el
envío y -a veces- la cuenta del alumno. Estos tests fijan exactamente hasta
dónde llega, para que nadie la amplíe sin darse cuenta.
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from catalog.models import Product
from invoicing.models import Invoice
from lms.models import Membership
from payments.models import Order


@override_settings(AXES_ENABLED=False)
class BorrarCompraTests(TestCase):

    def setUp(self):
        self.dueno = User.objects.create_user(
            username='dueno@ingenioblocks.com', email='dueno@ingenioblocks.com',
            password='UnaClaveLarga123', is_staff=True, is_superuser=True,
        )
        self.ayudante = User.objects.create_user(
            username='ayudante@ingenioblocks.com', email='ayudante@ingenioblocks.com',
            password='UnaClaveLarga123', is_staff=True,
        )
        self.producto = Product.objects.create(
            name='Kit de prueba', slug='kit-prueba', price=10000, access_months=12)

    def _compra(self, email='cliente@test.cl'):
        o = Order.objects.create(total_amount=10000, status='PAID', customer_email=email)
        o.products.add(self.producto)
        Invoice.objects.create(order=o, status='ISSUED', folio='123')
        return o

    def _alumno(self, orden, email='cliente@test.cl'):
        u = User.objects.create_user(username=email, email=email)
        m = Membership.objects.create(user=u, expires_at=timezone.now() + timedelta(days=365))
        m.orders.add(orden)
        return u, m

    # --- permisos ----------------------------------------------------------

    def test_un_ayudante_no_puede_borrar_compras(self):
        """Borrar una venta destruye el respaldo contable de esa operación, y en
        el listado una compra de prueba se ve igual que una real."""
        orden = self._compra()
        self.client.force_login(self.ayudante)
        self.client.post(reverse('panel:order_delete', args=[orden.pk]))
        self.assertTrue(Order.objects.filter(pk=orden.pk).exists())

    def test_un_anonimo_tampoco(self):
        orden = self._compra()
        self.client.post(reverse('panel:order_delete', args=[orden.pk]))
        self.assertTrue(Order.objects.filter(pk=orden.pk).exists())

    def test_no_se_borra_con_un_GET(self):
        """Si bastara un GET, un rastreador siguiendo enlaces borraría ventas."""
        orden = self._compra()
        self.client.force_login(self.dueno)
        self.client.get(reverse('panel:order_delete', args=[orden.pk]))
        self.assertTrue(Order.objects.filter(pk=orden.pk).exists())

    # --- qué se lleva por delante -----------------------------------------

    def test_borra_la_compra_con_su_boleta(self):
        orden = self._compra()
        self.client.force_login(self.dueno)
        self.client.post(reverse('panel:order_delete', args=[orden.pk]))
        self.assertFalse(Order.objects.filter(pk=orden.pk).exists())
        self.assertFalse(Invoice.objects.exists(), 'la boleta se va en cascada')

    def test_borra_tambien_la_cuenta_de_alumno_que_creo(self):
        """Sin esto, cada compra de prueba deja un alumno fantasma con acceso a
        un Aula que nunca pagó."""
        orden = self._compra()
        usuario, _ = self._alumno(orden)
        self.client.force_login(self.dueno)
        self.client.post(reverse('panel:order_delete', args=[orden.pk]))

        self.assertFalse(User.objects.filter(pk=usuario.pk).exists())
        self.assertFalse(Membership.objects.exists())

    def test_si_el_alumno_compro_otras_veces_conserva_su_cuenta(self):
        """Solo se desvincula esta compra: borrarle la cuenta le quitaría el
        acceso a lo demás que SÍ pagó."""
        primera = self._compra()
        segunda = self._compra()
        usuario, membresia = self._alumno(primera)
        membresia.orders.add(segunda)

        self.client.force_login(self.dueno)
        self.client.post(reverse('panel:order_delete', args=[primera.pk]))

        self.assertTrue(User.objects.filter(pk=usuario.pk).exists())
        membresia.refresh_from_db()
        self.assertEqual(list(membresia.orders.all()), [segunda])

    def test_no_borra_una_cuenta_de_gestion_que_compro_para_probar(self):
        """La clienta compra un kit para ver el Aula por dentro. Borrar esa
        compra no puede dejarla fuera del panel."""
        orden = self._compra(email=self.ayudante.email)
        membresia = Membership.objects.create(
            user=self.ayudante, expires_at=timezone.now() + timedelta(days=365))
        membresia.orders.add(orden)

        self.client.force_login(self.dueno)
        self.client.post(reverse('panel:order_delete', args=[orden.pk]))

        self.assertTrue(User.objects.filter(pk=self.ayudante.pk).exists())
        self.assertTrue(User.objects.get(pk=self.ayudante.pk).is_staff)
        self.assertFalse(Membership.objects.exists(), 'su membresía sí se va')

    def test_no_toca_las_demas_compras(self):
        borrar = self._compra(email='a@test.cl')
        conservar = self._compra(email='b@test.cl')
        self.client.force_login(self.dueno)
        self.client.post(reverse('panel:order_delete', args=[borrar.pk]))
        self.assertEqual(list(Order.objects.all()), [conservar])
