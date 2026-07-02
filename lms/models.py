from django.db import models
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.core.validators import FileExtensionValidator
from django.utils import timezone
from payments.models import Order

# Los PDFs se guardan FUERA de las carpetas públicas (static/media):
# solo se sirven vía endpoint autenticado que verifica la membresía.
protected_storage = FileSystemStorage(location=settings.PROTECTED_MEDIA_ROOT)


class Course(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    image_url = models.URLField(max_length=500, blank=True, help_text="Imagen de portada (URL)")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Lesson(models.Model):
    TYPE_CHOICES = (('VIDEO', 'Video'), ('PDF', 'Documento PDF'))

    course = models.ForeignKey(Course, related_name='lessons', on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=1, help_text="Orden de la lección dentro del curso")
    lesson_type = models.CharField(max_length=5, choices=TYPE_CHOICES)
    video_embed_url = models.URLField(
        max_length=500, blank=True,
        help_text="URL de embed del video (YouTube/Vimeo). Solo para lecciones de tipo VIDEO.",
    )
    pdf_file = models.FileField(
        storage=protected_storage, upload_to='lessons/', blank=True, null=True,
        validators=[FileExtensionValidator(allowed_extensions=['pdf'])],
        help_text="PDF protegido. Solo para lecciones de tipo PDF.",
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

    @property
    def is_active(self):
        return self.expires_at > timezone.now()

    def __str__(self):
        state = 'activa' if self.is_active else 'vencida'
        return f"Membresía de {self.user.email} ({state} hasta {self.expires_at:%d-%m-%Y})"
