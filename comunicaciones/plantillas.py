"""Plantillas para empezar un correo masivo con el estilo de Ingenio Blocks.

Se cargan en el editor del panel con un clic y desde ahí se editan como
cualquier texto. Son solo el CONTENIDO: el logo, el marco y el pie los pone
emails/base.html, igual que en todos los correos.

Usan solo lo que el editor sabe mostrar y html_correo.limpiar deja pasar
(títulos, negritas, colores, listas, citas, imágenes, alineación): una
plantilla con tablas o botones de HTML se desarmaría al abrirla en el editor.

Las fotos son las de la portada, pasadas a JPG (un correo no muestra bien
WEBP) y servidas desde /static/, que no pide sesión: las tiene que poder bajar
el programa de correo de cada cliente.
"""
from django.conf import settings

MORADO = '#8200db'


def _foto(nombre):
    base = (getattr(settings, 'BACKEND_PUBLIC_URL', '') or settings.FRONTEND_URL).rstrip('/')
    return f'{base}/{settings.STATIC_URL.strip("/")}/emails/plantillas/{nombre}'


def plantillas():
    web = settings.FRONTEND_URL.rstrip('/')
    return [
        {
            'clave': 'novedad',
            'nombre': 'Novedad o anuncio',
            'asunto': 'Tenemos novedades en Ingenio Blocks',
            'boton_texto': 'Conoce las novedades',
            'boton_url': web,
            'html': (
                f'<p><img src="{_foto("taladro.jpg")}" alt="Niño armando un taladro de Ingenio Blocks"></p>'
                '<h2>¡Tenemos novedades para tu familia!</h2>'
                '<p>Hola,</p>'
                '<p>Queremos contarte algo que preparamos pensando en los pequeños ingenieros de la casa. '
                'Cambia este texto por la novedad que quieres anunciar.</p>'
                '<blockquote><strong>Lo más importante en una frase:</strong> escribe aquí el dato que '
                'no quieres que se pierdan.</blockquote>'
                '<h3>¿Qué cambia para ti?</h3>'
                '<ul><li>Primer punto de la novedad.</li><li>Segundo punto.</li><li>Tercer punto.</li></ul>'
                '<p>Si tienes dudas, responde este correo y te ayudamos.</p>'
                f'<p>Un abrazo,<br><strong><span style="color:{MORADO}">El equipo de Ingenio Blocks</span></strong></p>'
            ),
        },
        {
            'clave': 'modelos',
            'nombre': 'Modelos nuevos',
            'asunto': '¡Llegaron modelos nuevos para armar!',
            'boton_texto': 'Ir a mis cursos',
            'boton_url': f'{web}/mis-cursos',
            'html': (
                f'<p><img src="{_foto("armando.jpg")}" alt="Niño armando un modelo de Ingenio Blocks"></p>'
                '<h2 style="text-align:center">¡Llegaron modelos nuevos!</h2>'
                '<p style="text-align:center">Este mes sumamos nuevos desafíos al Aula Virtual para seguir '
                'aprendiendo, creando y construyendo jugando.</p>'
                '<h3>Lo que viene</h3>'
                '<ol><li><strong>Nombre del modelo 1:</strong> qué aprende al armarlo.</li>'
                '<li><strong>Nombre del modelo 2:</strong> qué aprende al armarlo.</li>'
                '<li><strong>Nombre del modelo 3:</strong> qué aprende al armarlo.</li></ol>'
                '<blockquote>Recuerda: cada semana se abre un modelo nuevo, y para abrirlo hay que terminar '
                'el anterior. ¡Sin apuro, lo importante es disfrutar armando!</blockquote>'
                f'<p>Un abrazo,<br><strong><span style="color:{MORADO}">El equipo de Ingenio Blocks</span></strong></p>'
            ),
        },
        {
            'clave': 'promocion',
            'nombre': 'Promoción con cupón',
            'asunto': 'Un regalo para tu familia · Ingenio Blocks',
            'boton_texto': 'Ver los kits',
            'boton_url': f'{web}/#kits',
            'html': (
                f'<p><img src="{_foto("kit.jpg")}" alt="Niña con el kit de Ingenio Blocks"></p>'
                '<h2 style="text-align:center">Un regalo para tu familia</h2>'
                '<p style="text-align:center">Por ser parte de Ingenio Blocks, tienes un descuento especial '
                'en tu próxima compra.</p>'
                f'<h1 style="text-align:center"><span style="color:{MORADO}">CODIGO2026</span></h1>'
                '<p style="text-align:center">Escríbelo al pagar y se descuenta solo. '
                '<strong>Válido hasta el DD-MM-AAAA.</strong></p>'
                '<blockquote>Crea el cupón en el panel (Tienda → Cupones) con el mismo código que pongas '
                'aquí, y borra esta nota antes de enviar.</blockquote>'
                f'<p>Un abrazo,<br><strong><span style="color:{MORADO}">El equipo de Ingenio Blocks</span></strong></p>'
            ),
        },
    ]
