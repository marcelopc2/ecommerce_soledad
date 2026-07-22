from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from lms.models import Course, Diploma, Lesson, Membership
from payments.models import Order


class Command(BaseCommand):
    help = (
        'Borra todos los pedidos, boletas, envios, membresias (con su progreso '
        'y diplomas ganados), usuarios de prueba, y el catálogo LMS de prueba '
        '(cursos, lecciones con sus archivos, diplomas). NO toca productos ni '
        'categorías (esos son la tienda real), ni las cuentas de staff/admin. '
        'Solo corre con DEBUG=True.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--yes', action='store_true',
            help='No pedir confirmacion interactiva (para usar en scripts).',
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('Este comando solo corre con DEBUG=True: no se ejecuta contra producción.')

        orders_count = Order.objects.count()
        memberships_count = Membership.objects.count()
        courses_count = Course.objects.count()
        lessons_count = Lesson.objects.count()
        diplomas_count = Diploma.objects.count()
        # Las cuentas de staff/admin (ej. quien gestiona el panel) nunca se tocan,
        # solo alumnos/clientes de prueba creados por seed_dummy_data o a mano.
        dummy_users = User.objects.filter(is_staff=False, is_superuser=False)
        dummy_users_count = dummy_users.count()
        staff_emails = list(
            User.objects.filter(is_staff=True).values_list('email', flat=True)
        )

        self.stdout.write('Se van a borrar:')
        self.stdout.write(f'  {orders_count} pedido(s) (y sus boletas/envios asociados)')
        self.stdout.write(f'  {memberships_count} membresia(s) (y su progreso/diplomas ganados)')
        self.stdout.write(f'  {courses_count} curso(s) y {lessons_count} recurso(s) (con sus archivos PDF/imagen)')
        self.stdout.write(f'  {diplomas_count} diploma(s)')
        self.stdout.write(f'  {dummy_users_count} usuario(s) de prueba')
        self.stdout.write('')
        self.stdout.write('Se van a CONSERVAR:')
        self.stdout.write('  la tienda (productos y categorías)')
        self.stdout.write(f'  {len(staff_emails)} cuenta(s) de staff: {", ".join(staff_emails) or "-"}')

        totals = (orders_count, memberships_count, courses_count, lessons_count, diplomas_count, dummy_users_count)
        if not any(totals):
            self.stdout.write(self.style.SUCCESS('\nNo hay datos de prueba que borrar.'))
            return

        if not options['yes']:
            confirm = input('\nEscribe "borrar" para confirmar: ').strip().lower()
            if confirm != 'borrar':
                self.stdout.write(self.style.WARNING('Cancelado, no se borró nada.'))
                return

        # Los FileField de Lesson no se borran solos al borrar la fila (Django
        # nunca elimina el archivo en disco automáticamente): hay que sacarlos
        # de protected_media/ a mano ANTES de borrar los Lesson.
        deleted_files = 0
        for lesson in Lesson.objects.all():
            if lesson.pdf_file:
                lesson.pdf_file.delete(save=False)
                deleted_files += 1
            if lesson.image_file:
                lesson.image_file.delete(save=False)
                deleted_files += 1

        # Order no tiene FK a User (customer_email es solo texto), así que se
        # borra aparte. Shipment e Invoice son OneToOne CASCADE hacia Order, se
        # van solos. Membership sí es CASCADE hacia User: borrar los usuarios de
        # prueba ya arrastra su membresía (y con ella progreso/diplomas), pero se
        # borra explícito también por si quedó alguna membresía huérfana.
        Order.objects.all().delete()
        Membership.objects.all().delete()
        Course.objects.all().delete()  # cascada: se lleva los Lesson
        Diploma.objects.all().delete()
        dummy_users.delete()

        self.stdout.write(self.style.SUCCESS(
            f'\nListo: {orders_count} pedido(s), {memberships_count} membresía(s), '
            f'{courses_count} curso(s) con {lessons_count} recurso(s) ({deleted_files} archivo(s) '
            f'borrados de disco), {diplomas_count} diploma(s) y {dummy_users_count} usuario(s) '
            'de prueba eliminados.'
        ))
