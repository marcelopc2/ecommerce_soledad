from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .auth_views import LoginView, MeView, SetPasswordView, RequestResetView, ChangePasswordView
from .views import MyCoursesView, CourseDetailView, LessonPdfView
from .cms_views import (
    ProductCMSViewSet, CategoryCMSViewSet, ProductImageCMSViewSet,
    CourseCMSViewSet, LessonCMSViewSet, MembershipCMSViewSet,
)

# --- Auth (montado en /api/auth/) ---
auth_urlpatterns = [
    path('login/', LoginView.as_view(), name='auth-login'),
    path('refresh/', TokenRefreshView.as_view(), name='auth-refresh'),
    path('me/', MeView.as_view(), name='auth-me'),
    path('set-password/', SetPasswordView.as_view(), name='auth-set-password'),
    path('request-reset/', RequestResetView.as_view(), name='auth-request-reset'),
    path('change-password/', ChangePasswordView.as_view(), name='auth-change-password'),
]

# --- LMS alumno (montado en /api/lms/) ---
student_urlpatterns = [
    path('my-courses/', MyCoursesView.as_view(), name='lms-my-courses'),
    path('courses/<slug:slug>/', CourseDetailView.as_view(), name='lms-course-detail'),
    path('lessons/<int:pk>/pdf/', LessonPdfView.as_view(), name='lms-lesson-pdf'),
]

# --- CMS staff (montado en /api/cms/) ---
router = DefaultRouter()
router.register('products', ProductCMSViewSet, basename='cms-products')
router.register('categories', CategoryCMSViewSet, basename='cms-categories')
router.register('product-images', ProductImageCMSViewSet, basename='cms-product-images')
router.register('courses', CourseCMSViewSet, basename='cms-courses')
router.register('lessons', LessonCMSViewSet, basename='cms-lessons')
router.register('memberships', MembershipCMSViewSet, basename='cms-memberships')

cms_urlpatterns = [
    path('', include(router.urls)),
]
