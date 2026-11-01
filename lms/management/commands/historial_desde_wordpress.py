"""Trae del volcado de WordPress la HISTORIA de cada familia: sus compras, las
renovaciones automáticas, sus suscripciones y cada periodo de acceso (PMPro).

También todo lo demás que la página anterior sabía y que no tiene otro lugar:
- las notas de cada pedido (estados de Shipit, respuestas y errores de Transbank),
- los correos que se le mandaron a cada familia (asunto, fecha y si salió),
- su perfil: direcciones de facturación y despacho, cuándo se registró, su
  última actividad y cuántas veces entró (lms.models.PerfilWordPress),
- los mensajes del formulario de contacto (catalog.models.MensajeContacto),
- los cupones, que se traen APAGADOS y solo como registro.

La migración trajo el estado de hoy (quién tiene acceso y hasta cuándo); esto
trae cómo se llegó ahí, para que el panel pueda mostrar cuántas veces compró,
cuántas veces se le venció y volvió, etc. Ver lms.models.HistorialWordPress.

Además rellena el nombre del alumno (el niño) a quien lo tenga vacío, con el
que la familia escribió en su último pedido. Nunca pisa uno que ya exista: pudo
haberse corregido a mano en el panel.

No da ni quita acceso, no cobra, no factura y no manda correos.
Por omisión NO escribe: muestra qué haría. Con `--aplicar` guarda. Se puede
correr las veces que haga falta: actualiza lo que ya trajo, no lo duplica.

    python manage.py historial_desde_wordpress --dump volcado.sql
    python manage.py historial_desde_wordpress --dump volcado.sql --aplicar
"""
import html
import json
import re
import zlib
from collections import Counter, defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.models import MensajeContacto
from lms.models import HistorialWordPress as H, Membership, PerfilWordPress
from payments.models import Coupon

from ._wp_dump import una_pasada

UTC = ZoneInfo('UTC')
#: PMPro guarda sus fechas en la hora del sitio, no en UTC.
SANTIAGO = ZoneInfo('America/Santiago')

#: Estado del pedido -> (texto, ¿se pagó?). Lo que no está acá (papelera,
#: borradores del checkout) no es una compra y no se trae.
ESTADOS_PEDIDO = {
    'wc-completed': ('Completado', True),
    'wc-delivered': ('Entregado', True),
    'wc-processing': ('En proceso', True),
    'wc-in_preparation': ('En preparación', True),
    'wc-refunded': ('Reembolsado', False),
    'wc-cancelled': ('Cancelado', False),
    'wc-failed': ('Falló el pago', False),
    'wc-pending': ('No se pagó', False),
    'wc-on-hold': ('En espera', False),
}
ESTADOS_SUSCRIPCION = {
    'wc-active': 'Activa',
    'wc-expired': 'Vencida',
    'wc-cancelled': 'Cancelada',
    'wc-on-hold': 'En pausa',
    'wc-pending': 'Pendiente',
    'wc-pending-cancel': 'Por cancelar',
}
ESTADOS_PERIODO = {
    'active': 'Vigente',
    'expired': 'Venció',
    'inactive': 'Terminó',
    'changed': 'Cambió de plan',
    'admin_changed': 'Cambiado por la tienda',
    'cancelled': 'Cancelado',
    'admin_cancelled': 'Cancelado por la tienda',
}
PERIODOS = {'day': 'día', 'week': 'semana', 'month': 'mes', 'year': 'año'}


def _fecha(texto, zona):
    """'2025-07-07 14:32:21' -> datetime con zona. Vacío, '0' o fecha cero -> None.
    `_schedule_*` a veces viene como número de segundos (timestamp)."""
    texto = (texto or '').strip()
    if not texto or texto == '0' or texto.startswith('0000'):
        return None
    if texto.isdigit():
        return datetime.fromtimestamp(int(texto), tz=UTC)
    try:
        return datetime.strptime(texto[:19], '%Y-%m-%d %H:%M:%S').replace(tzinfo=zona)
    except ValueError:
        return None


def _producto(nombre):
    # WooCommerce guarda la variante como "Plan Individual<span> - </span>Promo".
    return ' '.join((nombre or '').replace('<span> - </span>', ' – ').split())


def _monto(texto):
    try:
        return max(int(round(float(texto or 0))), 0)
    except ValueError:
        return 0


def _texto(crudo, largo=400):
    """HTML de WordPress -> texto de una línea (las notas de Transbank vienen en <div>)."""
    sin_tags = re.sub(r'<[^>]+>', ' ', crudo or '')
    return ' '.join(html.unescape(sin_tags).split())[:largo]


#: Campos del formulario de contacto de Elementor (ver el volcado: _elementor_data).
CAMPOS_FORMULARIO = {
    'name': 'nombre', 'email': 'email', 'field_16509eb': 'telefono',
    'field_504f035': 'motivo', 'field_8ac25fa': 'mensaje', 'field_748c807': 'pagina',
}
DIRECCION = ('first_name', 'last_name', 'address_1', 'address_2', 'city', 'state', 'phone')


def leer(ruta):
    """Lee el volcado en una sola pasada y devuelve un dict con:

    registros: dicts con los campos de HistorialWordPress (incluye correos).
    nombres: {correo: nombre del niño en su último pedido pagado}.
    perfiles: {correo: datos para PerfilWordPress}.
    mensajes: dicts para MensajeContacto.
    cupones: dicts para Coupon (se crean apagados).
    """
    correo_de, registrado = {}, {}
    pedidos, meta, items, pmpro, planes = [], defaultdict(dict), defaultdict(list), [], {}
    notas = defaultdict(list)            # pedido -> [(fecha, texto)]
    usermeta = defaultdict(dict)
    correos_log = []
    envios, valores_envio = {}, defaultdict(dict)
    posts_cupon, meta_cupon = {}, defaultdict(dict)

    def usuario(f):
        correo_de[f['ID']] = (f.get('user_email') or '').strip().lower()
        registrado[f['ID']] = f.get('user_registered')

    def nota(f):
        if f.get('comment_type') == 'order_note':
            notas[f['comment_post_ID']].append((f.get('comment_date') or '', _texto(f.get('comment_content'))))

    def error_tbk(f):
        if f.get('order_id'):
            notas[f['order_id']].append((f.get('created_at') or '', 'Transbank: ' + _texto(
                f.get('custom_error') or f.get('error') or f.get('original_error'))))

    def umeta(f):
        k = f.get('meta_key') or ''
        if k.startswith(('billing_', 'shipping_')) or k in ('wc_last_active', 'pmpro_logins'):
            usermeta[f['user_id']][k] = f.get('meta_value') or ''

    def correo_enviado(f):
        correos_log.append(f)

    def envio_form(f):
        envios[f['id']] = f

    def valor_form(f):
        valores_envio[f['submission_id']][f['key']] = f.get('value') or ''

    def post(f):
        if f.get('post_type') == 'shop_coupon' and f.get('post_status') == 'publish':
            posts_cupon[f['ID']] = f

    def postmeta(f):
        meta_cupon[f['post_id']][f['meta_key']] = f.get('meta_value') or ''

    def pedido(f):
        pedidos.append(f)

    def meta_pedido(f):
        meta[f['order_id']][f['meta_key']] = f.get('meta_value') or ''

    def item(f):
        if f.get('order_item_type') == 'line_item':
            items[f['order_id']].append(_producto(f.get('order_item_name')))

    def periodo(f):
        pmpro.append(f)

    def plan(f):
        planes[f['id']] = (f.get('name') or '').strip().title()

    una_pasada(ruta, {
        'wp_users': usuario,
        'wp_wc_orders': pedido,
        'wp_wc_orders_meta': meta_pedido,
        'wp_woocommerce_order_items': item,
        'wp_pmpro_memberships_users': periodo,
        'wp_pmpro_membership_levels': plan,
        'wp_comments': nota,
        'wp_transbank_execution_error_log': error_tbk,
        'wp_usermeta': umeta,
        'wp_wpmailsmtp_emails_log': correo_enviado,
        'wp_e_submissions': envio_form,
        'wp_e_submissions_values': valor_form,
        'wp_posts': post,
        'wp_postmeta': postmeta,
    })

    registros, nombres = [], {}
    ultimo_nombre = {}   # correo -> (fecha, nombre)

    for p in pedidos:
        correo = (correo_de.get(p.get('customer_id')) if p.get('customer_id') not in (None, '0') else '') \
            or (p.get('billing_email') or '').strip().lower()
        if not correo:
            continue
        m = meta.get(p['id'], {})
        productos = ', '.join(items.get(p['id'], []))[:300]

        if p.get('type') == 'shop_order':
            if p['status'] not in ESTADOS_PEDIDO:
                continue
            estado, pagado = ESTADOS_PEDIDO[p['status']]
            if m.get('_subscription_renewal'):
                tipo = H.RENOVACION
            elif m.get('_subscription_resubscribe'):
                tipo = H.RESUSCRIPCION
            else:
                tipo = H.COMPRA
            fecha = _fecha(p.get('date_created_gmt'), UTC)
            if fecha is None:
                continue
            registros.append({
                'tipo': tipo, 'wp_id': int(p['id']), 'email': correo, 'fecha': fecha,
                'fecha_fin': None, 'estado': estado, 'pagado': pagado,
                'monto': _monto(p.get('total_amount')), 'detalle': productos,
                'medio_pago': (p.get('payment_method_title') or '')[:60],
                'notas': [list(n) for n in sorted(notas.get(p['id'], []))][-40:],
            })
            alumno = ' '.join(f"{m.get('_alumno_nombre', '')} {m.get('_alumno_apellido', '')}".split())
            if pagado and alumno and (correo not in ultimo_nombre or fecha > ultimo_nombre[correo][0]):
                ultimo_nombre[correo] = (fecha, alumno)

        elif p.get('type') == 'shop_subscription':
            if p['status'] not in ESTADOS_SUSCRIPCION:
                continue
            inicio = _fecha(m.get('_schedule_start'), UTC) or _fecha(p.get('date_created_gmt'), UTC)
            if inicio is None:
                continue
            fin = _fecha(m.get('_schedule_end'), UTC) or _fecha(m.get('_schedule_cancelled'), UTC)
            cada = m.get('_billing_interval') or '1'
            periodo_txt = PERIODOS.get(m.get('_billing_period'), '')
            detalle = productos
            if periodo_txt:
                detalle = f"{productos} · cada {cada} {periodo_txt}{'' if cada == '1' else ('es' if periodo_txt == 'mes' else 's')}"
            registros.append({
                'tipo': H.SUSCRIPCION, 'wp_id': int(p['id']), 'email': correo, 'fecha': inicio,
                'fecha_fin': fin, 'estado': ESTADOS_SUSCRIPCION[p['status']], 'pagado': False,
                'monto': _monto(p.get('total_amount')), 'detalle': detalle[:300],
                'medio_pago': (p.get('payment_method_title') or '')[:60],
                'notas': [list(n) for n in sorted(notas.get(p['id'], []))][-40:],
            })

    for f in pmpro:
        correo = correo_de.get(f.get('user_id'), '')
        inicio = _fecha(f.get('startdate'), SANTIAGO)
        if not correo or inicio is None:
            continue
        registros.append({
            'tipo': H.PERIODO, 'wp_id': int(f['id']), 'email': correo, 'fecha': inicio,
            'fecha_fin': _fecha(f.get('enddate'), SANTIAGO),
            'estado': ESTADOS_PERIODO.get(f.get('status'), f.get('status') or ''),
            'pagado': False, 'monto': 0,
            'detalle': planes.get(f.get('membership_id'), 'Plan'), 'medio_pago': '', 'notas': [],
        })

    # --- Correos que se le mandaron a cada familia ---
    for c in correos_log:
        try:
            para = json.loads(c.get('people') or '{}').get('to') or []
        except ValueError:
            para = []
        fecha = _fecha(c.get('date_sent'), UTC)
        if fecha is None:
            continue
        for correo in {(x or '').strip().lower() for x in para if x}:
            registros.append({
                # crc32 y no hash(): hash() cambia en cada ejecución y al repetir el
                # comando duplicaría los correos en vez de reconocerlos.
                'tipo': H.CORREO, 'wp_id': int(c['id']) * 10 + (zlib.crc32(correo.encode()) % 10),
                'email': correo, 'fecha': fecha, 'fecha_fin': None,
                'estado': 'Enviado' if c.get('status') == '1' else 'No salió',
                'pagado': False, 'monto': 0, 'detalle': _texto(c.get('subject'), 300),
                'medio_pago': '', 'notas': [],
            })

    # --- Perfil: direcciones, registro, última actividad e ingresos ---
    perfiles = {}
    for uid, correo in correo_de.items():
        um = usermeta.get(uid, {})
        datos = {}
        for tipo in ('billing', 'shipping'):
            d = {k: um.get(f'{tipo}_{k}', '').strip() for k in DIRECCION}
            if any(d.values()):
                datos['facturacion' if tipo == 'billing' else 'despacho'] = d
        alta = _fecha(registrado.get(uid), UTC)
        if alta:
            datos['registrado'] = alta.isoformat()
        activo = _fecha(um.get('wc_last_active'), UTC)
        if activo:
            datos['ultima_actividad'] = activo.isoformat()
        logins = um.get('pmpro_logins', '')
        total = re.search(r'"alltime";i:(\d+)', logins)
        ultimo = re.search(r'"last";s:\d+:"([^"]*)"', logins)
        if total:
            datos['ingresos'] = int(total.group(1))
        if ultimo:
            datos['ultimo_ingreso'] = ultimo.group(1)
        if datos and correo:
            perfiles[correo] = datos

    # --- Mensajes del formulario de contacto ---
    mensajes = []
    for sid, envio in envios.items():
        v = {CAMPOS_FORMULARIO[k]: val for k, val in valores_envio.get(sid, {}).items() if k in CAMPOS_FORMULARIO}
        creado = _fecha(envio.get('created_at_gmt'), UTC) or _fecha(envio.get('created_at'), SANTIAGO)
        if not v.get('email') or creado is None:
            continue
        if (envio.get('form_name') or '').lower().startswith('suscrip'):
            v.setdefault('motivo', 'Formulario de suscripción')
        mensajes.append({
            'wp_id': int(sid), 'creado': creado,
            'nombre': v.get('nombre', '')[:200], 'email': v['email'].strip()[:254],
            'telefono': v.get('telefono', '')[:40], 'motivo': v.get('motivo', '')[:120],
            'mensaje': v.get('mensaje', ''), 'pagina': (v.get('pagina') or envio.get('referer') or '')[:300],
        })

    # --- Cupones: apagados, solo como registro ---
    cupones = []
    for pid, p in posts_cupon.items():
        m = meta_cupon.get(pid, {})
        tipo_wp = m.get('discount_type', '')
        try:
            valor = int(float(m.get('coupon_amount') or 0))
        except ValueError:
            valor = 0
        limite = int(m['usage_limit']) if (m.get('usage_limit') or '0').isdigit() and int(m['usage_limit']) > 0 else None
        cupones.append({
            'code': (p.get('post_title') or '').strip()[:30],
            'discount_type': 'AMOUNT' if 'fixed' in tipo_wp else 'PERCENT',
            'value': min(valor, 100) if 'fixed' not in tipo_wp else valor,
            'max_uses': limite,
            'ends_at': _fecha(m.get('date_expires'), UTC),
            'description': f'De la página anterior ({tipo_wp}, usado {m.get("usage_count") or 0} veces). Revisar antes de prender.'[:200],
        })

    nombres = {correo: nombre for correo, (_, nombre) in ultimo_nombre.items()}
    return {'registros': registros, 'nombres': nombres, 'perfiles': perfiles,
            'mensajes': mensajes, 'cupones': cupones}


class Command(BaseCommand):
    help = 'Trae del volcado de WordPress el historial de compras y accesos de cada familia.'

    def add_arguments(self, parser):
        parser.add_argument('--dump', required=True, help='Ruta al archivo .sql')
        parser.add_argument('--aplicar', action='store_true', help='Guarda. Sin esto solo muestra qué haría.')

    def handle(self, *args, **op):
        self.stdout.write('Leyendo el volcado (una sola pasada)...')
        leido = leer(op['dump'])
        registros, nombres = leido['registros'], leido['nombres']

        por_tipo = Counter(r['tipo'] for r in registros)
        correos = {r['email'] for r in registros}
        alumnos = {
            m.user.email.lower(): m
            for m in Membership.objects.select_related('user').filter(user__is_staff=False)
            if m.user.email
        }
        sin_nombre = [m for e, m in alumnos.items() if not m.student_name.strip() and e in nombres]

        etiquetas = dict(H.TIPO_CHOICES)
        for tipo, n in por_tipo.most_common():
            self.stdout.write(f'  {n:5d}  {etiquetas[tipo]}')
        self.stdout.write(f'  Familias con historial: {len(correos)} '
                          f'(de ellas, con cuenta acá: {len(correos & set(alumnos))})')
        self.stdout.write(f'  Alumnos sin nombre del niño que se pueden rellenar: {len(sin_nombre)}')
        self.stdout.write(f'  Perfiles (direcciones, registro, actividad): {len(leido["perfiles"])}')
        self.stdout.write(f'  Mensajes del formulario de contacto: {len(leido["mensajes"])}')
        self.stdout.write(f'  Cupones (se traen apagados): {len(leido["cupones"])}')

        if not op['aplicar']:
            self.stdout.write(self.style.WARNING('No se guardó nada. Repite con --aplicar.'))
            return

        campos = ['email', 'fecha', 'fecha_fin', 'estado', 'pagado', 'monto', 'detalle', 'medio_pago', 'notas']
        with transaction.atomic():
            existentes = {(h.tipo, h.wp_id): h for h in H.objects.all()}
            nuevos, cambiados = [], []
            for r in registros:
                h = existentes.get((r['tipo'], r['wp_id']))
                if h is None:
                    nuevos.append(H(**r))
                else:
                    for c in campos:
                        setattr(h, c, r[c])
                    cambiados.append(h)
            H.objects.bulk_create(nuevos, batch_size=500)
            H.objects.bulk_update(cambiados, campos, batch_size=500)

            for m in sin_nombre:
                m.student_name = nombres[m.user.email.lower()][:200]
                m.save(update_fields=['student_name'])

            for correo, datos in leido['perfiles'].items():
                PerfilWordPress.objects.update_or_create(email=correo, defaults={'datos': datos})

            # Los mensajes viejos ya se leyeron en su momento (llegaban por
            # correo): entran como leídos para no llenar de pendientes el Inicio.
            nuevos_msj = 0
            for msj in leido['mensajes']:
                _, creado = MensajeContacto.objects.get_or_create(
                    wp_id=msj['wp_id'],
                    defaults={**msj, 'origen': MensajeContacto.WORDPRESS, 'leido': True})
                nuevos_msj += creado

            # Nunca se pisa ni se prende un cupón que ya exista acá.
            nuevos_cupones = 0
            for c in leido['cupones']:
                # Comparando en mayúsculas y no con iexact: SQLite no iguala Ñ con ñ.
                if c['code'] and not Coupon.objects.filter(code=c['code'].strip().upper()).exists():
                    Coupon.objects.create(**c, is_active=False)
                    nuevos_cupones += 1

        self.stdout.write(self.style.SUCCESS(
            f'Listo: {len(nuevos)} registros nuevos, {len(cambiados)} actualizados, '
            f'{len(sin_nombre)} nombres de alumno rellenados, {len(leido["perfiles"])} perfiles, '
            f'{nuevos_msj} mensajes y {nuevos_cupones} cupones (apagados). No se mandó ningún correo.'))
