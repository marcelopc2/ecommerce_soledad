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


class FormularioDelPanelTests(TestCase):
    """El formulario con el que la clienta crea un diploma.

    Existe porque tenía un agujero silencioso: `categoria` estaba declarada en
    el formulario pero la plantilla nunca la pintaba, así que TODOS los diplomas
    se guardaban sin categoría. Un diploma sin categoría no sabe cuándo se gana
    y el certificado no puede contar los desafíos.
    """

    def setUp(self):
        self.cat = CourseCategory.objects.create(nombre='General', slug='general')

    def _form(self, **datos):
        from panel.forms import DiplomaForm
        base = {'categoria': self.cat.pk, 'title': 'Diploma Nivel Básico', 'is_active': True}
        base.update(datos)
        return DiplomaForm(data=base)

    def test_se_puede_crear_con_categoria(self):
        f = self._form()
        self.assertTrue(f.is_valid(), f.errors)
        self.assertEqual(f.save().categoria, self.cat)

    def test_la_categoria_es_OPCIONAL(self):
        """Sin ella el diploma se gana por posición: al terminar los modelos
        que están antes en la fila. Es el modo del diploma intermedio.

        Estuvo obligatoria un rato y fue un error mío: mataba justo ese caso,
        que era el que la clienta estaba tratando de armar."""
        f = self._form(categoria='')
        self.assertTrue(f.is_valid(), f.errors)
        self.assertIsNone(f.save().categoria)

    def test_la_plantilla_DEL_PANEL_pinta_la_categoria(self):
        """El agujero original, y es el que hay que cuidar: el campo estaba en
        el formulario pero la plantilla no lo dibujaba, así que nunca llegaba
        nada y se guardaba en blanco. Se mira el archivo, no el formulario:
        comprobar el formulario habría pasado igual con el error puesto."""
        from django.template.loader import get_template
        fuente = get_template('panel/diploma_form.html').template.source
        self.assertIn('form.categoria', fuente)
        # Y que no hayan vuelto los campos que ya no se imprimen.
        self.assertNotIn('form.image_file', fuente)
        self.assertNotIn('form.description', fuente)

    def test_ya_no_pide_imagen_ni_mensaje(self):
        """El certificado es el diseño oficial y es el mismo para todos: esos
        campos no se imprimían en ninguna parte y confundían."""
        from panel.forms import DiplomaForm
        campos = set(DiplomaForm().fields)
        self.assertEqual(campos, {'categoria', 'title', 'is_active'})

    def test_solo_ofrece_categorias_activas(self):
        apagada = CourseCategory.objects.create(
            nombre='Vieja', slug='vieja', is_active=False)
        from panel.forms import DiplomaForm
        opciones = list(DiplomaForm().fields['categoria'].queryset)
        self.assertIn(self.cat, opciones)
        self.assertNotIn(apagada, opciones)


class ImpresionTests(TestCase):
    """La hoja impresa.

    El certificado salía en una hoja VERTICAL, ocupando el tercio de arriba y
    dejando el resto en blanco. Y el texto se agrandaba, porque las unidades
    `cqw` no se resuelven al imprimir y caía al tamaño de respaldo en píxeles.
    """

    def _css(self):
        from django.template.loader import render_to_string
        return render_to_string('lms/diploma.html', {
            'student_name': 'Emilia Rojas', 'desafios': 10,
            'awarded_at': timezone.localdate(),
        })

    def test_la_hoja_se_declara_apaisada(self):
        self.assertIn('size: A4 landscape', self._css())

    def test_sin_margenes_de_hoja(self):
        """Con margen el certificado no llega a los bordes y queda un marco
        blanco que no es parte del diseño."""
        self.assertIn('margin: 0;', self._css())

    def test_al_imprimir_los_tamanos_se_repiten_en_vw(self):
        """Es el arreglo de fondo: `cqw` no se resuelve en la hoja. Si alguien
        cambia un tamaño arriba y olvida el de abajo, vuelve el problema."""
        css = self._css()
        for medida in ('3.3vw', '2.30vw', '1.77vw'):
            self.assertIn(medida, css)

    def test_los_tamanos_de_pantalla_y_de_hoja_coinciden(self):
        """Los mismos números en cqw y en vw: el certificado tiene que verse
        igual en la pantalla que en el papel."""
        css = self._css()
        for pantalla, hoja in (('3.3cqw', '3.3vw'), ('2.30cqw', '2.30vw'),
                               ('1.77cqw', '1.77vw')):
            self.assertIn(pantalla, css)
            self.assertIn(hoja, css)

    def test_se_imprimen_los_colores_del_fondo(self):
        """Sin esto Chrome imprime el fondo en blanco y sale una hoja con tres
        palabras sueltas en medio de la nada."""
        self.assertIn('print-color-adjust: exact', self._css())

    def test_la_barra_de_botones_no_se_imprime(self):
        self.assertIn('.toolbar { display: none !important; }', self._css())


class ContarDesafiosSinLaBienvenidaTests(TestCase):
    """La bienvenida no es un desafío.

    El usuario puso un diploma en la posición 14 y lo llamó "12 desafíos". El
    conteo daba 13 porque sumaba la bienvenida, que es la introducción al Aula y
    no un modelo que el niño arme. Se marca con `cuenta_como_desafio`, un campo
    explícito y no una corazonada sobre el título.
    """

    def setUp(self):
        self.cat = CourseCategory.objects.create(nombre='General', slug='general')
        self.bienvenida = self._curso('Bienvenida a Ingenio Blocks', 1, desafio=False)
        for i in range(2, 14):                      # 12 modelos armables
            self._curso('Modelo %d' % i, i)

    def _curso(self, titulo, orden, desafio=True, activo=True):
        c = Course.objects.create(title=titulo, slug='c-%d' % orden, order=orden,
                                  is_active=activo, cuenta_como_desafio=desafio)
        CategoryCourse.objects.create(categoria=self.cat, curso=c, orden=orden)
        return c

    def test_por_categoria_no_cuenta_la_bienvenida(self):
        d = Diploma.objects.create(title='Diploma', categoria=self.cat, order=99)
        self.assertEqual(d.desafios, 12)

    def test_por_posicion_tampoco(self):
        """El diploma intermedio: en la posición 14 van los 12 de antes."""
        d = Diploma.objects.create(title='Diploma 12 desafíos', order=14)
        self.assertEqual(d.desafios, 12)

    def test_un_diploma_mas_adelante_cuenta_mas(self):
        self._curso('Modelo 14', 15)
        d = Diploma.objects.create(title='Diploma siguiente', order=27)
        self.assertEqual(d.desafios, 13)

    def test_los_apagados_siguen_sin_contar(self):
        self._curso('Modelo guardado', 14, activo=False)
        d = Diploma.objects.create(title='Diploma', categoria=self.cat, order=99)
        self.assertEqual(d.desafios, 12)

    def test_se_puede_volver_a_contarla_desde_el_panel(self):
        """Es un campo editable, no una regla escondida: si algún día la
        bienvenida sí cuenta, se prende y listo."""
        self.bienvenida.cuenta_como_desafio = True
        self.bienvenida.save()
        d = Diploma.objects.create(title='Diploma', categoria=self.cat, order=99)
        self.assertEqual(d.desafios, 13)


class DiplomaPorPosicionTests(TestCase):
    """La categoría volvió a ser opcional. Haberla puesto obligatoria mataba el
    diploma intermedio, que es el que el usuario estaba tratando de crear."""

    def setUp(self):
        self.cat = CourseCategory.objects.create(nombre='General', slug='general')

    def test_se_puede_guardar_sin_categoria(self):
        from panel.forms import DiplomaForm
        f = DiplomaForm(data={'title': 'Diploma 12 desafíos', 'is_active': True})
        self.assertTrue(f.is_valid(), f.errors)
        self.assertIsNone(f.save().categoria)

    def test_con_categoria_tambien(self):
        from panel.forms import DiplomaForm
        f = DiplomaForm(data={'categoria': self.cat.pk, 'title': 'Diploma final',
                              'is_active': True})
        self.assertTrue(f.is_valid(), f.errors)
        self.assertEqual(f.save().categoria, self.cat)
