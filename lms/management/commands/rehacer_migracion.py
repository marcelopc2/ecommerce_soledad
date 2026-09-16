"""Borra lo migrado y lo vuelve a traer desde un volcado más nuevo de WordPress.

Por qué existe
--------------
La migración no es un acto único: mientras el sitio viejo siga vendiendo, cada
volcado nuevo trae alumnos, renovaciones y modelos que el anterior no tenía. El
importador NO fusiona -se niega a correr si ya hay datos, porque agregar encima
deja cada modelo duplicado-, así que actualizar significa borrar y rehacer.

Y rehacer son siete pasos en orden, cada uno con su comando: bajar las fotos,
importar, cruzar los trailers, proteger los videos, traer los teléfonos, y
devolverle el acceso de gestión a quien lo tenía. Hacerlos a mano cada vez es
una invitación a saltarse uno y no notarlo hasta que una alumna reclame.

Qué se conserva
---------------
- Las cuentas de GESTIÓN, con su clave y sus permisos. Se guardan antes de
  borrar y se restauran después, porque el volcado las trae como usuarios
  normales y sin esto la clienta se quedaría fuera de su propio panel.
- La TIENDA: productos, categorías, precios, cupones, el punto de retiro. Nada
  de eso viene de WordPress.
- Las categorías de curso y los diplomas, que se configuran en el panel.

Qué se pierde, y hay que saberlo
--------------------------------
- Las correcciones hechas A MANO sobre los modelos: un título arreglado, un paso
  reordenado, una foto subida desde el panel. El volcado manda.
- Las claves que un alumno ya se haya definido: vuelve la de WordPress.
- Las fechas de vencimiento editadas a mano en el panel.

Por eso el comando saca un respaldo ANTES de tocar nada, y por omisión no hace
nada: hay que pasarle `--aplicar`.

    python manage.py rehacer_migracion --dump nuevo.sql
    python manage.py rehacer_migracion --dump nuevo.sql --aplicar
"""
import os
import shutil
import subprocess
from datetime import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from lms.models import (
    CategoryCourse, Course, CourseProgress, Lesson, LessonProgress,
    Membership, MembershipCategory,
)

User = get_user_model()

#: Dónde se guardan las fotos que se bajan del sitio viejo. Se reusa entre
#: corridas: el descargador es reanudable, así que la segunda vez solo trae lo
#: que cambió en vez de los 121 MB completos.
MEDIOS = os.environ.get('WP_MEDIOS', '/root/wp-medios')


class Command(BaseCommand):
    help = 'Rehace la migración de WordPress completa desde un volcado más nuevo.'

    def add_arguments(self, parser):
        parser.add_argument('--dump', required=True, help='Ruta al volcado .sql nuevo')
        parser.add_argument('--medios', default=MEDIOS,
                            help='Carpeta donde se guardan las fotos del sitio viejo')
        parser.add_argument('--aplicar', action='store_true',
                            help='Hace el trabajo. Sin esto solo dice qué haría.')
        parser.add_argument('--sin-respaldo', action='store_true',
                            help='No saca respaldo de la base antes de borrar. '
                                 'No usar salvo que ya tengas uno reciente.')
        parser.add_argument('--sin-fotos', action='store_true',
                            help='Salta la descarga de fotos del sitio viejo. '
                                 'Úsalo solo si la carpeta ya está completa.')

    # -- pasos ------------------------------------------------------------

    def handle(self, *args, **op):
        ruta = op['dump']
        if not os.path.exists(ruta):
            raise CommandError('No encuentro el volcado: %s' % ruta)

        self._resumen_de_lo_que_hay()

        if not op['aplicar']:
            self.stdout.write(self.style.WARNING(
                '\nEnsayo: no se tocó nada. Agrega --aplicar para rehacerla.'))
            return

        if not op['sin_respaldo']:
            self._respaldar()

        staff = self._guardar_cuentas_de_gestion()
        self._borrar_lo_migrado()

        if not op['sin_fotos']:
            self.stdout.write(self.style.MIGRATE_HEADING('\n[1/5] Bajando las fotos del sitio viejo'))
            call_command('bajar_fotos_wordpress', dump=ruta, destino=op['medios'])

        self.stdout.write(self.style.MIGRATE_HEADING('\n[2/5] Importando el volcado'))
        call_command('importar_wordpress', dump=ruta, medios=op['medios'], aplicar=True)

        self.stdout.write(self.style.MIGRATE_HEADING('\n[3/5] Cruzando los trailers de YouTube'))
        try:
            call_command('trailers_desde_youtube', aplicar=True)
        except Exception as e:
            # YouTube se lee raspando la página pública: si cambian el HTML o no
            # hay red, es lo ÚNICO de esta lista que se puede reintentar después
            # sin rehacer nada. No vale la pena abortar una migración por esto.
            self.stdout.write(self.style.ERROR(
                '  Falló y se sigue: %s\n  Reintenta después con: '
                'manage.py trailers_desde_youtube --aplicar' % e))

        self.stdout.write(self.style.MIGRATE_HEADING('\n[4/5] Protegiendo los videos subidos'))
        call_command('proteger_videos', aplicar=True, borrar_original=True)

        self.stdout.write(self.style.MIGRATE_HEADING('\n[5/5] Trayendo los teléfonos'))
        call_command('telefonos_desde_wordpress', ruta, aplicar=True)

        self._restaurar_cuentas_de_gestion(staff)
        self._resumen_final()

    # -- utilidades -------------------------------------------------------

    def _resumen_de_lo_que_hay(self):
        self.stdout.write(self.style.MIGRATE_HEADING('Lo que hay hoy y se va a rehacer'))
        self.stdout.write('  %4d modelos (%d con trailer)'
                          % (Course.objects.count(),
                             Course.objects.exclude(trailer_url='').count()))
        self.stdout.write('  %4d pasos' % Lesson.objects.count())
        self.stdout.write('  %4d alumnos (%d con teléfono)'
                          % (Membership.objects.count(),
                             Membership.objects.exclude(phone='').count()))
        self.stdout.write('  %4d avances de curso, %d de paso'
                          % (CourseProgress.objects.count(), LessonProgress.objects.count()))
        staff = User.objects.filter(is_staff=True)
        self.stdout.write(self.style.SUCCESS(
            '\n  Se CONSERVAN %d cuenta(s) de gestión: %s'
            % (staff.count(), ', '.join(u.username for u in staff))))
        self.stdout.write('  Se conserva la tienda (productos, cupones, retiro) y los diplomas.')
        self.stdout.write(self.style.WARNING(
            '  Se PIERDEN las correcciones hechas a mano sobre los modelos, '
            'las claves que los alumnos ya se definieron y los vencimientos '
            'editados en el panel.'))

    def _respaldar(self):
        """Copia la base antes de borrar. Es la única vuelta atrás que hay."""
        db = settings.DATABASES['default']
        sello = datetime.now().strftime('%Y%m%d_%H%M')
        motor = db['ENGINE']

        if 'sqlite' in motor:
            destino = '%s.respaldo_%s' % (db['NAME'], sello)
            shutil.copy2(db['NAME'], destino)
        elif 'postgres' in motor:
            destino = '/root/respaldo_antes_reimport_%s.sql' % sello
            with open(destino, 'wb') as f:
                subprocess.run(
                    ['pg_dump', '-U', db['USER'], '-h', db.get('HOST') or 'localhost',
                     db['NAME']],
                    stdout=f, check=True,
                    env={**os.environ, 'PGPASSWORD': db.get('PASSWORD', '')},
                )
        else:
            raise CommandError(
                'No sé respaldar el motor %s. Saca el respaldo a mano y corre '
                'de nuevo con --sin-respaldo.' % motor)

        self.stdout.write(self.style.SUCCESS('\nRespaldo guardado en %s' % destino))

    def _guardar_cuentas_de_gestion(self):
        """Se lleva las cuentas de staff a la mano antes del borrado.

        El volcado trae a esas mismas personas como usuarios normales, así que
        si no se restauran después, la clienta entra a su panel y no puede: su
        cuenta existe, pero sin permisos y con la clave vieja de WordPress.
        """
        staff = list(User.objects.filter(is_staff=True).values(
            'username', 'email', 'password', 'is_staff', 'is_superuser',
            'first_name', 'last_name',
        ))
        self.stdout.write('\nGuardadas %d cuenta(s) de gestión para restaurarlas después.'
                          % len(staff))
        return staff

    def _borrar_lo_migrado(self):
        """Borra el contenido y los alumnos, no la tienda.

        El orden importa: primero el progreso, que apunta a los cursos, y al
        final los usuarios. Al revés, las llaves foráneas lo impiden.
        """
        self.stdout.write(self.style.MIGRATE_HEADING('\nBorrando lo migrado'))
        with transaction.atomic():
            LessonProgress.objects.all().delete()
            CourseProgress.objects.all().delete()
            MembershipCategory.objects.all().delete()

            # Los archivos de cada paso viven en protected_media/ y NO se van
            # solos al borrar la fila: Django nunca borra archivos. Sin esto,
            # cada re-importación dejaba otra copia completa de las 1.277 fotos.
            for leccion in Lesson.objects.all().iterator():
                for campo in (leccion.image_file, leccion.pdf_file, leccion.video_file):
                    if campo:
                        campo.delete(save=False)
            Lesson.objects.all().delete()

            CategoryCourse.objects.all().delete()
            for curso in Course.objects.all().iterator():
                if curso.image_file:
                    curso.image_file.delete(save=False)
            Course.objects.all().delete()

            # Las membresías se van con su usuario (CASCADE), pero se borran
            # explícito para que el conteo del resumen sea honesto.
            Membership.objects.all().delete()
            borrados, _ = User.objects.filter(is_staff=False, is_superuser=False).delete()

        self.stdout.write('  listo (%d filas de usuario y lo que colgaba de ellas)' % borrados)

    def _restaurar_cuentas_de_gestion(self, staff):
        """Devuelve los permisos y la clave a quien administra.

        update_or_create y no create: el volcado ya las recreó como usuarios
        normales, así que lo que hay que hacer es pisarles los permisos y la
        clave, no duplicar la cuenta.
        """
        for datos in staff:
            User.objects.update_or_create(
                username=datos['username'],
                defaults={k: v for k, v in datos.items() if k != 'username'},
            )
        self.stdout.write(self.style.SUCCESS(
            '\nRestauradas %d cuenta(s) de gestión.' % len(staff)))

    def _resumen_final(self):
        self.stdout.write(self.style.MIGRATE_HEADING('\nComo quedó'))
        self.stdout.write('  %4d modelos (%d con trailer, %d en portada)'
                          % (Course.objects.count(),
                             Course.objects.exclude(trailer_url='').count(),
                             Course.objects.filter(mostrar_en_portada=True).count()))
        self.stdout.write('  %4d pasos' % Lesson.objects.count())
        self.stdout.write('  %4d alumnos (%d con teléfono)'
                          % (Membership.objects.count(),
                             Membership.objects.exclude(phone='').count()))
        self.stdout.write('  %4d avances de curso, %d de paso'
                          % (CourseProgress.objects.count(), LessonProgress.objects.count()))
        self.stdout.write('  %4d cuentas de gestión'
                          % User.objects.filter(is_staff=True).count())
