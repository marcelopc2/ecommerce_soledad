"""Los filtros de la lista de Alumnos.

El caso que motiva estas pruebas: los filtros se COMBINAN, así que basta venir
de "0 pausadas" y marcar "legado" para quedarse sin resultados. La pantalla
decía entonces "aún no hay membresías" -aunque hubiera 296- y quien lo veía
concluía que el filtro estaba roto.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from lms.models import Membership

User = get_user_model()


class FiltrosTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin@x.cl', email='admin@x.cl',
            password='clave-larga-1234', is_staff=True)
        self.client.force_login(self.admin)

        def alumno(correo, **extra):
            u = User.objects.create_user(username=correo, email=correo)
            datos = {'expires_at': timezone.now() + timedelta(days=30)}
            datos.update(extra)
            return Membership.objects.create(user=u, **datos)

        self.migrado = alumno('migrado@b.cl', es_legado=True)
        self.abierto = alumno('abierto@b.cl', es_legado=True, sin_vencimiento=True)
        self.nuevo = alumno('nuevo@b.cl')
        self.vencido = alumno('vencido@b.cl', es_legado=True,
                              expires_at=timezone.now() - timedelta(days=5))

    def _correos(self, **params):
        r = self.client.get(reverse('panel:memberships'), params)
        cuerpo = r.content.decode()
        return {c for c in ('migrado@b.cl', 'abierto@b.cl', 'nuevo@b.cl',
                            'vencido@b.cl') if c in cuerpo}

    # --- legado ---

    def test_legado_muestra_los_migrados(self):
        self.assertEqual(self._correos(legado='1'),
                         {'migrado@b.cl', 'abierto@b.cl', 'vencido@b.cl'})

    def test_sin_filtro_salen_todos(self):
        self.assertEqual(len(self._correos()), 4)

    # --- sin vencimiento ---

    def test_el_filtro_sin_vencimiento_aisla_las_abiertas(self):
        self.assertEqual(self._correos(sin_venc='1'), {'abierto@b.cl'})

    def test_la_pastilla_se_muestra_aunque_no_haya_ninguna(self):
        """La de "pausadas" también aparece en 0. Esconderla cuando no hay
        ninguna deja a quien la busca pensando que el filtro no existe."""
        Membership.objects.update(sin_vencimiento=False)
        r = self.client.get(reverse('panel:memberships'))
        self.assertContains(r, 'sin vencimiento')

    def test_la_pastilla_aparece_si_hay_alguna(self):
        r = self.client.get(reverse('panel:memberships'))
        self.assertContains(r, 'sin vencimiento')

    # --- la combinación que causó el reclamo ---

    def test_los_filtros_se_combinan(self):
        self.assertEqual(self._correos(estado='vencida', legado='1'),
                         {'vencido@b.cl'})

    def test_una_combinacion_sin_resultados_lo_dice_y_no_miente(self):
        """Antes decía "aún no hay membresías" con 296 en la base."""
        r = self.client.get(reverse('panel:memberships'),
                            {'estado': 'pausada', 'legado': '1'})
        self.assertContains(r, 'Ningún alumno cumple con los filtros')
        self.assertNotContains(r, 'Aún no hay membresías')

    def test_con_la_base_vacia_de_verdad_sí_dice_que_no_hay(self):
        Membership.objects.all().delete()
        r = self.client.get(reverse('panel:memberships'))
        self.assertContains(r, 'Aún no hay membresías')

    # --- los filtros no se pisan entre ellos ---

    def test_cambiar_de_estado_conserva_los_otros_filtros(self):
        """Las pastillas de estado llevan `legado` y `sin_venc` en su enlace: si
        no, marcar un estado los borraba en silencio."""
        r = self.client.get(reverse('panel:memberships'),
                            {'legado': '1', 'sin_venc': '1'})
        cuerpo = r.content.decode()
        self.assertIn('legado=1', cuerpo)
        self.assertIn('sin_venc=1', cuerpo)
