"""Resumen del día por Telegram para quien mantiene el sitio.

    0 21 * * * cd /srv/ingenioblocks && venv/bin/python manage.py resumen_diario

Ventas, mensajes, lo que quedó pendiente, lo que se cobra mañana y si las
tareas automáticas corrieron bien. Si una noche no llega, también es una señal:
el servidor o el cron no están funcionando.

--probar  manda un mensaje corto para comprobar que Telegram está bien configurado.
--ver     muestra el resumen acá en vez de mandarlo.
"""
import os
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.alertas import avisar, clp, configurado


def ok(bien, texto):
    return f'{"✅" if bien else "⚠️"} {texto}'


class Command(BaseCommand):
    help = 'Manda por Telegram el resumen del día (ventas, pendientes y chequeos).'

    def add_arguments(self, parser):
        parser.add_argument('--probar', action='store_true')
        parser.add_argument('--ver', action='store_true')

    def handle(self, *args, **op):
        if op['probar']:
            if not configurado():
                self.stdout.write('Falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en el .env.')
                return
            salio = avisar('👋 Las alertas de ingenioblocks.com quedaron funcionando.')
            self.stdout.write('Mensaje enviado.' if salio else 'Telegram no aceptó el mensaje: revisar clave y chat.')
            return

        partes = []
        for seccion in (self._ventas, self._clientes, self._pendientes, self._manana, self._chequeos):
            try:
                partes.append(seccion())
            except Exception as e:   # una sección que falla no puede tumbar el resumen
                partes.append(f'⚠️ No se pudo armar una parte del resumen ({type(e).__name__}).')
        texto = f'📊 Resumen {timezone.localdate():%d-%m} · ingenioblocks.com\n\n' + '\n\n'.join(p for p in partes if p)

        if op['ver'] or not configurado():
            self.stdout.write(texto)
        else:
            avisar(texto)
            self.stdout.write('Resumen enviado.')

    # ------------------------------------------------------------------
    def _hoy(self):
        return timezone.localdate()

    def _ventas(self):
        from payments.models import Order
        hoy = Order.objects.filter(created_at__date=self._hoy())
        pagadas = list(hoy.filter(status='PAID').prefetch_related('items'))
        lineas = [f'💰 Ventas: {len(pagadas)} · {clp(sum(o.total_amount for o in pagadas))}']
        detalle = Counter()
        for o in pagadas:
            tipo = 'cobro automático' if o.suscripcion_id else (o.get_pasarela_display() or 'sin dato')
            for item in o.items.all():
                detalle[f'{item.name} ({tipo})'] += item.quantity
        lineas += [f'  • {n}× {nombre}' for nombre, n in detalle.most_common()]
        fallidas = hoy.filter(status='FAILED').count()
        if fallidas:
            lineas.append(f'  Pagos rechazados o abandonados: {fallidas}')
        return '\n'.join(lineas)

    def _clientes(self):
        from catalog.models import MensajeContacto
        from lms.models import Membership
        nuevos = Membership.objects.filter(created_at__date=self._hoy()).count()
        mensajes = MensajeContacto.objects.filter(creado__date=self._hoy(), es_spam=False).count()
        sin_leer = MensajeContacto.objects.filter(leido=False, es_spam=False).count()
        return (f'👨‍👩‍👧 Alumnos nuevos: {nuevos}\n'
                f'💬 Mensajes de hoy: {mensajes} (sin leer en total: {sin_leer})')

    def _pendientes(self):
        from django.db.models import Q
        from payments.models import Order, Suscripcion
        sin_boleta = Order.objects.filter(Q(status='PAID') & (
            Q(invoice__isnull=True) | Q(invoice__status__in=['PENDING', 'ERROR']))).count()
        por_despachar = Order.objects.filter(
            status='PAID', shipment__status__in=['PENDING_DISPATCH', 'ERROR']).count()
        revisar = Order.objects.filter(status='REVIEW').count()
        suspendidas = Suscripcion.objects.filter(estado=Suscripcion.SUSPENDIDA).count()
        con_rechazo = Suscripcion.objects.filter(estado=Suscripcion.ACTIVA, intentos_fallidos__gt=0).count()
        lineas = ['📋 Pendientes']
        lineas.append(ok(not por_despachar, f'Pedidos por despachar: {por_despachar}'))
        lineas.append(ok(not sin_boleta, f'Boletas sin emitir: {sin_boleta}'))
        lineas.append(ok(not revisar, f'Pagos por revisar a mano: {revisar}'))
        lineas.append(ok(not (suspendidas or con_rechazo),
                         f'Suscripciones con cobro rechazado: {con_rechazo} · suspendidas: {suspendidas}'))
        return '\n'.join(lineas)

    def _manana(self):
        from payments.models import Suscripcion
        manana = self._hoy() + timedelta(days=1)
        subs = list(Suscripcion.objects.filter(estado=Suscripcion.ACTIVA, pasarela=Suscripcion.ONECLICK,
                                               proximo_cobro=manana))
        if not subs:
            return '🗓️ Mañana no hay cobros automáticos.'
        lineas = [f'🗓️ Mañana a las 10:00 se cobra: {clp(sum(s.monto for s in subs))}']
        lineas += [f'  • {s.email} · {clp(s.monto)}' for s in subs]
        return '\n'.join(lineas)

    def _servidor(self):
        """Si el sistema pide reinicio y cuántas actualizaciones tiene pendientes.

        Las de seguridad se instalan solas (unattended-upgrades), pero algunas
        (el núcleo del sistema) recién valen después de reiniciar: eso es lo
        que hay que hacer a mano, de madrugada.
        """
        import subprocess
        lineas = []
        aviso = Path('/var/run/reboot-required')
        if aviso.exists():
            desde = datetime.fromtimestamp(aviso.stat().st_mtime)
            lineas.append(ok(False, f'El servidor pide reiniciar desde el {desde:%d-%m} '
                                    '(actualizaciones ya instaladas que necesitan reinicio)'))
        try:
            r = subprocess.run(['/usr/lib/update-notifier/apt-check'], capture_output=True,
                               text=True, timeout=60)
            normales, seguridad = (int(x) for x in r.stderr.strip().split(';')[:2])
            lineas.append(ok(not seguridad, f'Actualizaciones del sistema: {normales} pendientes, '
                                            f'{seguridad} de seguridad'))
        except Exception:
            pass   # en el computador local no existe: no se informa
        return lineas

    def _chequeos(self):
        from comunicaciones.freno import correos_a_clientes
        from payments.models import AjustesCobros
        hoy = self._hoy()
        logs = Path(settings.LOG_DIR)
        lineas = ['🔧 Chequeos']

        respaldos = Path(os.environ.get('RESPALDOS_DIR', '/srv/respaldos'))
        hechos = sorted(respaldos.glob(f'base-{hoy:%Y%m%d}*')) if respaldos.exists() else []
        lineas.append(ok(bool(hechos), 'Respaldo de hoy' if hechos else 'No se encontró el respaldo de hoy'))

        for archivo, nombre in (('avisos.log', 'Avisos de modelo nuevo (9:00)'),
                                ('cobros.log', 'Cobros y Mercado Pago (10:00 y 11:00)')):
            ruta = logs / archivo
            corrio = ruta.exists() and datetime.fromtimestamp(ruta.stat().st_mtime).date() == hoy
            fallo = False
            if corrio:
                cola = ruta.read_text(encoding='utf-8', errors='ignore').splitlines()[-60:]
                fallo = any('Traceback' in linea for linea in cola)
            lineas.append(ok(corrio and not fallo, f'{nombre}: '
                             + ('falló, revisar' if fallo else 'corrió' if corrio else 'no corrió hoy')))

        errores_correo = 0
        pagos = logs / 'pagos.log'
        if pagos.exists():
            prefijo = f'{hoy:%Y-%m-%d}'
            errores_correo = sum(1 for linea in pagos.read_text(encoding='utf-8', errors='ignore').splitlines()
                                 if linea.startswith(prefijo) and 'CORREO NO SALIÓ' in linea)
        salen = correos_a_clientes()
        lineas.append(ok(salen and not errores_correo,
                         ('Correos a clientes: saliendo' if salen else 'Correos a clientes: EN PAUSA')
                         + (f' · {errores_correo} no salieron hoy' if errores_correo else '')))

        a = AjustesCobros.obtener()
        prendidos = settings.COBROS_AUTOMATICOS and a.cobros_automaticos
        lineas.append(ok(prendidos, 'Cobros automáticos: prendidos' if prendidos else 'Cobros automáticos: APAGADOS'))

        lineas += self._servidor()

        try:
            from comunicaciones.management.commands.vigilar_sitio import dias_de_certificado, revisar_disco
            dias = dias_de_certificado()
            lineas.append(ok(dias >= 20, f'Certificado: {dias} días'))
            disco = revisar_disco()
            lineas.append(ok(not disco, disco or 'Disco con espacio'))
        except Exception:
            pass
        return '\n'.join(lineas)
