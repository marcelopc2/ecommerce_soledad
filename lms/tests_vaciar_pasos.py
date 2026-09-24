"""Vaciar modelos para volver a cargarlos, sin romper la fila.

La administradora está rehaciendo el contenido modelo por modelo y borrar los
pasos desde el panel es de a uno: son más de mil. El comando los vacía de golpe.

Deja UN paso en cada uno y no cero. No es capricho: un modelo sin recursos no
cuenta como terminado, y como la cadena exige completar el anterior, un modelo
vacío no deja pasar a nadie. Con un paso adentro el problema no existe, y
borrarlo desde el panel es un clic.
"""
from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from lms.models import (
    Course, CourseProgress, Lesson, Membership,
)

User = get_user_model()


class ComandoVaciarPasosTests(TestCase):
    def setUp(self):
        self.bienvenida = Course.objects.create(
            title='Bienvenida a Ingenio Blocks', slug='bienvenida', order=1)
        self.taladro = Course.objects.create(
            title='Taladro y Herramientas', slug='taladro', order=2)
        self.otro = Course.objects.create(title='Aerogenerador', slug='aero', order=3)
        for c in (self.bienvenida, self.taladro, self.otro):
            for i in range(1, 4):
                Lesson.objects.create(course=c, title='Paso %d' % i, order=i,
                                      lesson_type='VIDEO')

    def _correr(self, excepto=('bienvenida', 'taladro'), aplicar=False):
        salida = StringIO()
        call_command('vaciar_pasos', excepto=list(excepto), aplicar=aplicar, stdout=salida)
        return salida.getvalue()

    def test_sin_aplicar_no_borra_nada(self):
        self._correr()
        self.assertEqual(Lesson.objects.count(), 9)

    def test_deja_UN_paso_en_los_que_no_estan_en_la_lista(self):
        """Uno y no cero, a pedido del usuario: borrar el que queda desde el
        panel es un clic, y así ni siquiera aparece el caso de un modelo sin
        nada adentro."""
        self._correr(aplicar=True)
        self.assertEqual(self.bienvenida.lessons.count(), 3)
        self.assertEqual(self.taladro.lessons.count(), 3)
        self.assertEqual(self.otro.lessons.count(), 1)

    def test_el_que_queda_es_el_primero(self):
        """No uno al azar: el primero sirve de muestra de lo que había."""
        self._correr(aplicar=True)
        self.assertEqual(self.otro.lessons.first().title, 'Paso 1')

    def test_con_cero_quedan_completamente_vacios(self):
        salida = StringIO()
        call_command('vaciar_pasos', excepto=['bienvenida', 'taladro'],
                     dejar=0, aplicar=True, stdout=salida)
        self.assertEqual(self.otro.lessons.count(), 0)

    def test_basta_un_trozo_del_nombre(self):
        """"taladro" tiene que alcanzar para "Taladro y Herramientas": nadie va
        a escribir el nombre completo sin equivocarse."""
        self._correr(excepto=('TALADRO',), aplicar=True)
        self.assertEqual(self.taladro.lessons.count(), 3)

    def test_un_nombre_mal_escrito_detiene_todo(self):
        """Sin esto, un dedazo se notaba recién cuando el modelo aparecía vacío,
        y para entonces ya no había vuelta atrás."""
        with self.assertRaises(CommandError) as e:
            self._correr(excepto=('taladroo',), aplicar=True)
        self.assertIn('taladroo', str(e.exception))
        self.assertEqual(Lesson.objects.count(), 9)

    def test_los_modelos_siguen_existiendo(self):
        """Se vacían, no se borran: conservan su portada y su lugar en la fila."""
        self._correr(aplicar=True)
        self.assertTrue(Course.objects.filter(pk=self.otro.pk).exists())

    def test_el_modelo_terminado_de_un_alumno_se_conserva(self):
        """`CourseProgress` vive aparte de los pasos y es el que usa la cadena:
        quien ya había terminado un modelo sigue terminado aunque se vacíe."""
        u = User.objects.create_user(username='a@b.cl', email='a@b.cl')
        mem = Membership.objects.create(
            user=u, expires_at=timezone.now() + timedelta(days=30))
        CourseProgress.objects.create(membership=mem, course=self.otro,
                                      completed_at=timezone.now())
        self._correr(aplicar=True)
        self.assertTrue(
            CourseProgress.objects.filter(membership=mem, course=self.otro).exists())

    def test_borra_tambien_los_archivos(self):
        """Django no borra el archivo al borrar la fila. Sin esto quedaban mil
        imágenes huérfanas ocupando disco que nadie iba a volver a mirar."""
        leccion = self.otro.lessons.order_by('-order').first()   # uno de los que SÍ se borran
        leccion.image_file.save('paso.jpg', ContentFile(b'imagen falsa'), save=True)
        ruta = leccion.image_file.path
        import os
        self.assertTrue(os.path.exists(ruta))
        self._correr(aplicar=True)
        self.assertFalse(os.path.exists(ruta))

    def test_dice_cuantos_avances_se_lleva(self):
        """Antes de borrar hay que poder ver el tamaño del daño."""
        self.assertIn('avances', self._correr())
