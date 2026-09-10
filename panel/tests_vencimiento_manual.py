"""Cambiar a mano hasta cuándo tiene acceso un alumno, desde el panel.

Es la contraparte manual de una compra: da o quita acceso pagado con un clic y
sin que haya plata de por medio, así que estos tests fijan hasta dónde llega
—quién puede hacerlo, qué día queda realmente cubierto, y qué pasa con el
calendario semanal al revivir una cuenta vencida—.
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from lms.models import (
    AjustesAula, CategoryCourse, Course, CourseCategory, Lesson, Membership,
    MembershipCategory,
)
from lms.services import get_course_access


@override_settings(AXES_ENABLED=False)
class VencimientoManualTests(TestCase):

    def setUp(self):
        ajustes = AjustesAula.obtener()
        ajustes.cursos_iniciales = 3
        ajustes.save()

        self.dueno = User.objects.create_user(
            username='dueno@ingenioblocks.com', email='dueno@ingenioblocks.com',
            password='UnaClaveLarga123', is_staff=True, is_superuser=True,
        )
        self.alumna = User.objects.create_user(
            username='alumna@test.cl', email='alumna@test.cl')
        self.membresia = Membership.objects.create(
            user=self.alumna, expires_at=timezone.now() + timedelta(days=10),
        )

        self.categoria = CourseCategory.objects.create(
            nombre='General', slug='general', cursos_iniciales=3)
        for i in range(1, 11):
            c = Course.objects.create(title=f'Modelo {i}', slug=f'modelo-{i}', order=i)
            Lesson.objects.create(
                course=c, title=f'Armado {i}', order=1, lesson_type='VIDEO',
                video_embed_url='https://www.youtube.com/embed/abc12345678',
            )
            CategoryCourse.objects.create(categoria=self.categoria, curso=c, orden=i)
        self.mc = MembershipCategory.objects.create(
            membership=self.membresia, categoria=self.categoria,
            obtenida_en=timezone.now(),
        )

    def _url(self):
        return reverse('panel:membership_expiry_update', args=[self.membresia.pk])

    def _cambiar(self, fecha, reanudar=False):
        datos = {'hasta': fecha.strftime('%Y-%m-%d')}
        if reanudar:
            datos['reanudar_goteo'] = 'on'
        return self.client.post(self._url(), datos)

    def _vencer_hace(self, dias):
        Membership.objects.filter(pk=self.membresia.pk).update(
            expires_at=timezone.now() - timedelta(days=dias))
        self.membresia.refresh_from_db()

    def _abiertos(self):
        return sum(1 for a in get_course_access(self.membresia) if a['unlocked'])

    def _fecha_del_modelo(self, orden):
        """Cuándo le toca el modelo en esa posición.

        Se mira la FECHA y no `unlocked`: para abrirse, un modelo además necesita
        que el anterior esté terminado, y esa regla taparía por completo el
        efecto del calendario (con 0 terminados siempre hay 1 solo abierto,
        pase lo que pase con las fechas)."""
        for a in get_course_access(self.membresia):
            if a['course'].order == orden:
                return a['unlock_date']
        self.fail('no existe el modelo %d' % orden)

    # --- permisos ---------------------------------------------------------

    def test_un_anonimo_no_puede_cambiar_el_vencimiento(self):
        """Es regalar acceso pagado: si esta URL quedara abierta, cualquiera se
        daría a sí mismo un año gratis."""
        antes = self.membresia.expires_at
        self._cambiar(timezone.localdate() + timedelta(days=365))
        self.membresia.refresh_from_db()
        self.assertEqual(self.membresia.expires_at, antes)

    def test_un_alumno_logueado_tampoco(self):
        antes = self.membresia.expires_at
        self.client.force_login(self.alumna)
        self._cambiar(timezone.localdate() + timedelta(days=365))
        self.membresia.refresh_from_db()
        self.assertEqual(self.membresia.expires_at, antes)

    def test_no_cambia_con_un_GET(self):
        """Un rastreador siguiendo enlaces no puede alterar vencimientos."""
        antes = self.membresia.expires_at
        self.client.force_login(self.dueno)
        self.client.get(self._url())
        self.membresia.refresh_from_db()
        self.assertEqual(self.membresia.expires_at, antes)

    # --- qué día queda cubierto -------------------------------------------

    def test_el_dia_elegido_todavia_tiene_acceso(self):
        """"Vence el 10" tiene que significar que el 10 puede entrar. Guardando
        las 00:00 de ese día, la familia se quedaría afuera toda esa jornada."""
        hoy = timezone.localdate()
        self.client.force_login(self.dueno)
        self._cambiar(hoy)

        self.membresia.refresh_from_db()
        local = timezone.localtime(self.membresia.expires_at)
        self.assertEqual(local.date(), hoy)
        self.assertEqual((local.hour, local.minute), (23, 59))
        self.assertTrue(self.membresia.is_active, 'el último día sigue activa')

    def test_extender_deja_la_membresia_activa(self):
        self.client.force_login(self.dueno)
        self._cambiar(timezone.localdate() + timedelta(days=60))

        self.membresia.refresh_from_db()
        self.assertTrue(self.membresia.is_active)
        self.assertEqual(
            timezone.localtime(self.membresia.expires_at).date(),
            timezone.localdate() + timedelta(days=60))

    def test_una_fecha_pasada_corta_el_acceso(self):
        """Cortar a alguien también tiene que ser posible: se cobró de más, o la
        cuenta se dio por error."""
        self.client.force_login(self.dueno)
        self._cambiar(timezone.localdate() - timedelta(days=1))

        self.membresia.refresh_from_db()
        self.assertFalse(self.membresia.is_active)

    def test_rechaza_una_fecha_de_hace_años(self):
        """Escribir 2025 en vez de 2026 dejaría a la familia sin acceso de golpe,
        y es un dedazo fácil en un campo lleno de números."""
        antes = self.membresia.expires_at
        self.client.force_login(self.dueno)
        respuesta = self._cambiar(timezone.localdate() - timedelta(days=400))

        self.membresia.refresh_from_db()
        self.assertEqual(self.membresia.expires_at, antes, 'no se guardó nada')
        self.assertContains(respuesta, 'más de un año')

    # --- el calendario semanal al revivir una cuenta ----------------------

    def test_al_revivir_con_reanudar_no_le_llegan_todos_los_modelos_de_golpe(self):
        """Lo que se vende es el ritmo semanal. Si alguien vuelve después de un
        año, reactivarlo sin reanclar el calendario le entrega el año entero de
        una vez y el producto se evapora justo en la reactivación."""
        MembershipCategory.objects.filter(pk=self.mc.pk).update(
            obtenida_en=timezone.now() - timedelta(days=365))
        self._vencer_hace(200)

        self.client.force_login(self.dueno)
        self._cambiar(timezone.localdate() + timedelta(days=30), reanudar=True)

        self.membresia.refresh_from_db()
        self.assertTrue(self.membresia.is_active)
        # Con `cursos_iniciales=3`, el 4º es el primero que espera una semana:
        # reanclado el calendario a hoy, su fecha tiene que quedar por delante.
        self.assertGreater(self._fecha_del_modelo(4), timezone.localdate())

    def test_al_revivir_sin_marcar_la_casilla_recibe_lo_atrasado(self):
        """La otra mitad de la decisión: a veces sí se quiere devolver todo (por
        ejemplo si el corte fue culpa nuestra). Tiene que ser posible."""
        MembershipCategory.objects.filter(pk=self.mc.pk).update(
            obtenida_en=timezone.now() - timedelta(days=365))
        self._vencer_hace(200)

        self.client.force_login(self.dueno)
        self._cambiar(timezone.localdate() + timedelta(days=30), reanudar=False)

        self.membresia.refresh_from_db()
        self.assertTrue(self.membresia.is_active)
        # El calendario quedó donde estaba, anclado hace un año: hasta el último
        # modelo tiene su fecha cumplida.
        self.assertLess(self._fecha_del_modelo(10), timezone.localdate())

    def test_extender_una_activa_no_toca_su_calendario(self):
        """Renovarle a alguien que sigue al día no puede devolverlo a la semana 1:
        su ritmo nunca se interrumpió."""
        MembershipCategory.objects.filter(pk=self.mc.pk).update(
            obtenida_en=timezone.now() - timedelta(days=60))
        antes = self._fecha_del_modelo(10)

        self.client.force_login(self.dueno)
        # Marcada a propósito: aunque venga marcada, no debe aplicarse a una
        # membresía que nunca se venció.
        self._cambiar(timezone.localdate() + timedelta(days=90), reanudar=True)

        self.membresia.refresh_from_db()
        self.assertEqual(self._fecha_del_modelo(10), antes)
