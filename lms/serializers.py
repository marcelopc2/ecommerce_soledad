from rest_framework import serializers
from .models import Course, Lesson


# ---------- LMS (alumno) ----------

class LessonStudentSerializer(serializers.ModelSerializer):
    """Recurso para el alumno. La URL del video solo se incluye si la membresía
    está activa (lo decide la vista); PDF e imagen se sirven por endpoint protegido.
    `completed` se inyecta desde el contexto (set de ids completados)."""
    has_pdf = serializers.SerializerMethodField()
    has_image = serializers.SerializerMethodField()
    completed = serializers.SerializerMethodField()

    class Meta:
        model = Lesson
        fields = ['id', 'title', 'description', 'order', 'lesson_type',
                  'video_embed_url', 'has_pdf', 'has_image', 'completed']

    def get_has_pdf(self, obj):
        return bool(obj.pdf_file)

    def get_has_image(self, obj):
        return bool(obj.image_file)

    def get_completed(self, obj):
        return obj.id in self.context.get('completed_lesson_ids', set())

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not self.context.get('membership_active', False):
            data['video_embed_url'] = ''  # sin membresía activa no se entrega la URL
        return data


class CourseStudentSerializer(serializers.ModelSerializer):
    lessons = LessonStudentSerializer(many=True, read_only=True)

    class Meta:
        model = Course
        fields = ['id', 'title', 'slug', 'description', 'image_url', 'lessons']


class CourseListSerializer(serializers.ModelSerializer):
    lessons_count = serializers.IntegerField(source='lessons.count', read_only=True)

    class Meta:
        model = Course
        fields = ['id', 'title', 'slug', 'description', 'image_url', 'lessons_count']


class ProfileSerializer(serializers.Serializer):
    """Edición de los nombres desde el perfil del alumno.

    Reutiliza `validar_nombre` del checkout (payments/serializers.py) para que
    las reglas sean LAS MISMAS en los dos lugares: si acá fueran más laxas, se
    podría dejar en el diploma un nombre que el checkout habría rechazado.
    """
    student_name = serializers.CharField(max_length=200, required=False)
    parent_name = serializers.CharField(max_length=200, required=False, allow_blank=True)

    def validate_student_name(self, v):
        from payments.serializers import validar_nombre
        return validar_nombre(v, 'nombre del niño o niña')

    def validate_parent_name(self, v):
        # El del apoderado sí puede quedar vacío: no sale en ningún documento.
        if not (v or '').strip():
            return ''
        from payments.serializers import validar_nombre
        return validar_nombre(v, 'nombre del apoderado')
