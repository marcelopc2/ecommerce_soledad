"""Pone en cada alumno migrado la fecha de término que traía el sistema viejo.

De dónde sale
-------------
De `_schedule_end` de su suscripción de WooCommerce. Es la fecha que el sitio
viejo calculaba solo al comprar y es la que ve la clienta en su panel. La traen
378 de las 387 suscripciones.

Por qué costó encontrarla
-------------------------
No está donde uno la buscaría. PMPro -que es el sistema de membresías- deja la
fila activa con `enddate = 0000-00-00`, o sea "no vence". Y
`_schedule_next_payment`, que sería lo natural de mirar en una suscripción,
está en 0 para casi todas, porque el cobro recurrente va por Transbank Oneclick
por fuera de WooCommerce. La fecha buena estaba en el tercer lugar.

Orden de preferencia
--------------------
1. `_schedule_end` de la suscripción; si tiene varias, la más lejana.
2. El `enddate` de PMPro, que es lo que trae quien ya se dio de baja.
3. Si no hay ninguna de las dos, se deja "sin vencimiento" y no se inventa nada.

    python manage.py vencimientos_desde_wordpress --dump volcado.sql
    python manage.py vencimientos_desde_wordpress --dump volcado.sql --aplicar
"""
from datetime import datetime

from dateutil.relativedelta import relativedelta
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from lms.models import Membership

from ._wp_dump import una_pasada

#: Estados de pedido de WooCommerce que significan "esta persona pagó". Se
#: incluye `wc-delivered` porque la tienda usa ese estado para lo ya despachado,
#: que obviamente se pagó antes.
PAGADOS = ('wc-completed', 'wc-processing', 'wc-delivered')

#: Los tres planes (Individual, Full, Institucional) son de ciclo mensual, así
#: que el período es el mismo para todos y no hace falta mirar el nivel.
PERIODO = relativedelta(months=1)


def _fecha(valor):
    """Convierte una fecha de MySQL a datetime, o None si viene vacía.

    MySQL escribe '0000-00-00 00:00:00' para "sin fecha", que no es una fecha
    válida y revienta cualquier parser: se trata como ausente.
    """
    if not valor or str(valor).startswith('0000'):
        return None
    for formato in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return timezone.make_aware(datetime.strptime(str(valor)[:19], formato))
        except (ValueError, TypeError):
            continue
    return None


class Command(BaseCommand):
    help = 'Recalcula el vencimiento de los alumnos migrados con su fecha real.'

    def add_arguments(self, parser):
        parser.add_argument('--dump', required=True, help='Ruta al volcado .sql')
        parser.add_argument('--aplicar', action='store_true',
                            help='Guarda. Sin esto solo muestra qué cambiaría.')
        parser.add_argument('--ver', type=int, default=15,
                            help='Cuántos ejemplos mostrar (por omisión 15).')

    def handle(self, *args, **op):
        if not __import__('os').path.exists(op['dump']):
            raise CommandError('No encuentro el volcado: %s' % op['dump'])

        self.stdout.write('Leyendo el volcado...')
        fechas = self._fechas_por_correo(op['dump'])
        self.stdout.write('  %d correos con alguna fecha utilizable' % len(fechas))

        cambios, sin_dato = [], []
        for m in Membership.objects.select_related('user'):
            correo = (m.user.email or m.user.username or '').lower().strip()
            nueva, origen = fechas.get(correo, (None, ''))
            if nueva is None:
                sin_dato.append(m)
                continue
            # Cuenta como cambio también si solo deja de estar abierta: la
            # fecha puede coincidir por casualidad y el estado igual cambia.
            if nueva.date() != m.expires_at.date() or m.sin_vencimiento:
                cambios.append((m, nueva, origen))

        self._informar(cambios, sin_dato, op['ver'])

        if not op['aplicar']:
            self.stdout.write(self.style.WARNING(
                '\nEnsayo: no se guardó nada. Agrega --aplicar.'))
            return

        for m, nueva, _ in cambios:
            m.expires_at = nueva
            # Tener fecha de término es justamente lo contrario de "abierta".
            m.sin_vencimiento = False
        Membership.objects.bulk_update(
            [c[0] for c in cambios], ['expires_at', 'sin_vencimiento'], batch_size=200)
        self.stdout.write(self.style.SUCCESS(
            '\n%d vencimiento(s) corregidos.' % len(cambios)))

    # -- lectura ----------------------------------------------------------

    def _fechas_por_correo(self, ruta):
        """{correo: (fecha, de_dónde_salió)} con la mejor fuente disponible."""
        pedidos, fin_sub, correo_de, pmpro = [], {}, {}, []

        def f_pedido(f):
            pedidos.append(f)

        def f_meta(f):
            if f.get('meta_key') == '_schedule_end':
                fin_sub[f.get('order_id')] = f.get('meta_value')

        def f_usuario(f):
            c = (f.get('user_email') or '').lower().strip()
            if c:
                correo_de[f['ID']] = c

        def f_pmpro(f):
            pmpro.append(f)

        una_pasada(ruta, {
            'wp_wc_orders': f_pedido,
            'wp_wc_orders_meta': f_meta,
            'wp_users': f_usuario,
            'wp_pmpro_memberships_users': f_pmpro,
        })

        # 1) el término que puso el sitio viejo al comprar
        por_sub = {}
        for o in pedidos:
            if o.get('type') != 'shop_subscription':
                continue
            f = _fecha(fin_sub.get(o['id']))
            if not f:
                continue
            c = ((o.get('billing_email') or '').lower().strip()
                 or correo_de.get(o.get('customer_id'), ''))
            # La más lejana: quien renovó tiene varias suscripciones y la que
            # manda es la última, no la primera.
            if c and (c not in por_sub or f > por_sub[c]):
                por_sub[c] = f

        # 2) lo que declare PMPro, para quien ya se dio de baja
        fin_pmpro = {}
        for r in pmpro:
            c = correo_de.get(r.get('user_id'))
            f = _fecha(r.get('enddate'))
            if c and f and (c not in fin_pmpro or f > fin_pmpro[c]):
                fin_pmpro[c] = f

        fechas = {}
        for c in set(por_sub) | set(fin_pmpro):
            if c in por_sub:
                fechas[c] = (por_sub[c], 'término de la suscripción')
            else:
                fechas[c] = (fin_pmpro[c], 'fin en PMPro')
        return fechas

    # -- informe ----------------------------------------------------------

    def _informar(self, cambios, sin_dato, cuantos):
        ahora = timezone.now()
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING(
            'Vencimientos que cambiarían: %d' % len(cambios)))

        por_origen = {}
        for _m, _f, origen in cambios:
            por_origen[origen] = por_origen.get(origen, 0) + 1
        for origen, n in sorted(por_origen.items(), key=lambda x: -x[1]):
            self.stdout.write('   %-26s %d' % (origen, n))

        # Lo que de verdad importa revisar: a quién le cambia el ESTADO. Que una
        # fecha se corra unos días no le cambia la vida a nadie; que alguien
        # pase de vigente a vencido sí, porque deja de poder entrar.
        se_vencen = [c for c in cambios if c[0].expires_at > ahora >= c[1]]
        reviven = [c for c in cambios if c[0].expires_at <= ahora < c[1]]
        self.stdout.write('')
        self.stdout.write('   pasan de VIGENTE a VENCIDA: %s'
                          % self.style.WARNING(str(len(se_vencen))))
        self.stdout.write('   pasan de VENCIDA a VIGENTE: %d' % len(reviven))
        self.stdout.write('   se quedan sin dato en el volcado: %d' % len(sin_dato))

        self.stdout.write('')
        self.stdout.write('   %-34s %-12s %-12s %s'
                          % ('alumno', 'ahora dice', 'deberia ser', 'de donde sale'))
        for m, nueva, origen in cambios[:cuantos]:
            self.stdout.write('   %-34s %-12s %-12s %s' % (
                (m.user.email or m.user.username)[:34],
                m.expires_at.date().isoformat(),
                nueva.date().isoformat(),
                origen))
        if len(cambios) > cuantos:
            self.stdout.write('   ... y %d más' % (len(cambios) - cuantos))
