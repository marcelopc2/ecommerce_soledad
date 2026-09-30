"""Trae del WordPress las tarjetas Oneclick y las suscripciones activas.

    python manage.py importar_suscripciones_wordpress --dump volcado.sql
    python manage.py importar_suscripciones_wordpress --dump volcado.sql --aplicar

Qué trae
--------
- Las TARJETAS: lo que Transbank le devolvió al WordPress al inscribirlas
  (`tbk_user` + el `username` con que se inscribió). Son del mismo código de
  comercio que usa esta tienda, así que sirven para cobrar desde acá. Con esto
  un cliente del sitio viejo puede pagar con su tarjeta de siempre sin volver
  a inscribirla.
- Las SUSCRIPCIONES activas, con su monto, cada cuántos meses se cobran y la
  fecha del próximo cobro que tenía el WordPress.

Lo que NO hace, a propósito
---------------------------
No cobra nada, ni ahora ni después por sí solo: mientras el WordPress siga
prendido, él sigue cobrando estas suscripciones, y cobrarlas también acá sería
cobrarle doble a cada cliente. Quedan marcadas como traídas de WordPress y
`cobrar_suscripciones` se las salta hasta que se ponga
COBRAR_SUSCRIPCIONES_WORDPRESS=1 en el .env, el día del cambio y DESPUÉS de
apagar el plugin de Transbank del WordPress.

Se puede correr las veces que haga falta: actualiza por el id de WordPress
en vez de duplicar. Lo normal es correrlo una última vez con el volcado del
día del lanzamiento, para traer las fechas de próximo cobro al día.

Cómo se sabe que las tarjetas sirven: el WordPress las cobra todos los meses
con el MISMO código de mall, tienda hija y llave que usa esta tienda. La
consulta de BIN de Transbank (la única que no cobra) NO sirve para probarlo:
responde "User not found" para las tarjetas inscritas por el plugin viejo,
aunque se estén cobrando sin problema.
"""
import html
import os
import re
from collections import defaultdict
from datetime import datetime, timezone as dt_timezone

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from catalog.models import Product
from lms.management.commands._wp_dump import una_pasada
from payments.models import Suscripcion, TarjetaOneclick

GATEWAY = 'transbank_oneclick_mall_rest'


def _fecha_gmt(valor):
    """'2026-10-03 14:00:00' (GMT, como lo guarda WooCommerce) -> fecha local."""
    if not valor or valor.startswith('0'):
        return None
    try:
        dt = datetime.strptime(valor[:19], '%Y-%m-%d %H:%M:%S').replace(tzinfo=dt_timezone.utc)
    except ValueError:
        return None
    return timezone.localtime(dt).date()


def _meses(intervalo, periodo):
    try:
        n = int(intervalo or 0)
    except ValueError:
        return 0
    return {'month': n, 'year': n * 12}.get(periodo, 0)


class Command(BaseCommand):
    help = 'Trae del WordPress las tarjetas Oneclick y las suscripciones activas (sin cobrar nada).'

    def add_arguments(self, parser):
        parser.add_argument('--dump', required=True)
        parser.add_argument('--aplicar', action='store_true', help='Guarda. Sin esto solo informa.')
        parser.add_argument('--producto', default='',
                            help='Slug del producto al que quedan asociadas. Por omisión, '
                                 'el primero marcado como suscripción.')

    def handle(self, *args, **op):
        if not os.path.exists(op['dump']):
            raise CommandError('No encuentro el volcado: %s' % op['dump'])

        producto = (Product.objects.filter(slug=op['producto']).first() if op['producto']
                    else Product.objects.filter(es_suscripcion=True).order_by('id').first())
        if producto is None:
            raise CommandError('No hay producto de suscripción. Marca uno como suscripción '
                               'en el panel o pasa --producto.')

        tarjetas, subs, omitidas = self._leer(op['dump'])

        self.stdout.write(self.style.MIGRATE_HEADING('Lo que hay en el volcado'))
        self.stdout.write(f'  {len(tarjetas)} tarjeta(s) Oneclick de producción')
        self.stdout.write(f'  {len(subs)} suscripción(es) activas que se pueden traer')
        for motivo, n in sorted(omitidas.items(), key=lambda x: -x[1]):
            self.stdout.write(f'  {n} activa(s) que NO se traen: {motivo}')
        por_periodo = defaultdict(int)
        for s in subs:
            por_periodo[s['cada_meses']] += 1
        self.stdout.write('  cada cuánto se cobran: ' + ', '.join(
            f'{n} cada {m} mes(es)' for m, n in sorted(por_periodo.items())))
        self.stdout.write(f'  quedan asociadas al producto: {producto.name}')

        if not op['aplicar']:
            self.stdout.write(self.style.WARNING('\nEnsayo: no se guardó nada. Agrega --aplicar.'))
            return

        with transaction.atomic():
            creadas = actualizadas = 0
            por_tbk = {}
            for t in tarjetas:
                obj, _ = TarjetaOneclick.objects.update_or_create(
                    tbk_user=t['tbk_user'],
                    defaults={k: t[k] for k in ('email', 'username', 'tipo', 'ultimos4')},
                )
                por_tbk[t['tbk_user']] = obj

            vistas = set()
            for s in subs:
                vistas.add(s['wp_id'])
                datos = {
                    'email': s['email'], 'producto': producto, 'tarjeta': por_tbk[s['tbk_user']],
                    'monto': s['monto'], 'cada_meses': s['cada_meses'],
                    'proximo_cobro': s['proximo_cobro'], 'nombre': s['nombre'][:200],
                    'origen': Suscripcion.WORDPRESS,
                }
                obj = Suscripcion.objects.filter(wp_id=s['wp_id']).first()
                if obj is None:
                    Suscripcion.objects.create(wp_id=s['wp_id'], **datos)
                    creadas += 1
                else:
                    # El estado no se pisa: si en el panel la cancelaron, sigue cancelada.
                    for k, v in datos.items():
                        setattr(obj, k, v)
                    obj.save()
                    actualizadas += 1

            # Las que se trajeron antes y en el WordPress ya no están activas.
            ya_no = (Suscripcion.objects.filter(origen=Suscripcion.WORDPRESS, estado=Suscripcion.ACTIVA)
                     .exclude(wp_id__in=vistas))
            n_ya_no = ya_no.update(estado=Suscripcion.CANCELADA, cancelada_en=timezone.now())

        self.stdout.write(self.style.SUCCESS(
            f'\n{len(por_tbk)} tarjeta(s) guardadas; suscripciones: {creadas} nuevas, '
            f'{actualizadas} actualizadas, {n_ya_no} canceladas porque ya no están activas '
            f'en WordPress. No se cobró nada.'))

    # -- lectura ----------------------------------------------------------

    def _leer(self, ruta):
        ordenes, meta, items = [], defaultdict(dict), defaultdict(list)
        tokens, tokmeta, correo_de = [], defaultdict(dict), {}

        claves = {'_billing_period', '_billing_interval', '_schedule_next_payment'}

        def f_orden(f):
            if f.get('type') == 'shop_subscription' and f.get('status') == 'wc-active':
                ordenes.append(f)

        def f_meta(f):
            if f.get('meta_key') in claves:
                meta[f.get('order_id')][f['meta_key']] = f.get('meta_value')

        def f_item(f):
            if f.get('order_item_type') == 'line_item':
                # WooCommerce guarda el nombre con HTML ('Plan<span> - </span>Trimestral').
                nombre = re.sub(r'<[^>]+>', '', f.get('order_item_name') or '')
                items[f.get('order_id')].append(html.unescape(nombre).strip())

        def f_tok(f):
            if f.get('gateway_id') == GATEWAY:
                tokens.append(f)

        def f_tokmeta(f):
            tokmeta[f.get('payment_token_id')][f.get('meta_key')] = f.get('meta_value')

        def f_usuario(f):
            c = (f.get('user_email') or '').lower().strip()
            if c:
                correo_de[f['ID']] = c

        una_pasada(ruta, {
            'wp_wc_orders': f_orden,
            'wp_wc_orders_meta': f_meta,
            'wp_woocommerce_order_items': f_item,
            'wp_woocommerce_payment_tokens': f_tok,
            'wp_woocommerce_payment_tokenmeta': f_tokmeta,
            'wp_users': f_usuario,
        })

        # Tarjetas: solo las de producción. Las de TEST son de cuando se
        # probaba el plugin y no sirven con el código de comercio real.
        tarjetas, por_usuario = [], defaultdict(list)
        for t in tokens:
            m = tokmeta[t['token_id']]
            if (m.get('environment') or '').upper() not in ('LIVE', 'PRODUCCION', 'PRODUCTION'):
                continue
            email = correo_de.get(t.get('user_id')) or (m.get('email') or '').lower().strip()
            if not email or not t.get('token') or not m.get('username'):
                continue
            tarjeta = {
                'tbk_user': t['token'], 'email': email, 'username': m['username'][:40],
                'tipo': (m.get('card_type') or '')[:30], 'ultimos4': (m.get('last4') or '')[-4:],
                'default': t.get('is_default') == '1', 'id': int(t['token_id']),
            }
            tarjetas.append(tarjeta)
            por_usuario[t.get('user_id')].append(tarjeta)

        def tarjeta_de(user_id):
            # La que WooCommerce usa para cobrar la suscripción es la
            # predeterminada del cliente; si no hay, la inscrita más nueva.
            opciones = por_usuario.get(user_id) or []
            if not opciones:
                return None
            return max(opciones, key=lambda t: (t['default'], t['id']))

        subs, omitidas = [], defaultdict(int)
        for o in ordenes:
            md = meta[o['id']]
            cada = _meses(md.get('_billing_interval'), md.get('_billing_period'))
            try:
                monto = int(float(o.get('total_amount') or 0))
            except ValueError:
                monto = 0
            proximo = _fecha_gmt(md.get('_schedule_next_payment'))
            tarjeta = tarjeta_de(o.get('customer_id'))
            email = ((o.get('billing_email') or '').lower().strip()
                     or correo_de.get(o.get('customer_id'), ''))
            if o.get('payment_method') != GATEWAY:
                omitidas['no se paga con Oneclick'] += 1
            elif not cada:
                omitidas['periodo que no es en meses ni años'] += 1
            elif monto <= 0:
                omitidas['monto $0 (Transbank no cobra $0)'] += 1
            elif proximo is None:
                omitidas['pago único con fecha de término (el WordPress no la vuelve a cobrar)'] += 1
            elif tarjeta is None:
                omitidas['sin tarjeta inscrita'] += 1
            elif not email:
                omitidas['sin correo'] += 1
            else:
                subs.append({
                    'wp_id': int(o['id']), 'email': email, 'monto': monto, 'cada_meses': cada,
                    'proximo_cobro': proximo, 'tbk_user': tarjeta['tbk_user'],
                    'nombre': ' + '.join(n for n in items[o['id']] if n),
                })

        # Una misma tarjeta puede venir repetida si WooCommerce la guardó dos
        # veces para el mismo cliente; en la base es una sola fila.
        unicas = {t['tbk_user']: t for t in tarjetas}
        return list(unicas.values()), subs, omitidas
