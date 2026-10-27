"""{% menu_panel as menu %}: el menú del panel según la pantalla actual (ver panel/navegacion.py)."""
from django import template

from panel.navegacion import menu_para, pestanas_de

register = template.Library()


@register.simple_tag(takes_context=True)
def menu_panel(context):
    request = context.get('request')
    return menu_para(context.get('section'), getattr(request, 'user', None))


@register.filter
def pestanas(menu):
    return pestanas_de(menu)
