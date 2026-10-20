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


def filtrar(queryset, consulta, campos, telefonos=()):
    """Deja en el queryset solo las filas que calzan con la consulta.

    `campos` y `telefonos` son rutas de campo (ej. 'user__email', 'phone').
    """
    if not normalizar(consulta).strip():
        return queryset
    ids = [
        fila[0]
        for fila in queryset.values_list('pk', *campos, *telefonos)
        if coincide(consulta, fila[1:1 + len(campos)], fila[1 + len(campos):])
    ]
    return queryset.filter(pk__in=ids)
