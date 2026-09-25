"""Direcciones completas para el certificado.

El alumno no abre el certificado navegando a una dirección del sitio: el Aula lo
baja con su token y lo abre como un archivo en memoria del navegador (una
dirección `blob:`), porque un enlace normal no puede mandar el token. Dentro de
esa página una ruta relativa como `/static/...` no apunta a ningún lado, y el
certificado salía en blanco: con el nombre, los desafíos y la fecha flotando
sobre nada. En la vista previa del panel sí se veía, porque ahí la página se
abre desde el sitio y la ruta relativa funciona. Por eso el error no se notó.

Si el navegador bloquea la ventana, el Aula lo descarga como `diploma.html`, y
abierto desde el disco una ruta relativa tampoco sirve. Con la dirección
completa funciona en los tres casos.
"""
from django import template
from django.conf import settings
from django.templatetags.static import static

register = template.Library()


@register.simple_tag(takes_context=True)
def estatico_absoluto(context, ruta):
    """Como `{% static %}`, pero con el dominio adelante.

    Se prefiere BACKEND_PUBLIC_URL, que se configura a mano y no depende de lo
    que informe el proxy: armarla desde la petición daría `http://` si nginx
    dejara de mandar la cabecera del protocolo, y el navegador bloquearía la
    imagen por venir sin cifrar a una página cifrada.
    """
    relativa = static(ruta)
    if relativa.startswith(('http://', 'https://')):
        return relativa
    base = getattr(settings, 'BACKEND_PUBLIC_URL', '')
    if base:
        return base.rstrip('/') + relativa
    request = context.get('request')
    return request.build_absolute_uri(relativa) if request else relativa
