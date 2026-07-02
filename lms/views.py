from django.http import FileResponse, Http404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from .models import Course, Lesson
from .serializers import CourseListSerializer, CourseStudentSerializer


def _get_membership(user):
    return getattr(user, 'membership', None)


class MyCoursesView(APIView):
    """Cursos del alumno + estado de su membresía."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        membership = _get_membership(request.user)
        if membership is None:
            return Response({'membership': None, 'courses': []})

        courses = membership.courses.filter(is_active=True)
        return Response({
            'membership': {
                'active': membership.is_active,
                'expires_at': membership.expires_at,
            },
            'courses': CourseListSerializer(courses, many=True).data,
        })


class CourseDetailView(APIView):
    """Lecciones de un curso. Las URLs de video solo se entregan con membresía ACTIVA."""
    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        membership = _get_membership(request.user)
        if membership is None or not membership.courses.filter(slug=slug).exists():
            return Response({'error': 'No tienes acceso a este curso'}, status=status.HTTP_403_FORBIDDEN)

        course = Course.objects.get(slug=slug)
        serializer = CourseStudentSerializer(
            course, context={'membership_active': membership.is_active},
        )
        data = serializer.data
        data['membership_active'] = membership.is_active
        return Response(data)


class LessonPdfView(APIView):
    """Descarga protegida del PDF: requiere membresía ACTIVA y que el curso esté otorgado."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            lesson = Lesson.objects.select_related('course').get(pk=pk)
        except Lesson.DoesNotExist:
            raise Http404

        membership = _get_membership(request.user)
        if (
            membership is None
            or not membership.is_active
            or not membership.courses.filter(pk=lesson.course_id).exists()
        ):
            return Response({'error': 'Necesitas una membresía activa para descargar este contenido'},
                            status=status.HTTP_403_FORBIDDEN)

        if not lesson.pdf_file:
            raise Http404

        return FileResponse(
            lesson.pdf_file.open('rb'),
            as_attachment=True,
            filename=lesson.pdf_file.name.split('/')[-1],
            content_type='application/pdf',
        )
