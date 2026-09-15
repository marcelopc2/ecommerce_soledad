"""Mueve los videos subidos de `media/` (público) a `protected_media/`.

Los videos de las lecciones se importaron desde WordPress como archivos sueltos
en `media/lesson_videos/`, y su URL absoluta quedó guardada en
`Lesson.video_embed_url`. Esa carpeta la sirve nginx como estático: cualquiera
con el link se bajaba el video sin pagar ni iniciar sesión.

Este comando los pasa al campo `video_file`, que vive en protected_media/ y solo
sale por el endpoint con permisos (membresía activa + curso otorgado + curso
desbloqueado), igual que los PDF y las imágenes.

De paso arregla un problema que iba a aparecer solo: esas URLs son absolutas y
apuntan al dominio actual, así que al cambiar el DNS los videos se habrían roto
todos sin que nadie se enterara hasta que un alumno reclamara.

Por omisión NO escribe: muestra qué haría. Con `--aplicar` mueve de verdad.

    python manage.py proteger_videos
    python manage.py proteger_videos --aplicar
"""
import os
import shutil
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand

from lms.models import Lesson


class Command(BaseCommand):
    help = 'Pasa los videos de media/ (público) a protected_media/ (con permisos).'

    def add_arguments(self, parser):
        parser.add_argument('--aplicar', action='store_true',
                            help='Mueve los archivos. Sin esto solo muestra qué haría.')
        parser.add_argument('--borrar-original', action='store_true',
                            help='Borra el archivo público después de copiarlo. '
                                 'Sin esto queda la copia vieja, que SIGUE siendo '
                                 'descargable: usarlo una vez comprobado que se ven.')

    def handle(self, *args, **op):
        # Solo los que apuntan a nuestro propio /media/: un embed de YouTube no
        # es un archivo nuestro y no hay nada que mover.
        pendientes = []
        for lesson in Lesson.objects.exclude(video_embed_url=''):
            ruta = urlparse(lesson.video_embed_url).path
            if '/media/lesson_videos/' not in ruta:
                continue
            nombre = os.path.basename(ruta)
            origen = os.path.join(settings.MEDIA_ROOT, 'lesson_videos', nombre)
            pendientes.append((lesson, nombre, origen))

        if not pendientes:
            # Nada que mover no significa nada que hacer: puede quedar la copia
            # publica de un movimiento anterior, que sigue siendo descargable.
            self.stdout.write(
                'Ninguna leccion apunta a media/: no hay videos que mover.')
            return self._limpiar_sobrantes(op)

        self.stdout.write(self.style.MIGRATE_HEADING(
            'Videos a proteger (%d)' % len(pendientes)))
        faltantes = []
        for lesson, nombre, origen in pendientes:
            existe = os.path.exists(origen)
            if not existe:
                faltantes.append(nombre)
            self.stdout.write('  %-28s %-32s %s' % (
                lesson.course.title[:28], nombre[:32],
                '' if existe else self.style.ERROR('NO ESTÁ EL ARCHIVO')))

        if faltantes:
            self.stdout.write(self.style.WARNING(
                '\n%d archivo(s) no están en disco. Esos se saltan.' % len(faltantes)))

        if not op['aplicar']:
            self.stdout.write(self.style.WARNING(
                '\nEnsayo: no se movió nada. Agrega --aplicar.'))
            return

        destino_dir = os.path.join(settings.PROTECTED_MEDIA_ROOT, 'lesson_videos')
        os.makedirs(destino_dir, exist_ok=True)

        movidos = 0
        for lesson, nombre, origen in pendientes:
            if not os.path.exists(origen):
                continue
            destino = os.path.join(destino_dir, nombre)
            # copy2 y no move: si algo falla a mitad de camino, el original
            # sigue ahí y el alumno no se queda sin ver el video. El borrado del
            # público es un paso aparte y explícito.
            shutil.copy2(origen, destino)

            lesson.video_file.name = 'lesson_videos/%s' % nombre
            # Se vacía la URL vieja: si quedara, el Aula seguiría prefiriendo…
            # bueno, no la prefiere (el archivo gana), pero dejarla es dejar
            # publicado el link que justamente se quiere sacar de circulación.
            lesson.video_embed_url = ''
            lesson.save(update_fields=['video_file', 'video_embed_url'])
            movidos += 1

            if op['borrar_original']:
                os.remove(origen)

        self.stdout.write(self.style.SUCCESS('\n%d video(s) protegidos.' % movidos))
        if not op['borrar_original']:
            self.stdout.write(self.style.WARNING(
                'La copia pública sigue en media/lesson_videos/ y TODAVÍA se puede '
                'descargar. Comprueba que los videos se ven en el Aula y después '
                'vuelve a correr el comando con --borrar-original.'))

    def _limpiar_sobrantes(self, op):
        """Borra las copias públicas que ya tienen su gemela protegida.

        Hace falta porque el borrado del original es un paso APARTE del
        movimiento -a propósito: primero se comprueba que los videos se ven, y
        recién después se borra-. Pero en la segunda pasada ya no queda ninguna
        lección apuntando a media/, así que sin esto el comando decía "no hay
        nada que hacer" y los archivos públicos se quedaban ahí para siempre.

        Solo borra si el archivo protegido existe y pesa EXACTAMENTE lo mismo:
        ante cualquier diferencia se deja y se informa, porque un video perdido
        no se recupera.
        """
        publico_dir = os.path.join(settings.MEDIA_ROOT, 'lesson_videos')
        protegido_dir = os.path.join(settings.PROTECTED_MEDIA_ROOT, 'lesson_videos')
        if not os.path.isdir(publico_dir):
            return

        sobrantes, dudosos = [], []
        for nombre in sorted(os.listdir(publico_dir)):
            publico = os.path.join(publico_dir, nombre)
            protegido = os.path.join(protegido_dir, nombre)
            if not os.path.isfile(publico):
                continue
            if (os.path.exists(protegido)
                    and os.path.getsize(protegido) == os.path.getsize(publico)):
                sobrantes.append((nombre, publico))
            else:
                dudosos.append(nombre)

        if dudosos:
            self.stdout.write(self.style.WARNING(
                'Sin copia protegida equivalente, NO se tocan (%d):' % len(dudosos)))
            for nombre in dudosos:
                self.stdout.write('  %s' % nombre)

        if not sobrantes:
            self.stdout.write(self.style.SUCCESS(
                'No quedan copias públicas de videos.'))
            return

        self.stdout.write(self.style.MIGRATE_HEADING(
            'Copias públicas que ya están protegidas (%d)' % len(sobrantes)))
        for nombre, _ in sobrantes:
            self.stdout.write('  media/lesson_videos/%s' % nombre)

        if not (op['aplicar'] and op['borrar_original']):
            self.stdout.write(self.style.WARNING(
                'Siguen siendo descargables por cualquiera. '
                'Para borrarlas: --aplicar --borrar-original'))
            return

        for nombre, publico in sobrantes:
            os.remove(publico)
        self.stdout.write(self.style.SUCCESS(
            '%d copia(s) publica(s) borrada(s).' % len(sobrantes)))
