"""El editor de los correos masivos: HTML limpio, con estilo, y la prueba al equipo.

El HTML lo escribe (o lo pega) quien administra, y sale a cientos de bandejas:
lo que importa es que no se cuele nada que no sea formato, que se vea con la
tipografía de la marca aunque el programa de correo ignore las hojas de
estilo, y que la prueba llegue SOLO a las cuentas de gestión.
"""
import io
import shutil
import tempfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from lms.models import Membership

from . import envio as masivos
from . import html_correo
from .models import EnvioMasivo

User = get_user_model()


class LimpiezaTests(TestCase):
    def test_se_van_los_scripts_los_eventos_y_los_enlaces_peligrosos(self):
        sucio = ('<p onclick="robar()">Hola</p><script>alert(1)</script>'
                 '<a href="javascript:alert(1)">x</a><iframe src="https://malo.cl"></iframe>'
                 '<p style="position:absolute;display:none;color:red">oculto</p>')
        limpio = html_correo.limpiar(sucio)
        for malo in ('onclick', '<script', 'javascript:', '<iframe', 'position', 'display'):
            self.assertNotIn(malo, limpio)
        self.assertIn('color:red', limpio)

    def test_se_conservan_los_formatos(self):
        limpio = html_correo.limpiar(
            '<h2>Título</h2><p style="text-align:center"><strong>a</strong> <em>b</em> <u>c</u></p>'
            '<ul><li>uno</li></ul><blockquote>cita</blockquote>'
            '<a href="https://ingenioblocks.com">web</a><img src="https://x.cl/a.png" alt="foto">')
        for bueno in ('<h2>', 'text-align:center', '<strong>', '<em>', '<u>', '<li>', '<blockquote>',
                      'href="https://ingenioblocks.com"', 'src="https://x.cl/a.png"'):
            self.assertIn(bueno, limpio)

    def test_cada_etiqueta_lleva_su_estilo_escrito_y_gana_el_de_quien_escribe(self):
        html = html_correo.con_estilos(html_correo.limpiar('<p style="color:red">x</p><h2>t</h2>'))
        self.assertIn('font-family:Arial', html)
        self.assertRegex(html, r'<p style="[^"]*color:#314158;[^"]*color:red"')

    def test_texto_plano(self):
        texto = html_correo.a_texto(html_correo.limpiar(
            '<h2>Hola</h2><p>Mira <a href="https://ib.cl">esto</a></p><ul><li>a</li><li>b</li></ul>'))
        self.assertEqual(texto, 'Hola\n\nMira esto (https://ib.cl)\n\n- a\n- b')


class FormularioTests(TestCase):
    def setUp(self):
        self.jefa = User.objects.create_user(username='jefa@ib.cl', email='jefa@ib.cl', is_staff=True)
        User.objects.create_user(username='socia@ib.cl', email='socia@ib.cl', is_staff=True)
        cliente = User.objects.create_user(username='cliente@correo.cl', email='cliente@correo.cl')
        Membership.objects.create(user=cliente, expires_at=timezone.now() + timedelta(days=30))
        self.client.force_login(self.jefa)

    def crear(self, **extra):
        datos = {'asunto': 'Novedades', 'audiencia': 'TODOS', 'boton_texto': '', 'boton_url': '',
                 'cuerpo_html': '<h2>Hola</h2><p>Texto <script>x()</script><strong>fuerte</strong></p>'}
        datos.update(extra)
        return self.client.post(reverse('panel:correo_new'), datos)

    def test_guarda_el_html_limpio_y_su_texto(self):
        self.crear()
        e = EnvioMasivo.objects.get()
        self.assertNotIn('script', e.cuerpo_html)
        self.assertIn('<strong>fuerte</strong>', e.cuerpo_html)
        self.assertEqual(e.cuerpo, 'Hola\n\nTexto fuerte')

    def test_vacio_no_se_acepta(self):
        r = self.crear(cuerpo_html='<p><br></p>')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(EnvioMasivo.objects.exists())

    @override_settings(ENVIAR_CORREOS=False)
    def test_guardar_y_enviar_prueba_llega_solo_a_los_administradores(self):
        self.crear(accion='enviar', audiencia='PRUEBA')
        destinos = sorted(d for m in mail.outbox for d in m.to)
        self.assertEqual(destinos, ['jefa@ib.cl', 'socia@ib.cl'])
        self.assertTrue(all(m.subject.startswith('[PRUEBA]') for m in mail.outbox))
        html = mail.outbox[0].alternatives[0][0]
        self.assertIn('<h2 style="', html)
        self.assertNotIn('script', html)
        self.assertIn('Texto fuerte', mail.outbox[0].body)
        self.assertTrue(EnvioMasivo.objects.get().prueba_al_dia)

    def test_guardar_y_enviar_a_clientes_pasa_por_la_confirmacion(self):
        r = self.crear(accion='enviar', audiencia='TODOS')
        e = EnvioMasivo.objects.get()
        self.assertRedirects(r, reverse('panel:correo_confirmar', args=[e.pk]), fetch_redirect_response=False)
        self.assertEqual(mail.outbox, [])
        self.assertEqual(e.estado, EnvioMasivo.BORRADOR)

    def test_la_prueba_es_la_opcion_marcada_y_no_se_puede_encolar(self):
        self.assertEqual(EnvioMasivo._meta.get_field('audiencia').default, EnvioMasivo.PRUEBA)
        e = EnvioMasivo.objects.create(asunto='x', cuerpo='y', audiencia=EnvioMasivo.PRUEBA)
        self.assertIsNotNone(masivos.motivo_para_no_enviar(e))
        self.assertEqual(sorted(masivos.correos_de_la_audiencia(EnvioMasivo.PRUEBA)), ['jefa@ib.cl', 'socia@ib.cl'])

    def test_un_borrador_antiguo_se_abre_en_el_editor(self):
        e = EnvioMasivo.objects.create(asunto='Viejo', cuerpo='Uno\n\nDos & tres', audiencia='TODOS')
        r = self.client.get(reverse('panel:correo_edit', args=[e.pk]))
        self.assertContains(r, '&lt;p&gt;Uno&lt;/p&gt;&lt;p&gt;Dos &amp;amp; tres&lt;/p&gt;')

    def test_un_borrador_antiguo_se_sigue_mandando_como_antes(self):
        e = EnvioMasivo.objects.create(asunto='Viejo', cuerpo='Uno\n\nDos', audiencia='TODOS')
        self.assertEqual(masivos.contexto_de(e)['parrafos'], ['Uno', 'Dos'])


class ImagenTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        jefa = User.objects.create_user(username='jefa@ib.cl', email='jefa@ib.cl', is_staff=True)
        self.client.force_login(jefa)

    def png(self):
        buf = io.BytesIO()
        Image.new('RGB', (4, 4), 'purple').save(buf, 'PNG')
        return SimpleUploadedFile('foto.png', buf.getvalue(), content_type='image/png')

    def test_sube_una_imagen_y_devuelve_su_direccion(self):
        with self.settings(MEDIA_ROOT=self.media, BACKEND_PUBLIC_URL='https://pre.ib.cl'):
            r = self.client.post(reverse('panel:correo_imagen'), {'imagen': self.png()})
        self.assertEqual(r.status_code, 200)
        self.assertRegex(r.json()['url'], r'^https://pre\.ib\.cl/.*correos/[0-9a-f]{32}\.png$')

    def test_un_archivo_que_no_es_imagen_se_rechaza(self):
        falso = SimpleUploadedFile('virus.png', b'<script>alert(1)</script>', content_type='image/png')
        with self.settings(MEDIA_ROOT=self.media):
            r = self.client.post(reverse('panel:correo_imagen'), {'imagen': falso})
        self.assertEqual(r.status_code, 400)

    def test_solo_el_equipo_puede_subir(self):
        self.client.logout()
        with self.settings(MEDIA_ROOT=self.media):
            r = self.client.post(reverse('panel:correo_imagen'), {'imagen': self.png()})
        self.assertNotEqual(r.status_code, 200)


class PlantillasTests(TestCase):
    def test_cada_plantilla_pasa_la_limpieza_sin_perder_nada(self):
        from .plantillas import plantillas
        for p in plantillas():
            limpio = html_correo.limpiar(p['html'])
            for pedazo in ('<img src="', '<h2', 'color:#8200db', '<blockquote>'):
                self.assertIn(pedazo, limpio, (p['clave'], pedazo))
            self.assertIn('/static/comunicaciones/plantillas/', limpio)
            self.assertTrue(p['asunto'] and p['boton_texto'] and p['boton_url'].startswith('http'))

    def test_el_formulario_las_ofrece(self):
        jefa = User.objects.create_user(username='jefa@ib.cl', email='jefa@ib.cl', is_staff=True)
        self.client.force_login(jefa)
        r = self.client.get(reverse('panel:correo_new'))
        self.assertContains(r, 'Cargar plantilla')
        self.assertContains(r, 'id="correo-plantillas"')
        self.assertNotContains(r, 'Cómo se envía')


class HtmlDelEditorTests(TestCase):
    """Lo que devuelve Quill 2 por dentro (visto con el editor de verdad)."""

    def test_las_vinetas_no_salen_numeradas(self):
        quill = ('<ol><li data-list="bullet"><span class="ql-ui" contenteditable="false"></span>uno</li>'
                 '<li data-list="bullet"><span class="ql-ui" contenteditable="false"></span>dos</li></ol>'
                 '<ol><li data-list="ordered"><span class="ql-ui" contenteditable="false"></span>tres</li></ol>')
        limpio = html_correo.limpiar(quill)
        self.assertIn('<ul><li>uno</li><li>dos</li></ul>', limpio)
        self.assertIn('<ol><li>tres</li></ol>', limpio)
        self.assertNotIn('ql-ui', limpio)

    def test_los_nbsp_vuelven_a_ser_espacios(self):
        limpio = html_correo.limpiar('<p>Hola&nbsp;a&nbsp;todos</p>')
        self.assertEqual(limpio, '<p>Hola a todos</p>')


class PlantillasSinFotosDeNinosTests(TestCase):
    """Solo hay permiso para usar fotos de niños en la página, no en correos."""

    def test_las_plantillas_usan_solo_los_banners_graficos(self):
        import re
        from .plantillas import plantillas
        permitidas = {'novedad.jpg', 'modelos.jpg', 'promocion.jpg'}
        for p in plantillas():
            usadas = set(re.findall(r'/plantillas/([\w.-]+)"', p['html']))
            self.assertTrue(usadas and usadas <= permitidas, (p['clave'], usadas))
