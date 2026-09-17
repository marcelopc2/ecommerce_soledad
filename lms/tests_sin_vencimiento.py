"""Membresías sin fecha de término.

En el sistema viejo las suscripciones mensuales NO caducaban: PMPro las deja
activas con `0000-00-00` y el cobro va por Transbank Oneclick por fuera, hasta
que alguien se da de baja. Al migrarlas había que inventarles una fecha, y
cualquier fecha inventada o dejaba gente afuera o regalaba meses: el primer
intento dejó a 128 de 296 alumnos venciendo todos el mismo día.

Ahora se respeta lo que dice el sistema viejo. Lo que se prueba acá es que
"sin vencimiento" signifique lo mismo en los tres lugares donde se decide si
alguien entra o no: la propiedad, las consultas del panel, y el momento en que
paga y vuelve a funcionar por fecha.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from lms.models import Membership

User = get_user_model()


def _membresia(correo, **extra):
    u = User.objects.create_user(username=correo, email=correo)
    datos = {'expires_at': timezone.now() - timedelta(days=400)}
    datos.update(extra)
    return Membership.objects.create(user=u, **datos)


class EstadoTests(TestCase):
    def test_sin_vencimiento_esta_activa_aunque_la_fecha_haya_pasado(self):
        """Es el punto de todo: la fecha que arrastra es basura y no se mira."""
        m = _membresia('a@b.cl', sin_vencimiento=True)
        self.assertTrue(m.is_active)

    def test_sin_el_flag_la_fecha_vieja_la_deja_vencida(self):
        self.assertFalse(_membresia('c@d.cl').is_active)

    def test_pausada_gana_sobre_sin_vencimiento(self):
        """Pausar es una decisión deliberada de la administradora: no puede
        quedar sin efecto porque la membresía venga abierta."""
        m = _membresia('e@f.cl', sin_vencimiento=True)
        m.pause()
        self.assertFalse(m.is_active)


class ConsultasTests(TestCase):
    """La base y la propiedad no pueden contradecirse: si el panel la cuenta
    como activa, el alumno tiene que poder entrar, y al revés."""

    def setUp(self):
        self.abierta = _membresia('abierta@b.cl', sin_vencimiento=True)
        self.vigente = _membresia('vigente@b.cl',
                                  expires_at=timezone.now() + timedelta(days=10))
        self.vencida = _membresia('vencida@b.cl')
        self.pausada = _membresia('pausada@b.cl', sin_vencimiento=True)
        self.pausada.pause()

    def test_la_consulta_cuenta_las_abiertas_como_vigentes(self):
        vigentes = set(Membership.objects.filter(Membership.VIGENTE)
                       .values_list('user__email', flat=True))
        self.assertEqual(vigentes, {'abierta@b.cl', 'vigente@b.cl'})

    def test_la_consulta_coincide_con_la_propiedad(self):
        for m in Membership.objects.all():
            esta = Membership.objects.filter(Membership.VIGENTE, pk=m.pk).exists()
            self.assertEqual(esta, m.is_active, m.user.email)


class PrimerPagoTests(TestCase):
    """Con el primer pago desde el sitio nuevo vuelve a funcionar por fecha."""

    def _comprar(self, membership, meses=1):
        from catalog.models import Category, Product
        from lms.models import CategoryCourse, Course, CourseCategory
        from lms.services import grant_access_for_order
        from payments.models import Order

        cat = Category.objects.create(name='Kits', slug='kits')
        prod = Product.objects.create(name='Kit', slug='kit', price=1000,
                                      category=cat, is_active=True,
                                      access_months=meses)
        cc = CourseCategory.objects.create(nombre='General', slug='general')
        curso = Course.objects.create(title='M1', slug='m1', order=1)
        CategoryCourse.objects.create(categoria=cc, curso=curso, orden=1)
        prod.categories.add(cc)

        orden = Order.objects.create(customer_email=membership.user.email,
                                     total_amount=1000, status='PAID')
        orden.products.set([prod])
        return grant_access_for_order(orden)

    def test_el_pago_apaga_el_sin_vencimiento(self):
        """Desde que paga por acá somos nosotros los que cobramos: dejarla
        abierta sería regalarle el acceso para siempre."""
        m = _membresia('paga@b.cl', sin_vencimiento=True)
        m = self._comprar(m)
        self.assertFalse(m.sin_vencimiento)

    def test_la_nueva_fecha_se_cuenta_desde_hoy(self):
        """Y no desde el expires_at viejo, que es una fecha que nunca se usó:
        contarlo desde ahí le daría un mes ya vencido."""
        m = _membresia('paga2@b.cl', sin_vencimiento=True)
        m = self._comprar(m, meses=1)
        self.assertTrue(m.is_active)
        self.assertGreater(m.expires_at, timezone.now() + timedelta(days=27))


class FechaAManoTests(TestCase):
    """Ponerle una fecha desde el panel es decir "esta sí vence"."""

    def test_guardar_un_vencimiento_cierra_la_membresia_abierta(self):
        from django.urls import reverse
        admin = User.objects.create_user(username='admin@x.cl', email='admin@x.cl',
                                         password='clave-larga-1234', is_staff=True)
        self.client.force_login(admin)
        m = _membresia('abierta2@b.cl', sin_vencimiento=True)

        hasta = (timezone.now() + timedelta(days=30)).date().isoformat()
        self.client.post(reverse('panel:membership_expiry_update', args=[m.pk]),
                         {'hasta': hasta})
        m.refresh_from_db()
        self.assertFalse(m.sin_vencimiento)
        # En hora LOCAL: la vista guarda el final de ese día, que en UTC ya es
        # el día siguiente. Es a propósito -"vence el 10" significa que el 10
        # todavía puede entrar-, así que comparar en UTC daba un día de más.
        self.assertEqual(timezone.localtime(m.expires_at).date().isoformat(), hasta)
