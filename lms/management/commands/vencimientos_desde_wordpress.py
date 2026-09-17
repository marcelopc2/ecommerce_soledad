"""Recalcula el vencimiento de cada alumno migrado con su fecha real.

El problema
-----------
El importador le daba 30 días DESDE EL DÍA DE LA IMPORTACIÓN a quien no tenía
fecha de término en PMPro. Como eso es casi la mitad de los alumnos, quedaban
todos venciendo el mismo día -el día que se corrió el comando + 30-, que no
tiene nada que ver con cuándo pagó cada uno. Y peor: cada re-importación movía
la fecha de todos otra vez.

De dónde sale la fecha buena
----------------------------
En orden de confianza, lo primero que haya para esa persona:

1. `_schedule_next_payment` de su suscripción activa de WooCommerce. Es la
   fecha exacta del próximo cobro. Solo la tienen unos pocos: el cobro va por
   Transbank Oneclick por fuera de WooCommerce, así que casi todas están en 0.

2. La fecha de su ÚLTIMO PAGO + un mes. Los tres planes de PMPro son de ciclo
   mensual, así que quien pagó el 11 vence el 11 del mes siguiente. Es la vía
   que cubre a la mayoría.

3. El `enddate` de PMPro, si lo trae. Es el caso de quien ya se dio de baja.

4. El `startdate` de su fila activa de PMPro + un mes. Último recurso, para
   quien no tiene ni un pago registrado.

Lo que NO hace
--------------
No toca a quien ya tiene una fecha que no salió de este error, ni a las
membresías que no son de la migración. Y por omisión no escribe nada.

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
            if nueva.date() != m.expires_at.date():
                cambios.append((m, nueva, origen))

        self._informar(cambios, sin_dato, op['ver'])

        if not op['aplicar']:
            self.stdout.write(self.style.WARNING(
                '\nEnsayo: no se guardó nada. Agrega --aplicar.'))
            return

        for m, nueva, _ in cambios:
            m.expires_at = nueva
        Membership.objects.bulk_update([c[0] for c in cambios], ['expires_at'],
                                       batch_size=200)
        self.stdout.write(self.style.SUCCESS(
            '\n%d vencimiento(s) corregidos.' % len(cambios)))

    # -- lectura ----------------------------------------------------------

    def _fechas_por_correo(self, ruta):
        """{correo: (fecha, de_dónde_salió)} con la mejor fuente disponible."""
        pedidos, meta_prox, correo_de, pmpro = [], {}, {}, []

        def f_pedido(f):
            pedidos.append(f)

        def f_meta(f):
            if f.get('meta_key') == '_schedule_next_payment':
                meta_prox[f.get('order_id')] = f.get('meta_value')

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

        def correo_del_pedido(o):
            return ((o.get('billing_email') or '').lower().strip()
                    or correo_de.get(o.get('customer_id'), ''))

        # 1) próximo cobro agendado, lo más confiable que hay
        prox = {}
        for o in pedidos:
            if o.get('status') != 'wc-active':
                continue
            f = _fecha(meta_prox.get(o['id']))
            c = correo_del_pedido(o)
            if f and c and (c not in prox or f > prox[c]):
                prox[c] = f

        # 2) último pago
        ultimo = {}
        for o in pedidos:
            if o.get('status') not in PAGADOS:
                continue
            f = _fecha(o.get('date_created_gmt'))
            c = correo_del_pedido(o)
            if f and c and (c not in ultimo or f > ultimo[c]):
                ultimo[c] = f

        # 3) y 4) lo que diga PMPro
        fin_pmpro, inicio_activa = {}, {}
        for r in pmpro:
            c = correo_de.get(r.get('user_id'))
            if not c:
                continue
            f = _fecha(r.get('enddate'))
            if f and (c not in fin_pmpro or f > fin_pmpro[c]):
                fin_pmpro[c] = f
            if r.get('status') == 'active':
                i = _fecha(r.get('startdate'))
                if i and (c not in inicio_activa or i > inicio_activa[c]):
                    inicio_activa[c] = i

        fechas = {}
        for c in set(prox) | set(ultimo) | set(fin_pmpro) | set(inicio_activa):
            if c in prox:
                fechas[c] = (prox[c], 'próximo cobro agendado')
            elif c in ultimo:
                fechas[c] = (ultimo[c] + PERIODO, 'último pago + 1 mes')
            elif c in fin_pmpro:
                fechas[c] = (fin_pmpro[c], 'fin en PMPro')
            else:
                fechas[c] = (inicio_activa[c] + PERIODO, 'inicio PMPro + 1 mes')
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
