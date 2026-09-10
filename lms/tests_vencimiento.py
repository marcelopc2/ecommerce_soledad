"""Qué pasa cuando se acaban los 12 meses, y qué pasa cuando vuelve a comprar.

Son las dos mitades de la misma promesa comercial: mientras no paga puede repasar
los modelos que terminó pero no abrir los que le faltan, y cuando vuelve retoma
su ritmo semanal desde donde quedó, en vez de recibir el año entero de golpe.
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from lms.models import (
    AjustesAula, CategoryCourse, Course, CourseCategory, CourseProgress, Lesson,
    Membership, MembershipCategory,
)
from lms.services import (
    reanudar_goteo, get_course_access, get_sequence_access, mark_lesson_completed,
    no_puede_avanzar,
)


class VencimientoYRenovacionTests(TestCase):

    def setUp(self):
        ajustes = AjustesAula.obtener()
        ajustes.cursos_iniciales = 3
        ajustes.bloqueados_visibles = 0
        ajustes.save()

        self.usuario = User.objects.create_user(
            username='alumna@test.cl', email='alumna@test.cl', password='clave-de-prueba')
        self.membresia = Membership.objects.create(
            user=self.usuario, expires_at=timezone.now() + timedelta(days=30),
            student_name='Emilia',
        )
        self.categoria = CourseCategory.objects.create(
            nombre='General', slug='general', cursos_iniciales=3)
        self.cursos = []
        for i in range(1, 11):
            c = Course.objects.create(title=f'Modelo {i}', slug=f'modelo-{i}', order=i)
            Lesson.objects.create(
                course=c, title=f'Armado {i}', order=1, lesson_type='VIDEO',
                video_embed_url='https://www.youtube.com/embed/abc12345678',
            )
            CategoryCourse.objects.create(categoria=self.categoria, curso=c, orden=i)
            self.cursos.append(c)
        self.mc = MembershipCategory.objects.create(
            membership=self.membresia, categoria=self.categoria,
            obtenida_en=timezone.now(),
        )

    # --- utilidades -------------------------------------------------------

    def _comprada_hace(self, dias):
        MembershipCategory.objects.filter(pk=self.mc.pk).update(
            obtenida_en=timezone.now() - timedelta(days=dias))
        self.mc.refresh_from_db()

    def _vencer(self):
        self.membresia.expires_at = timezone.now() - timedelta(days=1)
        self.membresia.save(update_fields=['expires_at'])

    def _renovar(self):
        self.membresia.expires_at = timezone.now() + timedelta(days=365)
        self.membresia.save(update_fields=['expires_at'])
        reanudar_goteo(self.membresia)

    def _terminar(self, n):
        for curso in self.cursos[:n]:
            CourseProgress.objects.get_or_create(membership=self.membresia, course=curso)

    # --- mientras está vencida --------------------------------------------

    def test_vencida_deja_repasar_lo_terminado_y_cierra_lo_demas(self):
        """Volver a armar un modelo que ya hizo es la razón más común para entrar
        con la suscripción caída, y ya lo pagó. Lo que no alcanzó a terminar es
        justamente lo que está comprando al renovar."""
        self._comprada_hace(60)
        self._terminar(3)
        self._vencer()
        seq = [it for it in get_sequence_access(self.membresia) if it['type'] == 'course']

        self.assertEqual(len(seq), 10, 'las carátulas se siguen viendo todas')
        for it in seq[:3]:
            self.assertTrue(it['unlocked'], 'lo terminado se puede repasar')
            self.assertIsNone(it['lock_reason'])
        for it in seq[3:]:
            self.assertFalse(it['unlocked'])
            self.assertEqual(it['lock_reason'], 'vencida')

    def test_vencida_sin_nada_terminado_no_deja_abrir_nada(self):
        self._comprada_hace(60)
        self._vencer()
        seq = [it for it in get_sequence_access(self.membresia) if it['type'] == 'course']
        self.assertEqual(len(seq), 10)
        self.assertTrue(all(not it['unlocked'] for it in seq))

    def test_vencida_no_deja_seguir_avanzando(self):
        """Repasar no es avanzar: puede volver a ver lo terminado, pero no sumar
        avance nuevo mientras no pague."""
        self._terminar(3)
        self._vencer()
        self.assertFalse(
            mark_lesson_completed(self.membresia, self.cursos[0].lessons.first()),
        )

    def test_con_NADA_ni_siquiera_puede_repasar_lo_terminado(self):
        from lms.services import get_course_access as acceso

        ajustes = AjustesAula.obtener()
        ajustes.acceso_vencido = AjustesAula.NADA
        ajustes.save()
        self._comprada_hace(60)
        self._terminar(3)
        self._vencer()

        self.assertEqual(get_sequence_access(self.membresia), [])
        self.assertTrue(all(not a['unlocked'] for a in acceso(self.membresia)),
                        'tampoco se le sirven los archivos de lo terminado')

    def test_se_puede_configurar_que_no_vea_nada(self):
        ajustes = AjustesAula.obtener()
        ajustes.acceso_vencido = AjustesAula.NADA
        ajustes.save()
        self._vencer()
        self.assertEqual(get_sequence_access(self.membresia), [])

    def test_se_puede_configurar_que_siga_viendo_todo(self):
        ajustes = AjustesAula.obtener()
        ajustes.acceso_vencido = AjustesAula.TODO
        ajustes.save()
        self._comprada_hace(60)
        self._vencer()

        seq = [it for it in get_sequence_access(self.membresia) if it['type'] == 'course']
        self.assertTrue(seq[0]['unlocked'])
        self.assertFalse(no_puede_avanzar(self.membresia))

    def test_una_pausa_cierra_lo_no_terminado_aunque_se_configure_ver_todo(self):
        """La pausa la aplica la clienta a mano: es una decisión explícita y no
        puede quedar anulada por un ajuste pensado para el vencimiento."""
        ajustes = AjustesAula.obtener()
        ajustes.acceso_vencido = AjustesAula.TODO
        ajustes.save()
        self._comprada_hace(60)
        self._terminar(3)
        self.membresia.pause()

        self.assertTrue(no_puede_avanzar(self.membresia))
        acceso = get_course_access(self.membresia)
        self.assertTrue(acceso[0]['unlocked'], 'lo terminado se sigue pudiendo repasar')
        self.assertEqual(acceso[3]['lock_reason'], 'vencida')

    # --- al renovar --------------------------------------------------------

    def test_al_renovar_el_goteo_sigue_desde_el_ultimo_terminado(self):
        """Terminó 4 de 10 y se le venció. Al renovar NO recibe los 10 de golpe.

        Los "3 modelos al comprar" son un permiso de FECHA: habilitan tres
        posiciones sin esperar la semana, pero la cadena de "termina el anterior"
        sigue mandando, igual que en una compra nueva. Así que quedan abiertos
        los 4 que ya terminó más el siguiente, y el 6º y el 7º esperan a que los
        vaya completando —sin semana de por medio—, mientras que el 8º sí espera
        su semana.
        """
        self._comprada_hace(300)   # el calendario ya había liberado los 10
        self._terminar(4)
        self._vencer()
        self._renovar()

        acceso = get_course_access(self.membresia)
        abiertos = [a for a in acceso if a['unlocked']]
        self.assertEqual(len(abiertos), 5,
                         'los 4 terminados más el siguiente de la fila')
        self.assertTrue(acceso[4]['unlocked'], 'retoma justo donde quedó')

        # El 6º y el 7º ya tienen la fecha cumplida: lo único que los traba es
        # terminar el anterior. Es la parte "se abren en orden, sin esperar".
        for i in (5, 6):
            self.assertEqual(acceso[i]['lock_reason'], 'previo')
            self.assertEqual(acceso[i]['unlock_date'], timezone.localdate())

        # El 8º es el primero que vuelve a depender del calendario semanal.
        self.assertEqual(acceso[7]['unlock_date'],
                         timezone.localdate() + timedelta(days=7))

    def test_al_renovar_el_siguiente_llega_una_semana_despues_y_no_antes(self):
        self._comprada_hace(300)
        self._terminar(4)
        self._vencer()
        self._renovar()

        acceso = get_course_access(self.membresia)
        self.assertEqual(acceso[7]['unlock_date'],
                         timezone.localdate() + timedelta(days=7))

    def test_renovar_no_le_quita_nada_de_lo_que_ya_tenia(self):
        self._comprada_hace(300)
        self._terminar(4)
        self._vencer()
        self._renovar()

        acceso = get_course_access(self.membresia)
        for i in range(4):
            self.assertTrue(acceso[i]['unlocked'], f'el modelo {i + 1} ya era suyo')
            self.assertTrue(acceso[i]['completed'])

    def test_sin_nada_terminado_la_renovacion_lo_deja_como_recien_llegado(self):
        self._comprada_hace(300)
        self._vencer()
        self._renovar()

        acceso = get_course_access(self.membresia)
        self.assertEqual(len([a for a in acceso if a['unlocked']]), 1,
                         'sin nada terminado, la cadena traba después del primero')
        self.assertTrue(acceso[0]['unlocked'])

    def test_apagar_la_reanudacion_devuelve_el_comportamiento_viejo(self):
        """Con el ajuste apagado, renovar abre de golpe todo lo que el calendario
        había liberado mientras estuvo vencido. Es lo que pasaba antes."""
        ajustes = AjustesAula.obtener()
        ajustes.reanudar_goteo = False
        ajustes.save()

        self._comprada_hace(300)
        self._terminar(4)
        self.membresia.expires_at = timezone.now() + timedelta(days=365)
        self.membresia.save(update_fields=['expires_at'])

        acceso = get_course_access(self.membresia)
        self.assertTrue(acceso[4]['unlocked'])
        self.assertEqual(acceso[5]['lock_reason'], 'previo',
                         'ya no lo traba la fecha, solo terminar el anterior')

    def test_una_compra_real_de_renovacion_reancla_el_goteo(self):
        """El camino de verdad: una orden pagada que entra por
        grant_access_for_order. Los tests de arriba llaman a reanudar_goteo a
        mano; este verifica que además esté enchufado donde corresponde, que es
        donde se rompería sin que nadie se diera cuenta.
        """
        from catalog.models import Product
        from lms.services import grant_access_for_order
        from payments.models import Order

        producto = Product.objects.create(
            name='Kit Inicial', slug='kit-inicial', price=10000, access_months=12)
        producto.categories.add(self.categoria)

        self._comprada_hace(300)
        self._terminar(4)
        self._vencer()

        orden = Order.objects.create(
            total_amount=10000, status='PAID',
            customer_email=self.usuario.email,
        )
        orden.products.add(producto)
        grant_access_for_order(orden)

        self.membresia.refresh_from_db()
        self.assertTrue(self.membresia.is_active, 'la compra la reactivó')

        acceso = get_course_access(self.membresia)
        self.assertEqual(len([a for a in acceso if a['unlocked']]), 5,
                         'retoma donde quedó y no le entrega los 10 de una')
        self.assertEqual(acceso[7]['unlock_date'],
                         timezone.localdate() + timedelta(days=7))

    def test_renovar_antes_de_que_se_venza_no_toca_el_calendario(self):
        """Extender una suscripción que sigue viva no es reactivar: el alumno
        nunca perdió el acceso, así que su calendario tiene que seguir igual."""
        from catalog.models import Product
        from lms.services import grant_access_for_order
        from payments.models import Order

        producto = Product.objects.create(
            name='Kit Inicial', slug='kit-inicial', price=10000, access_months=12)
        producto.categories.add(self.categoria)

        self._comprada_hace(300)
        self._terminar(4)
        # Sigue vigente (setUp la dejó con 30 días por delante).

        orden = Order.objects.create(
            total_amount=10000, status='PAID', customer_email=self.usuario.email)
        orden.products.add(producto)
        grant_access_for_order(orden)

        self.mc.refresh_from_db()
        self.assertIsNone(self.mc.reanudada_en)
        acceso = get_course_access(self.membresia)
        self.assertTrue(acceso[4]['unlocked'])
        self.assertEqual(acceso[5]['lock_reason'], 'previo',
                         'sus fechas ya estaban cumplidas y siguen estándolo')

    def test_una_pausa_vieja_no_empuja_el_calendario_reanclado(self):
        """Los días de pausa son un acumulado histórico de la membresía. Al
        reanudar se guarda cuántos llevaba, para que una pausa VIEJA no vuelva a
        correr hacia adelante un calendario que ya se reancló a hoy."""
        self.membresia.total_paused_days = 30
        self.membresia.save(update_fields=['total_paused_days'])
        self._comprada_hace(300)
        self._terminar(4)
        self._vencer()
        self._renovar()

        acceso = get_course_access(self.membresia)
        self.assertEqual(acceso[7]['unlock_date'],
                         timezone.localdate() + timedelta(days=7),
                         'los 30 días de pausa vieja no deben mover el calendario nuevo')
