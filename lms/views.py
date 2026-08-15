from django.http import FileResponse, Http404
from django.shortcuts import render
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from .models import Course, Lesson, Diploma, LessonProgress
from .serializers import CourseListSerializer, CourseStudentSerializer
from .services import (
    contenido_cerrado, cursos_de, get_course_access, get_preview_sequence,
    get_sequence_access, mark_lesson_completed,
)


def _get_membership(user):
    return getattr(user, 'membership', None)


def _es_vista_previa(user):
    """True si es una cuenta de gestión entrando al Aula sin ser alumna.

    Permite revisar el contenido tal como lo recibe el alumno, sin comprar un
    kit ni esperar el goteo semanal.

    No abre ninguna puerta nueva: quien es staff ya puede ver y descargar los
    mismos PDF e imágenes desde el panel (panel:lesson_preview_pdf), y además
    puede editarlos. Lo único que cambia es la comodidad de verlos montados.

    Si la cuenta de gestión SÍ tiene membresía (por ejemplo la clienta compró un
    kit para probar), manda su membresía real y no la vista previa: así ve
    exactamente lo mismo que vería su alumno, goteo incluido.
    """
    return bool(user.is_staff) and _get_membership(user) is None


def _serializar_secuencia(seq):
    """Convierte la secuencia de cursos y diplomas al JSON que espera el frontend.

    Sirve igual para la secuencia real del alumno y para la vista previa: las dos
    tienen la misma forma, así la tarjeta del Aula no necesita saber cuál está
    mirando.
    """
    items = []
    for it in seq:
        if it['type'] == 'course':
            data = CourseListSerializer(it['course']).data
            requerido = it.get('required_course')
            data.update({
                'type': 'course',
                'unlocked': it['unlocked'],
                'completed': it['completed'],
                'pct': it['pct'],
                'done': it['done'],
                'total': it['total'],
                'unlock_date': it['unlock_date'],
                # Para que la tarjeta pueda decir POR QUÉ está cerrado en vez de
                # mostrar siempre una fecha (que puede estar pasada).
                'lock_reason': it.get('lock_reason'),
                'required_course_title': requerido.title if requerido else None,
            })
        else:
            d = it['diploma']
            data = {
                'type': 'diploma',
                'id': d.id,
                'title': d.title,
                'description': d.description,
                'unlocked': it['unlocked'],
                'awarded_at': it['awarded_at'],
            }
        items.append(data)
    return items


class MyCoursesView(APIView):
    """Secuencia del alumno: cursos (con % de avance y estado de desbloqueo) y
    diplomas intercalados, más el estado de la membresía."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        membership = _get_membership(request.user)

        if membership is None:
            if _es_vista_previa(request.user):
                return Response({
                    'membership': None,
                    'preview': True,
                    'items': _serializar_secuencia(get_preview_sequence()),
                })
            return Response({'membership': None, 'items': []})

        return Response({
            'membership': {
                'active': membership.is_active,
                'expires_at': membership.expires_at,
                'student_name': membership.student_name,
            },
            'items': _serializar_secuencia(get_sequence_access(membership)),
        })


class CourseDetailView(APIView):
    """Recursos de un curso. Requiere que el curso esté DESBLOQUEADO (goteo
    semanal + completar el anterior). El video solo se entrega con membresía ACTIVA."""
    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        membership = _get_membership(request.user)

        # Vista previa de una cuenta de gestión: cualquier curso activo, sin
        # goteo ni progreso (no hay membresía donde guardarlo).
        if membership is None and _es_vista_previa(request.user):
            try:
                course = Course.objects.get(slug=slug, is_active=True)
            except Course.DoesNotExist:
                raise Http404
            data = CourseStudentSerializer(course, context={
                'membership_active': True,
                'completed_lesson_ids': set(),
            }).data
            data.update({
                'membership_active': True, 'preview': True,
                'completed': False, 'pct': 0, 'done': 0,
                'total': course.lessons.count(),
            })
            return Response(data)

        # cursos_de() y no membership.courses: el acceso se deriva de las
        # categorías del alumno, así que un curso agregado después a una
        # categoría que ya tiene también cuenta.
        if membership is None or not cursos_de(membership).filter(slug=slug).exists():
            return Response({'error': 'No tienes acceso a este curso'}, status=status.HTTP_403_FORBIDDEN)

        # Vencida: la carátula se sigue viendo en la lista, pero acá se corta. El
        # mensaje distingue "todavía no te toca" de "se te venció", que para el
        # apoderado son problemas distintos y con soluciones distintas.
        if contenido_cerrado(membership):
            return Response({
                'error': 'Tu suscripción venció. Renuévala para volver a entrar a los modelos.',
                'expired': True,
                'expires_at': membership.expires_at,
            }, status=status.HTTP_403_FORBIDDEN)

        course = Course.objects.get(slug=slug)
        access = get_course_access(membership)
        entry = next((a for a in access if a['course'].id == course.id), None)

        if entry is None or not entry['unlocked']:
            return Response({
                'error': 'Este curso todavía no está disponible.',
                'unlock_date': entry['unlock_date'] if entry else None,
            }, status=status.HTTP_403_FORBIDDEN)

        completed_ids = set(
            LessonProgress.objects.filter(membership=membership, lesson__course=course)
            .values_list('lesson_id', flat=True)
        )
        serializer = CourseStudentSerializer(course, context={
            'membership_active': membership.is_active,
            'completed_lesson_ids': completed_ids,
        })
        data = serializer.data
        data.update({
            'membership_active': membership.is_active,
            'completed': entry['completed'],
            'pct': entry['pct'],
            'done': entry['done'],
            'total': entry['total'],
        })
        return Response(data)


class LessonCompleteView(APIView):
    """El alumno marca un recurso como visto. Al completar el último, el curso
    queda terminado y se libera el siguiente en la secuencia."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        membership = _get_membership(request.user)
        if membership is None:
            if _es_vista_previa(request.user):
                # En vista previa no hay membresía donde guardar el avance. El
                # frontend oculta el botón; esto es la red por si igual llega.
                return Response(
                    {'error': 'Estás en vista previa: el avance no se guarda.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response({'error': 'Sin membresía'}, status=status.HTTP_403_FORBIDDEN)
        try:
            lesson = Lesson.objects.select_related('course').get(pk=pk)
        except Lesson.DoesNotExist:
            raise Http404
        if not mark_lesson_completed(membership, lesson):
            return Response({'error': 'Este recurso no está disponible todavía'}, status=status.HTTP_400_BAD_REQUEST)
        # devolvemos el avance actualizado del curso
        access = get_course_access(membership)
        entry = next((a for a in access if a['course'].id == lesson.course_id), None)
        return Response({'completed': True, 'pct': entry['pct'], 'done': entry['done'],
                         'total': entry['total'], 'course_completed': entry['completed']})


class LessonPdfView(APIView):
    """Descarga protegida del PDF: requiere membresía ACTIVA y curso otorgado."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        lesson, membership = _authorized_lesson_file(request, pk)
        if not lesson.pdf_file:
            raise Http404
        return FileResponse(
            lesson.pdf_file.open('rb'), as_attachment=True,
            filename=lesson.pdf_file.name.split('/')[-1], content_type='application/pdf',
        )


class LessonImageView(APIView):
    """Sirve la imagen protegida de un recurso (para mostrar el paso a paso).
    Requiere membresía ACTIVA y que el curso esté otorgado."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        lesson, membership = _authorized_lesson_file(request, pk)
        if not lesson.image_file:
            raise Http404
        return FileResponse(lesson.image_file.open('rb'))


def _authorized_lesson_file(request, pk):
    """Valida acceso a un archivo de recurso y devuelve (lesson, membership) o 403/404.

    Tener el curso OTORGADO no basta: al comprar un kit se otorgan de una vez
    todos sus cursos (grant_access_for_order), pero el goteo semanal libera uno
    por semana. Sin el chequeo de `unlocked`, un alumno con membresía válida
    podía enumerar los ids de recurso y bajarse el año completo de PDFs e
    imágenes el primer día. Es el mismo control que aplican CourseDetailView,
    mark_lesson_completed y DiplomaDownloadView; estos dos endpoints de archivo
    son la ÚNICA vía de acceso a protected_media, así que acá no es redundante.
    """
    from rest_framework.exceptions import PermissionDenied
    try:
        lesson = Lesson.objects.select_related('course').get(pk=pk)
    except Lesson.DoesNotExist:
        raise Http404
    membership = _get_membership(request.user)

    # Cuenta de gestión en vista previa: puede abrir cualquier recurso. No es
    # una fuga de contenido pagado —ya podía descargar estos mismos archivos
    # desde el panel—, pero sí es la única excepción a los tres chequeos de
    # abajo, así que va explícita y no escondida dentro de la condición.
    if membership is None and _es_vista_previa(request.user):
        return lesson, None

    # contenido_cerrado() y no `not is_active`: si la clienta configuró que al
    # vencer se siga viendo todo, los archivos tienen que seguir la misma regla
    # que la ficha del curso. La pausa sigue cerrando siempre.
    if (membership is None or contenido_cerrado(membership)
            or not cursos_de(membership).filter(pk=lesson.course_id).exists()):
        raise PermissionDenied('Necesitas una membresía activa para ver este contenido')

    access = get_course_access(membership)
    entry = next((a for a in access if a['course'].id == lesson.course_id), None)
    if entry is None or not entry['unlocked']:
        raise PermissionDenied('Este curso todavía no está disponible.')

    return lesson, membership


class DiplomaDownloadView(APIView):
    """Devuelve el diploma personalizado (HTML imprimible) si el alumno lo desbloqueó."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        membership = _get_membership(request.user)

        # Vista previa: se muestra el diploma con un nombre de ejemplo, para
        # revisar cómo queda impreso antes de que lo reciba un alumno real.
        if membership is None and _es_vista_previa(request.user):
            try:
                diploma = Diploma.objects.get(pk=pk, is_active=True)
            except Diploma.DoesNotExist:
                raise Http404
            return render(request, 'lms/diploma.html', {
                'diploma': diploma,
                'student_name': 'Nombre del alumno',
                'awarded_at': timezone.localdate(),
            })

        if membership is None:
            raise Http404
        try:
            diploma = Diploma.objects.get(pk=pk, is_active=True)
        except Diploma.DoesNotExist:
            raise Http404
        seq = get_sequence_access(membership)
        entry = next((it for it in seq if it['type'] == 'diploma' and it['diploma'].id == diploma.id), None)
        if entry is None or not entry['unlocked']:
            raise Http404
        return render(request, 'lms/diploma.html', {
            'diploma': diploma,
            'student_name': membership.student_name or membership.user.email,
            'awarded_at': entry['awarded_at'],
        })
