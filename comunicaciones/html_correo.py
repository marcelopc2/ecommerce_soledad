"""El HTML de un correo masivo: limpiarlo, darle estilo y sacarle el texto.

El editor del panel produce HTML. Antes de guardarlo o mandarlo pasa por acá:

1. `limpiar`: deja solo lo que es formato (negritas, títulos, listas, enlaces,
   imágenes, colores, alineación). Un <script>, un formulario o un
   `onclick=` se van. No es desconfianza de quien escribe: es que un correo
   con eso lo marcan como peligroso Gmail y Outlook, y un HTML pegado desde
   otro lado trae esas cosas sin que se note.

2. `con_estilos`: los programas de correo ignoran las hojas de estilo, así que
   cada etiqueta lleva su estilo escrito adentro (la tipografía y los colores
   de la marca, los mismos de las demás plantillas).

3. `a_texto`: la versión de texto plano que viaja junto al HTML. Los filtros
   de spam castigan los correos que vienen solo en HTML.
"""
import html
import re

import nh3

ETIQUETAS = {
    'p', 'br', 'strong', 'b', 'em', 'i', 'u', 's', 'a', 'h1', 'h2', 'h3',
    'ul', 'ol', 'li', 'blockquote', 'img', 'span', 'hr',
}
ATRIBUTOS = {
    'a': {'href', 'title'},
    'img': {'src', 'alt', 'width'},
    '*': {'style'},
}
# Solo lo que sirve para dar formato. Un `position` o un `display:none` se
# van: con eso se esconde texto, que es un truco típico del spam.
ESTILOS = {'color', 'background-color', 'text-align', 'font-weight', 'font-style', 'text-decoration'}

FUENTE = 'font-family:Arial,Helvetica,sans-serif;'
BASE = {
    'p': FUENTE + 'margin:0 0 14px;font-size:15px;line-height:1.75;color:#314158;',
    'h1': FUENTE + 'margin:22px 0 12px;font-size:26px;line-height:1.3;color:#2f0053;font-weight:bold;',
    'h2': FUENTE + 'margin:20px 0 10px;font-size:21px;line-height:1.35;color:#2f0053;font-weight:bold;',
    'h3': FUENTE + 'margin:18px 0 8px;font-size:17px;line-height:1.4;color:#8200db;font-weight:bold;',
    'ul': FUENTE + 'margin:0 0 14px;padding-left:22px;font-size:15px;line-height:1.75;color:#314158;',
    'ol': FUENTE + 'margin:0 0 14px;padding-left:22px;font-size:15px;line-height:1.75;color:#314158;',
    'li': 'margin:0 0 6px;',
    'blockquote': FUENTE + ('margin:0 0 14px;padding:12px 18px;border-left:4px solid #8200db;'
                            'background-color:#f8f4fe;border-radius:8px;font-size:15px;'
                            'line-height:1.7;color:#2f0053;'),
    'a': 'color:#8200db;font-weight:bold;text-decoration:underline;',
    'img': 'display:block;max-width:100%;height:auto;border:0;border-radius:10px;margin:0 auto 14px;',
    'hr': 'border:0;border-top:1px solid #ece5f4;margin:22px 0;',
}


_LISTA_QUILL = re.compile(r'<ol>((?:\s*<li[^>]*data-list="bullet"[^>]*>.*?</li>)+\s*)</ol>', re.S)


def _desde_quill(crudo):
    """Arregla el HTML interno del editor, por si llega así (borradores
    guardados antes de que el panel mandara el HTML de verdad):

    - Quill guarda las viñetas como <ol><li data-list="bullet">; sin el
      atributo, que la limpieza quita, salían como lista numerada.
    - `&nbsp;` en vez de espacios hace que el correo no corte las líneas.
    """
    t = (crudo or '').replace('&nbsp;', ' ').replace('\xa0', ' ')
    t = _LISTA_QUILL.sub(lambda m: '<ul>' + m.group(1) + '</ul>', t)
    return re.sub(r'<span class="ql-ui"[^>]*>\s*</span>', '', t)


def limpiar(crudo):
    """Solo formato: sin scripts, sin eventos, sin estilos raros."""
    limpio = nh3.clean(
        _desde_quill(crudo),
        tags=ETIQUETAS,
        attributes=ATRIBUTOS,
        url_schemes={'http', 'https', 'mailto'},
        filter_style_properties=ESTILOS,
        link_rel='noopener noreferrer',
        strip_comments=True,
    )
    # Un párrafo vacío (lo que deja el editor al apretar Enter de más) se ve
    # como un hueco grande en el correo.
    return re.sub(r'<p>(\s|<br>)*</p>', '', limpio).strip()


_ABRE = re.compile(r'<(' + '|'.join(BASE) + r')(\s[^>]*)?>')
_ESTILO = re.compile(r'style="([^"]*)"')


def _estilar(m):
    etiqueta, attrs = m.group(1), m.group(2) or ''
    base = BASE[etiqueta]
    propio = _ESTILO.search(attrs)
    if propio:
        # Lo que eligió quien escribe (un color, centrar) va DESPUÉS de lo de la
        # marca, para que gane.
        attrs = _ESTILO.sub(lambda s: f'style="{base}{s.group(1)}"', attrs, count=1)
    else:
        attrs = f'{attrs} style="{base}"'
    if etiqueta == 'a' and 'target=' not in attrs:
        attrs += ' target="_blank"'
    cierre = ' /' if etiqueta in ('img', 'hr') and attrs.endswith('/') else ''
    return f'<{etiqueta}{attrs}{cierre}>'


def con_estilos(limpio):
    """El HTML ya limpio, con el estilo de la marca escrito en cada etiqueta."""
    return _ABRE.sub(_estilar, limpio)


def a_texto(limpio):
    """Versión de texto plano: párrafos separados, enlaces con su dirección."""
    t = limpio
    t = re.sub(r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
               lambda m: m.group(2) if m.group(1) in m.group(2) else f'{m.group(2)} ({m.group(1)})', t)
    t = re.sub(r'<img\s[^>]*alt="([^"]+)"[^>]*>', r'[\1]\n\n', t)
    t = re.sub(r'<li[^>]*>', '- ', t)
    t = re.sub(r'<br\s*/?>|</li>', '\n', t)
    t = re.sub(r'</(p|h1|h2|h3|blockquote|ul|ol)>|<hr[^>]*>', '\n\n', t)
    t = re.sub(r'<[^>]+>', '', t)
    t = html.unescape(t)
    t = re.sub(r'[ \t]+\n', '\n', t)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()


def desde_texto(texto):
    """Un cuerpo viejo, escrito como texto, pasado a HTML para el editor."""
    parrafos = [p.strip() for p in (texto or '').replace('\r\n', '\n').split('\n\n') if p.strip()]
    return ''.join('<p>' + html.escape(p).replace('\n', '<br>') + '</p>' for p in parrafos)
