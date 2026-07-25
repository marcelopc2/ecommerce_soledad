from datetime import timedelta
from django.db import models
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.core.validators import FileExtensionValidator
from django.utils import timezone
from payments.models import Order

# Los PDFs se guardan FUERA de las carpetas públicas (static/media):
# solo se sirven vía endpoint autenticado que verifica la membresía.
#
# Es una función, no una instancia, a propósito: si se le pasa la instancia a
# storage=, Django serializa en la migración la ruta YA RESUELTA de la máquina
# donde se generó (venía quedando 'C:/Users/.../protected_media', que en el
# servidor Linux no existe). Con un callable la migración guarda una referencia
# a esta función y la ruta se resuelve en cada entorno.
def protected_storage():
    return FileSystemStorage(location=settings.PROTECTED_MEDIA_ROOT)


class Course(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    # Dos vías para la portada porque pedir una URL obliga a hospedar la imagen
    # en otra parte, y quien administra el sitio no tiene por qué saber hacerlo.
    # Se prioriza el archivo subido; image_url queda para los cursos que ya la
    # tenían y para pegar una imagen que vive en otro lado.
    # FileField y no ImageField: ImageField exige Pillow, que no es dependencia
    # del proyecto. Es el mismo criterio que ya usa LandingVideo.cover.
    image_file = models.FileField(
        upload_to='cursos/', blank=True,
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp'])],
        verbose_name='Imagen de portada',
        help_text='JPG, PNG o WEBP. Ideal horizontal (16:9). Si la subes acá, manda sobre la URL.',
    )
    image_url = models.URLField(max_length=500, blank=True,
                               help_text='Alternativa: dirección de una imagen ya publicada en internet.')
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(
        default=0,
        help_text="Posición en la secuencia semanal (1 = primero). Se arrastra en el panel.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'id']

    @property
    def portada_url(self):
        """Portada del curso, en orden de preferencia.

        1. La imagen subida.
        2. Una URL pegada a mano.
        3. La miniatura del primer video del curso.

        El paso 3 es el que evita el ladrillo gris genérico: casi todos los
        modelos abren con un video, así que sin hacer nada la tarjeta ya muestra
        un fotograma del contenido real.
        """
        from catalog.models import youtube_thumbnail

        if self.image_file:
            return self.image_file.url
        if self.image_url:
            return self.image_url
        primer_video = self.lessons.filter(
            lesson_type='VIDEO', video_embed_url__gt='',
        ).order_by('order', 'id').first()
        return youtube_thumbnail(primer_video.video_embed_url) if primer_video else ''

    def __str__(self):
        return self.title


class Lesson(models.Model):
    """Un recurso dentro de un curso: video de YouTube, documento PDF o imagen
    (paso a paso). Cada uno lleva una descripción que se muestra junto al recurso."""
    TYPE_CHOICES = (
        ('VIDEO', 'Video'),
        ('PDF', 'Documento PDF'),
        ('IMAGE', 'Imagen'),
    )

    course = models.ForeignKey(Course, related_name='lessons', on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, help_text="Texto que acompaña al recurso (paso a paso, instrucciones)")
    order = models.PositiveIntegerField(default=1, help_text="Orden del recurso dentro del curso")
    lesson_type = models.CharField(max_length=5, choices=TYPE_CHOICES)
    video_embed_url = models.URLField(
        max_length=500, blank=True,
        help_text="URL de embed del video (YouTube/Vimeo). Solo para recursos de tipo VIDEO.",
    )
    pdf_file = models.FileField(
        storage=protected_storage, upload_to='lessons/', blank=True, null=True,
        validators=[FileExtensionValidator(allowed_extensions=['pdf'])],
        help_text="PDF protegido. Solo para recursos de tipo PDF.",
    )
    image_file = models.FileField(
        storage=protected_storage, upload_to='lesson_images/', blank=True, null=True,
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp', 'gif'])],
        help_text="Imagen protegida (paso a paso). Solo para recursos de tipo IMAGE.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.course.title} · {self.order}. {self.title}"


class Membership(models.Model):
    """
    Membresía del alumno: acceso a los cursos de los productos que compró,
    hasta expires_at. Cada compra/renovación EXTIENDE el vencimiento y suma cursos.
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name='membership', on_delete=models.CASCADE)
    courses = models.ManyToManyField(Course, related_name='memberships', blank=True)
    orders = models.ManyToManyField(Order, related_name='memberships', blank=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # --- Datos de contacto (no se piden en el checkout hoy; se completan a mano
    # desde el panel, ej. tras hablar con la clienta) ---
    parent_name = models.CharField(max_length=200, blank=True, help_text="Nombre del padre/apoderado")
    student_name = models.CharField(max_length=200, blank=True, help_text="Nombre del alumno (niño/a)")

    # --- Pausa de suscripción: congela el acceso y el calendario semanal de
    # cursos sin cerrar la cuenta. Al reanudar, se le devuelven los días
    # pausados (tanto al vencimiento como al desbloqueo de cursos). ---
    paused_at = models.DateTimeField(null=True, blank=True, help_text="Si está pausada, desde cuándo")
    total_paused_days = models.PositiveIntegerField(
        default=0, help_text="Días acumulados en pausa (se usan para correr las fechas al reanudar)",
    )

    @property
    def is_paused(self):
        return self.paused_at is not None

    @property
    def is_active(self):
        if self.is_paused:
            return False
        return self.expires_at > timezone.now()

    def pause(self):
        if not self.paused_at:
            self.paused_at = timezone.now()
            self.save(update_fields=['paused_at'])

    def resume(self):
        if self.paused_at:
            days_paused = (timezone.now() - self.paused_at).days
            self.expires_at = self.expires_at + timedelta(days=days_paused)
            self.total_paused_days += days_paused
            self.paused_at = None
            self.save(update_fields=['expires_at', 'total_paused_days', 'paused_at'])

    def __str__(self):
        state = 'pausada' if self.is_paused else ('activa' if self.is_active else 'vencida')
        return f"Membresía de {self.user.email} ({state} hasta {self.expires_at:%d-%m-%Y})"


class CourseProgress(models.Model):
    """
    Marca que un alumno terminó un curso. Se usa junto con el desbloqueo semanal
    (ver lms/services.py::get_course_access): el curso siguiente en la secuencia
    no se libera hasta que el anterior tiene un registro aquí, aunque ya haya
    pasado el lunes que le correspondía.
    """
    membership = models.ForeignKey(Membership, related_name='course_progress', on_delete=models.CASCADE)
    course = models.ForeignKey(Course, related_name='progress_entries', on_delete=models.CASCADE)
    completed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ('membership', 'course')

    def __str__(self):
        return f"{self.membership.user.email} completó {self.course.title}"


class LessonProgress(models.Model):
    """Marca que un alumno vio/completó un recurso concreto. El % de avance del
    curso = recursos completados / total, y al llegar a 100% el curso se da por
    terminado (se crea el CourseProgress) y se libera el siguiente."""
    membership = models.ForeignKey(Membership, related_name='lesson_progress', on_delete=models.CASCADE)
    lesson = models.ForeignKey(Lesson, related_name='progress_entries', on_delete=models.CASCADE)
    completed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ('membership', 'lesson')

    def __str__(self):
        return f"{self.membership.user.email} vio {self.lesson.title}"


class Diploma(models.Model):
    """Reconocimiento que el alumno gana al completar los cursos que lo preceden
    en la secuencia. Comparte el espacio de orden con los cursos (Course.order):
    la lista arrastrable del panel mezcla cursos y diplomas."""
    title = models.CharField(max_length=200, help_text="Ej: 'Diploma Nivel Básico'")
    description = models.TextField(blank=True, help_text="Mensaje que aparece en el diploma")
    image_file = models.FileField(
        upload_to='diplomas/', blank=True,
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp'])],
        verbose_name='Imagen del diploma',
        help_text='Opcional (JPG, PNG o WEBP). Si no subes nada se usa el diseño por defecto.',
    )
    image_url = models.URLField(
        max_length=500, blank=True,
        help_text='Alternativa: dirección de una imagen ya publicada en internet.',
    )
    order = models.PositiveIntegerField(default=0, help_text="Posición en la secuencia (compartida con los cursos)")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'id']

    @property
    def portada_url(self):
        """Imagen del diploma: la subida manda sobre la pegada por URL."""
        if self.image_file:
            return self.image_file.url
        return self.image_url or ''

    def __str__(self):
        return f"🎓 {self.title}"


class UnlockNotice(models.Model):
    """Marca que ya se avisó por correo del desbloqueo de un curso.

    Existe solo para que el comando `enviar_avisos_desbloqueo` sea idempotente:
    corre todos los días, y sin este registro le reenviaría el mismo aviso al
    mismo alumno cada día hasta que complete el curso.

    La unicidad (membresía, curso) es la que garantiza el "una sola vez": si dos
    ejecuciones se pisan, la segunda choca con IntegrityError en vez de mandar
    un correo repetido.
    """
    membership = models.ForeignKey(Membership, related_name='unlock_notices', on_delete=models.CASCADE)
    course = models.ForeignKey(Course, related_name='unlock_notices', on_delete=models.CASCADE)
    sent_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ('membership', 'course')

    def __str__(self):
        return f"aviso de {self.course.title} a {self.membership.user.email}"


class DiplomaAward(models.Model):
    """Registro de que un alumno desbloqueó un diploma (congela la fecha de logro)."""
    membership = models.ForeignKey(Membership, related_name='diploma_awards', on_delete=models.CASCADE)
    diploma = models.ForeignKey(Diploma, related_name='awards', on_delete=models.CASCADE)
    awarded_at = models.DateTimeField(default=timezone.now)
    # Cuándo se avisó por correo. Nulo = todavía no se avisó, y es lo que busca
    # el comando `enviar_avisos_desbloqueo` para no repetir el correo cada día.
    # El diploma se otorga al abrir la página, así que el aviso no puede salir
    # en ese mismo momento sin acoplar el envío de correo a un GET.
    email_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('membership', 'diploma')

    def __str__(self):
        return f"{self.membership.user.email} ganó {self.diploma.title}"


class AjustesAula(models.Model):
    """Ajustes del goteo, editables desde el panel. Es una fila única.

    Antes estaban implícitos en el código: se abría un modelo al comprar y se
    mostraban todos los bloqueados. Los dos son decisiones comerciales —cuánto
    contenido regalar de entrada y cuánta expectativa dejar a la vista—, así que
    tienen que poder cambiarse sin tocar código.
    """

    cursos_iniciales = models.PositiveIntegerField(
        default=3,
        help_text='Cuántos modelos quedan disponibles apenas se compra. Del siguiente '
                  'en adelante se libera uno por semana.',
    )
    bloqueados_visibles = models.PositiveIntegerField(
        default=1,
        help_text='Cuántos modelos bloqueados se muestran después de los disponibles, '
                  'para dar a entender que viene más. 0 = mostrarlos todos.',
    )
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Ajustes del Aula Virtual'
        verbose_name_plural = 'Ajustes del Aula Virtual'

    def __str__(self):
        return 'Ajustes del Aula Virtual'

    def save(self, *args, **kwargs):
        # Fila única: da igual desde dónde se guarde, siempre es la misma.
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def obtener(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
