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

from lms.models import (
    AjustesAula, CategoryCourse, Course, CourseCategory, Lesson, Membership,
    MembershipCategory, UnlockNotice,
)
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


class CategoriasDeCursosTests(TestCase):
    """Cada categoría corre su propio calendario y su propio ritmo.

    Antes había UN solo calendario anclado a la creación de la membresía, así
    que un pack comprado más tarde heredaba el ritmo ya en marcha en vez de
    abrir lo suyo. Estos tests fijan el comportamiento nuevo.
    """

    def setUp(self):
        self.usuario = User.objects.create_user(
            username='alumno@test.cl', email='alumno@test.cl', password='x')
        # La membresía nació hace 60 días: si algo se anclara a esa fecha en vez
        # de a la de la categoría, el goteo ya vendría muy avanzado y los tests
        # de "recién comprado" no detectarían el error.
        self.membresia = Membership.objects.create(
            user=self.usuario, expires_at=timezone.now() + timedelta(days=300))
        Membership.objects.filter(pk=self.membresia.pk).update(
            created_at=timezone.now() - timedelta(days=60))
        self.membresia.refresh_from_db()

    def _categoria(self, nombre, modo, iniciales=1, cursos=(), obtenida_hace=0):
        cat = CourseCategory.objects.create(
            nombre=nombre, slug=nombre.lower().replace(' ', '-'),
            modo=modo, cursos_iniciales=iniciales)
        for i, curso in enumerate(cursos):
            CategoryCourse.objects.create(categoria=cat, curso=curso, orden=i + 1)
        MembershipCategory.objects.create(
            membership=self.membresia, categoria=cat,
            obtenida_en=timezone.now() - timedelta(days=obtenida_hace))
        return cat

    def _cursos(self, cuantos, prefijo='c'):
        return [
            Course.objects.create(title=f'{prefijo}{i}', slug=f'{prefijo}-{i}', order=i)
            for i in range(1, cuantos + 1)
        ]

    def test_modo_todo_abre_los_cursos_apenas_se_obtiene(self):
        """El caso que motivó todo esto: un pack premium comprado hoy debe abrir
        sus modelos hoy, no meterlos en la fila del goteo que ya venía."""
        cursos = self._cursos(8, 'premium')
        self._categoria('Premium', CourseCategory.TODO, cursos=cursos, obtenida_hace=0)
        acceso = get_course_access(self.membresia)
        self.assertEqual(len(acceso), 8)
        self.assertTrue(all(a['unlocked'] for a in acceso),
                        'el modo TODO debe abrir todos sus cursos de inmediato')

    def test_modo_goteo_respeta_los_iniciales_de_su_categoria(self):
        """`cursos_iniciales` = cuántos quedan disponibles POR FECHA el día de la
        compra. No significa tres abiertos a la vez: la cadena de "termina el
        anterior" sigue rigiendo, así que el efecto real es poder recorrer tres
        seguidos sin esperar una semana entre uno y otro."""
        cursos = self._cursos(6, 'normal')
        self._categoria('Normal', CourseCategory.GOTEO, iniciales=3,
                        cursos=cursos, obtenida_hace=0)
        acceso = get_course_access(self.membresia)
        hoy = timezone.localdate()

        disponibles_por_fecha = [a for a in acceso if a['unlock_date'] <= hoy]
        self.assertEqual(len(disponibles_por_fecha), 3,
                         'con 3 iniciales, los tres primeros no deben esperar')
        self.assertGreater(acceso[3]['unlock_date'], hoy,
                           'el cuarto sí espera a la semana siguiente')
        # Solo el primero está abierto de entrada: los otros dos esperan a que
        # se complete el anterior, no a que pase el tiempo.
        self.assertTrue(acceso[0]['unlocked'])
        self.assertEqual(acceso[1]['lock_reason'], 'previo')

    def test_cada_categoria_tiene_su_propio_calendario(self):
        """Una categoría obtenida hace 60 días va más avanzada que una de hoy,
        aunque las dos vivan en la misma membresía."""
        viejos = self._cursos(6, 'viejo')
        nuevos = self._cursos(6, 'nuevo')
        self._categoria('Antigua', CourseCategory.GOTEO, iniciales=1,
                        cursos=viejos, obtenida_hace=60)
        self._categoria('Reciente', CourseCategory.GOTEO, iniciales=1,
                        cursos=nuevos, obtenida_hace=0)
        acceso = {a['course'].title: a for a in get_course_access(self.membresia)}
        # En la antigua ya pasaron 8 semanas: el 2º está disponible por fecha
        # (aunque la cadena de "completa el anterior" lo trabe, la FECHA ya pasó).
        self.assertLess(acceso['viejo2']['unlock_date'], acceso['nuevo2']['unlock_date'],
                        'la categoría más antigua debe ir más adelantada')

    def test_un_curso_en_dos_categorias_toma_el_estado_mas_favorable(self):
        """Si Premium lo abre, da igual que en Normal todavía falten semanas."""
        curso = Course.objects.create(title='Compartido', slug='compartido', order=1)
        relleno = self._cursos(5, 'relleno')
        # En Normal queda al final de la fila: le faltarían semanas.
        self._categoria('Normal', CourseCategory.GOTEO, iniciales=1,
                        cursos=relleno + [curso], obtenida_hace=0)
        # En Premium está abierto de una.
        self._categoria('Premium', CourseCategory.TODO, cursos=[curso], obtenida_hace=0)
        acceso = {a['course'].title: a for a in get_course_access(self.membresia)}
        self.assertTrue(acceso['Compartido']['unlocked'],
                        'basta que UNA categoría lo abra para que esté disponible')

    def test_un_curso_agregado_despues_llega_a_quien_ya_tenia_la_categoria(self):
        """El problema original: agregar un modelo nuevo obligaba a ir producto
        por producto marcándolo."""
        cursos = self._cursos(2, 'inicial')
        cat = self._categoria('Normal', CourseCategory.TODO, cursos=cursos, obtenida_hace=10)
        self.assertEqual(len(get_course_access(self.membresia)), 2)

        nuevo = Course.objects.create(title='Modelo 9', slug='modelo-9', order=9)
        CategoryCourse.objects.create(categoria=cat, curso=nuevo, orden=3)

        titulos = [a['course'].title for a in get_course_access(self.membresia)]
        self.assertIn('Modelo 9', titulos,
                      'el curso nuevo debe llegar solo, sin tocar la membresía')

    def test_un_curso_inactivo_no_aparece_aunque_este_en_la_categoria(self):
        cursos = self._cursos(3, 'x')
        cursos[1].is_active = False
        cursos[1].save()
        self._categoria('Normal', CourseCategory.TODO, cursos=cursos, obtenida_hace=0)
        titulos = [a['course'].title for a in get_course_access(self.membresia)]
        self.assertNotIn('x2', titulos)

    def test_sin_categorias_sigue_funcionando_lo_otorgado_a_mano(self):
        """Respaldo para lo que se otorgó antes de que existieran las categorías:
        esos cursos no pueden quedar cerrados para siempre."""
        cursos = self._cursos(3, 'legado')
        self.membresia.courses.add(*cursos)
        acceso = get_course_access(self.membresia)
        self.assertEqual(len(acceso), 3)
        self.assertTrue(acceso[0]['unlocked'],
                        'el primero debe estar disponible, como antes')
