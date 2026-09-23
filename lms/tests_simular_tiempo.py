"""El reloj de las cuentas de prueba.

Existe para poder mirar el Aula "al mes y medio" sin esperar mes y medio: el
comando corre la fecha de compra hacia atrás. Lo que se cuida acá es que mueva
lo que tiene que mover y nada más, porque apuntado a una cuenta real le cambia
lo que ve y cuándo se le vence.
"""
from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from lms.models import (
    CategoryCourse, Course, CourseCategory, CourseProgress, Membership,
    MembershipCategory,
)

User = get_user_model()


class SimularPasoDelTiempoTests(TestCase):
    def setUp(self):
        self.cat = CourseCategory.objects.create(
            nombre='General', slug='general', modo=CourseCategory.GOTEO)
        self.cursos = []
        for i in range(1, 6):
            c = Course.objects.create(title='Modelo %d' % i, slug='modelo-%d' % i,
                                      description='', order=i, is_active=True)
            CategoryCourse.objects.create(categoria=self.cat, curso=c, orden=i)
            self.cursos.append(c)

        self.user = User.objects.create_user(username='yo@correo.cl', email='yo@correo.cl')
        self.mem = Membership.objects.create(
            user=self.user, expires_at=timezone.now() + timedelta(days=180))
        self.mc = MembershipCategory.objects.create(
            membership=self.mem, categoria=self.cat, obtenida_en=timezone.now())

    def _correr(self, **extra):
        salida = StringIO()
        opciones = {'email': 'yo@correo.cl', 'semanas': 0, 'stdout': salida}
        opciones.update(extra)
        call_command('simular_paso_del_tiempo', **opciones)
        return salida.getvalue()

    # --- seguridad ---

    def test_sin_aplicar_no_toca_nada(self):
        antes = self.mc.obtenida_en
        self._correr(semanas=10)
        self.mc.refresh_from_db()
        self.assertEqual(self.mc.obtenida_en, antes)

    def test_un_correo_que_no_existe_avisa(self):
        with self.assertRaises(CommandError):
            self._correr(email='nadie@correo.cl', aplicar=True)

    def test_semanas_negativas_se_rechazan(self):
        """El reloj solo va hacia atrás; un número negativo sería una compra en
        el futuro, que deja al alumno sin nada abierto y sin explicación."""
        with self.assertRaises(CommandError):
            self._correr(semanas=-3, aplicar=True)

    def test_avisa_si_es_una_cuenta_de_gestion(self):
        self.user.is_staff = True
        self.user.save(update_fields=['is_staff'])
        self.assertIn('gestión', self._correr(semanas=1))

    # --- lo que hace ---

    def test_mueve_la_fecha_de_compra(self):
        self._correr(semanas=6, aplicar=True)
        self.mc.refresh_from_db()
        dias = (timezone.now() - self.mc.obtenida_en).days
        self.assertGreaterEqual(dias, 41)
        self.assertLessEqual(dias, 43)

    def test_el_vencimiento_acompana_a_la_compra(self):
        """Si compró hace seis semanas, le quedan seis semanas menos de plan.
        Dejar el vencimiento donde estaba daría un alumno imposible."""
        self._correr(semanas=6, meses_de_acceso=6, aplicar=True)
        self.mem.refresh_from_db()
        faltan = (self.mem.expires_at - timezone.now()).days
        self.assertGreater(faltan, 120)
        self.assertLess(faltan, 145)

    def test_limpia_el_ancla_de_una_reanudacion_vieja(self):
        """Con la fecha de compra movida a mano, un ancla de renovación anterior
        daría un calendario que no corresponde a ninguna de las dos."""
        self.mc.reanudada_en = timezone.now() - timedelta(days=10)
        self.mc.entregados_al_reanudar = 3
        self.mc.save()
        self._correr(semanas=2, aplicar=True)
        self.mc.refresh_from_db()
        self.assertIsNone(self.mc.reanudada_en)
        self.assertEqual(self.mc.entregados_al_reanudar, 0)

    # --- lo que muestra ---

    def test_recien_comprado_ve_solo_el_primero(self):
        """El segundo candado: un modelo se abre por fecha Y por haber terminado
        el anterior. Sin terminar nada, correr el reloj no abre más."""
        salida = self._correr(semanas=0, aplicar=True)
        self.assertIn('1 de 5 modelos abiertos', salida)

    def test_correr_el_reloj_sin_completar_no_abre_mas(self):
        salida = self._correr(semanas=8, aplicar=True)
        self.assertIn('1 de 5 modelos abiertos', salida)

    def test_completando_el_primero_se_abre_el_segundo(self):
        CourseProgress.objects.create(
            membership=self.mem, course=self.cursos[0], completed_at=timezone.now())
        salida = self._correr(semanas=8, aplicar=True)
        self.assertIn('2 de 5 modelos abiertos', salida)
