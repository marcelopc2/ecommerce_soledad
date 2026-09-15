"""Los videos propios del Aula salen por el endpoint con permisos, no por nginx.

Antes vivían en `media/lesson_videos/`, que nginx sirve como estático: cualquiera
con el link se los bajaba sin pagar ni iniciar sesión. Estos tests cubren que el
archivo nuevo tenga exactamente los mismos controles que el PDF y la imagen.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from lms.models import (
    Course, CourseCategory, CategoryCourse, Lesson, Membership, MembershipCategory,
)

User = get_user_model()

#: Unos bytes cualquiera: no se decodifica el video, solo se comprueba quién lo
#: puede bajar.
VIDEO = b'\x00\x00\x00\x18ftypmp42' + b'0' * 64


class VideoProtegidoTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.categoria = CourseCategory.objects.create(
            nombre='Modelos', slug='modelos', cursos_iniciales=3)
        self.curso = Course.objects.create(title='Taladro', slug='taladro', order=1)
        CategoryCourse.objects.create(categoria=self.categoria, curso=self.curso, orden=1)

        self.lesson = Lesson.objects.create(
            course=self.curso, title='Bienvenida', order=1, lesson_type='VIDEO',
            video_file=SimpleUploadedFile('bienvenida.mp4', VIDEO, content_type='video/mp4'),
        )

        self.alumno = User.objects.create_user(
            username='alumno@correo.cl', email='alumno@correo.cl', password='clave-larga-1234',
        )
        self.membership = Membership.objects.create(
            user=self.alumno, expires_at=timezone.now() + timedelta(days=90),
        )
        MembershipCategory.objects.create(
            membership=self.membership, categoria=self.categoria,
            obtenida_en=timezone.now() - timedelta(days=1),
        )

        self.url = reverse('lms-lesson-video', args=[self.lesson.pk])

    def tearDown(self):
        # El archivo lo escribe el storage de verdad: se limpia para no dejar
        # basura en protected_media/ cada vez que corren los tests.
        if self.lesson.video_file:
            self.lesson.video_file.delete(save=False)
        Lesson.objects.exclude(video_file='').exclude(video_file=None).delete()

    def test_sin_sesion_no_se_puede(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 401)

    def test_con_sesion_pero_sin_membresia_no_se_puede(self):
        otro = User.objects.create_user(
            username='curioso@correo.cl', email='curioso@correo.cl', password='clave-larga-1234',
        )
        self.client.force_authenticate(otro)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 403)

    def test_con_membresia_activa_si_se_puede(self):
        self.client.force_authenticate(self.alumno)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(b''.join(r.streaming_content), VIDEO)

    def test_no_se_ofrece_como_descarga_ni_se_cachea(self):
        """Mismas cabeceras que el PDF y la imagen: se mira, no se guarda."""
        self.client.force_authenticate(self.alumno)
        r = self.client.get(self.url)
        self.assertEqual(r['Content-Disposition'], 'inline')
        self.assertIn('no-store', r['Cache-Control'])
        # FileResponse deja el archivo abierto hasta que se consume o se cierra.
        # En Windows un archivo abierto no se puede borrar, así que sin esto el
        # tearDown reventaba con PermissionError.
        r.close()

    def test_con_la_membresia_vencida_no_se_puede(self):
        self.membership.expires_at = timezone.now() - timedelta(days=1)
        self.membership.save()
        self.client.force_authenticate(self.alumno)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 403)

    def test_una_leccion_sin_archivo_da_404(self):
        sin_video = Lesson.objects.create(
            course=self.curso, title='Solo link', order=2, lesson_type='VIDEO',
            video_embed_url='https://www.youtube.com/embed/abc',
        )
        self.client.force_authenticate(self.alumno)
        r = self.client.get(reverse('lms-lesson-video', args=[sin_video.pk]))
        self.assertEqual(r.status_code, 404)


class SerializerVideoTests(TestCase):
    """La API no debe delatar que existe un archivo si no hay membresía."""

    def setUp(self):
        self.curso = Course.objects.create(title='Taladro', slug='taladro', order=1)
        self.lesson = Lesson.objects.create(
            course=self.curso, title='Bienvenida', order=1, lesson_type='VIDEO',
            video_file=SimpleUploadedFile('x.mp4', VIDEO, content_type='video/mp4'),
        )

    def tearDown(self):
        if self.lesson.video_file:
            self.lesson.video_file.delete(save=False)

    def _datos(self, activa):
        from lms.serializers import LessonStudentSerializer
        return LessonStudentSerializer(
            self.lesson, context={'membership_active': activa},
        ).data

    def test_con_membresia_activa_se_anuncia(self):
        self.assertTrue(self._datos(True)['has_video_file'])

    def test_sin_membresia_activa_no_se_anuncia(self):
        self.assertFalse(self._datos(False)['has_video_file'])


class FormularioVideoTests(TestCase):
    """El panel acepta el archivo, y pone un tope para no dejar al alumno
    esperando una descarga eterna."""

    def test_un_paso_de_video_se_puede_guardar_solo_con_archivo(self):
        """Antes el formulario exigía el link de YouTube, así que subir solo el
        archivo se negaba a guardar."""
        from panel.forms import LessonForm
        curso = Course.objects.create(title='Taladro', slug='taladro', order=1)
        form = LessonForm(
            data={'title': 'Bienvenida', 'lesson_type': 'VIDEO',
                  'description': '', 'video_embed_url': ''},
            files={'video_file': SimpleUploadedFile('x.mp4', VIDEO, content_type='video/mp4')},
        )
        form.instance.course = curso
        self.assertTrue(form.is_valid(), form.errors)

    def test_un_paso_de_video_sin_link_ni_archivo_se_rechaza(self):
        from panel.forms import LessonForm
        form = LessonForm(data={'title': 'Vacío', 'lesson_type': 'VIDEO',
                                'description': '', 'video_embed_url': ''})
        self.assertFalse(form.is_valid())
        self.assertIn('video_embed_url', form.errors)

    def test_un_video_enorme_se_rechaza(self):
        from panel.forms import LessonForm
        gordo = SimpleUploadedFile('grande.mp4', b'0' * (61 * 1024 * 1024),
                                   content_type='video/mp4')
        form = LessonForm(
            data={'title': 'Grande', 'lesson_type': 'VIDEO',
                  'description': '', 'video_embed_url': ''},
            files={'video_file': gordo},
        )
        self.assertFalse(form.is_valid())
        self.assertIn('video_file', form.errors)
        self.assertIn('YouTube', str(form.errors['video_file']))
