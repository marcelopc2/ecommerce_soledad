"""Editar los datos de contacto de un alumno desde el panel.

El correo es el caso delicado: en este proyecto el `username` ES el correo, así
que cambiarlo cambia con qué inicia sesión la persona. Si el formulario tocara
solo `email`, el alumno seguiría entrando con el viejo y el nuevo no le serviría
—sin ningún error visible para nadie—.
"""
from datetime import timedelta

from django.contrib.auth import authenticate, get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from lms.models import Membership
from payments.models import Order

User = get_user_model()

CLAVE = 'clave-larga-de-prueba-1234'


class DatosDelAlumnoTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin@ingenioblocks.com', email='admin@ingenioblocks.com',
            password=CLAVE, is_staff=True,
        )
        self.client.force_login(self.admin)

        self.alumno = User.objects.create_user(
            username='mama@correo.cl', email='mama@correo.cl', password=CLAVE,
        )
        self.m = Membership.objects.create(
            user=self.alumno, expires_at=timezone.now() + timedelta(days=90),
            student_name='Beni', parent_name='Ana', phone='+56911111111',
        )
        self.url = reverse('panel:membership_names_update', args=[self.m.pk])

    def _guardar(self, **campos):
        datos = {
            'student_name': 'Beni', 'parent_name': 'Ana',
            'phone': '+56911111111', 'email': 'mama@correo.cl',
        }
        datos.update(campos)
        return self.client.post(self.url, datos)

    # --- nombres y teléfono ---

    def test_se_edita_el_nombre_del_alumno(self):
        self._guardar(student_name='Benjamín')
        self.m.refresh_from_db()
        self.assertEqual(self.m.student_name, 'Benjamín')

    def test_se_edita_el_telefono(self):
        self._guardar(phone='+56 9 8765 4321')
        self.m.refresh_from_db()
        self.assertEqual(self.m.phone, '+56 9 8765 4321')

    def test_el_telefono_se_acepta_como_lo_escriban(self):
        """Quien escribe es la administradora corrigiendo un dato: a veces tiene
        un fijo, uno extranjero o una anotación al lado. Rechazárselo sería
        impedirle guardar el único contacto que tiene."""
        self._guardar(phone='222 345 678 (casa)')
        self.m.refresh_from_db()
        self.assertEqual(self.m.phone, '222 345 678 (casa)')

    def test_el_telefono_puede_quedar_vacio(self):
        self._guardar(phone='')
        self.m.refresh_from_db()
        self.assertEqual(self.m.phone, '')

    # --- correo ---

    def test_cambiar_el_correo_cambia_tambien_el_usuario(self):
        """Lo que de verdad importa: si solo cambiara `email`, la persona
        seguiría entrando con el correo viejo."""
        self._guardar(email='nueva@correo.cl')
        self.alumno.refresh_from_db()
        self.assertEqual(self.alumno.email, 'nueva@correo.cl')
        self.assertEqual(self.alumno.username, 'nueva@correo.cl')

    def _entra(self, correo):
        """django-axes exige el `request` para poder contar los intentos, así
        que authenticate() sin él revienta en vez de responder."""
        peticion = RequestFactory().post('/gestion/ingresar/')
        return authenticate(peticion, username=correo, password=CLAVE)

    def test_despues_de_cambiarlo_entra_con_el_nuevo(self):
        self._guardar(email='nueva@correo.cl')
        self.assertIsNotNone(self._entra('nueva@correo.cl'))

    def test_y_ya_no_entra_con_el_viejo(self):
        self._guardar(email='nueva@correo.cl')
        self.assertIsNone(self._entra('mama@correo.cl'))

    def test_se_normaliza_a_minusculas_y_sin_espacios(self):
        self._guardar(email='  NUEVA@Correo.CL  ')
        self.alumno.refresh_from_db()
        self.assertEqual(self.alumno.username, 'nueva@correo.cl')

    def test_no_se_puede_poner_el_correo_de_otra_cuenta(self):
        """Antes esto reventaba con un IntegrityError -username es único- y la
        clienta veía un error 500 en vez de una explicación."""
        User.objects.create_user(username='otra@correo.cl', email='otra@correo.cl',
                                 password=CLAVE)
        r = self._guardar(email='otra@correo.cl')
        self.assertEqual(r.status_code, 200)
        self.alumno.refresh_from_db()
        self.assertEqual(self.alumno.username, 'mama@correo.cl')   # intacto
        self.assertContains(r, 'ya lo usa otra cuenta')

    def test_guardar_sin_cambiar_el_correo_no_choca_consigo_mismo(self):
        """El propio alumno no puede contar como 'otra cuenta que ya lo usa'."""
        r = self._guardar(student_name='Beni II')
        self.m.refresh_from_db()
        self.assertEqual(self.m.student_name, 'Beni II')
        self.assertNotContains(r, 'ya lo usa otra cuenta')

    def test_un_correo_invalido_se_rechaza(self):
        self._guardar(email='esto no es un correo')
        self.alumno.refresh_from_db()
        self.assertEqual(self.alumno.username, 'mama@correo.cl')

    def test_el_cambio_de_correo_queda_en_el_log(self):
        """Si mañana alguien dice "no puedo entrar", esa línea es la única forma
        de saber que el correo se editó, cuándo y quién lo hizo."""
        with self.assertLogs('ingenioblocks.pagos', level='INFO') as registro:
            self._guardar(email='nueva@correo.cl')
        self.assertTrue(any('nueva@correo.cl' in linea for linea in registro.output))


class TelefonoDesdeLaCompraTests(TestCase):
    """El teléfono se rellena solo desde el checkout, como los nombres."""

    def test_una_compra_rellena_el_telefono_si_estaba_vacio(self):
        from lms.services import grant_access_for_order
        from catalog.models import Product, Category

        categoria = Category.objects.create(name='Kits', slug='kits')
        producto = Product.objects.create(
            name='Kit', slug='kit', price=1000, is_active=True,
            category=categoria, access_months=12,
        )
        from lms.models import CourseCategory, Course, CategoryCourse
        cat = CourseCategory.objects.create(nombre='General', slug='general')
        curso = Course.objects.create(title='Modelo 1', slug='modelo-1', order=1)
        CategoryCourse.objects.create(categoria=cat, curso=curso, orden=1)
        producto.categories.add(cat)

        order = Order.objects.create(
            customer_email='nueva@correo.cl', customer_name='Ana',
            student_name='Beni', customer_phone='+56922222222',
            total_amount=1000, status='PAID',
        )
        order.products.set([producto])

        membership = grant_access_for_order(order)
        self.assertEqual(membership.phone, '+56922222222')

    def test_una_compra_posterior_no_pisa_el_telefono_corregido(self):
        """Mismo criterio que los nombres: si la clienta lo corrigió a mano, una
        compra nueva no debe deshacer esa corrección."""
        from lms.services import grant_access_for_order
        from catalog.models import Product, Category
        from lms.models import CourseCategory, Course, CategoryCourse

        categoria = Category.objects.create(name='Kits', slug='kits')
        producto = Product.objects.create(
            name='Kit', slug='kit', price=1000, is_active=True,
            category=categoria, access_months=12,
        )
        cat = CourseCategory.objects.create(nombre='General', slug='general')
        curso = Course.objects.create(title='Modelo 1', slug='modelo-1', order=1)
        CategoryCourse.objects.create(categoria=cat, curso=curso, orden=1)
        producto.categories.add(cat)

        usuario = User.objects.create_user(username='x@correo.cl', email='x@correo.cl')
        Membership.objects.create(
            user=usuario, expires_at=timezone.now() + timedelta(days=30),
            phone='+56999999999',
        )

        order = Order.objects.create(
            customer_email='x@correo.cl', customer_phone='+56911111111',
            total_amount=1000, status='PAID',
        )
        order.products.set([producto])

        membership = grant_access_for_order(order)
        self.assertEqual(membership.phone, '+56999999999')
