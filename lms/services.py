"""
Otorgamiento de acceso al LMS cuando se confirma un pago, y correos asociados.
Mismos principios que la boleta: idempotente y no-bloqueante (el pago nunca
se rompe por un problema de LMS/email).
"""
import logging
from datetime import timedelta
from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from core.emails import enviar_email
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes

from .models import Membership, CourseProgress, LessonProgress, Diploma, DiplomaAward

User = get_user_model()
log = logging.getLogger('ingenioblocks.pagos')


# ---------- Desbloqueo semanal de cursos ----------
#
# El curso 1 (según Course.order) está disponible desde el día de la compra.
# Desde ahí, se libera uno nuevo cada lunes -pero solo si el alumno ya marcó
# como completado el curso anterior-. Si llega el lunes y el curso actual
# sigue sin completarse, el siguiente queda bloqueado hasta que lo termine
# (no se salta la fila). Comprar un kit adicional simplemente agrega más
# cursos al final de esta misma secuencia: el calendario no se reinicia.

def _next_monday_strictly_after(d):
    """Primer lunes DESPUÉS de `d` (si `d` ya es lunes, devuelve el de la semana siguiente)."""
    days_ahead = (7 - d.weekday()) % 7  # weekday(): lunes=0 ... domingo=6
    if days_ahead == 0:
        days_ahead = 7
    return d + timedelta(days=days_ahead)


def _unlock_date(start_date, index):
    """Fecha programada de liberación del curso en la posición `index` (0-based).
    El curso 0 está disponible desde `start_date`; el resto, cada lunes siguiente."""
    if index == 0:
        return start_date
    first_monday = _next_monday_strictly_after(start_date)
    return first_monday + timedelta(weeks=index - 1)


def _completion_map(membership, courses):
    """Por cada curso: recursos totales, completados, % y si está terminado.
    Un curso se da por terminado cuando todos sus recursos están vistos (o si
    tiene un CourseProgress heredado del sistema anterior / cursos sin recursos)."""
    course_ids = [c.id for c in courses]
    totals = {c.id: c.lessons.count() for c in courses}
    done = {}
    for lp in LessonProgress.objects.filter(membership=membership, lesson__course_id__in=course_ids).values('lesson__course_id'):
        cid = lp['lesson__course_id']
        done[cid] = done.get(cid, 0) + 1
    legacy_completed = set(
        CourseProgress.objects.filter(membership=membership, course_id__in=course_ids)
        .values_list('course_id', flat=True)
    )
    out = {}
    for c in courses:
        total = totals[c.id]
        d = done.get(c.id, 0)
        completed = (c.id in legacy_completed) or (total > 0 and d >= total)
        out[c.id] = {
            'total': total,
            'done': d,
            'completed': completed,
            'pct': 100 if completed else (round(d / total * 100) if total else 0),
        }
    return out


def get_course_access(membership):
    """
    Devuelve la lista de cursos de la membresía (en orden), cada uno con:
    - course, unlocked, completed, pct, done, total, unlock_date.
    """
    courses = list(membership.courses.filter(is_active=True).order_by('order', 'id'))
    comp = _completion_map(membership, courses)
    # Los días que estuvo pausada no cuentan para el calendario: se corre el
    # punto de partida hacia adelante esa misma cantidad de días.
    #
    # localtime() antes de .date() porque con USE_TZ las fechas se guardan en
    # UTC, y Chile va 3-4 horas atrás: sin convertir, el "día" del goteo
    # cambiaba a las 20:00/21:00 hora local, así que el contenido se liberaba
    # una tarde antes de lo prometido y una compra hecha un domingo por la
    # noche quedaba registrada como lunes, corriendo toda la secuencia.
    start_date = (timezone.localtime(membership.created_at).date()
                  + timedelta(days=membership.total_paused_days))
    today = timezone.localdate()

    result = []
    blocked = False
    curso_previo = None      # el que hay que terminar para abrir el siguiente
    for i, course in enumerate(courses):
        unlock_date = _unlock_date(start_date, i)
        info = comp[course.id]
        falta_fecha = today < unlock_date
        unlocked = not falta_fecha and not blocked

        # Por qué está cerrado. Son dos motivos distintos y el alumno necesita
        # distinguirlos: mostrar siempre "disponible el <fecha>" hacía que un
        # curso trabado por no haber terminado el anterior luciera una fecha ya
        # pasada, y el apoderado concluía que la plataforma estaba fallando.
        if unlocked:
            motivo, curso_requerido = None, None
        elif blocked:
            motivo, curso_requerido = 'previo', curso_previo
        else:
            motivo, curso_requerido = 'fecha', None

        result.append({
            'course': course,
            'unlocked': unlocked,
            'completed': info['completed'],
            'pct': info['pct'],
            'done': info['done'],
            'total': info['total'],
            'unlock_date': unlock_date,
            'lock_reason': motivo,              # None | 'fecha' | 'previo'
            'required_course': curso_requerido,  # el curso que falta completar
        })
        # Lo que sigue queda bloqueado si este no se pudo desbloquear, o si se
        # desbloqueó pero el alumno todavía no lo completa.
        if not unlocked or not info['completed']:
            if not blocked:
                curso_previo = course   # el primero que traba la cadena
            blocked = True
    return result


def get_sequence_access(membership):
    """Secuencia completa del alumno: cursos y diplomas mezclados por su `order`.
    Un diploma se desbloquea cuando todos los cursos que lo preceden están
    completos. Al desbloquearse se registra el DiplomaAward (congela la fecha)."""
    course_access = get_course_access(membership)
    items = [{'type': 'course', 'order': a['course'].order, **a} for a in course_access]
    for d in Diploma.objects.filter(is_active=True):
        items.append({'type': 'diploma', 'order': d.order, 'diploma': d})
    # dentro del mismo `order`, el curso va antes que el diploma
    items.sort(key=lambda x: (x['order'], 0 if x['type'] == 'course' else 1))

    all_prev_courses_done = True
    for it in items:
        if it['type'] == 'course':
            if not it['completed']:
                all_prev_courses_done = False
        else:
            it['unlocked'] = all_prev_courses_done
            it['awarded_at'] = None
            if all_prev_courses_done:
                award, _ = DiplomaAward.objects.get_or_create(membership=membership, diploma=it['diploma'])
                it['awarded_at'] = award.awarded_at
    return items


def mark_lesson_completed(membership, lesson):
    """Marca un recurso como visto (solo si su curso está desbloqueado). Al
    completar el último recurso, marca el curso como terminado. Idempotente."""
    access = get_course_access(membership)
    entry = next((a for a in access if a['course'].id == lesson.course_id), None)
    if entry is None or not entry['unlocked']:
        return False
    LessonProgress.objects.get_or_create(membership=membership, lesson=lesson)

    course = lesson.course
    total = course.lessons.count()
    done = LessonProgress.objects.filter(membership=membership, lesson__course=course).count()
    if total > 0 and done >= total:
        CourseProgress.objects.get_or_create(membership=membership, course=course)
    return True


def grant_access_for_order(order):
    """
    Crea/extiende la membresía del comprador según los productos de la orden.
    - Idempotente: si la orden ya fue aplicada a la membresía, no vuelve a sumar meses.
    - No-bloqueante: nunca lanza excepción hacia el flujo de pago.
    Retorna la Membership o None si la orden no otorga cursos.
    """
    try:
        return _grant(order)
    except Exception:
        # No rompemos el pago por un fallo de LMS, pero queda en pagos.log con
        # el id de la orden para poder otorgar el acceso a mano desde el panel.
        log.exception('No se pudo otorgar el acceso al LMS de la orden %s', order.order_id)
        return None


@transaction.atomic
def _grant(order):
    """Crea o extiende la membresía de una orden pagada.

    Va en una transacción porque son cuatro escrituras encadenadas (membresía,
    cursos, orden aplicada, vencimiento). Si fallaba entre el save() —que ya
    había extendido expires_at— y el orders.add() —que es la marca de
    idempotencia—, un reintento volvía a sumar los meses.
    """
    products = list(order.products.all())
    courses = [c for p in products for c in p.courses.filter(is_active=True)]
    months = max((p.access_months for p in products), default=0)

    if not courses or months <= 0:
        return None  # la orden no incluye contenido LMS

    email = order.customer_email.lower().strip()
    user, user_created = User.objects.get_or_create(
        username=email,
        defaults={'email': email},
    )
    if user_created:
        user.set_unusable_password()  # definirá su clave con el link del correo
        user.save()

    membership, _ = Membership.objects.get_or_create(
        user=user,
        defaults={'expires_at': timezone.now()},
    )

    # Nombres del checkout → membresía. El del alumno es el que sale impreso en
    # el DIPLOMA (ver lms/views.py DiplomaDownloadView). Solo se rellenan si
    # están vacíos: si la clienta los corrigió a mano en el panel, una compra
    # posterior no debe pisar esa corrección.
    if order.student_name and not membership.student_name:
        membership.student_name = order.student_name
    if order.customer_name and not membership.parent_name:
        membership.parent_name = order.customer_name

    # Idempotencia: si esta orden ya fue aplicada (webhook + retorno duplicado), no re-sumar.
    if membership.orders.filter(pk=order.pk).exists():
        membership.save()   # los nombres sí se guardan aunque no se re-sumen meses
        return membership

    base = membership.expires_at if membership.expires_at > timezone.now() else timezone.now()
    membership.expires_at = base + relativedelta(months=months)
    membership.save()
    membership.courses.add(*courses)
    membership.orders.add(order)

    if user_created or not user.has_usable_password():
        _send_welcome_email(user, membership)
    else:
        _send_extended_email(user, membership)

    return membership


def _set_password_link(user):
    """Link de un solo uso para definir/restablecer la contraseña (token estándar de Django)."""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return f"{settings.FRONTEND_URL}/definir-clave/{uid}/{token}"


def _nombre_para_saludo(user, membership=None):
    """El nombre del apoderado si lo tenemos; si no, la parte previa al @.
    Nunca el correo completo: queda feo en un saludo."""
    if membership and membership.parent_name:
        return membership.parent_name.split()[0]
    return (user.email or user.username).split('@')[0]


def _send_welcome_email(user, membership):
    enviar_email(
        'bienvenida',
        asunto='¡Bienvenido a Ingenio Blocks! Activa tu acceso',
        destinatarios=[user.email],
        contexto={
            'nombre': _nombre_para_saludo(user, membership),
            'email': user.email,
            'link': _set_password_link(user),
            'vigencia_texto': f'Tu acceso está activo hasta el {membership.expires_at:%d-%m-%Y}.',
        },
    )


def _send_extended_email(user, membership):
    enviar_email(
        'acceso_extendido',
        asunto='Tu acceso a Ingenio Blocks fue extendido',
        destinatarios=[user.email],
        contexto={
            'nombre': _nombre_para_saludo(user, membership),
            'link': f'{settings.FRONTEND_URL}/mis-cursos',
            'vigencia_texto': f'Ahora tu acceso está activo hasta el {membership.expires_at:%d-%m-%Y}.',
        },
    )


def send_reset_email(user):
    """Correo de recuperación de contraseña (mismo link de un solo uso)."""
    enviar_email(
        'recuperar_clave',
        asunto='Restablece tu contraseña de Ingenio Blocks',
        destinatarios=[user.email],
        contexto={'link': _set_password_link(user)},
    )


def send_course_unlocked_email(membership, course, numero):
    """Avisa que se liberó un modelo nuevo. Lo dispara el comando
    `enviar_avisos_desbloqueo` (ver lms/management/commands/), porque el goteo
    depende del paso del tiempo y no de una acción del usuario."""
    alumno = membership.student_name or ''
    saludo = (f'Hola {_nombre_para_saludo(membership.user, membership)}, esta semana '
              f'{alumno or "tu hijo/a"} puede construir un modelo nuevo:')
    enviar_email(
        'curso_desbloqueado',
        asunto='¡Se desbloqueó un modelo nuevo! · Ingenio Blocks',
        destinatarios=[membership.user.email],
        contexto={
            'saludo': saludo,
            'numero': numero,
            'curso_titulo': course.title,
            'curso_descripcion': course.description,
            'link': f'{settings.FRONTEND_URL}/curso/{course.slug}',
        },
    )


def send_diploma_email(membership, diploma, awarded_at=None):
    """Avisa que el alumno se ganó un diploma."""
    enviar_email(
        'diploma_obtenido',
        asunto='¡Conseguiste un diploma! · Ingenio Blocks',
        destinatarios=[membership.user.email],
        contexto={
            'nombre': membership.student_name or _nombre_para_saludo(membership.user, membership),
            'diploma_titulo': diploma.title,
            'fecha': awarded_at.strftime('%d-%m-%Y') if awarded_at else '',
            'link': f'{settings.FRONTEND_URL}/mis-cursos',
        },
    )
