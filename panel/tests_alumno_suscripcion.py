"""Alumnos y Suscripciones son pantallas separadas, pero conectadas.

El acceso al Aula (Alumnos) y el cobro automático (Suscripciones) son cosas
distintas y la mayoría de los alumnos pagó una sola vez. Lo que no puede
pasar es que, mirando a un alumno, no se sepa que se le cobra solo, ni que
desde una suscripción no se llegue al alumno.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import Product
from lms.models import Membership
from payments.models import Suscripcion, TarjetaOneclick

User = get_user_model()


def alumno(correo, nombre):
    u = User.objects.create_user(username=correo, email=correo)
    return Membership.objects.create(user=u, student_name=nombre,
                                     expires_at=timezone.now() + timedelta(days=30))


class AlumnoSuscripcionTests(TestCase):
    def setUp(self):
        admin = User.objects.create_user(username='admin@ib.cl', email='admin@ib.cl', is_staff=True)
        self.client.force_login(admin)
        # El correo con mayúsculas en la cuenta: el cruce no puede depender de eso.
        self.con = alumno('Mama@Correo.cl', 'Beni')
        self.sin = alumno('papa@correo.cl', 'Tomi')
        producto = Product.objects.create(name='Membresía Familiar', slug='mf', price=4990,
                                          is_digital=True, es_suscripcion=True, access_months=1)
        tarjeta = TarjetaOneclick.objects.create(email='mama@correo.cl', username='u', tbk_user='t',
                                                 tipo='Visa', ultimos4='6623')
        self.s = Suscripcion.objects.create(
            email='mama@correo.cl', producto=producto, tarjeta=tarjeta, monto=4990, cada_meses=1,
            proximo_cobro=timezone.localdate() + timedelta(days=10), origen=Suscripcion.WORDPRESS,
            nombre='Plan Individual - Trimestral',
        )

    def test_la_lista_de_alumnos_marca_y_filtra_a_los_que_tienen_suscripcion(self):
        r = self.client.get(reverse('panel:memberships'))
        self.assertContains(r, '1 con suscripción')
        self.assertContains(r, reverse('panel:suscripcion_detalle', args=[self.s.pk]))
        r = self.client.get(reverse('panel:memberships') + '?con_sub=1')
        self.assertContains(r, 'Beni')
        self.assertNotContains(r, 'Tomi')

    def test_una_cancelada_no_cuenta_como_con_suscripcion(self):
        self.s.estado = Suscripcion.CANCELADA
        self.s.save()
        r = self.client.get(reverse('panel:memberships') + '?con_sub=1')
        self.assertNotContains(r, 'Beni')

    def test_el_detalle_del_alumno_muestra_su_cobro_automatico(self):
        r = self.client.get(reverse('panel:membership_detail', args=[self.con.pk]))
        self.assertContains(r, 'Cobro automático')
        self.assertContains(r, 'Plan Individual - Trimestral')
        self.assertContains(r, 'Acceso al Aula')
        self.assertContains(r, reverse('panel:suscripcion_detalle', args=[self.s.pk]))
        r = self.client.get(reverse('panel:membership_detail', args=[self.sin.pk]))
        self.assertNotContains(r, 'Cobro automático')

    def test_desde_la_suscripcion_se_llega_al_alumno(self):
        url_alumno = reverse('panel:membership_detail', args=[self.con.pk])
        self.assertContains(self.client.get(reverse('panel:suscripcion_detalle', args=[self.s.pk])), url_alumno)
        self.assertContains(self.client.get(reverse('panel:suscripciones')), url_alumno)
