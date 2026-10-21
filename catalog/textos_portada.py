"""Los textos fijos de la portada que se editan desde el panel.

Los originales viven en textos_portada.json, y el Aula tiene una copia idéntica
(frontend/src/textosPortada.json) para mostrar la portada igual si la API no
responde; una prueba avisa si las dos se desalinean. En la base se guarda solo
lo que la clienta cambió: un campo vacío vuelve al texto original.

Para agregar un texto editable: sumarlo a los dos JSON, a SECCIONES y usarlo en
Landing.jsx. No hace falta migración.
"""
import json
from pathlib import Path

ORIGINALES = json.loads((Path(__file__).with_name('textos_portada.json')).read_text(encoding='utf-8'))

LINEA, TEXTO, EMAIL, URL = 'linea', 'texto', 'email', 'url'

#: Cómo se muestran en el panel: (sección, ícono, id, [(clave, etiqueta, tipo)]).
#: El id es el que usa la vista previa para saltar a esa parte de la portada
#: (ver SECCIONES_VISTA_PREVIA en frontend/src/textos.jsx).
SECCIONES = [
    ('Portada principal', 'bi-house-door', 'hero', [
        ('hero_etiqueta', 'Etiqueta', LINEA),
        ('hero_titulo', 'Título grande', TEXTO),
        ('hero_texto', 'Texto', TEXTO),
        ('hero_boton', 'Botón', LINEA),
    ]),
    ('Cómo funciona', 'bi-signpost-2', 'como', [
        ('como_etiqueta', 'Etiqueta', LINEA),
        ('como_titulo', 'Título', LINEA),
        ('como_boton', 'Botón', LINEA),
    ]),
    ('Beneficios', 'bi-stars', 'beneficios', [
        ('beneficios_etiqueta', 'Etiqueta', LINEA),
        ('beneficios_titulo', 'Título', LINEA),
        ('beneficios_texto', 'Texto', TEXTO),
        ('beneficios_recuadro_titulo', 'Título del recuadro de modelos', LINEA),
        ('beneficios_recuadro_texto', 'Texto del recuadro de modelos', TEXTO),
    ]),
    ('Productos', 'bi-box-seam', 'productos', [
        ('productos_titulo', 'Título', LINEA),
        ('productos_texto', 'Texto', TEXTO),
    ]),
    ('Quiénes somos', 'bi-people', 'quienes', [
        ('quienes_etiqueta', 'Etiqueta', LINEA),
        ('quienes_titulo', 'Título', LINEA),
        ('quienes_texto', 'Texto', TEXTO),
    ]),
    ('Testimonios y preguntas', 'bi-chat-quote', 'testimonios', [
        ('testimonios_etiqueta', 'Etiqueta de testimonios', LINEA),
        ('testimonios_titulo', 'Título de testimonios', LINEA),
        ('faq_etiqueta', 'Etiqueta de preguntas', LINEA),
        ('faq_titulo', 'Título de preguntas', LINEA),
    ]),
    ('Contacto', 'bi-envelope', 'contacto', [
        ('contacto_etiqueta', 'Etiqueta', LINEA),
        ('contacto_titulo', 'Título', LINEA),
        ('contacto_email', 'Correo', EMAIL),
        ('contacto_telefono', 'Teléfono', LINEA),
        ('contacto_ubicacion', 'Ubicación', LINEA),
        ('contacto_texto', 'Texto sobre el formulario', TEXTO),
    ]),
    ('Pie de página', 'bi-layout-text-window-reverse', 'pie', [
        ('pie_texto', 'Texto', LINEA),
        ('instagram_url', 'Instagram', URL),
        ('facebook_url', 'Facebook', URL),
        ('youtube_url', 'YouTube', URL),
    ]),
]

CAMPOS = {clave: (etiqueta, tipo) for _, _, _, campos in SECCIONES for clave, etiqueta, tipo in campos}
assert set(CAMPOS) == set(ORIGINALES), 'SECCIONES y textos_portada.json no tienen las mismas claves'


def textos_actuales():
    """Los originales con lo que la clienta haya cambiado encima."""
    from .models import TextosPortada
    guardados = TextosPortada.obtener().textos or {}
    return {clave: guardados.get(clave) or original for clave, original in ORIGINALES.items()}


def fechas_sugeridas(hoy=None):
    """Cuándo conviene prender cada temporada: la próxima vez que toque (o la
    que está corriendo). Son sugerencias para el panel, nada se prende solo.

    Las de fecha móvil se calculan: Pascua, y los domingos del Día de la Madre
    (2º de mayo), del Padre (3º de junio) y del Niño (2º de agosto). Las
    vacaciones de invierno cambian cada año según el Mineduc: es aproximada.
    """
    from datetime import date, timedelta
    from dateutil.easter import easter
    from django.utils import timezone

    hoy = hoy or timezone.localdate()

    def domingo(anio, mes, n):
        d = date(anio, mes, 1)
        d += timedelta(days=(6 - d.weekday()) % 7)
        return d + timedelta(weeks=n - 1)

    def rangos(anio):
        pascua = easter(anio)
        madre, padre, nino = domingo(anio, 5, 2), domingo(anio, 6, 3), domingo(anio, 8, 2)
        return [
            ('ano_nuevo', date(anio, 12, 26), date(anio + 1, 1, 2)),
            ('verano', date(anio, 1, 3), date(anio, 2, 28)),
            ('san_valentin', date(anio, 2, 7), date(anio, 2, 14)),
            ('vuelta_clases', date(anio, 2, 20), date(anio, 3, 15)),
            ('pascua', pascua - timedelta(days=7), pascua),
            ('dia_madre', madre - timedelta(days=10), madre),
            ('dia_padre', padre - timedelta(days=10), padre),
            ('invierno', date(anio, 6, 22), date(anio, 7, 17)),
            ('dia_nino', nino - timedelta(days=14), nino),
            ('fiestas_patrias', date(anio, 9, 1), date(anio, 9, 20)),
            ('halloween', date(anio, 10, 15), date(anio, 11, 1)),
            ('navidad', date(anio, 12, 1), date(anio, 12, 26)),
        ]

    proximas = {}
    for anio in (hoy.year - 1, hoy.year, hoy.year + 1):
        for tema, desde, hasta in rangos(anio):
            if hasta >= hoy and tema not in proximas:
                proximas[tema] = (desde, hasta)
    from .models import TextosPortada
    etiquetas = dict(TextosPortada.TEMAS)
    salida = [(tema, etiquetas[tema], desde, hasta) for tema, (desde, hasta) in proximas.items()]
    return sorted(salida, key=lambda x: x[2])


def portada_para_el_sitio(request=None):
    """Lo que pide la portada: los textos, las fotos (None = la original) y el
    tema de temporada que corresponde hoy."""
    from .models import TextosPortada
    fila = TextosPortada.obtener()

    def url(archivo):
        if not archivo:
            return None
        return request.build_absolute_uri(archivo.url) if request else archivo.url

    return {
        **textos_actuales(),
        'hero_imagen': url(fila.hero_imagen),
        'quienes_imagen': url(fila.quienes_imagen),
        'tema': fila.tema_vigente(),
    }
