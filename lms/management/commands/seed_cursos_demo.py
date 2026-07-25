"""
Crea un año de contenido de prueba en el Aula Virtual para poder ver cómo se
comporta con volumen: varios modelos, diplomas intercalados y un alumno con
avance real (unos completados, uno a medias y el resto esperando el goteo).

    python manage.py seed_cursos_demo            # crea el contenido
    python manage.py seed_cursos_demo --limpiar  # lo borra y sale

Solo corre con DEBUG=True: no es contenido real y no debe tocar producción.
"""
import struct
import zlib
from datetime import timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from catalog.models import Product
from lms.models import Course, Lesson, Diploma, Membership
from lms.services import mark_lesson_completed

PREFIJO = 'demo-'   # marca los cursos creados acá, para poder limpiarlos después

# (título, descripción, cuántos recursos)
MODELOS = [
    ('Taladro y Herramientas', 'Aprende cómo una correa transmite la energía del motor y arma tu primer taladro.', 4),
    ('Caleidoscopio', 'Descubre cómo los espejos multiplican las figuras y crea combinaciones de colores.', 3),
    ('Centrífuga de Ropa', 'Descubre cómo el giro rápido saca el agua de la ropa y arma tu propia centrífuga.', 4),
    ('Grúa Torre', 'Poleas y contrapesos: levanta cargas pesadas con muy poca fuerza.', 5),
    ('Ventilador de Mesa', 'Cómo las aspas mueven el aire, y por qué su inclinación importa.', 3),
    ('Carrusel', 'Engranajes que cambian la velocidad de giro para que el carrusel gire parejo.', 4),
    ('Molino de Viento', 'Transformar el movimiento del aire en energía para mover otras piezas.', 3),
    ('Robot Explorador', 'Tu primer vehículo motorizado: tracción, dirección y equilibrio.', 5),
]

# Diplomas intercalados: se ganan al completar todo lo anterior.
DIPLOMAS = [
    (4, 'Diploma Constructor Inicial', '¡Completaste tus primeros 4 modelos! Ya dominas correas, espejos y poleas.'),
    (9, 'Diploma Constructor Avanzado', '¡Terminaste los 8 modelos! Ya eres un constructor Ingenio Blocks.'),
]


def _png(rgb):
    """PNG de un color sólido, sin depender de Pillow (no es dependencia del proyecto)."""
    def chunk(tag, data):
        return (struct.pack('>I', len(data)) + tag + data
                + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff))

    w = h = 160
    sig = b'\x89PNG\r\n\x1a\n'
    ihdr = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)
    fila = b'\x00' + bytes(rgb) * w
    return (sig + chunk(b'IHDR', ihdr)
            + chunk(b'IDAT', zlib.compress(fila * h)) + chunk(b'IEND', b''))


def _pdf(texto):
    """PDF mínimo válido de una página, sin librerías externas.
    El texto no puede llevar '(', ')' ni '\\' sin escapar."""
    objetos = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] '
        b'/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    ]
    flujo = f'BT /F1 13 Tf 20 110 Td ({texto}) Tj ET'.encode('ascii', 'ignore')
    objetos.append(b'<< /Length %d >>\nstream\n' % len(flujo) + flujo + b'\nendstream')

    cuerpo = b'%PDF-1.4\n'
    offsets = []
    for i, obj in enumerate(objetos, start=1):
        offsets.append(len(cuerpo))
        cuerpo += f'{i} 0 obj\n'.encode() + obj + b'\nendobj\n'

    xref_pos = len(cuerpo)
    n = len(objetos) + 1
    xref = f'xref\n0 {n}\n0000000000 65535 f \n'.encode()
    for off in offsets:
        xref += f'{off:010d} 00000 n \n'.encode()
    fin = f'trailer\n<< /Size {n} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF'.encode()
    return cuerpo + xref + fin


class Command(BaseCommand):
    help = 'Contenido de prueba del Aula Virtual: 8 modelos, 2 diplomas y un alumno con avance.'

    def add_arguments(self, parser):
        parser.add_argument('--limpiar', action='store_true',
                            help='Borra el contenido de prueba y termina.')
        parser.add_argument('--forzar', action='store_true',
                            help='Permite correr con DEBUG=False (servidor de pruebas). '
                                 'Hay que escribirlo a propósito: es la única forma de '
                                 'meter contenido falso en un servidor.')
        parser.add_argument('--alumno', default='alumno.demo@test.cl',
                            help='Correo de la membresía a la que se le marca avance. '
                                 'Si no existe, se usa la primera que haya.')
        parser.add_argument('--reemplazar-todo', action='store_true',
                            help='Borra TODOS los cursos y diplomas antes de crear, no solo '
                                 'los de prueba. Se lleva por delante el contenido real.')

    def handle(self, *args, **opciones):
        # La guarda evita el accidente; --forzar deja la puerta para el servidor
        # de pruebas, donde DEBUG va en False pero el contenido igual es falso.
        if not settings.DEBUG and not opciones['forzar']:
            raise CommandError(
                'Con DEBUG=False esto no corre solo. Si de verdad quieres sembrar '
                'contenido de prueba en este servidor, repite con --forzar.'
            )

        if opciones['limpiar']:
            n, _ = Course.objects.filter(slug__startswith=PREFIJO).delete()
            d, _ = Diploma.objects.filter(title__startswith='Diploma Constructor').delete()
            self.stdout.write(self.style.SUCCESS(f'Borrado: {n} registros de cursos, {d} de diplomas.'))
            return

        if opciones['reemplazar_todo']:
            n, _ = Course.objects.all().delete()
            d, _ = Diploma.objects.all().delete()
            self.stdout.write(self.style.WARNING(
                f'Se borró TODO el contenido anterior ({n} registros de cursos, {d} de diplomas).'))
        else:
            # Se parte de cero para que el orden quede parejo al correrlo dos
            # veces. Se llevan también los cursos sueltos de seed_dummy_data: si
            # no, quedan mezclados y la secuencia se ve desordenada.
            Course.objects.filter(slug__startswith=PREFIJO).delete()
            Course.objects.filter(slug__startswith='curso-demo').delete()
            Diploma.objects.filter(title__startswith='Diploma Constructor').delete()

        colores = [(130, 0, 219), (255, 203, 0), (0, 166, 62), (255, 97, 1),
                   (47, 0, 83), (89, 5, 153), (6, 124, 113), (192, 52, 52)]

        cursos = []
        for i, (titulo, desc, n_rec) in enumerate(MODELOS, start=1):
            c = Course.objects.create(
                slug=f'{PREFIJO}{i}', title=titulo, description=desc,
                order=i, is_active=True,
            )
            # Cada modelo abre con el video, sigue con el manual y termina con
            # los pasos en imagen: es la estructura que describe la clienta en
            # las preguntas frecuentes.
            Lesson.objects.create(
                course=c, order=1, title='Video de presentación', lesson_type='VIDEO',
                description=f'Qué vas a construir en «{titulo}» y qué vas a aprender.',
                video_embed_url='https://www.youtube.com/embed/aqz-KE-bpKQ',
            )
            Lesson.objects.create(
                course=c, order=2, title='Manual de construcción', lesson_type='PDF',
                description='Instrucciones paso a paso, solo con imágenes.',
                pdf_file=ContentFile(_pdf(f'Manual de ejemplo - {titulo}'),
                                     name=f'manual-{i}.pdf'),
            )
            for p in range(3, n_rec + 1):
                Lesson.objects.create(
                    course=c, order=p, title=f'Paso {p - 2}', lesson_type='IMAGE',
                    description=f'Detalle del paso {p - 2} de la construcción.',
                    image_file=ContentFile(_png(colores[(i - 1) % len(colores)]),
                                           name=f'paso-{i}-{p}.png'),
                )
            cursos.append(c)

        for orden, titulo, desc in DIPLOMAS:
            Diploma.objects.create(title=titulo, description=desc, order=orden, is_active=True)

        # Los cursos se otorgan al comprar, así que hay que engancharlos a los
        # productos que dan acceso y a las membresías que ya existen.
        for p in Product.objects.filter(access_months__gt=0):
            p.courses.add(*cursos)
        for m in Membership.objects.all():
            m.courses.add(*cursos)

        self.stdout.write(self.style.SUCCESS(
            f'{len(cursos)} modelos y {len(DIPLOMAS)} diplomas creados.'))

        # --- Alumno con avance, para ver el goteo en acción ---
        # Sin esto la membresía es de hoy y solo el primer modelo estaría
        # abierto: no se vería ni un curso completado ni el contador del
        # siguiente. Se corre la fecha de compra 5 semanas hacia atrás.
        m = (Membership.objects.filter(user__email=opciones['alumno']).first()
             or Membership.objects.first())
        if m:
            m.created_at = timezone.now() - timedelta(weeks=5)
            m.save(update_fields=['created_at'])

            for c in cursos[:3]:                      # 3 modelos terminados
                for l in c.lessons.all():
                    mark_lesson_completed(m, l)
            cuarto = cursos[3].lessons.order_by('order')
            for l in cuarto[:2]:                      # el 4º a medio camino
                mark_lesson_completed(m, l)

            self.stdout.write(
                f'\n{m.user.email}: 3 modelos completos, 1 a medias, '
                'el resto esperando su semana.\n'
                'Las demás membresías parten desde cero.'
            )
