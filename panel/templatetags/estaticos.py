"""{% estatico 'panel/panel.css' %}: la dirección del archivo con su versión.

nginx le dice al navegador que guarde los estáticos 30 días. Sin versión, un
cambio de estilos no se ve hasta que vence ese plazo (o hasta que alguien
fuerza la recarga): la página nueva sale con el CSS viejo y se ve rota. Con
`?v=<fecha del archivo>` la dirección cambia en cada despliegue que lo toca, y
el navegador lo pide de nuevo; mientras no cambie, sigue sirviéndolo del caché.
"""
import os

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def estatico(ruta):
    url = static(ruta)
    archivo = finders.find(ruta)
    if archivo:
        url += '?v=%d' % os.path.getmtime(archivo)
    return url
