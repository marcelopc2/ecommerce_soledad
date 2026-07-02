"""
API del panel CMS de la clienta. Todos los endpoints requieren usuario STAFF.
El panel React (/panel) consume esta API; el admin de Django queda como
herramienta interna de desarrollo.
"""
from rest_framework import viewsets
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAdminUser

from catalog.models import Product, Category, ProductImage
from .models import Course, Lesson, Membership
from .serializers import (
    ProductCMSSerializer, CategoryCMSSerializer, ProductImageCMSSerializer,
    CourseCMSSerializer, LessonCMSSerializer, MembershipCMSSerializer,
)


class ProductCMSViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all().order_by('-created_at')
    serializer_class = ProductCMSSerializer
    permission_classes = [IsAdminUser]


class CategoryCMSViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategoryCMSSerializer
    permission_classes = [IsAdminUser]


class ProductImageCMSViewSet(viewsets.ModelViewSet):
    queryset = ProductImage.objects.all()
    serializer_class = ProductImageCMSSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = super().get_queryset()
        product_id = self.request.query_params.get('product')
        return qs.filter(product_id=product_id) if product_id else qs

    def perform_create(self, serializer):
        serializer.save(product_id=self.request.data.get('product'))


class CourseCMSViewSet(viewsets.ModelViewSet):
    queryset = Course.objects.all().order_by('-created_at')
    serializer_class = CourseCMSSerializer
    permission_classes = [IsAdminUser]


class LessonCMSViewSet(viewsets.ModelViewSet):
    queryset = Lesson.objects.all()
    serializer_class = LessonCMSSerializer
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser, FormParser, JSONParser]  # multipart para subir PDFs

    def get_queryset(self):
        qs = super().get_queryset()
        course_id = self.request.query_params.get('course')
        return qs.filter(course_id=course_id) if course_id else qs


class MembershipCMSViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Membership.objects.select_related('user').order_by('-updated_at')
    serializer_class = MembershipCMSSerializer
    permission_classes = [IsAdminUser]
