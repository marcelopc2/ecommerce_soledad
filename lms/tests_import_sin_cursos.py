"""La re-importación no puede volver a borrar el contenido.

Por qué existe este archivo
---------------------------
El comando `rehacer_migracion` borraba los 44 modelos y los 1.283 pasos en cada
corrida y los volvía a traer desde WordPress. Eso destruyó TRES veces el trabajo
que la administradora había hecho a mano en el panel: el 16 y el 17 de
septiembre de 2026 se perdió el curso de bienvenida que ella había armado paso a
paso, con sus videos y su portada, y tuvo que rehacerlo entero el día 22.

Desde entonces la regla es al revés: **el contenido lo manda el panel**. La
importación trae alumnos, membresías y avance, y no toca los modelos.

Estas pruebas cuidan justamente eso, porque es un daño silencioso: nadie se
entera hasta que alguien entra al Aula y ve el curso viejo de vuelta.
"""
from django.contrib.auth import get_user_model
from django.core.management import CommandError
from django.test import TestCase
from django.utils import timezone

from lms.management.commands.importar_wordpress import Command as Importador
from lms.management.commands.rehacer_migracion import Command as Rehacer
from lms.models import (
    Course, CourseCategory, CategoryCourse, Lesson, Membership,
)

User = get_user_model()


def _curso(titulo, pasos=(), orden=1):
    c = Course.objects.create(title=titulo, slug=titulo.lower().replace(' ', '-'),
                              description='', order=orden, is_active=True)
    for i, nombre in enumerate(pasos, 1):
        Lesson.objects.create(course=c, title=nombre, order=i, lesson_type='VIDEO')
    return c


class NoBorrarElContenidoTests(TestCase):
    """Lo que hace (y lo que NO hace) el borrado previo a la importación."""

    def setUp(self):
        self.curso = _curso('Bienvenida a Ingenio Blocks',
                            ['Bienvenida paso 1', 'Bienvenida paso 2'])
        self.cat = CourseCategory.objects.create(nombre='General', slug='general')
        CategoryCourse.objects.create(categoria=self.cat, curso=self.curso, orden=1)

        alumna = User.objects.create_user(username='a@b.cl', email='a@b.cl')
        Membership.objects.create(user=alumna,
                                  expires_at=timezone.now() + timezone.timedelta(days=30))

    def _borrar(self, con_cursos):
        cmd = Rehacer()
        cmd.stdout = type('X', (), {'write': lambda *a, **k: None})()
        cmd.style = type('S', (), {'MIGRATE_HEADING': staticmethod(lambda t: t)})()
        cmd._borrar_lo_migrado(con_cursos)

    def test_por_omision_los_modelos_sobreviven(self):
        """El caso que motivó todo: actualizar alumnos no puede tocar el curso."""
        self._borrar(con_cursos=False)
        self.assertEqual(Course.objects.count(), 1)
        self.assertEqual(Lesson.objects.count(), 2)

    def test_por_omision_el_vinculo_con_la_categoria_sobrevive(self):
        """Sin CategoryCourse el modelo existe pero no se le entrega a nadie:
        borrarlo dejaría a los alumnos sin acceso aunque el curso siga ahí."""
        self._borrar(con_cursos=False)
        self.assertEqual(CategoryCourse.objects.count(), 1)

    def test_los_alumnos_si_se_borran(self):
        """Es el único propósito que le queda al borrado."""
        self._borrar(con_cursos=False)
        self.assertEqual(Membership.objects.count(), 0)
        self.assertEqual(User.objects.filter(is_staff=False).count(), 0)

    def test_las_cuentas_de_gestion_no_se_tocan(self):
        User.objects.create_user(username='jefa@ib.cl', email='jefa@ib.cl', is_staff=True)
        self._borrar(con_cursos=False)
        self.assertTrue(User.objects.filter(username='jefa@ib.cl').exists())

    def test_con_cursos_si_borra_el_contenido(self):
        """La escotilla sigue existiendo para una instalación desde cero."""
        self._borrar(con_cursos=True)
        self.assertEqual(Course.objects.count(), 0)
        self.assertEqual(Lesson.objects.count(), 0)


class EmparejarConLoQueHayTests(TestCase):
    """Sin crear cursos hay que reencontrarlos igual, o el avance se pierde.

    El progreso del alumno viene del volcado identificado con los id de
    WordPress; si no se traducen a las filas de acá, un alumno que ya terminó
    diez modelos aparece en cero y el goteo vuelve a encerrarle el contenido.
    """

    def setUp(self):
        self.cmd = Importador()
        self.curso = _curso('Taladro y Herramientas',
                            ['Taladro paso 1', 'Taladro paso 2', 'Taladro paso 3'])

    def _emparejar(self, titulo_wp, pasos_wp=()):
        """pasos_wp: lista de (orden, id_wp, titulo_wp)."""
        ordenados = [(7, {'post_title': titulo_wp})]
        pasos_de = {7: [(o, lid) for o, lid, _t in pasos_wp]}
        d = {'posts': {lid: {'post_title': t} for _o, lid, t in pasos_wp}}
        return self.cmd._emparejar_con_lo_que_hay(ordenados, pasos_de, d)

    def test_encuentra_el_modelo_por_titulo(self):
        cursos, _l, sin_par, _p = self._emparejar('Taladro y Herramientas')
        self.assertEqual(cursos[7], self.curso)
        self.assertEqual(sin_par, [])

    def test_el_numero_del_titulo_de_wordpress_no_estorba(self):
        """En WordPress los modelos se llaman "01 - Taladro y Herramientas"; el
        importador les saca el número al crearlos, así que acá también."""
        cursos, _l, _s, _p = self._emparejar('01 - Taladro y Herramientas')
        self.assertEqual(cursos[7], self.curso)

    def test_no_lo_separan_ni_acentos_ni_mayusculas(self):
        _curso('Avioneta a Hélice', [])
        cursos, _l, sin_par, _p = self._emparejar('AVIONETA A HELICE')
        self.assertEqual(sin_par, [])
        self.assertEqual(cursos[7].title, 'Avioneta a Hélice')

    def test_los_pasos_se_emparejan_por_posicion(self):
        _c, pasos, _s, sin_pareja = self._emparejar(
            'Taladro y Herramientas',
            [(1, 'wp1', 'Taladro paso 1'), (2, 'wp2', 'Taladro paso 2')])
        self.assertEqual(pasos['wp1'].order, 1)
        self.assertEqual(pasos['wp2'].order, 2)
        self.assertEqual(sin_pareja, 0)

    def test_si_alguien_reordeno_en_el_panel_cae_al_titulo(self):
        """Consuelo puede haber movido un paso de lugar. La posición ya no
        calza, pero el nombre sí, y vale más emparejar que perder el avance."""
        Lesson.objects.filter(course=self.curso, title='Taladro paso 3').update(order=9)
        _c, pasos, _s, sin_pareja = self._emparejar(
            'Taladro y Herramientas', [(3, 'wp3', 'Taladro paso 3')])
        self.assertEqual(pasos['wp3'].title, 'Taladro paso 3')
        self.assertEqual(sin_pareja, 0)

    def test_un_paso_que_ya_no_existe_se_cuenta_y_no_revienta(self):
        _c, pasos, _s, sin_pareja = self._emparejar(
            'Taladro y Herramientas', [(88, 'wpX', 'Un paso que se borro')])
        self.assertNotIn('wpX', pasos)
        self.assertEqual(sin_pareja, 1)

    def test_un_modelo_nuevo_en_wordpress_se_ignora_y_se_avisa(self):
        """WordPress ya no manda: si allá aparece un modelo que acá no está, no
        se crea. Pero tiene que salir en pantalla, no desaparecer callado."""
        cursos, _l, sin_par, _p = self._emparejar('Modelo inventado en WordPress')
        self.assertEqual(cursos, {})
        self.assertEqual(sin_par, ['Modelo inventado en WordPress'])

    def test_no_crea_ni_modifica_nada(self):
        antes_c = list(Course.objects.values_list('id', 'title', 'order'))
        antes_l = list(Lesson.objects.values_list('id', 'title', 'order'))
        self._emparejar('Taladro y Herramientas', [(1, 'wp1', 'Taladro paso 1')])
        self.assertEqual(list(Course.objects.values_list('id', 'title', 'order')), antes_c)
        self.assertEqual(list(Lesson.objects.values_list('id', 'title', 'order')), antes_l)


class GuardiasTests(TestCase):
    def test_sin_cursos_exige_que_ya_existan(self):
        """Correrlo sobre una base vacía dejaría el Aula sin nada y sin aviso."""
        cmd = Importador()
        with self.assertRaises(CommandError) as e:
            cmd.handle(dump=__file__, medios='/no/existe', aplicar=True,
                       sin_cursos=True, sobre_lo_que_hay=False,
                       categoria='General', dias_vigencia=30)
        self.assertIn('sin-cursos', str(e.exception))
