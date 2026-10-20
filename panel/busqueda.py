"""Búsqueda "como la piensa una persona" para las listas del panel.

Lo que escribe quien busca casi nunca calza letra por letra con lo guardado:

- sin tilde ("tomas" tiene que encontrar a "Tomás", "munoz" a "Muñoz");
- nombre y apellido juntos, en cualquier orden y repartidos entre campos
  ("rojas tomas" encuentra al alumno Tomás de la apoderada Catalina Rojas);
- un teléfono escrito como sea ("7123 4581", "+56 9 7123 4581", "971234581").

Cada palabra tiene que aparecer en ALGÚN campo; no hace falta que estén
juntas. Se resuelve en Python y no en la base de datos porque la comparación
sin tildes en Postgres pide una extensión (unaccent) que hay que instalar a
mano en el servidor. Con cientos de alumnos es instantáneo.
"""
import re
import unicodedata


def normalizar(texto):
    t = unicodedata.normalize('NFKD', str(texto or '').lower())
    return ''.join(c for c in t if not unicodedata.combining(c))


def _digitos(texto):
    return re.sub(r'\D', '', texto or '')


def coincide(consulta, campos, telefonos=()):
    """¿Todas las palabras de la consulta aparecen en estos campos?"""
    palabras = normalizar(consulta).split()
    if not palabras:
        return True
    texto = normalizar(' '.join(str(c or '') for c in campos))
    digitos_tel = ' '.join(_digitos(t) for t in telefonos)
    # El teléfono escrito con espacios llega en pedazos ("7123 4581"): se
    # prueba también la consulta entera, solo con sus dígitos.
    tel_entero = _digitos(consulta)
    if len(tel_entero) >= 6 and tel_entero in digitos_tel.replace(' ', ''):
        return True
    for p in palabras:
        if p in texto:
            continue
        d = _digitos(p)
        if len(d) >= 3 and d in digitos_tel:
            continue
        return False
    return True


MESES = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
         'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre')


def texto_de_fecha(valor):
    """Una fecha escrita de todas las formas en que alguien la buscaría:
    20-10-2026, 20/10/2026, 20-10, 20/10, "20 de octubre de 2026", "octubre 2026"."""
    if not valor:
        return ''
    from datetime import datetime
    from django.utils import timezone
    if isinstance(valor, datetime):
        if timezone.is_aware(valor):
            valor = timezone.localtime(valor)
        valor = valor.date()
    mes = MESES[valor.month - 1]
    return (f'{valor:%d-%m-%Y} {valor:%d/%m/%Y} {valor:%d-%m} {valor:%d/%m} {valor:%Y-%m-%d} '
            f'{valor.day} de {mes} de {valor.year} {mes} {valor.year}')


def filtrar(queryset, consulta, campos, telefonos=(), fechas=(), etiquetas=None, extra=()):
    """Deja en el queryset solo las filas que calzan con la consulta.

    `campos`, `telefonos` y `fechas` son rutas de campo (ej. 'user__email',
    'phone', 'expires_at'). `etiquetas(fila)` puede sumar palabras calculadas,
    como el estado ("vencida"); recibe la fila como dict, con los `extra`
    que necesite leer.
    """
    if not normalizar(consulta).strip():
        return queryset
    rutas = ('pk', *campos, *telefonos, *fechas, *extra)
    ids = []
    for fila in queryset.values(*rutas):
        textos = [fila[c] for c in campos]
        textos += [texto_de_fecha(fila[f]) for f in fechas]
        if etiquetas:
            textos.append(etiquetas(fila))
        if coincide(consulta, textos, [fila[t] for t in telefonos]):
            ids.append(fila['pk'])
    return queryset.filter(pk__in=ids)
