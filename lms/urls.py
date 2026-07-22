from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .auth_views import (
    LoginView, MeView, ProfileView, SetPasswordView, RequestResetView,
    ChangePasswordView,
)
from .views import (
    MyCoursesView, CourseDetailView, LessonPdfView, LessonImageView,
    LessonCompleteView, DiplomaDownloadView,
)

# --- Auth (montado en /api/auth/) ---
auth_urlpatterns = [
    path('login/', LoginView.as_view(), name='auth-login'),
    path('refresh/', TokenRefreshView.as_view(), name='auth-refresh'),
    path('me/', MeView.as_view(), name='auth-me'),
    path('profile/', ProfileView.as_view(), name='auth-profile'),
    path('set-password/', SetPasswordView.as_view(), name='auth-set-password'),
    path('request-reset/', RequestResetView.as_view(), name='auth-request-reset'),
    path('change-password/', ChangePasswordView.as_view(), name='auth-change-password'),
]

# --- LMS alumno (montado en /api/lms/) ---
student_urlpatterns = [
    path('my-courses/', MyCoursesView.as_view(), name='lms-my-courses'),
    path('courses/<slug:slug>/', CourseDetailView.as_view(), name='lms-course-detail'),
    path('lessons/<int:pk>/complete/', LessonCompleteView.as_view(), name='lms-lesson-complete'),
    path('lessons/<int:pk>/pdf/', LessonPdfView.as_view(), name='lms-lesson-pdf'),
    path('lessons/<int:pk>/image/', LessonImageView.as_view(), name='lms-lesson-image'),
    path('diplomas/<int:pk>/download/', DiplomaDownloadView.as_view(), name='lms-diploma-download'),
]
