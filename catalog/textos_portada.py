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

#: Cómo se muestran en el panel: (sección, ícono, [(clave, etiqueta, tipo)]).
SECCIONES = [
    ('Portada principal', 'bi-house-door', [
        ('hero_etiqueta', 'Etiqueta', LINEA),
        ('hero_titulo', 'Título grande', TEXTO),
        ('hero_texto', 'Texto', TEXTO),
        ('hero_boton', 'Botón', LINEA),
    ]),
    ('Cómo funciona', 'bi-signpost-2', [
        ('como_etiqueta', 'Etiqueta', LINEA),
        ('como_titulo', 'Título', LINEA),
        ('como_boton', 'Botón', LINEA),
    ]),
    ('Beneficios', 'bi-stars', [
        ('beneficios_etiqueta', 'Etiqueta', LINEA),
        ('beneficios_titulo', 'Título', LINEA),
        ('beneficios_texto', 'Texto', TEXTO),
        ('beneficios_recuadro_titulo', 'Título del recuadro de modelos', LINEA),
        ('beneficios_recuadro_texto', 'Texto del recuadro de modelos', TEXTO),
    ]),
    ('Productos', 'bi-box-seam', [
        ('productos_titulo', 'Título', LINEA),
        ('productos_texto', 'Texto', TEXTO),
    ]),
    ('Quiénes somos', 'bi-people', [
        ('quienes_etiqueta', 'Etiqueta', LINEA),
        ('quienes_titulo', 'Título', LINEA),
        ('quienes_texto', 'Texto', TEXTO),
    ]),
    ('Testimonios y preguntas frecuentes', 'bi-chat-quote', [
        ('testimonios_etiqueta', 'Etiqueta de testimonios', LINEA),
        ('testimonios_titulo', 'Título de testimonios', LINEA),
        ('faq_etiqueta', 'Etiqueta de preguntas', LINEA),
        ('faq_titulo', 'Título de preguntas', LINEA),
    ]),
    ('Contacto', 'bi-envelope', [
        ('contacto_etiqueta', 'Etiqueta', LINEA),
        ('contacto_titulo', 'Título', LINEA),
        ('contacto_email', 'Correo', EMAIL),
        ('contacto_telefono', 'Teléfono', LINEA),
        ('contacto_ubicacion', 'Ubicación', LINEA),
        ('contacto_texto', 'Texto sobre el formulario', TEXTO),
    ]),
    ('Pie de página', 'bi-layout-text-window-reverse', [
        ('pie_texto', 'Texto', LINEA),
        ('instagram_url', 'Instagram', URL),
        ('facebook_url', 'Facebook', URL),
        ('youtube_url', 'YouTube', URL),
    ]),
]

CAMPOS = {clave: (etiqueta, tipo) for _, _, campos in SECCIONES for clave, etiqueta, tipo in campos}
assert set(CAMPOS) == set(ORIGINALES), 'SECCIONES y textos_portada.json no tienen las mismas claves'


def textos_actuales():
    """Los originales con lo que la clienta haya cambiado encima."""
    from .models import TextosPortada
    guardados = TextosPortada.obtener().textos or {}
    return {clave: guardados.get(clave) or original for clave, original in ORIGINALES.items()}
