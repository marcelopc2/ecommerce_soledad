"""Los tres datos que se imprimen en el certificado.

El certificado es la imagen que hizo la clienta; encima se escriben solo el
nombre, la cantidad de desafíos y la fecha. Lo que se cuida acá es de dónde sale
cada uno, porque un certificado se imprime, se enmarca y se regala: que diga
"1 desafíos" o el correo de la mamá en vez del nombre de la niña no se arregla
después.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from lms.models import (
    CategoryCourse, Course, CourseCategory, Diploma, Membership,
)

User = get_user_model()


class NombreParaDiplomaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='mama@correo.cl', email='mama@correo.cl')
        self.mem = Membership.objects.create(
            user=self.user, expires_at=timezone.now() + timedelta(days=30))

    def test_manda_el_nombre_del_alumno(self):
        """Es su logro, no el de quien pagó."""
        self.mem.student_name = 'Emilia Rojas'
        self.mem.parent_name = 'Carolina Rojas'
        self.assertEqual(self.mem.nombre_para_diploma, 'Emilia Rojas')

    def test_sin_nombre_de_alumno_usa_el_de_la_cuenta(self):
        """Lo pidió el usuario: si no llenaron el del niño al comprar, va el de
        quien creó la cuenta. Un certificado a nombre de la familia se entiende."""
        self.mem.parent_name = 'Carolina Rojas'
        self.assertEqual(self.mem.nombre_para_diploma, 'Carolina Rojas')

    def test_si_tampoco_hay_apoderado_usa_el_nombre_del_usuario(self):
        self.user.first_name = 'Carolina'
        self.user.last_name = 'Rojas'
        self.user.save()
        self.assertEqual(self.mem.nombre_para_diploma, 'Carolina Rojas')

    def test_como_ultimo_recurso_el_correo_SIN_el_dominio(self):
        """Antes se imprimía el correo entero. Además de quedar mal, no cabía
        en la línea."""
        self.assertEqual(self.mem.nombre_para_diploma, 'mama')

    def test_los_espacios_de_mas_no_cuentan_como_nombre(self):
        """Un campo con solo espacios pasaba el `or` y salía un diploma en
        blanco, que es peor que uno con el correo."""
        self.mem.student_name = '   '
        self.mem.parent_name = 'Carolina Rojas'
        self.assertEqual(self.mem.nombre_para_diploma, 'Carolina Rojas')


class DesafiosDelDiplomaTests(TestCase):
    def setUp(self):
        self.cat = CourseCategory.objects.create(nombre='Normal', slug='normal')
        self.diploma = Diploma.objects.create(
            title='Diploma Nivel Básico', categoria=self.cat, order=99)

    def _curso(self, n, activo=True):
        c = Course.objects.create(title='Modelo %d' % n, slug='modelo-%d' % n,
                                  order=n, is_active=activo)
        CategoryCourse.objects.create(categoria=self.cat, curso=c, orden=n)
        return c

    def test_cuenta_los_modelos_de_su_categoria(self):
        for i in range(1, 11):
            self._curso(i)
        self.assertEqual(self.diploma.desafios, 10)

    def test_no_cuenta_los_modelos_apagados(self):
        """Un modelo despublicado no se le pide a nadie, así que tampoco puede
        aparecer en la cuenta del certificado."""
        for i in range(1, 6):
            self._curso(i)
        self._curso(6, activo=False)
        self.assertEqual(self.diploma.desafios, 5)

    def test_se_actualiza_solo_al_agregar_un_modelo(self):
        """No es un número guardado a mano: si mañana la categoría crece, el
        certificado del que la termine lo dice sin que nadie edite nada."""
        for i in range(1, 6):
            self._curso(i)
        self.assertEqual(self.diploma.desafios, 5)
        self._curso(6)
        self.assertEqual(self.diploma.desafios, 6)

    def test_un_diploma_sin_categoria_cuenta_los_que_lo_preceden(self):
        """Comportamiento heredado de los diplomas viejos, que no tienen
        categoría y se ganan por posición en la secuencia."""
        suelto = Diploma.objects.create(title='Diploma viejo', order=4)
        for i in range(1, 7):
            Course.objects.create(title='M%d' % i, slug='m-%d' % i, order=i)
        self.assertEqual(suelto.desafios, 3)   # los de order 1, 2 y 3


class PlantillaDelCertificadoTests(TestCase):
    """Que el HTML salga con los datos puestos. No se comprueba el diseño -eso
    se miró renderizado- sino que no queden huecos ni plurales rotos."""

    def _html(self, **ctx):
        from django.template.loader import render_to_string
        base = {'student_name': 'Emilia Rojas', 'desafios': 10,
                'awarded_at': timezone.localdate()}
        base.update(ctx)
        return render_to_string('lms/diploma.html', base)

    def test_escribe_el_nombre_y_la_cantidad(self):
        html = self._html()
        self.assertIn('Emilia Rojas', html)
        self.assertIn('10 desafíos', html)

    def test_uno_solo_va_en_singular(self):
        self.assertIn('1 desafío<', self._html(desafios=1))

    def test_la_fecha_va_en_formato_chileno(self):
        from datetime import date
        self.assertIn('23/09/2026', self._html(awarded_at=date(2026, 9, 23)))

    def test_usa_la_imagen_de_la_clienta(self):
        self.assertIn('certificado.png', self._html())

    def test_la_vista_previa_se_distingue(self):
        """Para que nadie confunda una prueba con un certificado ganado."""
        self.assertIn('VISTA PREVIA', self._html(is_preview=True))
        self.assertNotIn('VISTA PREVIA', self._html())
