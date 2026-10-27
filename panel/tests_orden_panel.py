"""El panel ordenado: menú de 8 entradas, pendientes en Inicio, Interruptores y buscador."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import SeccionClub
from lms.models import Membership
from payments.models import AjustesCobros

User = get_user_model()


class OrdenPanelTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin@ib.cl', email='admin@ib.cl', is_staff=True)
        self.client.force_login(self.admin)

    def test_el_menu_tiene_ocho_entradas_y_pestanas(self):
        r = self.client.get(reverse('panel:products'))
        for entrada in ('Inicio', 'Pedidos', 'Alumnos', 'Productos', 'Cursos', 'Portada', 'Correos', 'Ajustes'):
            self.assertContains(r, entrada)
        self.assertContains(r, 'pnl-subnav')
        self.assertContains(r, reverse('panel:coupons'))   # Cupones como pestaña de Productos
        self.assertNotContains(r, 'pnl-nav-label">Tienda')

    def test_cuentas_de_gestion_solo_para_la_cuenta_principal(self):
        r = self.client.get(reverse('panel:interruptores'))
        self.assertNotContains(r, 'Cuentas de gestión')

    def test_inicio_muestra_los_pendientes(self):
        u = User.objects.create_user(username='a@b.cl', email='a@b.cl')
        Membership.objects.create(user=u, expires_at=timezone.now() + timedelta(days=3))
        r = self.client.get(reverse('panel:dashboard'))
        self.assertContains(r, 'Alumnos que vencen esta semana')
        r = self.client.get(reverse('panel:memberships') + '?estado=por_vencer')
        self.assertContains(r, 'a@b.cl')

    def test_inicio_sin_pendientes(self):
        self.assertContains(self.client.get(reverse('panel:dashboard')), 'Todo al día')

    def test_interruptores_cambian_lo_mismo_que_antes(self):
        self.client.post(reverse('panel:cobros_ajustes'),
                         {'campo': 'cobros_automaticos', 'valor': '1', 'volver': reverse('panel:interruptores')})
        self.assertTrue(AjustesCobros.obtener().cobros_automaticos)
        r = self.client.post(reverse('panel:club_interruptor'), {'valor': '1', 'volver': reverse('panel:interruptores')})
        self.assertRedirects(r, reverse('panel:interruptores'))
        self.assertTrue(SeccionClub.obtener().visible)
        # Un "volver" a otro sitio se ignora.
        r = self.client.post(reverse('panel:club_interruptor'), {'valor': '0', 'volver': 'https://otro.com/'})
        self.assertRedirects(r, reverse('panel:cfg_club'), fetch_redirect_response=False)

    def test_buscador(self):
        u = User.objects.create_user(username='isidora@correo.cl', email='isidora@correo.cl')
        m = Membership.objects.create(user=u, student_name='Isidora Pérez', expires_at=timezone.now())
        r = self.client.get(reverse('panel:buscar'), {'q': 'perez'})
        self.assertContains(r, reverse('panel:membership_detail', args=[m.pk]))
        self.assertContains(self.client.get(reverse('panel:buscar'), {'q': 'x'}), 'Escribe')

    def test_buscador_solo_gestion(self):
        alumno = User.objects.create_user(username='a@b.cl', email='a@b.cl')
        self.client.force_login(alumno)
        r = self.client.get(reverse('panel:buscar'), {'q': 'admin'})
        self.assertNotEqual(r.status_code, 200)
