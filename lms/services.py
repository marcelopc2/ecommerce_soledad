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

from .models import (
    AjustesAula, Course, Membership, CourseProgress, LessonProgress, Diploma, DiplomaAward,
)

User = get_user_model()
log = logging.getLogger('ingenioblocks.pagos')


# ---------- Desbloqueo de cursos ----------
#
# El acceso se organiza por CATEGORÍAS (lms.CourseCategory). Cada una tiene su
# propio ritmo y su propio calendario, anclado al día en que ESE alumno la
# obtuvo (MembershipCategory.obtenida_en):
#
#   - modo TODO:   sus cursos quedan abiertos desde ese mismo día.
#   - modo GOTEO:  los primeros `cursos_iniciales` abren ese día y de ahí se
#                  libera uno cada 7 días, pero solo si el alumno completó el
#                  anterior (no se salta la fila).
#
# Un curso que está en varias categorías toma el estado MÁS FAVORABLE: si
# cualquiera de las categorías del alumno lo tiene abierto, está abierto. Así,
# comprar un pack premium que abre todo no queda anulado porque el mismo curso
# también viva en una categoría con goteo.
#
# El alumno ve una sola lista ordenada por Course.order; las categorías son
# maquinaria interna que él no necesita entender.

def _unlock_date(start_date, index, iniciales=1):
    """Fecha programada de liberación del curso en la posición `index` (0-based).

    El calendario es RELATIVO a la fecha de compra de cada alumno, no a un día
    fijo de la semana: quien compró un miércoles recibe su modelo nuevo cada
    miércoles, y quien compró un lunes lo recibe cada lunes.

    Antes se saltaba al lunes siguiente, con dos efectos raros: al que compraba
    un miércoles le llegaba el segundo modelo a los 5 días (no a los 7), y al
    que compraba un domingo le llegaba al día siguiente. Además el "cada semana"
    que se promete en la portada dejaba de cumplirse para casi todos.

    `start_date` ya viene corrido por los días que la membresía estuvo pausada.

    `iniciales` es cuántos modelos quedan abiertos el día de la compra (ajustable
    desde el panel). Con 3, las posiciones 0, 1 y 2 salen ese mismo día y recién
    la 3 espera una semana: el recién llegado tiene con qué empezar sin esperar,
    y de ahí en adelante se mantiene el ritmo semanal que promete la portada.
    """
    return start_date + timedelta(weeks=max(0, index - (iniciales - 1)))


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


def _categorias_del_alumno(membership):
    """Categorías que obtuvo, con sus cursos ya precargados.

    Se traen los cursos de una sola vez (prefetch) porque el cálculo recorre
    cada categoría por separado: sin esto, un alumno con varias categorías
    dispararía una consulta por cada una en cada carga del Aula.
    """
    from .models import MembershipCategory

    return (
        MembershipCategory.objects
        .filter(membership=membership, categoria__is_active=True)
        .select_related('categoria')
        .prefetch_related('categoria__cursos_en_categoria__curso')
    )


def cursos_de(membership):
    """Todos los cursos activos a los que el alumno tiene derecho.

    Se DERIVAN de sus categorías, no de una lista copiada al comprar: por eso
    agregar un curso a una categoría lo entrega a todos los que ya la tienen,
    sin tocar productos ni membresías.

    `membership.courses` se sigue considerando para no dejar afuera lo otorgado
    antes de que existieran las categorías (y cualquier asignación manual).
    """
    ids = set()
    for mc in _categorias_del_alumno(membership):
        for cc in mc.categoria.cursos_en_categoria.all():
            if cc.curso.is_active:
                ids.add(cc.curso.id)
    ids.update(membership.courses.filter(is_active=True).values_list('id', flat=True))
    return Course.objects.filter(id__in=ids).order_by('order', 'id')


def _estado_en_categoria(mc, comp, today):
    """Cómo queda cada curso de UNA categoría: {curso_id: (abierto, fecha, motivo, curso_requerido)}.

    Es el cálculo de siempre, pero acotado a los cursos de esta categoría y
    anclado a la fecha en que el alumno la obtuvo.
    """
    categoria = mc.categoria
    membership = mc.membership

    # Los días que estuvo pausada no cuentan: se corre el punto de partida hacia
    # adelante esa misma cantidad de días.
    #
    # localtime() antes de .date() porque con USE_TZ las fechas se guardan en
    # UTC, y Chile va 3-4 horas atrás: sin convertir, el "día" del goteo
    # cambiaba a las 20:00/21:00 hora local, así que el contenido se liberaba
    # una tarde antes de lo prometido y una compra hecha un domingo por la
    # noche quedaba registrada como lunes, corriendo toda la secuencia.
    inicio = (timezone.localtime(mc.obtenida_en).date()
              + timedelta(days=membership.total_paused_days))

    cursos = [cc.curso for cc in categoria.cursos_en_categoria.all() if cc.curso.is_active]

    estados = {}

    if categoria.abre_todo:
        # Sin goteo ni cadena de "termina el anterior": la categoría se compró
        # justamente para tenerlo todo disponible.
        for curso in cursos:
            estados[curso.id] = (True, inicio, None, None)
        return estados

    bloqueado = False
    curso_previo = None      # el que hay que terminar para abrir el siguiente
    for i, curso in enumerate(cursos):
        fecha = _unlock_date(inicio, i, categoria.cursos_iniciales)
        info = comp.get(curso.id)
        falta_fecha = today < fecha
        abierto = not falta_fecha and not bloqueado

        # Por qué está cerrado. Son dos motivos distintos y el alumno necesita
        # distinguirlos: mostrar siempre "disponible el <fecha>" hacía que un
        # curso trabado por no haber terminado el anterior luciera una fecha ya
        # pasada, y el apoderado concluía que la plataforma estaba fallando.
        if abierto:
            motivo, requerido = None, None
        elif bloqueado:
            motivo, requerido = 'previo', curso_previo
        else:
            motivo, requerido = 'fecha', None

        estados[curso.id] = (abierto, fecha, motivo, requerido)

        completado = info['completed'] if info else False
        if not abierto or not completado:
            if not bloqueado:
                curso_previo = curso
            bloqueado = True

    return estados


def get_course_access(membership):
    """
    Devuelve la lista de cursos de la membresía (en orden), cada uno con:
    - course, unlocked, completed, pct, done, total, unlock_date.

    Cada categoría se evalúa por separado y el curso toma el estado MÁS
    FAVORABLE de todas las que lo incluyen: abierto gana sobre cerrado, y entre
    cerrados gana la fecha más cercana. Si no, tener un pack que abre todo no
    serviría de nada cuando el mismo curso vive también en una categoría con
    goteo.
    """
    courses = list(cursos_de(membership))
    comp = _completion_map(membership, courses)
    today = timezone.localdate()

    por_categoria = [
        _estado_en_categoria(mc, comp, today)
        for mc in _categorias_del_alumno(membership)
    ]

    # Respaldo para lo otorgado antes de las categorías (o a mano): sin esto,
    # esos cursos no aparecerían en ninguna categoría y quedarían cerrados para
    # siempre. Replica el cálculo anterior, anclado a la creación de la membresía.
    sueltos = [c for c in courses if not any(c.id in est for est in por_categoria)]
    if sueltos:
        inicio = (timezone.localtime(membership.created_at).date()
                  + timedelta(days=membership.total_paused_days))
        iniciales = AjustesAula.obtener().cursos_iniciales
        estados_sueltos = {}
        bloqueado = False
        previo = None
        for i, curso in enumerate(sueltos):
            fecha = _unlock_date(inicio, i, iniciales)
            info = comp.get(curso.id)
            abierto = today >= fecha and not bloqueado
            if abierto:
                motivo, requerido = None, None
            elif bloqueado:
                motivo, requerido = 'previo', previo
            else:
                motivo, requerido = 'fecha', None
            estados_sueltos[curso.id] = (abierto, fecha, motivo, requerido)
            if not abierto or not (info['completed'] if info else False):
                if not bloqueado:
                    previo = curso
                bloqueado = True
        por_categoria.append(estados_sueltos)

    result = []
    for course in courses:
        candidatos = [est[course.id] for est in por_categoria if course.id in est]
        if not candidatos:
            # No debería pasar: `courses` sale de las mismas fuentes. Se cierra
            # por seguridad antes que regalar contenido por un hueco de datos.
            abierto, fecha, motivo, requerido = False, today, 'fecha', None
        else:
            abiertos = [c for c in candidatos if c[0]]
            # Abierto gana; si todas están cerradas, la que abra primero.
            abierto, fecha, motivo, requerido = (
                min(abiertos, key=lambda c: c[1]) if abiertos
                else min(candidatos, key=lambda c: c[1])
            )

        info = comp[course.id]
        result.append({
            'course': course,
            'unlocked': abierto,
            'completed': info['completed'],
            'pct': info['pct'],
            'done': info['done'],
            'total': info['total'],
            'unlock_date': fecha,
            'lock_reason': motivo,              # None | 'fecha' | 'previo'
            'required_course': requerido,        # el curso que falta completar
        })
    return result


def get_sequence_access(membership):
    """Secuencia completa del alumno: cursos y diplomas mezclados por su `order`.

    Un diploma CON categoría se gana al completar todos los cursos de esa
    categoría que el alumno tenga; uno SIN categoría conserva el comportamiento
    anterior (todos los cursos que lo preceden en la secuencia). Al desbloquearse
    se registra el DiplomaAward, que congela la fecha del logro.
    """
    course_access = get_course_access(membership)
    items = [{'type': 'course', 'order': a['course'].order, **a} for a in course_access]

    # Solo los diplomas de categorías que el alumno tiene (más los sin categoría,
    # que son globales): mostrarle el diploma de una línea que no compró es
    # ofrecerle algo que nunca va a poder ganar.
    mis_categorias = {mc.categoria_id for mc in _categorias_del_alumno(membership)}
    diplomas = [
        d for d in Diploma.objects.filter(is_active=True)
        if d.categoria_id is None or d.categoria_id in mis_categorias
    ]
    for d in diplomas:
        items.append({'type': 'diploma', 'order': d.order, 'diploma': d})
    # dentro del mismo `order`, el curso va antes que el diploma
    items.sort(key=lambda x: (x['order'], 0 if x['type'] == 'course' else 1))

    # Por categoría: qué cursos de ella le faltan al alumno. Se calcula una vez
    # para no recorrer la lista entera por cada diploma.
    completado_por_categoria = {}
    for cat_id in mis_categorias:
        completado_por_categoria[cat_id] = True
    accesos_por_curso = {a['course'].id: a for a in course_access}
    from .models import CategoryCourse
    for cc in CategoryCourse.objects.filter(categoria_id__in=mis_categorias).select_related('curso'):
        acceso = accesos_por_curso.get(cc.curso_id)
        if acceso is not None and not acceso['completed']:
            completado_por_categoria[cc.categoria_id] = False

    all_prev_courses_done = True
    for it in items:
        if it['type'] == 'course':
            if not it['completed']:
                all_prev_courses_done = False
        else:
            diploma = it['diploma']
            if diploma.categoria_id:
                it['unlocked'] = completado_por_categoria.get(diploma.categoria_id, False)
            else:
                it['unlocked'] = all_prev_courses_done
            it['awarded_at'] = None
            if it['unlocked']:
                award, _ = DiplomaAward.objects.get_or_create(membership=membership, diploma=diploma)
                it['awarded_at'] = award.awarded_at

    return _recortar_bloqueados(items, AjustesAula.obtener().bloqueados_visibles)


def _recortar_bloqueados(items, limite):
    """Deja a la vista lo disponible y solo `limite` modelos bloqueados.

    Mostrar de una los 20 modelos que faltan aplasta el avance real del alumno y
    delata todo el catálogo; dejar uno solo insinúa que viene más. `limite` sale
    del panel, y 0 significa mostrarlos todos (como era antes).

    Se cuentan solo los CURSOS: un diploma bloqueado que cae dentro del tramo
    visible se muestra igual —es el premio de ese tramo, no contenido futuro—,
    y si contara, un diploma intercalado podría tapar el próximo modelo.
    """
    if limite <= 0:
        return items

    salida = []
    bloqueados = 0
    for it in items:
        if it['type'] == 'course' and not it['unlocked']:
            bloqueados += 1
            if bloqueados > limite:
                break   # de acá en adelante no se muestra nada
        salida.append(it)
    return salida


def get_preview_sequence():
    """Secuencia completa para la VISTA PREVIA de una cuenta de gestión.

    Devuelve la misma forma que get_sequence_access(), pero sin membresía: todos
    los cursos y diplomas activos, desbloqueados y sin avance. Sirve para que
    quien administra el sitio revise cómo le llega el contenido al alumno sin
    tener que comprar un kit ni esperar el goteo semanal.

    No escribe nada: a diferencia de get_sequence_access(), acá NO se crea
    ningún DiplomaAward. Una vista previa no debe dejar rastro en los datos del
    negocio (ni diplomas otorgados, ni progreso, ni membresías fantasma que
    aparezcan luego en el listado de alumnos o en los KPIs del panel).
    """
    items = []
    for course in Course.objects.filter(is_active=True).order_by('order', 'id'):
        items.append({
            'type': 'course', 'order': course.order, 'course': course,
            'unlocked': True, 'completed': False,
            'pct': 0, 'done': 0, 'total': course.lessons.count(),
            'unlock_date': None, 'lock_reason': None, 'required_course': None,
        })
    for d in Diploma.objects.filter(is_active=True):
        items.append({
            'type': 'diploma', 'order': d.order, 'diploma': d,
            'unlocked': True, 'awarded_at': None,
        })
    # Mismo criterio de orden que la secuencia real: dentro de un mismo `order`,
    # el curso va antes que el diploma.
    items.sort(key=lambda x: (x['order'], 0 if x['type'] == 'course' else 1))
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
    categorias = {c for p in products for c in p.categories.filter(is_active=True)}
    months = max((p.access_months for p in products), default=0)

    # Basta con que otorgue categorías O cursos sueltos: los productos migrados
    # traen las dos cosas, pero uno nuevo bien configurado solo trae categorías.
    if (not courses and not categorias) or months <= 0:
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

    # Cada categoría arranca su calendario el día en que se obtuvo. get_or_create
    # y no update: si el alumno ya la tenía, reiniciar la fecha le quitaría de
    # golpe los modelos que ya tenía disponibles.
    from .models import MembershipCategory
    for categoria in categorias:
        MembershipCategory.objects.get_or_create(
            membership=membership, categoria=categoria,
            defaults={'obtenida_en': timezone.now()},
        )

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
    """Avisa que se liberó un modelo nuevo.

    Lo dispara el comando `enviar_avisos_desbloqueo`, que corre a diario desde
    cron: el goteo depende del paso del tiempo y no de una acción del usuario,
    así que no hay ninguna petición web donde engancharlo. Ese comando lleva el
    registro de lo ya avisado (UnlockNotice), no esta función.
    """
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
