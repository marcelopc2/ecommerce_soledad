"""¿Pueden salir correos a clientes ahora? La única respuesta, para todos los envíos.

Dos frenos, los dos tienen que estar sueltos:
1. settings.ENVIAR_CORREOS: solo en el dominio de verdad (ingenioblocks.com).
2. La pausa del panel (AjustesCorreos): para soltarlos recién después del
   anuncio de la tienda.
Al equipo (cuentas de gestión) le llegan igual: no son clientes.
"""
from django.conf import settings


def correos_a_clientes():
    if not settings.ENVIAR_CORREOS:
        return False
    from .models import AjustesCorreos
    return not AjustesCorreos.obtener().pausar_correos_a_clientes
