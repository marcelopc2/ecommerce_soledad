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


class PedidosWordPressTests(TestCase):
    def test_lista_los_pedidos_de_la_pagina_anterior(self):
        from lms.models import HistorialWordPress as H
        admin = User.objects.create_user(username='admin@ib.cl', email='admin@ib.cl', is_staff=True)
        self.client.force_login(admin)
        u = User.objects.create_user(username='ana@b.cl', email='ana@b.cl')
        m = Membership.objects.create(user=u, expires_at=timezone.now())
        H.objects.create(tipo=H.COMPRA, wp_id=55, email='ana@b.cl', fecha=timezone.now(), estado='Completado',
                         pagado=True, monto=58900, detalle='Kit', notas=[['2025-07-01 12:00:00', 'Pago aprobado']])
        H.objects.create(tipo=H.CORREO, wp_id=56, email='ana@b.cl', fecha=timezone.now(), detalle='Hola')
        r = self.client.get(reverse('panel:pedidos_wordpress'))
        self.assertContains(r, '#55')
        self.assertContains(r, reverse('panel:membership_detail', args=[m.pk]))
        self.assertContains(r, 'Pago aprobado')
        self.assertNotContains(r, '#56')   # los correos no son pedidos


class PausaCorreosTests(TestCase):
    """Correos a clientes en pausa aunque el sitio ya esté en el dominio real."""

    def setUp(self):
        self.admin = User.objects.create_user(username='admin@ib.cl', email='admin@ib.cl', is_staff=True)
        self.client.force_login(self.admin)

    def _mandar(self):
        from django.core import mail
        from core.emails import enviar_email
        mail.outbox = []
        enviar_email('contacto_interno', asunto='x', destinatarios=['cliente@correo.cl', 'admin@ib.cl'],
                     contexto={'nombre': 'a', 'email': 'a@b.cl'})
        return sorted(d for m in mail.outbox for d in m.to)

    def test_en_pausa_solo_le_llega_al_equipo(self):
        from django.test import override_settings
        with override_settings(ENVIAR_CORREOS=True):
            self.assertIn('cliente@correo.cl', self._mandar())
            self.client.post(reverse('panel:correos_interruptor'), {'valor': '0'})
            self.assertEqual(self._mandar(), ['admin@ib.cl'])
            r = self.client.get(reverse('panel:dashboard'))
            self.assertContains(r, 'Correos a clientes en pausa')
            self.client.post(reverse('panel:correos_interruptor'), {'valor': '1'})
            self.assertIn('cliente@correo.cl', self._mandar())

    def test_el_interruptor_se_ve(self):
        from comunicaciones.models import AjustesCorreos
        r = self.client.get(reverse('panel:interruptores'))
        self.assertContains(r, 'Correos a clientes')
        self.client.post(reverse('panel:correos_interruptor'), {'valor': '0'})
        self.assertTrue(AjustesCorreos.obtener().pausar_correos_a_clientes)
