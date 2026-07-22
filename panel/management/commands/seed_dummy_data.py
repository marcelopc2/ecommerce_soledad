import struct
import zlib

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from catalog.models import Product
from invoicing.models import Invoice
from lms.models import Course, Lesson
from lms.services import grant_access_for_order, mark_lesson_completed
from payments.models import Order, OrderItem

DEMO_PASSWORD = 'MiClaveSegura123'

# Un pedido por cada estado relevante del flujo, para poder probar cada pill
# de filtro y cada botón del panel sin tener que generarlos manualmente.
DEMO_ACCOUNTS = [
    # (email, estado del pedido, estado de la boleta, con progreso de curso)
    ('alumno.demo@test.cl', 'PAID', 'ISSUED', True),
    ('reciente@test.cl', 'PAID', None, False),
    ('boleta.error@test.cl', 'PAID', 'ERROR', False),
    ('pendiente@test.cl', 'PENDING', None, False),
    ('rechazado@test.cl', 'FAILED', None, False),
]


def _demo_png(width=120, height=120, rgb=(130, 0, 219)):
    """PNG mínimo de un color sólido, sin depender de Pillow (no es dependencia
    del proyecto). Truecolor de 8 bits, un filtro 'None' por fila."""
    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)

    sig = b'\x89PNG\r\n\x1a\n'
    ihdr = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    row = b'\x00' + bytes(rgb) * width
    idat = zlib.compress(row * height)
    return sig + chunk(b'IHDR', ihdr) + chunk(b'IDAT', idat) + chunk(b'IEND', b'')


def _demo_pdf(text):
    """PDF mínimo válido de una página con un texto, sin depender de ninguna
    librería de PDF (el proyecto deliberadamente no tiene una, ver diploma.html).
    Nota: el texto no puede llevar '(', ')' ni '\\' sin escapar en el content stream."""
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] '
        b'/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    ]
    stream = f'BT /F1 12 Tf 15 100 Td ({text}) Tj ET'.encode('ascii')
    objects.append(b'<< /Length %d >>\nstream\n' % len(stream) + stream + b'\nendstream')

    body = b'%PDF-1.4\n'
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(body))
        body += f'{i} 0 obj\n'.encode() + obj + b'\nendobj\n'

    xref_offset = len(body)
    n = len(objects) + 1
    xref = f'xref\n0 {n}\n0000000000 65535 f \n'.encode()
    for off in offsets[1:]:
        xref += f'{off:010d} 00000 n \n'.encode()
    trailer = f'trailer\n<< /Size {n} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF'.encode()
    return body + xref + trailer


class Command(BaseCommand):
    help = (
        'Recrea un curso de juguete (3 recursos: video, PDF e imagen, todos '
        'con archivos reales generados sin dependencias externas), lo asocia '
        'a un producto activo, y crea un pedido de ejemplo para cada estado '
        'del flujo de compra (pagado con boleta emitida, pagado sin boleta, '
        'boleta con error, pendiente de pago, rechazado). Pensado para correr '
        'después de clear_dummy_data. Solo corre con DEBUG=True.'
    )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('Este comando solo corre con DEBUG=True: no se ejecuta contra producción.')

        product = Product.objects.filter(is_active=True).order_by('id').first()
        if not product:
            raise CommandError('No hay ningún producto activo en la tienda: crea uno primero en /gestion/productos/.')

        course, created = Course.objects.get_or_create(
            slug='curso-demo-flujo-compra',
            defaults={
                'title': 'Curso demo (flujo de compra)',
                'description': 'Curso de juguete generado por seed_dummy_data para probar el flujo completo.',
                'is_active': True,
                'order': 1,
            },
        )
        if created:
            Lesson.objects.create(
                course=course, order=1, title='Video de bienvenida', lesson_type='VIDEO',
                description='Recurso de ejemplo tipo video.',
                video_embed_url='https://www.youtube.com/embed/dQw4w9WgXcQ',
            )
            Lesson.objects.create(
                course=course, order=2, title='Manual del modelo', lesson_type='PDF',
                description='Recurso de ejemplo tipo PDF (generado, no es un manual real).',
                pdf_file=ContentFile(_demo_pdf('Manual de ejemplo - dato de prueba'), name='manual-demo.pdf'),
            )
            Lesson.objects.create(
                course=course, order=3, title='Paso 1: la base', lesson_type='IMAGE',
                description='Recurso de ejemplo tipo imagen (color sólido, no es una foto real).',
                image_file=ContentFile(_demo_png(), name='paso1-demo.png'),
            )
        first_lesson = course.lessons.order_by('order').first()

        product.courses.add(course)

        existing = Order.objects.filter(customer_email__in=[e for e, *_ in DEMO_ACCOUNTS])
        if existing.exists():
            self.stdout.write(self.style.WARNING(
                'Ya hay pedidos de una siembra anterior para estos correos; se '
                'agregarán más encima (corre clear_dummy_data primero si quieres '
                'partir de cero).\n'
            ))

        rows = []
        for email, order_status, invoice_status, with_progress in DEMO_ACCOUNTS:
            user, _ = User.objects.get_or_create(username=email, defaults={'email': email})
            user.email = email
            user.set_password(DEMO_PASSWORD)  # conocida, para poder iniciar sesión y probar el LMS
            user.is_active = True
            user.save()

            order = Order.objects.create(status=order_status, total_amount=product.price, customer_email=email)
            order.products.add(product)
            OrderItem.objects.create(
                order=order, product=product, name=product.name,
                unit_price=int(product.effective_price), quantity=1,
            )

            membership = None
            if order_status == 'PAID':
                membership = grant_access_for_order(order)  # crea/extiende membresía + envía el correo real

            if invoice_status == 'ISSUED':
                Invoice.objects.create(
                    order=order, status='ISSUED', folio='DEMO-0001', token='demo-token',
                    issued_at=timezone.now(),
                )
            elif invoice_status == 'ERROR':
                Invoice.objects.create(
                    order=order, status='ERROR',
                    error_message='OpenFactura 500: Internal Server Error (dato de prueba, no una falla real)',
                )
            # invoice_status=None -> no se crea Invoice (pedido pagado "sin boleta", o pedido no pagado)

            if with_progress and membership and first_lesson:
                mark_lesson_completed(membership, first_lesson)

            rows.append((email, order_status, invoice_status or ('sin boleta' if order_status == 'PAID' else '—')))

        self.stdout.write(self.style.SUCCESS(
            f'Listo. Producto usado: "{product.name}" (curso: "{course.title}", '
            f'{course.lessons.count()} recurso(s)).\n'
        ))
        self.stdout.write(f'{"Correo":<26}{"Pedido":<12}Boleta')
        self.stdout.write('-' * 50)
        for email, order_status, invoice_note in rows:
            self.stdout.write(f'{email:<26}{order_status:<12}{invoice_note}')

        self.stdout.write(f'\nClave para iniciar sesión como cualquiera de estos alumnos: {DEMO_PASSWORD}')
        self.stdout.write('Revisa /gestion/pedidos/, /gestion/membresias/ y /gestion/cursos/ para seguir el flujo.')
        self.stdout.write(self.style.WARNING(
            '\nOjo: esto no recrea diplomas (clear_dummy_data borra el catálogo de '
            'diplomas y este comando no los repone). Si los necesitas para probar '
            'la secuencia completa, créalos a mano en /gestion/diplomas/nuevo/.'
        ))
