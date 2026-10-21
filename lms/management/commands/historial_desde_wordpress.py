"""Trae del volcado de WordPress la HISTORIA de cada familia: sus compras, las
renovaciones automáticas, sus suscripciones y cada periodo de acceso (PMPro).

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
from collections import Counter, defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand
from django.db import transaction

from lms.models import HistorialWordPress as H, Membership

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


def leer(ruta):
    """Lee el volcado y devuelve (registros, nombres_de_alumno).

    registros: lista de dicts con los campos de HistorialWordPress.
    nombres_de_alumno: {correo: nombre del niño en su último pedido pagado}.
    """
    correo_de = {}
    pedidos, meta, items, pmpro, planes = [], defaultdict(dict), defaultdict(list), [], {}

    def usuario(f):
        correo_de[f['ID']] = (f.get('user_email') or '').strip().lower()

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
            'detalle': planes.get(f.get('membership_id'), 'Plan'), 'medio_pago': '',
        })

    nombres = {correo: nombre for correo, (_, nombre) in ultimo_nombre.items()}
    return registros, nombres


class Command(BaseCommand):
    help = 'Trae del volcado de WordPress el historial de compras y accesos de cada familia.'

    def add_arguments(self, parser):
        parser.add_argument('--dump', required=True, help='Ruta al archivo .sql')
        parser.add_argument('--aplicar', action='store_true', help='Guarda. Sin esto solo muestra qué haría.')

    def handle(self, *args, **op):
        self.stdout.write('Leyendo el volcado (una sola pasada)...')
        registros, nombres = leer(op['dump'])

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

        if not op['aplicar']:
            self.stdout.write(self.style.WARNING('No se guardó nada. Repite con --aplicar.'))
            return

        campos = ['email', 'fecha', 'fecha_fin', 'estado', 'pagado', 'monto', 'detalle', 'medio_pago']
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

        self.stdout.write(self.style.SUCCESS(
            f'Listo: {len(nuevos)} registros nuevos, {len(cambiados)} actualizados, '
            f'{len(sin_nombre)} nombres de alumno rellenados. No se mandó ningún correo.'))
