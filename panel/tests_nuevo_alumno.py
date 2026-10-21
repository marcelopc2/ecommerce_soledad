"""Alta manual de un alumno desde el panel (pagó por fuera, regalo, beca)."""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from lms.models import CategoryCourse, Course, CourseCategory, Lesson, Membership, UnlockNotice
from lms.services import get_course_access

User = get_user_model()


class NuevoAlumnoTests(TestCase):
    def setUp(self):
        admin = User.objects.create_user(username='admin@ib.cl', email='admin@ib.cl', is_staff=True)
        self.client.force_login(admin)
        self.cat = CourseCategory.objects.create(nombre='General', slug='general', cursos_iniciales=2)
        for i in range(1, 6):
            c = Course.objects.create(title=f'00{i} - Modelo {i}', slug=f'm{i}', order=i, is_active=True)
            Lesson.objects.create(course=c, title='Paso 1', order=1)
            CategoryCourse.objects.create(categoria=self.cat, curso=c, orden=i)

    def crear(self, **extra):
        hoy = timezone.localdate()
        datos = {'email': 'Nueva.Alumna@Correo.cl', 'parent_name': 'Ana Pérez', 'student_name': 'Beni Pérez',
                 'phone': '+56 9 1111 2222', 'categorias': [self.cat.pk], 'inicio': hoy.isoformat(),
                 'hasta': (hoy + timedelta(days=180)).isoformat(), 'enviar_bienvenida': 'on'}
        datos.update(extra)
        return self.client.post(reverse('panel:membership_new'), datos)

    def test_la_lista_tiene_el_boton(self):
        self.assertContains(self.client.get(reverse('panel:memberships')), reverse('panel:membership_new'))

    @override_settings(ENVIAR_CORREOS=True)
    def test_crea_cuenta_membresia_y_manda_la_bienvenida(self):
        r = self.crear()
        m = Membership.objects.get(user__email='nueva.alumna@correo.cl')
        self.assertRedirects(r, reverse('panel:membership_detail', args=[m.pk]))
        self.assertEqual((m.student_name, m.parent_name, m.user.username), ('Beni Pérez', 'Ana Pérez', 'nueva.alumna@correo.cl'))
        self.assertFalse(m.user.has_usable_password())
        self.assertTrue(m.is_active)
        self.assertEqual(timezone.localtime(m.expires_at).date(), timezone.localdate() + timedelta(days=180))
        self.assertEqual([c.pk for c in m.categorias.all()], [self.cat.pk])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['nueva.alumna@correo.cl'])

    def test_si_empezo_antes_ya_tiene_abiertas_esas_semanas_y_no_se_le_avisan(self):
        inicio = timezone.localdate() - timedelta(days=21)
        self.crear(inicio=inicio.isoformat(), enviar_bienvenida='')
        m = Membership.objects.get(user__email='nueva.alumna@correo.cl')
        fechas = [a['unlock_date'] for a in get_course_access(m)]
        self.assertEqual(fechas[3], inicio + timedelta(weeks=2))
        abiertos = sum(1 for a in get_course_access(m) if a['unlocked'])
        self.assertEqual(UnlockNotice.objects.filter(membership=m).count(), abiertos)
        self.assertEqual(len(mail.outbox), 0)

    def test_un_correo_que_ya_es_alumno_no_se_duplica(self):
        self.crear(enviar_bienvenida='')
        r = self.crear(email='nueva.alumna@correo.cl')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Ese correo ya es alumno')
        self.assertEqual(Membership.objects.count(), 1)

    def test_no_se_le_da_membresia_a_una_cuenta_de_gestion(self):
        r = self.crear(email='admin@ib.cl')
        self.assertContains(r, 'cuenta de gestión')

    def test_el_fin_no_puede_ser_antes_del_inicio(self):
        r = self.crear(hasta=(timezone.localdate() - timedelta(days=1)).isoformat())
        self.assertContains(r, 'no puede terminar antes de empezar')
        self.assertFalse(Membership.objects.exists())

    def test_solo_gestion(self):
        alumno = User.objects.create_user(username='x@y.cl', email='x@y.cl')
        self.client.force_login(alumno)
        self.crear()
        self.assertFalse(Membership.objects.exists())
