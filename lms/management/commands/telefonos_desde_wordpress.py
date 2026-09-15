"""Rellena el teléfono de los alumnos migrados, leyéndolo del volcado de WordPress.

El campo `Membership.phone` nació vacío para los 286 alumnos que venían de la
migración: se creó una migración que lo rellenaba desde las órdenes, pero en la
base no hay ninguna -esos alumnos se importaron directo, sin pasar por el
checkout-. El dato sí existe, pero en el volcado de WordPress.

Se cruza por correo, que es la única llave que compartimos con la base vieja.

Por omisión NO escribe: muestra qué haría. Con `--aplicar` guarda.

    python manage.py telefonos_desde_wordpress localhost.sql
    python manage.py telefonos_desde_wordpress localhost.sql --aplicar
"""
import re

from django.core.management.base import BaseCommand, CommandError

from lms.models import Membership

from ._wp_dump import una_pasada

#: De dónde sale el número, en orden de preferencia. `billing_phone` es el de
#: WooCommerce y el que más cobertura tiene; `pmpro_bphone` es el de la
#: membresía y suele traer lo mismo; el de envío es el último recurso porque
#: puede ser el de quien recibe el paquete y no el de la familia.
CLAVES = ['billing_phone', 'pmpro_bphone', 'shipping_phone']


def normalizar(crudo):
    """Deja el número como lo guarda el checkout, si es chileno reconocible.

    Devuelve (numero, es_chileno). Lo que no se reconoce se devuelve limpio pero
    tal cual: un número extranjero o con una anotación al lado es mejor guardarlo
    feo que perderlo, y la administradora lo puede corregir a mano.
    """
    crudo = ' '.join((crudo or '').split())
    if not crudo:
        return '', False

    digitos = re.sub(r'\D', '', crudo)
    if digitos.startswith('56') and len(digitos) == 11:
        digitos = digitos[2:]

    # Chile: 9 dígitos. Los móviles parten en 9 y los fijos entre 2 y 8; nada
    # empieza en 0 ni en 1, así que eso descarta la basura tipo "123456789".
    if len(digitos) == 9 and digitos[0] in '23456789':
        return '+56' + digitos, True
    return crudo, False


class Command(BaseCommand):
    help = 'Rellena el teléfono de los alumnos migrados desde el volcado de WordPress.'

    def add_arguments(self, parser):
        parser.add_argument('volcado', help='Ruta al archivo .sql')
        parser.add_argument('--aplicar', action='store_true',
                            help='Guarda. Sin esto solo muestra qué haría.')
        parser.add_argument('--pisar', action='store_true',
                            help='También cambia los que YA tienen teléfono. '
                                 'Por omisión no, para no deshacer correcciones '
                                 'hechas a mano en el panel.')

    def handle(self, *args, **op):
        ruta = op['volcado']

        correo_de = {}        # user_id -> correo
        telefonos = {}        # user_id -> {clave: valor}

        def usuario(f):
            correo = (f.get('user_email') or '').lower().strip()
            if correo:
                correo_de[f['ID']] = correo

        def meta(f):
            if f.get('meta_key') in CLAVES and (f.get('meta_value') or '').strip():
                telefonos.setdefault(f['user_id'], {})[f['meta_key']] = f['meta_value']

        self.stdout.write('Leyendo el volcado (una sola pasada)...')
        una_pasada(ruta, {'wp_users': usuario, 'wp_usermeta': meta})
        self.stdout.write('  %d usuarios, %d con algún teléfono'
                          % (len(correo_de), len(telefonos)))

        # correo -> número, eligiendo la primera clave disponible.
        por_correo = {}
        for user_id, claves in telefonos.items():
            correo = correo_de.get(user_id)
            if not correo:
                continue
            for clave in CLAVES:
                if claves.get(clave):
                    por_correo[correo] = claves[clave]
                    break

        pendientes = Membership.objects.select_related('user')
        if not op['pisar']:
            pendientes = pendientes.filter(phone='')

        calzados, chilenos, raros, sin_dato = [], 0, [], 0
        for m in pendientes:
            correo = (m.user.email or m.user.username or '').lower().strip()
            crudo = por_correo.get(correo)
            if not crudo:
                sin_dato += 1
                continue
            numero, es_chileno = normalizar(crudo)
            if not numero:
                sin_dato += 1
                continue
            calzados.append((m, numero))
            if es_chileno:
                chilenos += 1
            else:
                raros.append((correo, crudo))

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING(
            'Alumnos a los que se les puede poner el teléfono: %d' % len(calzados)))
        self.stdout.write('  %d con número chileno reconocido' % chilenos)
        self.stdout.write('  %d se guardan tal cual (extranjero o formato raro)' % len(raros))
        self.stdout.write('  %d sin teléfono en el volcado' % sin_dato)

        for correo, crudo in raros[:10]:
            self.stdout.write(self.style.WARNING('    %-38s %r' % (correo[:38], crudo)))
        if len(raros) > 10:
            self.stdout.write('    ... y %d más' % (len(raros) - 10))

        if not op['aplicar']:
            self.stdout.write(self.style.WARNING(
                '\nEnsayo: no se guardó nada. Agrega --aplicar.'))
            return

        for m, numero in calzados:
            m.phone = numero
        Membership.objects.bulk_update([m for m, _ in calzados], ['phone'], batch_size=200)
        self.stdout.write(self.style.SUCCESS(
            '\n%d teléfono(s) guardados.' % len(calzados)))
