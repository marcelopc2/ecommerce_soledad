"""Deja los modelos casi sin pasos, para volver a cargarlos desde el panel.

Para qué sirve
--------------
La administradora está rehaciendo el contenido modelo por modelo. Los pasos que
hay son los que se importaron del WordPress viejo y hay que reemplazarlos, pero
borrarlos desde el panel es de a uno: son más de mil. Este comando vacía los que
se le indiquen y deja intactos los que ella ya actualizó.

    manage.py vaciar_pasos --excepto bienvenida taladro carrusel
    manage.py vaciar_pasos --excepto bienvenida taladro carrusel --aplicar

Deja UN paso en cada modelo, no cero. Es a pedido: borrar ese que queda desde
el panel es un clic, y evita el caso raro de un modelo sin nada adentro.

Qué se lleva por delante
------------------------
- Los pasos y SUS ARCHIVOS. Django no borra archivos al borrar la fila, así que
  se borran a mano: si no, quedan mil imágenes huérfanas ocupando disco que
  nadie va a volver a mirar.
- El avance de los alumnos SOBRE ESOS PASOS. Es inevitable -cuelga de ellos- y
  tampoco significa nada: son pasos que van a dejar de existir.

Qué NO se toca
--------------
- El `CourseProgress`, que es el "este alumno terminó este modelo". Vive aparte
  y es el que usa la cadena para decidir si abre el siguiente, así que quien ya
  había terminado un modelo sigue terminado aunque se vacíe.
- Los modelos en sí: siguen publicados, con su portada y su lugar en la fila.

Por omisión no hace nada: hay que pasarle `--aplicar`.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from lms.models import Course, CourseProgress, Lesson, LessonProgress


class Command(BaseCommand):
    help = 'Borra los pasos de los modelos, salvo los que se indiquen.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--excepto', nargs='*', default=[], metavar='TEXTO',
            help='Modelos a NO tocar. Basta un trozo del nombre, sin importar '
                 'mayúsculas: "taladro" alcanza para "Taladro y Herramientas".')
        parser.add_argument('--dejar', type=int, default=1, metavar='N',
                            help='Cuántos pasos dejar en cada modelo (por omisión 1). '
                                 'Con 0 quedan completamente vacíos.')
        parser.add_argument('--aplicar', action='store_true',
                            help='Hace el trabajo. Sin esto solo dice qué haría.')

    def handle(self, *args, **op):
        salvar = [t.strip().lower() for t in op['excepto'] if t.strip()]

        intactos, a_vaciar = [], []
        for curso in Course.objects.order_by('order', 'id'):
            destino = intactos if any(t in curso.title.lower() for t in salvar) else a_vaciar
            destino.append(curso)

        # Que un nombre escrito mal no se note recién cuando el modelo aparece
        # vacío: se avisa antes de borrar nada.
        for texto in salvar:
            if not any(texto in c.title.lower() for c in intactos):
                raise CommandError(
                    'Ningún modelo se llama algo parecido a "%s". Revisa el nombre '
                    'antes de seguir: sin esto se vaciaría uno que querías salvar.' % texto)

        if not a_vaciar:
            self.stdout.write(self.style.WARNING('No queda ningún modelo por vaciar.'))
            return

        dejar = max(0, op['dejar'])
        # Se salvan los PRIMEROS `dejar` pasos de cada modelo, no unos al azar:
        # el que queda sirve de muestra de lo que había.
        a_borrar = []
        for curso in a_vaciar:
            sobran = list(curso.lessons.order_by('order', 'id')[dejar:])
            a_borrar.extend(l.id for l in sobran)

        pasos = Lesson.objects.filter(id__in=a_borrar)
        ids = [c.id for c in a_vaciar]
        n_pasos = len(a_borrar)
        n_avance = LessonProgress.objects.filter(lesson_id__in=a_borrar).count()
        n_terminados = CourseProgress.objects.filter(course_id__in=ids).count()

        self.stdout.write(self.style.MIGRATE_HEADING('Se mantienen intactos'))
        for c in intactos:
            self.stdout.write('  %-34s %d pasos' % (c.title[:34], c.lessons.count()))

        self.stdout.write(self.style.MIGRATE_HEADING(
            chr(10) + 'Se vacían (queda%s %d paso%s en cada uno)'
            % ('n' if dejar != 1 else '', dejar, '' if dejar == 1 else 's')))
        for c in a_vaciar[:6]:
            tiene = c.lessons.count()
            self.stdout.write('  %-34s %d pasos -> %d'
                              % (c.title[:34], tiene, min(tiene, dejar)))
        if len(a_vaciar) > 6:
            self.stdout.write('  ... y %d modelos más' % (len(a_vaciar) - 6))

        self.stdout.write('\n  %d modelos, %d pasos y sus archivos' % (len(a_vaciar), n_pasos))
        self.stdout.write('  %d avances sobre esos pasos se van con ellos' % n_avance)
        self.stdout.write(self.style.SUCCESS(
            '  %d "modelo terminado" se CONSERVAN: quien ya lo hizo sigue hecho'
            % n_terminados))

        if not op['aplicar']:
            self.stdout.write(self.style.WARNING(
                '\nEnsayo: no se tocó nada. Agrega --aplicar para vaciarlos.'))
            return

        borrados_archivos = 0
        with transaction.atomic():
            # Los archivos primero y uno por uno: Django nunca borra el archivo
            # al borrar la fila, y un `delete()` masivo se lleva las filas
            # dejando las imágenes tiradas en el disco para siempre.
            for leccion in pasos.iterator():
                for campo in (leccion.image_file, leccion.pdf_file, leccion.video_file):
                    if campo:
                        campo.delete(save=False)
                        borrados_archivos += 1
            pasos.delete()

        self.stdout.write(self.style.SUCCESS(
            chr(10) + 'Listo: %d pasos y %d archivos borrados en %d modelos. '
            'A cada uno le quedó %d paso para borrar a mano antes de cargarlo '
            'de nuevo.' % (n_pasos, borrados_archivos, len(a_vaciar), dejar)))
