"""Tests del goteo semanal y del control de acceso al contenido.

Cubren la promesa comercial del producto ("un modelo nuevo cada semana") y el
punto donde un error deja el contenido pagado al alcance de cualquiera.
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from lms.models import AjustesAula, Course, Lesson, Membership, UnlockNotice
from lms.services import _unlock_date, get_course_access, mark_lesson_completed


class CalendarioDelGoteoTests(TestCase):
    """Cada alumno recibe su modelo nuevo el mismo día de la semana en que compró."""

    def test_siempre_siete_dias_exactos_entre_entregas(self):
        from datetime import date
        for compra in [date(2026, 6, 1),    # lunes
                       date(2026, 3, 25),   # miércoles
                       date(2026, 6, 7)]:   # domingo
            fechas = [_unlock_date(compra, i) for i in range(5)]
            diferencias = {(fechas[i + 1] - fechas[i]).days for i in range(4)}
            self.assertEqual(diferencias, {7}, f'compra del {compra}')

    def test_conserva_el_dia_de_la_semana_de_la_compra(self):
        from datetime import date
        miercoles = date(2026, 3, 25)
        self.assertEqual(miercoles.weekday(), 2)
        for i in range(5):
            self.assertEqual(_unlock_date(miercoles, i).weekday(), 2)

    def test_el_primer_curso_esta_disponible_el_dia_de_la_compra(self):
        from datetime import date
        compra = date(2026, 6, 3)
        self.assertEqual(_unlock_date(compra, 0), compra)


class DesbloqueoTests(TestCase):
    """Estos tests miden EL CALENDARIO, así que fijan "1 modelo disponible al
    comprar" en vez de confiar en el valor por defecto: con el ajuste de fábrica
    (3 al inicio) los primeros modelos se abren de entrada y el calendario no
    sería lo que los está trabando. El comportamiento configurable tiene sus
    propios tests en ModelosInicialesTests."""

    def setUp(self):
        ajustes = AjustesAula.obtener()
        ajustes.cursos_iniciales = 1
        ajustes.save()

        self.usuario = User.objects.create_user(
            username='alumno@test.cl', email='alumno@test.cl', password='clave-de-prueba')
        self.membresia = Membership.objects.create(
            user=self.usuario, expires_at=timezone.now() + timedelta(days=180),
            student_name='Tomás',
        )
        self.cursos = []
        for i in range(1, 4):
            c = Course.objects.create(title=f'Modelo {i}', slug=f'modelo-{i}', order=i)
            Lesson.objects.create(
                course=c, title=f'Armado {i}', order=1,
                lesson_type='VIDEO', video_embed_url='https://www.youtube.com/embed/abc12345678',
            )
            self.cursos.append(c)
        self.membresia.courses.add(*self.cursos)

    def _retroceder_compra(self, dias):
        Membership.objects.filter(pk=self.membresia.pk).update(
            created_at=timezone.now() - timedelta(days=dias))
        self.membresia.refresh_from_db()

    def test_recien_comprado_solo_el_primero_esta_abierto(self):
        acceso = get_course_access(self.membresia)
        self.assertTrue(acceso[0]['unlocked'])
        self.assertFalse(acceso[1]['unlocked'])
        self.assertFalse(acceso[2]['unlocked'])

    def test_pasada_la_semana_sin_completar_el_anterior_sigue_cerrado(self):
        """La fecha no basta: hay que terminar el modelo anterior. Es lo que
        evita que alguien se salte la fila."""
        self._retroceder_compra(8)
        acceso = get_course_access(self.membresia)
        self.assertFalse(acceso[1]['unlocked'])
        self.assertEqual(acceso[1]['lock_reason'], 'previo')
        self.assertEqual(acceso[1]['required_course'], self.cursos[0])

    def test_pasada_la_semana_y_completado_el_anterior_se_abre(self):
        self._retroceder_compra(8)
        mark_lesson_completed(self.membresia, self.cursos[0].lessons.first())

        acceso = get_course_access(self.membresia)
        self.assertTrue(acceso[1]['unlocked'])
        self.assertIsNone(acceso[1]['lock_reason'])
        # El tercero sigue cerrado. El motivo es 'previo' y no 'fecha': una vez
        # que hay un curso abierto sin completar, lo que traba la fila es ese
        # curso, no el calendario (aunque su fecha tampoco haya llegado).
        self.assertFalse(acceso[2]['unlocked'])
        self.assertEqual(acceso[2]['lock_reason'], 'previo')

    def test_completar_todo_antes_de_tiempo_no_adelanta_el_calendario(self):
        """Aunque termine el modelo 1 el mismo día, el 2 espera su semana."""
        mark_lesson_completed(self.membresia, self.cursos[0].lessons.first())
        acceso = get_course_access(self.membresia)
        self.assertFalse(acceso[1]['unlocked'])
        self.assertEqual(acceso[1]['lock_reason'], 'fecha')

    def test_los_dias_pausados_corren_el_calendario(self):
        self._retroceder_compra(8)
        self.membresia.total_paused_days = 8
        self.membresia.save(update_fields=['total_paused_days'])
        mark_lesson_completed(self.membresia, self.cursos[0].lessons.first())

        # Con 8 días de pausa, los 8 transcurridos no cuentan.
        acceso = get_course_access(self.membresia)
        self.assertFalse(acceso[1]['unlocked'])


class ModelosInicialesTests(TestCase):
    """"Modelos disponibles al comprar" (Configuración → Aula Virtual).

    Con el valor por defecto (3) quien compra tiene con qué empezar: termina el
    primero y el segundo se abre al instante, sin esperar la semana. Recién a
    partir del cuarto manda el calendario."""

    def setUp(self):
        self.usuario = User.objects.create_user(
            username='alumna@test.cl', email='alumna@test.cl', password='clave-de-prueba')
        self.membresia = Membership.objects.create(
            user=self.usuario, expires_at=timezone.now() + timedelta(days=180),
            student_name='Emilia',
        )
        self.cursos = []
        for i in range(1, 5):
            c = Course.objects.create(title=f'Modelo {i}', slug=f'modelo-{i}', order=i)
            Lesson.objects.create(
                course=c, title=f'Armado {i}', order=1,
                lesson_type='VIDEO', video_embed_url='https://www.youtube.com/embed/abc12345678',
            )
            self.cursos.append(c)
        self.membresia.courses.add(*self.cursos)

    def _fijar(self, iniciales):
        ajustes = AjustesAula.obtener()
        ajustes.cursos_iniciales = iniciales
        ajustes.save()

    def test_con_tres_iniciales_el_segundo_se_abre_al_terminar_el_primero(self):
        self._fijar(3)
        # Sin terminar nada, solo el primero: los demás esperan su turno en la fila.
        acceso = get_course_access(self.membresia)
        self.assertTrue(acceso[0]['unlocked'])
        self.assertFalse(acceso[1]['unlocked'])
        self.assertEqual(acceso[1]['lock_reason'], 'previo')

        # Al terminarlo el segundo se abre el mismo día: lo que lo trababa era
        # la fila, no el calendario.
        mark_lesson_completed(self.membresia, self.cursos[0].lessons.first())
        acceso = get_course_access(self.membresia)
        self.assertTrue(acceso[1]['unlocked'])

    def test_el_cuarto_ya_depende_del_calendario(self):
        """Con 3 iniciales, el 4º es el primero que además tiene que esperar."""
        self._fijar(3)
        for curso in self.cursos[:3]:
            mark_lesson_completed(self.membresia, curso.lessons.first())

        acceso = get_course_access(self.membresia)
        self.assertTrue(acceso[2]['unlocked'])
        self.assertFalse(acceso[3]['unlocked'])
        self.assertEqual(acceso[3]['lock_reason'], 'fecha')

    def test_con_uno_inicial_el_segundo_espera_la_semana(self):
        """El ajuste manda: bajándolo a 1 vuelve el goteo semanal desde el 2º."""
        self._fijar(1)
        mark_lesson_completed(self.membresia, self.cursos[0].lessons.first())

        acceso = get_course_access(self.membresia)
        self.assertFalse(acceso[1]['unlocked'])
        self.assertEqual(acceso[1]['lock_reason'], 'fecha')


class AvisosDeDesbloqueoTests(TestCase):
    """El comando que corre a diario desde cron."""

    def setUp(self):
        self.usuario = User.objects.create_user(
            username='alumno@test.cl', email='alumno@test.cl', password='clave-de-prueba')
        self.membresia = Membership.objects.create(
            user=self.usuario, expires_at=timezone.now() + timedelta(days=180),
            student_name='Tomás',
        )
        self.curso = Course.objects.create(title='Modelo 1', slug='modelo-1', order=1)
        Lesson.objects.create(
            course=self.curso, title='Armado', order=1,
            lesson_type='VIDEO', video_embed_url='https://www.youtube.com/embed/abc12345678',
        )
        self.membresia.courses.add(self.curso)

    def test_avisa_del_curso_abierto(self):
        call_command('enviar_avisos_desbloqueo', verbosity=0)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('alumno@test.cl', mail.outbox[0].to)
        self.assertEqual(UnlockNotice.objects.count(), 1)

    def test_correrlo_de_nuevo_no_reenvia(self):
        """Lo crítico de un cron diario: sin esto el alumno recibiría el mismo
        correo todos los días hasta completar el curso."""
        call_command('enviar_avisos_desbloqueo', verbosity=0)
        mail.outbox.clear()

        call_command('enviar_avisos_desbloqueo', verbosity=0)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(UnlockNotice.objects.count(), 1)

    def test_no_avisa_a_membresias_vencidas(self):
        self.membresia.expires_at = timezone.now() - timedelta(days=1)
        self.membresia.save(update_fields=['expires_at'])

        call_command('enviar_avisos_desbloqueo', verbosity=0)
        self.assertEqual(len(mail.outbox), 0)

    def test_no_avisa_con_la_suscripcion_pausada(self):
        self.membresia.paused_at = timezone.now()
        self.membresia.save(update_fields=['paused_at'])

        call_command('enviar_avisos_desbloqueo', verbosity=0)
        self.assertEqual(len(mail.outbox), 0)

    def test_simular_no_envia_ni_registra(self):
        call_command('enviar_avisos_desbloqueo', simular=True, verbosity=0)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(UnlockNotice.objects.count(), 0)


class AccesoAArchivosTests(TestCase):
    """El contenido pagado no se sirve sin membresía activa y curso desbloqueado."""

    def setUp(self):
        self.usuario = User.objects.create_user(
            username='alumno@test.cl', email='alumno@test.cl', password='clave-de-prueba')
        self.membresia = Membership.objects.create(
            user=self.usuario, expires_at=timezone.now() + timedelta(days=180))
        self.curso_abierto = Course.objects.create(title='Modelo 1', slug='modelo-1', order=1)
        self.curso_futuro = Course.objects.create(title='Modelo 2', slug='modelo-2', order=2)
        for c in (self.curso_abierto, self.curso_futuro):
            Lesson.objects.create(
                course=c, title='PDF', order=1, lesson_type='PDF')
        self.membresia.courses.add(self.curso_abierto, self.curso_futuro)

    def test_no_se_puede_bajar_el_pdf_de_un_curso_aun_bloqueado(self):
        """El ataque a anticipar: el alumno enumera ids y se baja el año
        completo de contenido el primer día."""
        self.client.force_login(self.usuario)
        leccion = self.curso_futuro.lessons.first()
        respuesta = self.client.get(f'/api/lms/lessons/{leccion.id}/pdf/')
        self.assertIn(respuesta.status_code, (401, 403))

    def test_sin_sesion_no_se_sirve_nada(self):
        leccion = self.curso_abierto.lessons.first()
        respuesta = self.client.get(f'/api/lms/lessons/{leccion.id}/pdf/')
        self.assertIn(respuesta.status_code, (401, 403))
