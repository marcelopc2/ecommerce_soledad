import base64
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.db.models import Q, Sum, Max, Count
from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponse, FileResponse, Http404
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError as DjangoValidationError
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from catalog.models import Product, FAQ, Testimonial, LandingVideo, LandingStep
from invoicing.models import Invoice
from invoicing.services import issue_invoice_for_order
from lms.models import Course, Lesson, Membership, Diploma
from lms.services import get_course_access, send_reset_email
from payments.models import Order
from .forms import LoginForm, ProductForm, CourseForm, LessonForm, MembershipForm, DiplomaForm, FAQForm, TestimonialForm, LandingVideoForm, LandingStepForm


def staff_required(view):
    """Solo usuarios staff; si no hay sesión, manda al login del panel."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            return redirect(f"{reverse('panel:login')}?next={request.path}")
        return view(request, *args, **kwargs)

    return wrapper


def is_search_request(request):
    """True si es una petición htmx dirigida (búsqueda en vivo), no una navegación boosted."""
    return request.headers.get('HX-Request') == 'true' and request.headers.get('HX-Boosted') != 'true'


# Alias genérico: mismo chequeo que is_search_request, pero para vistas que no
# son de búsqueda (ej. detalle de membresía). hx-boost pone HX-Request=true en
# TODA navegación de un <a> normal (heredan hx-boost del <body>), así que hay
# que distinguirlo de una petición htmx "real" con su propio hx-target: boost
# necesita recibir la página completa (con sidebar) para reemplazar el <body>
# correctamente; solo las acciones con hx-target propio quieren el fragmento.
is_htmx_partial_request = is_search_request


def is_htmx(request):
    return request.headers.get('HX-Request') == 'true'


def _sort_params(request, allowed):
    """Lee sort/dir de la query y los valida contra las columnas ordenables de la
    tabla. Devuelve además next_dir: la dirección que debe pedir cada cabecera en
    su próximo clic (la actual invertida si ya se está ordenando por ella)."""
    sort = request.GET.get('sort', '').strip()
    direction = request.GET.get('dir', 'asc').strip()
    if direction not in ('asc', 'desc'):
        direction = 'asc'
    if sort not in allowed:
        sort = ''
    next_dir = {col: ('desc' if sort == col and direction == 'asc' else 'asc') for col in allowed}
    return sort, direction, next_dir


# ---------- Autenticación ----------

def login_view(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect('panel:dashboard')

    form = LoginForm(request.POST or None)
    error = ''
    if request.method == 'POST' and form.is_valid():
        # Si django-axes tiene bloqueada la combinación usuario+IP, su backend
        # lanza PermissionDenied, pero Django la ATRAPA dentro de authenticate()
        # y devuelve None (no se propaga acá). Quien corta la respuesta es
        # AxesMiddleware, que la reemplaza por la página de bloqueo
        # (AXES_LOCKOUT_TEMPLATE). Por eso acá no hay try/except: sería código
        # muerto y daría la falsa impresión de que el bloqueo se maneja aquí.
        user = authenticate(
            request,
            username=form.cleaned_data['email'],
            password=form.cleaned_data['password'],
        )
        if user and user.is_staff:
            login(request, user)
            return redirect(_safe_next(request) or 'panel:dashboard')
        error = 'Credenciales incorrectas o la cuenta no tiene permisos de administración.'

    return render(request, 'panel/login.html', {'form': form, 'error': error})


def _safe_next(request):
    """Devuelve ?next= solo si apunta a este mismo sitio.

    Sin validar, `?next=https://sitio-falso.cl` mandaría al staff -recién
    autenticado de verdad- a una copia del panel que le pide la clave otra vez.
    Es la misma comprobación que hace el LoginView de Django."""
    destino = request.GET.get('next') or ''
    if destino and url_has_allowed_host_and_scheme(
        destino, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        return destino
    return ''


def logout_view(request):
    logout(request)
    return redirect('panel:login')


# ---------- Dashboard ----------

@staff_required
def dashboard(request):
    now = timezone.now()
    paid_orders = Order.objects.filter(status='PAID')
    stats = {
        'products': Product.objects.count(),
        'active_products': Product.objects.filter(is_active=True).count(),
        'courses': Course.objects.count(),
        'lessons': Lesson.objects.count(),
        'students': Membership.objects.count(),
        'active_memberships': Membership.objects.filter(expires_at__gt=now).count(),
        'paid_orders': paid_orders.count(),
        'revenue': paid_orders.aggregate(total=Sum('total_amount'))['total'] or 0,
    }
    recent_orders = paid_orders.order_by('-created_at')[:6]
    recent_memberships = Membership.objects.select_related('user').order_by('-updated_at')[:6]
    return render(request, 'panel/dashboard.html', {
        'stats': stats,
        'recent_orders': recent_orders,
        'recent_memberships': recent_memberships,
        'section': 'dashboard',
    })


# ---------- Productos ----------

def _products_queryset(q):
    """Productos de portada primero (ordenados por landing_order), luego el resto
    por más reciente. Así quedan agrupados y el drag & drop de la tabla no se
    mezcla con productos que no están en la portada."""
    items = Product.objects.select_related('category').order_by(
        '-show_on_landing', 'landing_order', '-created_at',
    )
    if q:
        items = items.filter(Q(name__icontains=q) | Q(slug__icontains=q) | Q(category__name__icontains=q))
    return items


@staff_required
def products(request):
    q = request.GET.get('q', '').strip()
    ctx = {'products': _products_queryset(q), 'section': 'products', 'q': q}
    if is_search_request(request):
        return render(request, 'panel/partials/products_rows.html', ctx)
    return render(request, 'panel/products.html', ctx)


@staff_required
def product_form(request, pk=None):
    product = get_object_or_404(Product, pk=pk) if pk else None
    form = ProductForm(request.POST or None, instance=product)
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        messages.success(request, f'Producto "{obj.name}" guardado.')
        return redirect('panel:products')
    return render(request, 'panel/product_form.html', {
        'form': form, 'product': product, 'section': 'products',
    })


@staff_required
@require_POST
def product_delete(request, pk):
    """Elimina un producto, salvo que ya se haya vendido.

    `Order.products` es un M2M sin modelo intermedio: al borrar el producto
    desaparecen las filas de la tabla de unión y los pedidos históricos quedan
    con su total pero SIN líneas. Eso destruye el historial de ventas y hace
    imposible re-emitir una boleta. Un producto vendido se desactiva, no se borra.
    """
    product = get_object_or_404(Product, pk=pk)
    name = product.name

    pedidos = product.orders.count()
    if pedidos:
        messages.error(
            request,
            f'No se puede eliminar "{name}": aparece en {pedidos} pedido'
            f'{"s" if pedidos != 1 else ""} y se perdería ese historial de '
            f'ventas. Si ya no lo vendes, desmarca "Activo": deja de aparecer '
            f'en la tienda y los pedidos quedan intactos.'
        )
        return redirect('panel:products')

    product.delete()
    if is_htmx(request):
        # devolvemos vacío: la fila se desvanece (swap con animación)
        return HttpResponse('')
    messages.success(request, f'Producto "{name}" eliminado.')
    return redirect('panel:products')


@staff_required
@require_POST
def products_reorder(request):
    """Guarda el nuevo orden (arrastrar y soltar) de los productos de la portada.
    Recibe 'order' como lista repetida de ids en el orden final; solo reordena
    los productos que ya están marcados para la portada (show_on_landing=True).
    Devuelve la tabla completa para reflejar el nuevo orden (sin recargar)."""
    order_ids = [int(pid) for pid in request.POST.getlist('order') if pid.isdigit()]
    by_id = {p.id: p for p in Product.objects.filter(id__in=order_ids, show_on_landing=True)}
    to_update = []
    for i, pid in enumerate(order_ids, start=1):
        p = by_id.get(pid)
        if p and p.landing_order != i:
            p.landing_order = i
            to_update.append(p)
    if to_update:
        Product.objects.bulk_update(to_update, ['landing_order'])

    return render(request, 'panel/partials/products_rows.html', {'products': _products_queryset(''), 'q': ''})


# ---------- Cursos ----------

def _sequence_items(q=''):
    """Cursos + diplomas mezclados por su `order` (la secuencia que arma el staff).
    Cada item: {'kind': 'course'|'diploma', 'obj': <modelo>, 'order': int}.
    Los cursos traen el desglose de recursos por tipo (pdf/video/imagen) ya
    contado en la consulta, para mostrarlo en la lista sin queries extra."""
    courses = Course.objects.annotate(
        pdf_count=Count('lessons', filter=Q(lessons__lesson_type='PDF')),
        video_count=Count('lessons', filter=Q(lessons__lesson_type='VIDEO')),
        image_count=Count('lessons', filter=Q(lessons__lesson_type='IMAGE')),
    )
    diplomas = Diploma.objects.all()
    if q:
        courses = courses.filter(Q(title__icontains=q) | Q(slug__icontains=q))
        diplomas = diplomas.filter(title__icontains=q)
    items = [{'kind': 'course', 'obj': c, 'order': c.order} for c in courses]
    items += [{'kind': 'diploma', 'obj': d, 'order': d.order} for d in diplomas]
    items.sort(key=lambda x: (x['order'], 0 if x['kind'] == 'course' else 1))
    return items


@staff_required
def courses(request):
    q = request.GET.get('q', '').strip()
    ctx = {'items': _sequence_items(q), 'section': 'courses', 'q': q}
    if is_search_request(request):
        return render(request, 'panel/partials/courses_rows.html', ctx)
    return render(request, 'panel/courses.html', ctx)


@staff_required
@require_POST
def courses_reorder(request):
    """Guarda el nuevo orden de la secuencia (cursos Y diplomas mezclados). Los
    ids vienen tipados: 'course-5' / 'diploma-2'. Renumera todo 1..N en un mismo
    espacio de orden, de modo que los diplomas queden intercalados entre cursos."""
    tokens = request.POST.getlist('order')
    course_updates, diploma_updates = [], []
    courses_by_id = {c.id: c for c in Course.objects.all()}
    diplomas_by_id = {d.id: d for d in Diploma.objects.all()}
    for i, tok in enumerate(tokens, start=1):
        kind, _, sid = tok.partition('-')
        if not sid.isdigit():
            continue
        pk = int(sid)
        if kind == 'course' and pk in courses_by_id:
            c = courses_by_id[pk]
            if c.order != i:
                c.order = i
                course_updates.append(c)
        elif kind == 'diploma' and pk in diplomas_by_id:
            d = diplomas_by_id[pk]
            if d.order != i:
                d.order = i
                diploma_updates.append(d)
    if course_updates:
        Course.objects.bulk_update(course_updates, ['order'])
    if diploma_updates:
        Diploma.objects.bulk_update(diploma_updates, ['order'])
    return render(request, 'panel/partials/courses_rows.html', {'items': _sequence_items(), 'q': ''})


@staff_required
def course_form(request, pk=None):
    """Página única para un curso: sus datos (nombre, descripción, etc.) y sus
    recursos (videos/PDF/imágenes) en dos secciones. La sección de recursos solo
    se muestra si el curso ya existe (hace falta su id para asociarlos).
    Dos formularios en la misma página, distinguidos por el campo oculto
    'form_name' para saber cuál se envió."""
    course = get_object_or_404(Course, pk=pk) if pk else None
    form = CourseForm(instance=course)
    lesson_form = LessonForm()

    if request.method == 'POST' and request.POST.get('form_name') == 'lesson' and course:
        lesson_form = LessonForm(request.POST, request.FILES)
        if lesson_form.is_valid():
            lesson = lesson_form.save(commit=False)
            lesson.course = course
            last = course.lessons.aggregate(m=Max('order'))['m'] or 0
            lesson.order = last + 1
            lesson.save()
            messages.success(request, f'Recurso "{lesson.title}" agregado.')
            return redirect('panel:course_edit', pk=course.pk)
    elif request.method == 'POST':
        form = CourseForm(request.POST, instance=course)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'Curso "{obj.title}" guardado.')
            return redirect('panel:course_edit', pk=obj.pk)

    return render(request, 'panel/course_form.html', {
        'form': form, 'lesson_form': lesson_form, 'course': course,
        'lessons': course.lessons.all() if course else None,
        'section': 'courses',
    })


@staff_required
@require_POST
def course_delete(request, pk):
    """Elimina un curso, salvo que ya lo tengan alumnos.

    Borrar el curso arrastra en cascada sus lecciones, el CourseProgress y el
    LessonProgress de TODOS los alumnos que lo tengan: gente que pagó pierde su
    avance, de forma irreversible y con un solo clic en un botón que tiene el
    mismo peso visual que "Editar". Se prefiere ocultarlo (is_active=False),
    que saca el curso de la vista del alumno sin destruir nada.
    """
    course = get_object_or_404(Course, pk=pk)
    title = course.title

    alumnos = Membership.objects.filter(courses=course).count()
    if alumnos:
        messages.error(
            request,
            f'No se puede eliminar "{title}": {alumnos} alumno'
            f'{"s lo tienen" if alumnos != 1 else " lo tiene"} asignado y se '
            f'perdería su avance. Si ya no quieres mostrarlo, desmarca '
            f'"Activo" en el curso: deja de aparecer y no se borra nada.'
        )
        # Se redirige (y no se devuelve vacío) también en htmx, para que la
        # fila NO desaparezca de la tabla y se vea el mensaje.
        return redirect('panel:courses')

    course.delete()
    if is_htmx(request):
        return HttpResponse('')
    messages.success(request, f'Curso "{title}" y sus lecciones eliminados.')
    return redirect('panel:courses')


@staff_required
@require_POST
def course_duplicate(request, pk):
    """Clona un curso con todos sus recursos (útil para armar cursos parecidos)."""
    original = get_object_or_404(Course, pk=pk)
    lessons_copy = list(original.lessons.all())
    last = Course.objects.aggregate(m=Max('order'))['m'] or 0
    base_slug = f'{original.slug}-copia'
    slug = base_slug
    n = 2
    while Course.objects.filter(slug=slug).exists():
        slug = f'{base_slug}-{n}'
        n += 1
    clone = Course.objects.create(
        title=f'{original.title} (copia)', slug=slug, description=original.description,
        image_url=original.image_url, is_active=False, order=last + 1,
    )
    for l in lessons_copy:
        Lesson.objects.create(
            course=clone, title=l.title, description=l.description, order=l.order,
            lesson_type=l.lesson_type, video_embed_url=l.video_embed_url,
            pdf_file=l.pdf_file, image_file=l.image_file,
        )
    messages.success(request, f'Curso duplicado como "{clone.title}" (queda inactivo hasta que lo revises).')
    return redirect('panel:courses')


# ---------- Diplomas ----------

@staff_required
def diploma_form(request, pk=None):
    diploma = get_object_or_404(Diploma, pk=pk) if pk else None
    form = DiplomaForm(request.POST or None, instance=diploma)
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        messages.success(request, f'Diploma "{obj.title}" guardado.')
        return redirect('panel:courses')
    return render(request, 'panel/diploma_form.html', {
        'form': form, 'diploma': diploma, 'section': 'courses',
    })


@staff_required
@require_POST
def diploma_delete(request, pk):
    diploma = get_object_or_404(Diploma, pk=pk)
    title = diploma.title
    diploma.delete()
    if is_htmx(request):
        return HttpResponse('')
    messages.success(request, f'Diploma "{title}" eliminado.')
    return redirect('panel:courses')


@staff_required
def diploma_preview(request, pk):
    """Vista previa del diploma con datos ficticios (nunca datos de un alumno
    real), para que el staff vea el diseño antes de publicarlo. La plantilla
    marca claramente que es una vista previa, no un diploma real."""
    diploma = get_object_or_404(Diploma, pk=pk)
    return render(request, 'lms/diploma.html', {
        'diploma': diploma,
        'student_name': 'Nombre de Ejemplo',
        'awarded_at': timezone.now(),
        'is_preview': True,
    })


# ---------- Recursos (lecciones) ----------
# El alta de recursos vive en course_form (sección 2 de la página del curso).
# Acá solo quedan las acciones puntuales: reordenar y eliminar.

@staff_required
@require_POST
def lessons_reorder(request, pk):
    """Reordena los recursos de un curso (arrastrar y soltar)."""
    course = get_object_or_404(Course, pk=pk)
    order_ids = [int(lid) for lid in request.POST.getlist('order') if lid.isdigit()]
    by_id = {l.id: l for l in course.lessons.all()}
    to_update = []
    for i, lid in enumerate(order_ids, start=1):
        l = by_id.get(lid)
        if l and l.order != i:
            l.order = i
            to_update.append(l)
    if to_update:
        Lesson.objects.bulk_update(to_update, ['order'])
    return render(request, 'panel/partials/lessons_rows.html', {'course': course, 'lessons': course.lessons.all()})


@staff_required
@require_POST
def lesson_delete(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    course_pk = lesson.course_id
    title = lesson.title
    lesson.delete()
    if is_htmx(request):
        return HttpResponse('')
    messages.success(request, f'Recurso "{title}" eliminado.')
    return redirect('panel:course_edit', pk=course_pk)


@staff_required
def lesson_preview(request, pk):
    """Fragmento para el modal de vista previa de un recurso (video/imagen/pdf)."""
    lesson = get_object_or_404(Lesson, pk=pk)
    return render(request, 'panel/partials/lesson_preview_modal.html', {'lesson': lesson})


@staff_required
def lesson_preview_image(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    if not lesson.image_file:
        raise Http404
    return FileResponse(lesson.image_file.open('rb'))


@staff_required
@xframe_options_sameorigin
def lesson_preview_pdf(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    if not lesson.pdf_file:
        raise Http404
    return FileResponse(lesson.pdf_file.open('rb'), content_type='application/pdf')


# ---------- Membresías ----------

MEMBERSHIP_DB_SORT_FIELDS = {
    'alumno': 'student_name',
    'apoderado': 'parent_name',
    'inicio': 'created_at',
    'vencimiento': 'expires_at',
}
# progreso y estado no son columnas de la base: se calculan por membresía, así que
# se ordenan en Python más abajo (después de armar las filas).
MEMBERSHIP_SORT_COLUMNS = ['alumno', 'apoderado', 'inicio', 'vencimiento', 'progreso', 'estado']


@staff_required
def memberships(request):
    q = request.GET.get('q', '').strip()
    estado = request.GET.get('estado', '').strip()
    sort, direction, next_dir = _sort_params(request, MEMBERSHIP_SORT_COLUMNS)

    base = Membership.objects.select_related('user').prefetch_related('courses')
    if q:
        base = base.filter(
            Q(user__email__icontains=q) | Q(student_name__icontains=q) | Q(parent_name__icontains=q)
        )

    now = timezone.now()
    total_count = base.count()
    active_count = base.filter(paused_at__isnull=True, expires_at__gt=now).count()
    paused_count = base.filter(paused_at__isnull=False).count()
    expired_count = base.filter(paused_at__isnull=True, expires_at__lte=now).count()

    items = base
    if estado == 'activa':
        items = items.filter(paused_at__isnull=True, expires_at__gt=now)
    elif estado == 'pausada':
        items = items.filter(paused_at__isnull=False)
    elif estado == 'vencida':
        items = items.filter(paused_at__isnull=True, expires_at__lte=now)

    if sort in MEMBERSHIP_DB_SORT_FIELDS:
        field = MEMBERSHIP_DB_SORT_FIELDS[sort]
        items = items.order_by(field if direction == 'asc' else f'-{field}')
    else:
        items = items.order_by('-updated_at')
    items = list(items)

    rows = []
    for m in items:
        access = get_course_access(m)
        completed = sum(1 for a in access if a['completed'])
        current = next((a for a in access if a['unlocked'] and not a['completed']), None)
        if m.is_paused:
            status_rank = 1
        elif m.is_active:
            status_rank = 0
        else:
            status_rank = 2
        rows.append({
            'm': m,
            'completed': completed,
            'total': len(access),
            'pct': round(completed / len(access) * 100) if access else 0,
            'current_course': current['course'] if current else None,
            'status_rank': status_rank,
        })

    if sort == 'progreso':
        rows.sort(key=lambda r: r['pct'], reverse=(direction == 'desc'))
    elif sort == 'estado':
        rows.sort(key=lambda r: r['status_rank'], reverse=(direction == 'desc'))

    ctx = {
        'rows': rows,
        'total_count': total_count,
        'active_count': active_count,
        'paused_count': paused_count,
        'expired_count': expired_count,
        'section': 'memberships',
        'q': q,
        'estado': estado,
        'sort': sort,
        'dir': direction,
        'next_dir': next_dir,
    }
    if is_search_request(request):
        return render(request, 'panel/partials/memberships_rows.html', ctx)
    return render(request, 'panel/memberships.html', ctx)


def _membership_context(m):
    """Datos derivados para el detalle de una membresía: progreso de cursos,
    facturas asociadas, qué compras otorgaron el acceso, y KPIs simples."""
    access = get_course_access(m)
    completed_count = sum(1 for a in access if a['completed'])
    current = next((a for a in access if a['unlocked'] and not a['completed']), None)

    orders = list(m.orders.order_by('-created_at'))
    invoices = []
    for order in orders:
        try:
            invoice = order.invoice
        except Invoice.DoesNotExist:
            invoice = None
        invoices.append({'order': order, 'invoice': invoice})

    # Productos que otorgaron acceso, para explicar de dónde sale el vencimiento.
    granting = []
    seen = set()
    for order in orders:
        for p in order.products.filter(access_months__gt=0):
            if p.id not in seen:
                seen.add(p.id)
                granting.append(p)

    days_as_member = (timezone.now().date() - m.created_at.date()).days
    total_spent = sum((o.total_amount for o in orders), 0)

    return {
        'completed_count': completed_count,
        'total_courses': len(access),
        'current_course': current['course'] if current else None,
        'invoices': invoices,
        'granting_products': granting,
        'days_as_member': days_as_member,
        'total_spent': total_spent,
    }


def _membership_detail_response(request, m, form=None):
    """Renderiza el detalle: la página completa (con sidebar) en una navegación
    normal O boosted, o solo el bloque de contenido cuando es una acción htmx
    con su propio hx-target (pausar, guardar nombres, etc.)."""
    ctx = {'m': m, 'name_form': form or MembershipForm(instance=m), 'section': 'memberships'}
    ctx.update(_membership_context(m))
    template = (
        'panel/partials/membership_detail_body.html'
        if is_htmx_partial_request(request)
        else 'panel/membership_detail.html'
    )
    return render(request, template, ctx)


@staff_required
def membership_detail(request, pk):
    m = get_object_or_404(
        Membership.objects.select_related('user').prefetch_related('courses', 'orders'), pk=pk,
    )
    return _membership_detail_response(request, m)


@staff_required
@require_POST
def membership_names_update(request, pk):
    m = get_object_or_404(Membership.objects.select_related('user'), pk=pk)
    form = MembershipForm(request.POST, instance=m)
    if form.is_valid():
        form.save()
        form = None
    return _membership_detail_response(request, m, form)


@staff_required
@require_POST
def membership_toggle_pause(request, pk):
    m = get_object_or_404(Membership.objects.select_related('user'), pk=pk)
    if m.is_paused:
        m.resume()
    else:
        m.pause()
    return _membership_detail_response(request, m)


@staff_required
@require_POST
def membership_toggle_user(request, pk):
    m = get_object_or_404(Membership.objects.select_related('user'), pk=pk)
    m.user.is_active = not m.user.is_active
    m.user.save(update_fields=['is_active'])
    return _membership_detail_response(request, m)


@staff_required
@require_POST
def membership_delete(request, pk):
    m = get_object_or_404(Membership.objects.select_related('user'), pk=pk)
    user = m.user
    email = user.email
    user.delete()  # cascada: borra también la Membership (OneToOne on_delete=CASCADE)
    messages.success(request, f'Cuenta de "{email}" eliminada.')
    # HX-Redirect hace que HTMX navegue a la lista (venimos de la página de detalle)
    if is_htmx(request):
        resp = HttpResponse()
        resp['HX-Redirect'] = reverse('panel:memberships')
        return resp
    return redirect('panel:memberships')


# ---------- Pedidos ----------

ORDER_SORT_FIELDS = {
    'cliente': 'customer_email',
    'folio': 'invoice__folio',
    'total': 'total_amount',
    'estado': 'status',
    'boleta': 'invoice__status',
    'fecha': 'created_at',
}
ORDER_STATUS_FILTERS = {'pagados': 'PAID', 'pendientes': 'PENDING', 'fallidos': 'FAILED'}

# Lo accionable del lado tributario: pedidos cobrados cuya boleta NO está emitida
# (nunca se creó, quedó pendiente, o falló). Se filtra explícito en vez de con
# exclude(invoice__status='ISSUED') porque el exclude sobre un join nullable
# también descartaría los pedidos que directamente no tienen boleta.
ORDERS_SIN_BOLETA = Q(status='PAID') & (
    Q(invoice__isnull=True) | Q(invoice__status__in=['PENDING', 'ERROR'])
)


@staff_required
def orders(request):
    q = request.GET.get('q', '').strip()
    estado = request.GET.get('estado', '').strip()
    sort, direction, next_dir = _sort_params(request, ORDER_SORT_FIELDS)

    base = Order.objects.select_related('invoice').prefetch_related('products')
    if q:
        # El id corto que muestra la tabla se ve como «#a1b2c3d4»: se acepta con o sin #.
        base = base.filter(
            Q(customer_email__icontains=q)
            | Q(order_id__icontains=q.lstrip('#'))
            | Q(invoice__folio__icontains=q)
        )

    counts = {
        'total': base.count(),
        'pagados': base.filter(status='PAID').count(),
        'pendientes': base.filter(status='PENDING').count(),
        'fallidos': base.filter(status='FAILED').count(),
        'sin_boleta': base.filter(ORDERS_SIN_BOLETA).count(),
    }
    revenue = base.filter(status='PAID').aggregate(t=Sum('total_amount'))['t'] or 0

    items = base
    if estado == 'sin_boleta':
        items = items.filter(ORDERS_SIN_BOLETA)
    elif estado in ORDER_STATUS_FILTERS:
        items = items.filter(status=ORDER_STATUS_FILTERS[estado])

    if sort:
        field = ORDER_SORT_FIELDS[sort]
        items = items.order_by(field if direction == 'asc' else f'-{field}')
    else:
        items = items.order_by('-created_at')

    ctx = {
        'orders': items,
        'counts': counts,
        'revenue': revenue,
        'section': 'orders',
        'q': q,
        'estado': estado,
        'sort': sort,
        'dir': direction,
        'next_dir': next_dir,
    }
    if is_search_request(request):
        return render(request, 'panel/partials/orders_rows.html', ctx)
    return render(request, 'panel/orders.html', ctx)


@staff_required
def order_detail(request, pk):
    order = get_object_or_404(
        Order.objects.prefetch_related('products', 'memberships__user'),
        pk=pk,
    )
    return render(request, 'panel/order_detail.html', {
        'order': order,
        # Reverse OneToOne: si la orden no tiene boleta/envío, el acceso lanza
        # DoesNotExist (que hereda de AttributeError), así que getattr da None.
        'invoice': getattr(order, 'invoice', None),
        'shipment': getattr(order, 'shipment', None),
        'section': 'orders',
    })


# ---------- Boletas (OpenFactura) ----------
# No tienen lista propia: como Invoice es OneToOne con Order, viven como columna
# y acciones dentro de /gestion/pedidos/.

@staff_required
@require_POST
def order_invoice_issue(request, pk):
    """Emite (o reintenta) en OpenFactura la boleta de un pedido.

    Sirve para los dos casos que el panel deja accionar: el pedido nunca llegó a
    tener boleta, o la tiene pendiente/con error. issue_invoice_for_order hace
    get_or_create, así que cubre ambos.
    """
    order = get_object_or_404(Order, pk=pk)
    invoice = getattr(order, 'invoice', None)

    if order.status != 'PAID':
        # Una boleta es un documento tributario: no se emite por una venta que no se cobró.
        messages.error(request, 'Solo se puede emitir la boleta de un pedido pagado.')
    elif invoice and invoice.status == 'ISSUED':
        messages.info(request, f'La boleta {invoice.folio} ya estaba emitida.')
    else:
        invoice = issue_invoice_for_order(order)  # nunca lanza: deja ERROR si falla
        if invoice.status == 'ISSUED':
            messages.success(request, f'Boleta {invoice.folio} emitida correctamente.')
        else:
            messages.error(request, f'No se pudo emitir la boleta: {invoice.error_message[:200]}')

    # Recarga la página actual: así se ven el mensaje, el estado nuevo y los
    # contadores de los filtros, conservando el filtro/orden que tenía la tabla.
    if is_htmx(request):
        resp = HttpResponse()
        resp['HX-Refresh'] = 'true'
        return resp
    return redirect('panel:orders')


@staff_required
def invoice_pdf(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    if not invoice.pdf_base64:
        raise Http404("La boleta no tiene PDF")
    pdf_bytes = base64.b64decode(invoice.pdf_base64)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    filename = f"boleta_{invoice.folio or invoice.pk}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ---------- Configuración (preguntas frecuentes + testimonios) ----------

@staff_required
def configuracion(request):
    tab = request.GET.get('tab', 'faqs')
    ctx = {
        'faqs': FAQ.objects.all(),
        'testimonials': Testimonial.objects.all(),
        'videos': LandingVideo.objects.all(),
        'steps': LandingStep.objects.all(),
        'tab': tab if tab in ('faqs', 'testimonios', 'videos', 'pasos') else 'faqs',
        'section': 'config',
    }
    return render(request, 'panel/configuracion.html', ctx)


@staff_required
def faq_form(request, pk=None):
    faq = get_object_or_404(FAQ, pk=pk) if pk else None
    form = FAQForm(request.POST or None, instance=faq)
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        messages.success(request, f'Pregunta "{obj.question}" guardada.')
        return redirect(f"{reverse('panel:config')}?tab=faqs")
    return render(request, 'panel/faq_form.html', {
        'form': form, 'faq': faq, 'section': 'config',
    })


@staff_required
@require_POST
def faq_delete(request, pk):
    faq = get_object_or_404(FAQ, pk=pk)
    question = faq.question
    faq.delete()
    if is_htmx(request):
        return HttpResponse('')
    messages.success(request, f'Pregunta "{question}" eliminada.')
    return redirect(f"{reverse('panel:config')}?tab=faqs")


@staff_required
@require_POST
def faq_restore_defaults(request):
    """Borra todas las preguntas actuales (personalizadas o editadas) y recrea
    el set original. Acción destructiva: el botón que la dispara lleva
    hx-confirm (modal de confirmación propio del panel, no el confirm() nativo)."""
    FAQ.objects.restore_defaults()
    messages.success(request, 'Preguntas frecuentes restauradas a los valores por defecto.')
    target = f"{reverse('panel:config')}?tab=faqs"
    if is_htmx(request):
        resp = HttpResponse()
        resp['HX-Redirect'] = target
        return resp
    return redirect(target)


@staff_required
def testimonial_form(request, pk=None):
    testimonial = get_object_or_404(Testimonial, pk=pk) if pk else None
    form = TestimonialForm(request.POST or None, instance=testimonial)
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        messages.success(request, f'Testimonio de "{obj.name}" guardado.')
        return redirect(f"{reverse('panel:config')}?tab=testimonios")
    return render(request, 'panel/testimonial_form.html', {
        'form': form, 'testimonial': testimonial, 'section': 'config',
    })


@staff_required
@require_POST
def testimonial_delete(request, pk):
    testimonial = get_object_or_404(Testimonial, pk=pk)
    name = testimonial.name
    testimonial.delete()
    if is_htmx(request):
        return HttpResponse('')
    messages.success(request, f'Testimonio de "{name}" eliminado.')
    return redirect(f"{reverse('panel:config')}?tab=testimonios")


@staff_required
@require_POST
def testimonial_restore_defaults(request):
    """Borra todos los testimonios actuales (personalizados o editados) y recrea
    el set original. Acción destructiva: el botón que la dispara lleva
    hx-confirm (modal de confirmación propio del panel, no el confirm() nativo)."""
    Testimonial.objects.restore_defaults()
    messages.success(request, 'Testimonios restaurados a los valores por defecto.')
    target = f"{reverse('panel:config')}?tab=testimonios"
    if is_htmx(request):
        resp = HttpResponse()
        resp['HX-Redirect'] = target
        return resp
    return redirect(target)


@staff_required
def video_form(request, pk=None):
    video = get_object_or_404(LandingVideo, pk=pk) if pk else None
    # request.FILES: el formulario sube la portada, así que va multipart.
    form = LandingVideoForm(request.POST or None, request.FILES or None, instance=video)
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        messages.success(request, f'Video "{obj.title}" guardado.')
        return redirect(f"{reverse('panel:config')}?tab=videos")
    return render(request, 'panel/video_form.html', {
        'form': form, 'video': video, 'section': 'config',
    })


@staff_required
@require_POST
def video_delete(request, pk):
    video = get_object_or_404(LandingVideo, pk=pk)
    title = video.title
    # Borra también la portada del disco: si no, MEDIA_ROOT se llena de
    # imágenes huérfanas cada vez que la clienta reemplaza un video.
    video.cover.delete(save=False)
    video.delete()
    if is_htmx(request):
        return HttpResponse('')
    messages.success(request, f'Video "{title}" eliminado.')
    return redirect(f"{reverse('panel:config')}?tab=videos")


@staff_required
@require_POST
def video_restore_defaults(request):
    """Vuelve a los 3 videos originales. Acción destructiva: el botón que la
    dispara lleva hx-confirm (modal propio del panel, no el confirm() nativo).
    Las portadas NO se recuperan (son archivos subidos), y el modal lo avisa."""
    LandingVideo.objects.restore_defaults()
    messages.success(
        request,
        'Videos restaurados a los valores por defecto. Recuerda volver a subir las portadas.',
    )
    target = f"{reverse('panel:config')}?tab=videos"
    if is_htmx(request):
        resp = HttpResponse()
        resp['HX-Redirect'] = target
        return resp
    return redirect(target)


@staff_required
def step_form(request, pk=None):
    step = get_object_or_404(LandingStep, pk=pk) if pk else None
    # request.FILES: el formulario sube la foto, así que va multipart.
    form = LandingStepForm(request.POST or None, request.FILES or None, instance=step)
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        messages.success(request, f'Paso "{obj.title}" guardado.')
        return redirect(f"{reverse('panel:config')}?tab=pasos")
    return render(request, 'panel/step_form.html', {
        'form': form, 'step': step, 'section': 'config',
    })


@staff_required
@require_POST
def step_delete(request, pk):
    step = get_object_or_404(LandingStep, pk=pk)
    title = step.title
    # Borra también la foto del disco para no dejar huérfanos en MEDIA_ROOT.
    step.photo.delete(save=False)
    step.delete()
    if is_htmx(request):
        return HttpResponse('')
    messages.success(request, f'Paso "{title}" eliminado.')
    return redirect(f"{reverse('panel:config')}?tab=pasos")


@staff_required
@require_POST
def step_restore_defaults(request):
    """Vuelve a los 3 pasos originales. Destructiva: el botón lleva hx-confirm.
    Las fotos NO se recuperan (son archivos subidos) y el modal lo avisa."""
    LandingStep.objects.restore_defaults()
    messages.success(
        request,
        'Pasos restaurados a los valores por defecto. Recuerda volver a subir las fotos.',
    )
    target = f"{reverse('panel:config')}?tab=pasos"
    if is_htmx(request):
        resp = HttpResponse()
        resp['HX-Redirect'] = target
        return resp
    return redirect(target)


# ---------- Contraseña del alumno (soporte manual) ----------

@staff_required
@require_POST
def membership_send_reset(request, pk):
    """Reenvía el correo con el link para definir/restablecer la contraseña.

    Es la vía normal cuando el alumno dice "no me llegó el correo" o "el link
    expiró": no expone ninguna clave y el link sigue siendo de un solo uso.
    """
    m = get_object_or_404(Membership.objects.select_related('user'), pk=pk)
    try:
        send_reset_email(m.user)
        messages.success(
            request,
            f'Le enviamos a {m.user.email} un correo con el link para definir su contraseña.',
        )
    except Exception:
        # fail_silently=False no aplica acá: preferimos avisar al staff que el
        # correo no salió, en vez de decirle que sí y que el alumno siga esperando.
        messages.error(
            request,
            f'No pudimos enviar el correo a {m.user.email}. Revisa la configuración '
            f'de correo (SMTP) o asígnale una contraseña manualmente.',
        )
    return redirect('panel:membership_detail', pk=pk)


@staff_required
@require_POST
def membership_set_password(request, pk):
    """Asigna una contraseña a mano.

    Salida de emergencia para cuando el correo no funciona (SMTP caído, casilla
    llena, el alumno no recibe nada). La clave se muestra UNA vez en pantalla
    para dictarla por teléfono/WhatsApp; no se guarda en texto plano en ninguna
    parte (Django guarda solo el hash) ni se manda por correo.
    """
    m = get_object_or_404(Membership.objects.select_related('user'), pk=pk)
    nueva = (request.POST.get('password') or '').strip()

    # Se valida con las MISMAS reglas que usa el alumno al definirla desde el
    # correo: si acá se pudiera poner "1234", quedaría una cuenta débil.
    try:
        validate_password(nueva, user=m.user)
    except DjangoValidationError as e:
        messages.error(request, ' '.join(e.messages))
        return redirect('panel:membership_detail', pk=pk)

    m.user.set_password(nueva)
    m.user.save()
    messages.success(
        request,
        f'Contraseña actualizada para {m.user.email}. Anótala o díctasela ahora: '
        f'por seguridad no volverá a mostrarse.',
    )
    return redirect('panel:membership_detail', pk=pk)
