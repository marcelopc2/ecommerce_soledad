from rest_framework import serializers
from catalog.models import Product, Category, ProductImage
from .models import Course, Lesson, Membership


# ---------- LMS (alumno) ----------

class LessonStudentSerializer(serializers.ModelSerializer):
    """Lección para el alumno. La URL del video solo se incluye si la membresía está activa
    (lo decide la vista); el PDF siempre se baja por el endpoint protegido."""
    has_pdf = serializers.SerializerMethodField()

    class Meta:
        model = Lesson
        fields = ['id', 'title', 'order', 'lesson_type', 'video_embed_url', 'has_pdf']

    def get_has_pdf(self, obj):
        return bool(obj.pdf_file)

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


# ---------- CMS (staff) ----------

class LessonCMSSerializer(serializers.ModelSerializer):
    pdf_filename = serializers.SerializerMethodField()

    class Meta:
        model = Lesson
        fields = ['id', 'course', 'title', 'order', 'lesson_type', 'video_embed_url', 'pdf_file', 'pdf_filename']
        extra_kwargs = {'pdf_file': {'write_only': True, 'required': False}}

    def get_pdf_filename(self, obj):
        return obj.pdf_file.name.split('/')[-1] if obj.pdf_file else ''


class CourseCMSSerializer(serializers.ModelSerializer):
    lessons = LessonCMSSerializer(many=True, read_only=True)

    class Meta:
        model = Course
        fields = ['id', 'title', 'slug', 'description', 'image_url', 'is_active', 'lessons']


class ProductImageCMSSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'image_url', 'is_main']


class ProductCMSSerializer(serializers.ModelSerializer):
    images = ProductImageCMSSerializer(many=True, read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'category', 'category_name', 'name', 'slug', 'description', 'price',
            'stock', 'is_digital', 'is_active', 'weight_kg', 'width_cm', 'height_cm',
            'length_cm', 'courses', 'access_months', 'images',
        ]


class CategoryCMSSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug']


class MembershipCMSSerializer(serializers.ModelSerializer):
    email = serializers.CharField(source='user.email', read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    courses_count = serializers.IntegerField(source='courses.count', read_only=True)

    class Meta:
        model = Membership
        fields = ['id', 'email', 'expires_at', 'is_active', 'courses_count', 'created_at']
