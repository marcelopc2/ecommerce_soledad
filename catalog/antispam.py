"""Filtro de spam del formulario de contacto, sin captcha.

Un captcha también lo sufren las familias que escriben de verdad. Estos robots
se delatan solos, así que se los reconoce por lo que hacen:

1. Llenan el campo trampa: un campo invisible que una persona nunca ve ni toca.
2. Mandan el formulario en menos de 3 segundos desde que se abrió la página.
3. Escriben texto al azar con mayúsculas en medio de la palabra
   ("hljLYiHOcVqhZhTykY"), que ningún nombre ni mensaje real tiene.

Lo que se marca como spam igual se guarda (por si alguna vez hay un falso
positivo, se ve en Mensajes → Spam), pero no avisa a nadie: ni correo ni Telegram.
"""
import re
import time

SEGUNDOS_MINIMOS = 3

_PALABRA = re.compile(r'[A-Za-zÁÉÍÓÚÑáéíóúñ]+')


def _al_azar(texto):
    """Una palabra larga con 3 o más mayúsculas metidas en medio (no al inicio)."""
    for palabra in _PALABRA.findall(texto or ''):
        if len(palabra) < 8:
            continue
        internas = sum(1 for c in palabra[1:] if c.isupper())
        minusculas = sum(1 for c in palabra if c.islower())
        if internas >= 3 and minusculas >= 3:
            return True
    return False


def motivo_de_spam(datos):
    """Por qué parece spam, o '' si parece de una persona.

    `datos` es lo que mandó el formulario (request.data).
    """
    if (datos.get('sitio_web') or '').strip():
        return 'llenó el campo trampa'
    abierto = datos.get('t')
    if abierto:
        try:
            if time.time() - int(abierto) / 1000 < SEGUNDOS_MINIMOS:
                return 'se mandó en menos de 3 segundos'
        except (TypeError, ValueError):
            return 'marca de tiempo inválida'
    for campo in ('nombre', 'apellido', 'comentarios'):
        if _al_azar(datos.get(campo)):
            return f'texto al azar en {campo}'
    return ''
