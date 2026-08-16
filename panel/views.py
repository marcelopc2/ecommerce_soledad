import base64
import logging
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.db.models import Q, Sum, Max, Count
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.http import HttpResponse, FileResponse, Http404
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError as DjangoValidationError
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from catalog.models import (
    Product, FAQ, Testimonial, LandingVideo, LandingStep,
    SeccionConcurso, GanadorConcurso,
)
from invoicing.models import Invoice
from invoicing.services import issue_invoice_for_order
from lms.models import AjustesAula, Course, Lesson, Membership, Diploma
from lms.services import get_course_access, send_reset_email
from payments.models import Order
from shipments.services import send_dispatch_email
from .forms import (
    LoginForm, ProductForm, CourseForm, CourseCategoryForm, LessonForm, MembershipForm,
    DiplomaForm, FAQForm, TestimonialForm, LandingVideoForm, LandingStepForm,
    StaffUserForm, AjustesAulaForm, SeccionConcursoForm, GanadorConcursoForm,
    MiCuentaForm,
)

log = logging.getLogger('ingenioblocks.pagos')


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
            username=_username_de(form.cleaned_data['email']),
            password=form.cleaned_data['password'],
        )
        if user and user.is_staff:
            login(request, user)
            return redirect(_safe_next(request) or 'panel:dashboard')
        error = 'Credenciales incorrectas o la cuenta no tiene permisos de administración.'

    return render(request, 'panel/login.html', {'form': form, 'error': error})


def _username_de(correo):
    """Traduce el correo escrito en el formulario al `username` real de esa cuenta.

    El formulario pide el correo, pero `authenticate()` busca por el campo de
    identificación de Django, que es `username`. Las cuentas de alumno se crean
    con username=email y coincidían de casualidad; una creada con
    `createsuperuser` no (la del proyecto tiene username "admin"), así que su
    clave correcta era rechazada como si estuviera mala y no había forma de
    entrar con ella.

    Si el correo no existe se devuelve tal cual: authenticate() falla igual, pero
    recorriendo el mismo camino que una clave equivocada, sin delatar cuáles
    correos están registrados.
    """
    from django.contrib.auth.models import User
    cuenta = User.objects.filter(email__iexact=correo.strip()).order_by('pk').first()
    return cuenta.username if cuenta else correo


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

def _products_queryset(q, orden_previo=None):
    """Productos de portada primero (ordenados por landing_order), luego el resto
    por más reciente. Así quedan agrupados y el drag & drop de la tabla no se
    mezcla con productos que no están en la portada.

    `orden_previo`: lista de pks tal como el navegador los tiene en pantalla (la
    manda el propio cliente, ver pnlOrdenDeFilas en products.html). Con ella las
    filas se devuelven en ese mismo orden en vez de reagruparse al instante:
    apagar un producto lo mandaba abajo y además renumeraba a los que quedaban,
    así que saltaban varias filas a la vez sin que nadie hubiera arrastrado
    nada. El reagrupado real se ve en la siguiente carga completa de la página."""
    items = Product.objects.select_related('category').order_by(
        '-show_on_landing', 'landing_order', '-created_at',
    )
    if q:
        items = items.filter(Q(name__icontains=q) | Q(slug__icontains=q) | Q(category__name__icontains=q))
    if not orden_previo:
        return items

    posicion = {pk: i for i, pk in enumerate(orden_previo)}
    # Un producto que no estaba en la lista previa (recién creado en otra
    # pestaña) va al final en vez de romper el orden.
    return sorted(items, key=lambda p: posicion.get(p.pk, len(posicion)))


@staff_required
def products(request):
    q = request.GET.get('q', '').strip()
    ctx = {
        'products': _products_queryset(q), 'section': 'products', 'q': q,
        # cuántos lugares de la portada están ocupados (ver product_toggle_landing)
        'en_portada': _en_portada(), 'portada_max': PORTADA_MAX,
    }
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


#: La portada muestra exactamente 4 tarjetas (3 normales + 1 ancha).
PORTADA_MAX = 4


@staff_required
@require_POST
def product_toggle_landing(request, pk):
    """Enciende o apaga un producto en la portada, desde la propia lista.

    Antes esto era un check dentro del formulario del producto, mientras el
    ORDEN se decidía arrastrando en la lista. Dos controles en dos pantallas
    para un mismo resultado, y con una trampa: se podía marcar el check, guardar
    y que el producto no apareciera igual, porque quedaba en una cola invisible
    más allá de los 4 lugares de la portada.

    Ahora se decide en un solo lugar y con un tope explícito: si ya hay 4, el
    ojo de los demás viene deshabilitado y el aviso dice qué hacer.

    El ojo mueve `is_active` junto con `show_on_landing`: en esta tienda los
    productos se venden desde la portada, así que "publicado" y "destacado" son
    la misma decisión. Tenerlas separadas permitía estados que no le sirven a
    nadie, como un producto a la venta que no aparece en ninguna parte."""
    product = get_object_or_404(Product, pk=pk)
    # El orden que se está viendo y la búsqueda activa viajan en la petición: sin
    # ellos la respuesta reagrupaba la tabla y borraba el filtro, o sea todo se
    # movía de lugar sin que nadie lo hubiera arrastrado (ver pnlOrdenDeFilas).
    q = request.POST.get('q', '').strip()
    orden_previo = [
        int(x) for x in request.POST.get('orden', '').split(',') if x.strip().isdigit()
    ]

    if product.show_on_landing:
        product.show_on_landing = False
        product.is_active = False
        product.landing_order = 0
        product.save(update_fields=['show_on_landing', 'is_active', 'landing_order'])
        messages.success(request, f'"{product.name}" ya no se vende ni se muestra.')
    elif _en_portada() >= PORTADA_MAX:
        messages.error(
            request,
            f'La portada muestra {PORTADA_MAX} productos y ya están los '
            f'{PORTADA_MAX}. Saca uno primero para poder poner este.'
        )
    else:
        product.show_on_landing = True
        product.is_active = True
        product.save(update_fields=['show_on_landing', 'is_active'])
        messages.success(request, f'"{product.name}" ya está a la venta en la portada.')

    _renumerar_portada(orden_previo)

    return render(request, 'panel/partials/products_panel.html', {
        'products': _products_queryset(q, orden_previo=orden_previo), 'q': q,
        'en_portada': _en_portada(), 'portada_max': PORTADA_MAX, 'oob': True,
    })


def _en_portada():
    return Product.objects.filter(show_on_landing=True).count()


def _renumerar_portada(orden_en_pantalla):
    """Numera del 1 al N los productos de la portada siguiendo el orden en que
    aparecen en la tabla.

    El número es SIEMPRE la posición que se ve, no un contador aparte. Antes se
    le asignaba al que se encendía "el último lugar libre", así que apagar el 2
    y volver a encenderlo lo dejaba de 3 mientras el de más abajo pasaba a 2:
    los números decían una cosa y las filas otra.

    `orden_en_pantalla` son los pks tal como los tiene el navegador. Un producto
    que no venga en esa lista (pantalla filtrada por una búsqueda) queda al final
    conservando su orden anterior."""
    posicion = {pk: i for i, pk in enumerate(orden_en_pantalla)}
    # sorted() es estable: los que no están en pantalla mantienen entre sí el
    # orden que traen de la consulta.
    en_portada = sorted(
        Product.objects.filter(show_on_landing=True).order_by('landing_order', 'id'),
        key=lambda p: posicion.get(p.pk, len(posicion)),
    )
    cambios = []
    for i, p in enumerate(en_portada, start=1):
        if p.landing_order != i:
            p.landing_order = i
            cambios.append(p)
    if cambios:
        Product.objects.bulk_update(cambios, ['landing_order'])


@staff_required
@require_POST
def products_reorder(request):
    """Guarda el nuevo orden (arrastrar y soltar) de los productos de la portada.
    Recibe 'order' como lista repetida de ids en el orden final; solo reordena
    los productos que ya están marcados para la portada (show_on_landing=True).
    Devuelve la tabla completa para reflejar el nuevo orden (sin recargar)."""
    # Misma regla que al prender el ojo: el número es la posición en la tabla.
    order_ids = [int(pid) for pid in request.POST.getlist('order') if pid.isdigit()]
    _renumerar_portada(order_ids)

    return render(request, 'panel/partials/products_panel.html', {
        'products': _products_queryset(''), 'q': '',
        'en_portada': _en_portada(), 'portada_max': PORTADA_MAX, 'oob': True,
    })


# ---------- Cursos ----------

def _sequence_items(q=''):
    """Cursos + diplomas mezclados por su `order` (la secuencia que arma el staff).
    Cada item: {'kind': 'course'|'diploma', 'obj': <modelo>, 'order': int}.
    Los cursos traen el desglose de recursos por tipo (pdf/video/imagen) ya
    contado en la consulta, para mostrarlo en la lista sin queries extra, y sus
    categorías prefetcheadas por lo mismo: son una columna de la lista."""
    courses = Course.objects.annotate(
        pdf_count=Count('lessons', filter=Q(lessons__lesson_type='PDF')),
        video_count=Count('lessons', filter=Q(lessons__lesson_type='VIDEO')),
        image_count=Count('lessons', filter=Q(lessons__lesson_type='IMAGE')),
    ).prefetch_related('categorias_del_curso__categoria')
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
        form = CourseForm(request.POST, request.FILES, instance=course)
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
def course_toggle_active(request, pk):
    """Muestra u oculta un modelo desde la propia lista — mismo ojo que en
    Productos, Videos y Testimonios. Devuelve la tabla completa y no solo la
    fila porque el orden es una secuencia: se lee mejor viéndola entera."""
    c = get_object_or_404(Course, pk=pk)
    c.is_active = not c.is_active
    c.save(update_fields=['is_active'])
    verbo = 'se muestra' if c.is_active else 'quedó oculto'
    messages.success(request, f'El modelo "{c.title}" {verbo} en el Aula.')
    q = request.POST.get('q', '').strip()
    return render(request, 'panel/partials/courses_rows.html',
                  {'items': _sequence_items(q), 'q': q})


@staff_required
@require_POST
def diploma_toggle_active(request, pk):
    """El mismo ojo para los diplomas: viven en la misma tabla que los modelos."""
    d = get_object_or_404(Diploma, pk=pk)
    d.is_active = not d.is_active
    d.save(update_fields=['is_active'])
    verbo = 'se puede ganar' if d.is_active else 'quedó oculto'
    messages.success(request, f'El diploma "{d.title}" {verbo}.')
    q = request.POST.get('q', '').strip()
    return render(request, 'panel/partials/courses_rows.html',
                  {'items': _sequence_items(q), 'q': q})


# ---------- Diplomas ----------

@staff_required
def diploma_form(request, pk=None):
    diploma = get_object_or_404(Diploma, pk=pk) if pk else None
    form = DiplomaForm(request.POST or None, request.FILES or None, instance=diploma)
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

    today = timezone.localdate()
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
        # Con la membresía en pausa el conteo está congelado -no baja mientras
        # dure la pausa-, así que un número ahí sería falso: se muestra "En
        # pausa" en su lugar y no `dias_restantes`.
        dias = (m.expires_at.date() - today).days
        rows.append({
            'm': m,
            'completed': completed,
            'total': len(access),
            'pct': round(completed / len(access) * 100) if access else 0,
            'current_course': current['course'] if current else None,
            'status_rank': status_rank,
            'dias_restantes': dias,
            'dias_vencida': -dias,
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
@require_POST
def order_shipment_dispatch(request, pk):
    """Marca el envío de un pedido como despachado: guarda el número de
    seguimiento a mano (hoy no hay integración que lo traiga sola, ver
    shipments/services.py) y avisa al cliente por correo."""
    order = get_object_or_404(Order.objects.select_related('shipment'), pk=pk)
    shipment = getattr(order, 'shipment', None)

    if not shipment:
        messages.error(request, 'Este pedido no tiene envío asociado.')
        return redirect('panel:order_detail', pk=pk)

    tracking = request.POST.get('tracking_number', '').strip()
    if not tracking:
        messages.error(request, 'Ingresa el número de seguimiento antes de marcar el despacho.')
        return redirect('panel:order_detail', pk=pk)

    shipment.tracking_number = tracking
    shipment.status = 'IN_TRANSIT'
    shipment.dispatched_at = timezone.now()
    shipment.save(update_fields=['tracking_number', 'status', 'dispatched_at'])

    try:
        send_dispatch_email(shipment)
        messages.success(request, 'Envío marcado como despachado. Se avisó al cliente por correo.')
    except Exception:
        log.exception('Falló el correo de despacho del pedido %s', order.order_id)
        messages.warning(request, 'Envío marcado como despachado, pero no se pudo enviar el correo de aviso.')

    return redirect('panel:order_detail', pk=pk)


@staff_required
def invoice_pdf(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    if not invoice.pdf_base64:
        raise Http404("La boleta no tiene PDF")
    pdf_bytes = base64.b64decode(invoice.pdf_base64)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    filename = f"boleta_{invoice.folio or invoice.pk}.pdf"
    # `inline` y no `attachment`: la boleta se abre en una pestaña y se mira. Casi
    # siempre lo que se necesita es revisar un folio o un monto, no guardar el
    # archivo; con `attachment` eso obligaba a bajarlo, abrirlo desde la carpeta
    # de descargas y después borrarlo. Quien sí la necesite la baja desde el
    # visor del navegador, que ya trae su botón. El filename se conserva para
    # que ese botón proponga el nombre correcto.
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


# ---------- Contenido del sitio público (portada) + ritmo del Aula ----------

#: Cada sección editable del sitio público es ahora una entrada propia del menú.
#: Antes eran seis pestañas metidas dentro de "Configuración", un cajón que además
#: mezclaba el contenido de la portada con un ajuste del Aula Virtual que no tiene
#: nada que ver con la portada. Sigue siendo UNA vista y UNA plantilla: lo que
#: cambia es cómo se llega y cómo se llama cada cosa.
#:   tab -> (título, grupo del menú, url de "nuevo", etiqueta, url de "restaurar",
#:           texto de confirmación del restaurar)
SECCIONES_CONTENIDO = {
    # Sin 'nuevo': el diseño de la landing da por hecho exactamente 3 pasos y 3
    # videos (la grilla de "Cómo funciona" y los recuadros de "Sobre el Mundo
    # Ingenio Blocks" no tienen dónde poner un 4º). Por ahora el CMS acá es solo
    # de edición, no de alta/baja -si el cliente pide poder agregar más
    # adelante, basta con devolverle su 'panel:step_new'/'panel:video_new' y
    # 'Nuevo paso'/'Nuevo video' a esta tupla, y destapar el botón "Eliminar"
    # comentado en steps_rows.html / videos_rows.html-.
    'pasos': (
        'Cómo funciona', 'Portada', None, None,
        'panel:step_restore_defaults',
        '¿Restaurar los pasos a los valores por defecto? Se perderán las '
        'ediciones que hayas hecho, y las FOTOS habrá que volver a subirlas. '
        'Esta acción no se puede deshacer.',
    ),
    'videos': (
        'Videos', 'Portada', None, None,
        'panel:video_restore_defaults',
        '¿Restaurar los videos a los valores por defecto? Se perderán las '
        'ediciones que hayas hecho, y las PORTADAS habrá que volver a subirlas. '
        'Esta acción no se puede deshacer.',
    ),
    'testimonios': (
        'Testimonios', 'Portada', 'panel:testimonial_new', 'Nuevo testimonio',
        'panel:testimonial_restore_defaults',
        '¿Restaurar los testimonios a los valores por defecto? Se perderán todos '
        'los testimonios agregados y ediciones que hayas hecho. Esta acción no se '
        'puede deshacer.',
    ),
    'faqs': (
        'Preguntas frecuentes', 'Portada', 'panel:faq_new', 'Nueva pregunta',
        'panel:faq_restore_defaults',
        '¿Restaurar las preguntas frecuentes a los valores por defecto? Se perderán '
        'todas las preguntas agregadas y ediciones que hayas hecho. Esta acción no '
        'se puede deshacer.',
    ),
    # Estas dos no son listas: son un formulario de ajustes, no tienen "nuevo"
    # ni valores por defecto que restaurar.
    'concurso': ('Concurso', 'Portada', None, None, None, None),
    'aula': ('Ritmo de entrega', 'Academia', None, None, None, None),
}


@staff_required
def configuracion_legacy(request):
    """La vieja pantalla única de Configuración, ahora repartida en el menú.

    Un favorito o un enlace pegado en un correo seguía apuntando acá, así que
    en vez de un 404 se manda a la sección que pedía el viejo `?tab=`."""
    tab = request.GET.get('tab', 'faqs')
    destino = {
        'pasos': 'panel:cfg_pasos', 'videos': 'panel:cfg_videos',
        'testimonios': 'panel:cfg_testimonios', 'faqs': 'panel:cfg_faqs',
        'concurso': 'panel:cfg_concurso', 'aula': 'panel:cfg_aula',
    }.get(tab, 'panel:cfg_faqs')
    return redirect(destino)


@staff_required
def configuracion(request, tab='faqs'):

    # Los ajustes del Aula son una fila única, así que se editan en la misma
    # página en vez de tener su propio formulario aparte.
    ajustes = AjustesAula.obtener()
    if request.method == 'POST' and request.POST.get('form') == 'aula':
        ajustes_form = AjustesAulaForm(request.POST, instance=ajustes)
        if ajustes_form.is_valid():
            ajustes_form.save()
            messages.success(request, 'Ritmo de entrega guardado.')
            return redirect('panel:cfg_aula')
    else:
        ajustes_form = AjustesAulaForm(instance=ajustes)

    # La franja del concurso también es fila única. request.FILES: sin esto la
    # imagen se descartaría en silencio.
    concurso = SeccionConcurso.obtener()
    if request.method == 'POST' and request.POST.get('form') == 'concurso':
        concurso_form = SeccionConcursoForm(request.POST, request.FILES, instance=concurso)
        if concurso_form.is_valid():
            concurso_form.save()
            messages.success(request, 'Sección del concurso guardada.')
            return redirect('panel:cfg_concurso')
        tab = 'concurso'   # que la página con el error quede a la vista
    else:
        concurso_form = SeccionConcursoForm(instance=concurso)

    titulo, grupo, nuevo_url, nuevo_label, restaurar_url, restaurar_confirm = \
        SECCIONES_CONTENIDO.get(tab, SECCIONES_CONTENIDO['faqs'])

    ctx = {
        'faqs': FAQ.objects.all(),
        'testimonials': Testimonial.objects.all(),
        'videos': LandingVideo.objects.all(),
        'steps': LandingStep.objects.all(),
        'ajustes_form': ajustes_form,
        'concurso_form': concurso_form,
        'ganadores': GanadorConcurso.objects.all(),
        'total_cursos': Course.objects.filter(is_active=True).count(),
        'tab': tab if tab in SECCIONES_CONTENIDO else 'faqs',
        # el menú marca la entrada concreta, no un "config" genérico
        'section': f'cfg-{tab}',
        'titulo': titulo,
        'grupo': grupo,
        'nuevo_url': nuevo_url,
        'nuevo_label': nuevo_label,
        'restaurar_url': restaurar_url,
        'restaurar_confirm': restaurar_confirm,
    }
    return render(request, 'panel/configuracion.html', ctx)


@staff_required
def faq_form(request, pk=None):
    faq = get_object_or_404(FAQ, pk=pk) if pk else None
    form = FAQForm(request.POST or None, instance=faq)
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        messages.success(request, f'Pregunta "{obj.question}" guardada.')
        return redirect(reverse('panel:cfg_faqs'))
    return render(request, 'panel/faq_form.html', {
        'form': form, 'faq': faq, 'section': 'cfg-faqs',
    })


@staff_required
@require_POST
def faq_toggle_active(request, pk):
    """Prende o apaga una pregunta frecuente desde la propia lista — mismo
    patrón que el ojo en Productos y Testimonios."""
    f = get_object_or_404(FAQ, pk=pk)
    f.is_active = not f.is_active
    f.save(update_fields=['is_active'])
    verbo = 'se muestra' if f.is_active else 'ya no se muestra'
    messages.success(request, f'La pregunta "{f.question}" {verbo} en la landing.')
    return render(request, 'panel/partials/faqs_panel.html', {
        'faqs': FAQ.objects.all(), 'oob': True,
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
    return redirect(reverse('panel:cfg_faqs'))


@staff_required
@require_POST
def faq_restore_defaults(request):
    """Borra todas las preguntas actuales (personalizadas o editadas) y recrea
    el set original. Acción destructiva: el botón que la dispara lleva
    hx-confirm (modal de confirmación propio del panel, no el confirm() nativo)."""
    FAQ.objects.restore_defaults()
    messages.success(request, 'Preguntas frecuentes restauradas a los valores por defecto.')
    target = reverse('panel:cfg_faqs')
    if is_htmx(request):
        resp = HttpResponse()
        resp['HX-Redirect'] = target
        return resp
    return redirect(target)


@staff_required
def ganador_form(request, pk=None):
    ganador = get_object_or_404(GanadorConcurso, pk=pk) if pk else None
    # request.FILES: sin esto la foto se descarta en silencio.
    form = GanadorConcursoForm(request.POST or None, request.FILES or None, instance=ganador)
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        messages.success(request, f'Ganador "{obj.nombre}" guardado.')
        return redirect(reverse('panel:cfg_concurso'))
    return render(request, 'panel/ganador_form.html', {
        'form': form, 'ganador': ganador, 'section': 'cfg-concurso',
    })


@staff_required
@require_POST
def ganador_delete(request, pk):
    ganador = get_object_or_404(GanadorConcurso, pk=pk)
    nombre = ganador.nombre
    ganador.delete()
    if is_htmx(request):
        return HttpResponse('')
    messages.success(request, f'Ganador "{nombre}" eliminado.')
    return redirect(reverse('panel:cfg_concurso'))


@staff_required
def testimonial_form(request, pk=None):
    testimonial = get_object_or_404(Testimonial, pk=pk) if pk else None
    form = TestimonialForm(request.POST or None, instance=testimonial)
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        messages.success(request, f'Testimonio de "{obj.name}" guardado.')
        return redirect(reverse('panel:cfg_testimonios'))
    return render(request, 'panel/testimonial_form.html', {
        'form': form, 'testimonial': testimonial, 'section': 'cfg-testimonios',
    })


@staff_required
@require_POST
def testimonial_toggle_active(request, pk):
    """Prende o apaga un testimonio desde la propia lista — mismo patrón que el
    ojo de portada en Productos: antes esto solo se podía tocar abriendo el
    formulario de edición, un paso de más para algo que se hace a cada rato y
    que además duplicaba el control con el check "Visible en la landing" de
    ahí adentro."""
    t = get_object_or_404(Testimonial, pk=pk)
    t.is_active = not t.is_active
    t.save(update_fields=['is_active'])
    verbo = 'se muestra' if t.is_active else 'ya no se muestra'
    messages.success(request, f'El testimonio de "{t.name}" {verbo} en la landing.')
    return render(request, 'panel/partials/testimonials_panel.html', {
        'testimonials': Testimonial.objects.all(), 'oob': True,
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
    return redirect(reverse('panel:cfg_testimonios'))


@staff_required
@require_POST
def testimonial_restore_defaults(request):
    """Borra todos los testimonios actuales (personalizados o editados) y recrea
    el set original. Acción destructiva: el botón que la dispara lleva
    hx-confirm (modal de confirmación propio del panel, no el confirm() nativo)."""
    Testimonial.objects.restore_defaults()
    messages.success(request, 'Testimonios restaurados a los valores por defecto.')
    target = reverse('panel:cfg_testimonios')
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
        return redirect(reverse('panel:cfg_videos'))
    return render(request, 'panel/video_form.html', {
        'form': form, 'video': video, 'section': 'cfg-videos',
    })


@staff_required
@require_POST
def video_toggle_active(request, pk):
    """Prende o apaga un video desde la propia lista — mismo patrón que el ojo
    en Productos, Testimonios y Preguntas frecuentes.

    Sin ningún botón que la llame por ahora: el ojo de Videos está comentado
    en videos_rows.html (grilla rígida de 3 columnas, ver la nota ahí). La
    vista se deja viva por si se reactiva."""
    v = get_object_or_404(LandingVideo, pk=pk)
    v.is_active = not v.is_active
    v.save(update_fields=['is_active'])
    verbo = 'se muestra' if v.is_active else 'ya no se muestra'
    messages.success(request, f'El video "{v.title}" {verbo} en la landing.')
    return render(request, 'panel/partials/videos_panel.html', {
        'videos': LandingVideo.objects.all(), 'oob': True,
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
    return redirect(reverse('panel:cfg_videos'))


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
    target = reverse('panel:cfg_videos')
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
        return redirect(reverse('panel:cfg_pasos'))
    return render(request, 'panel/step_form.html', {
        'form': form, 'step': step, 'section': 'cfg-pasos',
    })


@staff_required
@require_POST
def step_toggle_active(request, pk):
    """Prende o apaga un paso desde la propia lista — mismo patrón que el ojo
    en Productos, Testimonios y Preguntas frecuentes.

    Sin ningún botón que la llame por ahora: el ojo de Cómo funciona está
    comentado en steps_rows.html (grilla rígida de 3 columnas, ver la nota
    ahí). La vista se deja viva por si se reactiva."""
    s = get_object_or_404(LandingStep, pk=pk)
    s.is_active = not s.is_active
    s.save(update_fields=['is_active'])
    verbo = 'se muestra' if s.is_active else 'ya no se muestra'
    messages.success(request, f'El paso "{s.title}" {verbo} en la landing.')
    return render(request, 'panel/partials/steps_panel.html', {
        'steps': LandingStep.objects.all(), 'oob': True,
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
    return redirect(reverse('panel:cfg_pasos'))


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
    target = reverse('panel:cfg_pasos')
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


# ---------------------------------------------------------------------------
# Cuentas de gestión
#
# Solo superusuarios. La clienta y sus ayudantes son staff: entran al panel y
# manejan la tienda, pero no pueden crear ni borrar cuentas. Así una cuenta
# comprometida no puede fabricarse más accesos ni dejar fuera al dueño.
# ---------------------------------------------------------------------------

def superuser_required(view):
    """Como staff_required, pero además exige ser superusuario.

    A un staff normal se le manda al panel con un mensaje en vez de un 403: no
    es un intento de ataque, es alguien que llegó a una URL que no le toca.
    """

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            return redirect(f"{reverse('panel:login')}?next={request.path}")
        if not request.user.is_superuser:
            messages.error(request, 'Solo la cuenta principal puede administrar las cuentas de gestión.')
            return redirect('panel:dashboard')
        return view(request, *args, **kwargs)

    return wrapper


def _puede_modificarse(request, user):
    """Reglas de a quién SÍ se puede tocar desde esta pantalla.

    - La propia cuenta no: desactivarse o borrarse a sí mismo deja al dueño
      fuera del panel sin forma de volver a entrar.
    - Otros superusuarios tampoco: evita que dos dueños se saquen entre ellos y
      que el sistema quede sin ninguna cuenta principal.
    """
    if user.pk == request.user.pk:
        return False, 'No puedes modificar tu propia cuenta desde acá.'
    if user.is_superuser:
        return False, 'Las cuentas principales no se administran desde acá.'
    return True, ''


@superuser_required
def staff_users(request):
    from django.contrib.auth.models import User

    form = StaffUserForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data['email']
        user = User.objects.create_user(
            username=email,
            email=email,
            password=form.cleaned_data['password'],
            first_name=form.cleaned_data['nombre'],
        )
        # staff sí, superusuario no: puede gestionar la tienda pero no crear
        # más cuentas ni entrar al admin de Django.
        user.is_staff = True
        user.save()
        messages.success(
            request,
            f'Cuenta creada para {email}. Dictale la contraseña que acabas de escribir: '
            f'no vuelve a mostrarse.',
        )
        return redirect('panel:staff_users')

    cuentas = User.objects.filter(is_staff=True).order_by('-is_superuser', 'email')
    return render(request, 'panel/staff_users.html', {
        'section': 'staff',
        'form': form,
        'cuentas': cuentas,
    })


@superuser_required
@require_POST
def staff_user_toggle(request, pk):
    from django.contrib.auth.models import User
    user = get_object_or_404(User, pk=pk, is_staff=True)
    ok, motivo = _puede_modificarse(request, user)
    if not ok:
        messages.error(request, motivo)
        return redirect('panel:staff_users')

    user.is_active = not user.is_active
    user.save(update_fields=['is_active'])
    messages.success(
        request,
        f'Cuenta de {user.email} {"activada" if user.is_active else "desactivada"}.',
    )
    return redirect('panel:staff_users')


@superuser_required
@require_POST
def staff_user_password(request, pk):
    from django.contrib.auth.models import User
    user = get_object_or_404(User, pk=pk, is_staff=True)
    ok, motivo = _puede_modificarse(request, user)
    if not ok:
        messages.error(request, motivo)
        return redirect('panel:staff_users')

    nueva = (request.POST.get('password') or '').strip()
    try:
        validate_password(nueva, user=user)
    except DjangoValidationError as e:
        messages.error(request, ' '.join(e.messages))
        return redirect('panel:staff_users')

    user.set_password(nueva)
    user.save(update_fields=['password'])
    messages.success(
        request,
        f'Contraseña de {user.email} actualizada. Dictasela: no vuelve a mostrarse.',
    )
    return redirect('panel:staff_users')


@superuser_required
@require_POST
def staff_user_delete(request, pk):
    from django.contrib.auth.models import User
    user = get_object_or_404(User, pk=pk, is_staff=True)
    ok, motivo = _puede_modificarse(request, user)
    if not ok:
        messages.error(request, motivo)
        return redirect('panel:staff_users')

    # Si la cuenta además es alumna (compró un kit para probar), borrarla se
    # llevaría por delante su membresía y su avance. En ese caso se desactiva:
    # deja de entrar al panel y al sitio, pero el historial queda intacto.
    if hasattr(user, 'membership'):
        user.is_active = False
        user.is_staff = False
        user.save(update_fields=['is_active', 'is_staff'])
        messages.success(
            request,
            f'{user.email} también es alumno, así que se desactivó en vez de borrarse '
            f'(su membresía y su avance se conservan).',
        )
        return redirect('panel:staff_users')

    email = user.email
    user.delete()
    messages.success(request, f'Cuenta de {email} eliminada.')
    return redirect('panel:staff_users')


# ---------------------------------------------------------------------------
# Visitas y registro de accesos
# ---------------------------------------------------------------------------

# Rango de tiempo que se puede elegir en pantalla. La clave es lo que viaja en
# la URL (?rango=mes) y el valor es (etiqueta, días hacia atrás).
RANGOS_VISITAS = {
    'semana': ('Últimos 7 días', 7),
    'mes': ('Últimos 30 días', 30),
    'anio': ('Último año', 365),
}


@staff_required
def visitas(request):
    """Cuánta gente entra al sitio, por día, mes o año."""
    from django.db.models.functions import TruncMonth
    from .models import OrigenDiario, VisitaDiaria, VisitanteDiario

    clave = request.GET.get('rango', 'mes')
    if clave not in RANGOS_VISITAS:
        clave = 'mes'
    etiqueta, dias = RANGOS_VISITAS[clave]

    hoy = timezone.localdate()
    desde = hoy - timedelta(days=dias - 1)

    vistas_qs = VisitaDiaria.objects.filter(fecha__gte=desde)
    unicos_qs = VisitanteDiario.objects.filter(fecha__gte=desde)

    total_vistas = vistas_qs.aggregate(t=Sum('vistas'))['t'] or 0
    total_personas = unicos_qs.count()

    # Serie para el gráfico. En el rango de un año se agrupa por mes: 365
    # barras no se leen, y la pregunta ahí es "cómo viene el año", no "qué pasó
    # el 14 de marzo".
    if clave == 'anio':
        serie_raw = (
            vistas_qs.annotate(periodo=TruncMonth('fecha'))
            .values('periodo').annotate(v=Sum('vistas')).order_by('periodo')
        )
        personas_raw = (
            unicos_qs.annotate(periodo=TruncMonth('fecha'))
            .values('periodo').annotate(p=Count('id')).order_by('periodo')
        )
        formato = '%b %Y'
    else:
        serie_raw = (
            vistas_qs.values('fecha').annotate(v=Sum('vistas')).order_by('fecha')
        )
        serie_raw = [{'periodo': r['fecha'], 'v': r['v']} for r in serie_raw]
        personas_raw = (
            unicos_qs.values('fecha').annotate(p=Count('id')).order_by('fecha')
        )
        personas_raw = [{'periodo': r['fecha'], 'p': r['p']} for r in personas_raw]
        formato = '%d/%m'

    personas_por_periodo = {r['periodo']: r['p'] for r in personas_raw}
    serie = [
        {
            'etiqueta': r['periodo'].strftime(formato),
            'vistas': r['v'],
            'personas': personas_por_periodo.get(r['periodo'], 0),
        }
        for r in serie_raw
    ]
    tope = max([p['vistas'] for p in serie], default=0) or 1
    for p in serie:
        p['alto'] = round(p['vistas'] * 100 / tope)

    paginas = (
        vistas_qs.values('ruta').annotate(v=Sum('vistas')).order_by('-v')[:10]
    )
    origenes = (
        OrigenDiario.objects.filter(fecha__gte=desde)
        .values('origen').annotate(v=Sum('visitas')).order_by('-v')[:10]
    )

    return render(request, 'panel/visitas.html', {
        'section': 'visitas',
        'rango': clave,
        'rango_etiqueta': etiqueta,
        'rangos': RANGOS_VISITAS,
        'total_vistas': total_vistas,
        'total_personas': total_personas,
        'serie': serie,
        'paginas': paginas,
        'origenes': origenes,
        'hay_datos': total_vistas > 0,
    })


@staff_required
def accesos(request):
    """Quién entró al panel y al Aula, y quién lo intentó sin lograrlo."""
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    from .models import RegistroAcceso

    zona = request.GET.get('zona', '')
    tipo = request.GET.get('tipo', '')
    q = request.GET.get('q', '').strip()

    items = RegistroAcceso.objects.select_related('usuario')
    if zona in (RegistroAcceso.PANEL, RegistroAcceso.SITIO):
        items = items.filter(zona=zona)
    if tipo in (RegistroAcceso.ENTRADA, RegistroAcceso.FALLIDO, RegistroAcceso.SALIDA):
        items = items.filter(tipo=tipo)
    if q:
        items = items.filter(Q(email__icontains=q) | Q(ip__icontains=q))

    # Scroll infinito y no un tope fijo: este registro lo alimenta tráfico de
    # bots (30.000+ intentos de SSH vistos en la auditoría de seguridad), así
    # que crece rápido. Con un corte duro, los accesos más antiguos del día
    # quedaban invisibles sin ninguna forma de llegar a ellos. Tampoco es
    # "página 1, 2, 3…" con números: es un log para revisar de lo más
    # reciente hacia atrás, no para saltar a una página puntual.
    TAMANO_PAGINA = 50
    paginador = Paginator(items, TAMANO_PAGINA)
    try:
        pagina = paginador.page(int(request.GET.get('page', 1)))
    except (ValueError, EmptyPage, PageNotAnInteger):
        pagina = paginador.page(1)

    desde_24h = timezone.now() - timedelta(hours=24)
    counts = {
        'entradas_24h': RegistroAcceso.objects.filter(
            tipo=RegistroAcceso.ENTRADA, momento__gte=desde_24h,
        ).count(),
        'fallidos_24h': RegistroAcceso.objects.filter(
            tipo=RegistroAcceso.FALLIDO, momento__gte=desde_24h,
        ).count(),
    }

    ctx = {
        'section': 'accesos',
        'items': pagina.object_list,
        'pagina': pagina,
        'counts': counts,
        'zona': zona,
        'tipo': tipo,
        'q': q,
    }
    # El buscador (sin `page` en la URL) y el centinela del scroll infinito
    # (con `page=N`) son los dos casos que piden solo las filas: cubre ambos
    # porque los dos llegan como petición htmx sin boost.
    if is_search_request(request):
        return render(request, 'panel/partials/accesos_rows.html', ctx)
    return render(request, 'panel/accesos.html', ctx)


@staff_required
def mi_cuenta(request):
    """Los datos de la propia cuenta: foto, nombre y contraseña.

    Existe aparte de la pantalla de cuentas porque aquella es solo para
    superusuarios y, a propósito, no deja tocarse a uno mismo. Sin esto, un
    ayudante no tenía forma de cambiar la clave que le dictaron.

    Se llega desde el avatar de la barra lateral y no desde una entrada del
    menú: los datos propios no son una sección del sitio que se administra, son
    de quien lo administra. Es el mismo lugar donde todo el mundo los busca.
    """
    from lms.models import PerfilUsuario

    perfil = PerfilUsuario.de(request.user)
    formulario = request.POST.get('form')

    if request.method == 'POST' and formulario == 'datos':
        form = MiCuentaForm(request.POST, request.FILES, instance=perfil)
        if form.is_valid():
            form.save()
            request.user.first_name = (request.POST.get('first_name') or '').strip()
            request.user.save(update_fields=['first_name'])
            messages.success(request, 'Listo, guardamos tus datos.')
            return redirect('panel:mi_cuenta')
    else:
        form = MiCuentaForm(instance=perfil)

    if request.method == 'POST' and formulario == 'clave':
        actual = request.POST.get('actual') or ''
        nueva = (request.POST.get('nueva') or '').strip()
        repetir = (request.POST.get('repetir') or '').strip()

        if not request.user.check_password(actual):
            messages.error(request, 'Tu contraseña actual no es correcta.')
        elif nueva != repetir:
            messages.error(request, 'Las dos contraseñas nuevas no coinciden.')
        else:
            try:
                validate_password(nueva, user=request.user)
            except DjangoValidationError as e:
                messages.error(request, ' '.join(e.messages))
            else:
                request.user.set_password(nueva)
                request.user.save(update_fields=['password'])
                # Cambiar la clave invalida la sesión actual: sin esto, quien
                # acaba de cambiarla queda deslogueado sin entender por qué.
                update_session_auth_hash(request, request.user)
                messages.success(request, 'Tu contraseña quedó actualizada.')
                return redirect('panel:mi_cuenta')

    return render(request, 'panel/mi_cuenta.html', {
        'section': 'mi_cuenta',
        'form': form,
        'perfil': perfil,
    })


@staff_required
@require_POST
def mi_cuenta_quitar_foto(request):
    from lms.models import PerfilUsuario

    perfil = PerfilUsuario.de(request.user)
    if perfil.avatar:
        perfil.avatar.delete(save=True)
        messages.success(request, 'Se quitó tu foto de perfil.')
    return redirect('panel:mi_cuenta')


# ---------------------------------------------------------------------------
# Categorías de cursos
#
# Una categoría agrupa modelos y define su ritmo de entrega. Es lo que hace que
# agregar un modelo nuevo no obligue a ir producto por producto marcándolo:
# se etiqueta con la categoría y llega solo a todos los alumnos que la tienen.
# ---------------------------------------------------------------------------

@staff_required
def categories(request):
    """Pantalla interna a la que se entra desde Cursos y diplomas. No tiene
    entrada propia en el menú a propósito: se administran categorías cuando se
    está trabajando en el contenido, no como una tarea aparte. Por eso la sección
    marcada sigue siendo 'courses'."""
    from lms.models import CourseCategory

    return render(request, 'panel/categories.html', {
        'section': 'courses',
        'categorias': (
            CourseCategory.objects.prefetch_related('cursos_en_categoria__curso').all()
        ),
        # Un modelo sin categoría no lo puede ver NADIE. Es un error silencioso
        # -crearlo y olvidar etiquetarlo- que no se nota hasta que alguien
        # reclama, así que se avisa en la pantalla donde se arregla.
        'cursos_sin_categoria': Course.objects.filter(
            is_active=True, categorias_del_curso__isnull=True,
        ),
    })


@staff_required
def category_form(request, pk=None):
    from lms.models import CourseCategory

    categoria = get_object_or_404(CourseCategory, pk=pk) if pk else None
    form = CourseCategoryForm(request.POST or None, instance=categoria)
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        messages.success(request, f'Categoría "{obj.nombre}" guardada.')
        return redirect('panel:category_edit', pk=obj.pk)

    return render(request, 'panel/category_form.html', {
        'section': 'courses',
        'form': form,
        'categoria': categoria,
        'cursos_en_categoria': (
            categoria.cursos_en_categoria.select_related('curso').all() if categoria else None
        ),
    })


@staff_required
@require_POST
def category_delete(request, pk):
    """Borra una categoría, salvo que haya alumnos que la tengan.

    Borrarla les quitaría el acceso a todo su contenido de golpe, y a productos
    que ya se vendieron. En ese caso se desactiva: deja de ofrecerse en
    productos nuevos, pero quien ya la compró conserva lo suyo.
    """
    from lms.models import CourseCategory

    categoria = get_object_or_404(CourseCategory, pk=pk)
    nombre = categoria.nombre
    alumnos = categoria.membresias_con_categoria.count()

    if alumnos:
        categoria.is_active = False
        categoria.save(update_fields=['is_active'])
        messages.success(
            request,
            f'"{nombre}" tiene {alumnos} alumno{"s" if alumnos != 1 else ""}, '
            f'así que se desactivó en vez de borrarse (conservan su acceso).',
        )
    else:
        categoria.delete()
        messages.success(request, f'Categoría "{nombre}" eliminada.')
    return redirect('panel:categories')


@staff_required
@require_POST
def category_courses_reorder(request, pk):
    """Reordena los cursos DENTRO de una categoría (arrastre)."""
    from lms.models import CategoryCourse, CourseCategory

    categoria = get_object_or_404(CourseCategory, pk=pk)
    ids = [int(i) for i in request.POST.getlist('order') if str(i).isdigit()]
    for posicion, cc_id in enumerate(ids, start=1):
        CategoryCourse.objects.filter(pk=cc_id, categoria=categoria).update(orden=posicion)

    return render(request, 'panel/partials/category_courses_rows.html', {
        'categoria': categoria,
        'cursos_en_categoria': categoria.cursos_en_categoria.select_related('curso').all(),
    })
