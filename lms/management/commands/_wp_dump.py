"""Lee un volcado SQL de WordPress hecho con phpMyAdmin.

Se lee el archivo de texto en vez de levantar un MySQL porque el volcado es lo
único que tenemos: el hosting viejo (Kinsta) no da acceso remoto a la base, y
montar un MySQL solo para la migración agrega una pieza más que puede fallar el
día del cambio.

El archivo pesa ~177 MB, así que todo acá va en streaming: nunca se carga
entero en memoria.
"""
import re

BARRA = chr(92)  # la barra invertida


def _partir_fila(texto):
    """Parte el contenido de un `(...)` en sus valores, respetando las comillas.

    No sirve un `split(',')`: los valores de texto traen comas adentro (las
    direcciones, las descripciones) y partirían la fila en pedazos corridos.
    """
    vals, buf, i, n = [], [], 0, len(texto)
    en_str = False
    while i < n:
        c = texto[i]
        if en_str:
            if c == BARRA and i + 1 < n:
                siguiente = texto[i + 1]
                # phpMyAdmin escapa los saltos de línea y los tabs; el resto de
                # los escapes son el carácter tal cual (\' \" \\).
                buf.append({'n': '\n', 'r': '\r', 't': '\t', '0': '\0'}.get(siguiente, siguiente))
                i += 2
                continue
            if c == "'":
                en_str = False
                i += 1
                continue
            buf.append(c)
            i += 1
            continue
        if c == "'":
            en_str = True
            i += 1
            continue
        if c == ',':
            vals.append(''.join(buf).strip())
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    vals.append(''.join(buf).strip())
    return [None if v == 'NULL' else v for v in vals]


def filas(ruta, tabla, limite=None):
    """Genera las filas de una tabla del volcado, como diccionarios."""
    re_ins = re.compile(r"^INSERT INTO `" + re.escape(tabla) + r"` \(([^)]*)\) VALUES")
    cols = None
    salidas = 0
    with open(ruta, 'r', encoding='utf-8', errors='replace') as f:
        acumulando = False
        for linea in f:
            m = re_ins.match(linea)
            if m:
                cols = [c.strip(' `') for c in m.group(1).split(',')]
                trozo = linea.split('VALUES', 1)[1]
                acumulando = True
            elif acumulando and linea.lstrip().startswith('('):
                # phpMyAdmin parte los INSERT largos en varias líneas.
                trozo = linea
            elif acumulando:
                acumulando = False
                continue
            else:
                continue

            i, n = 0, len(trozo)
            while i < n:
                if trozo[i] != '(':
                    i += 1
                    continue
                j, prof, en_str = i + 1, 1, False
                while j < n and prof:
                    c = trozo[j]
                    if en_str:
                        if c == BARRA:
                            j += 2
                            continue
                        if c == "'":
                            en_str = False
                    elif c == "'":
                        en_str = True
                    elif c == '(':
                        prof += 1
                    elif c == ')':
                        prof -= 1
                    j += 1
                vals = _partir_fila(trozo[i + 1:j - 1])
                if cols and len(vals) == len(cols):
                    yield dict(zip(cols, vals))
                    salidas += 1
                    if limite and salidas >= limite:
                        return
                i = j


def una_pasada(ruta, tablas):
    """Lee varias tablas en UNA sola pasada por el archivo.

    Recorrer 177 MB una vez por tabla es lo que hacía que el importador
    demorara minutos; así se recorre una sola vez.

    `tablas` es un dict {nombre_de_tabla: función(fila)}. Devuelve nada: cada
    función va guardando lo que necesita.
    """
    patrones = {t: re.compile(r"^INSERT INTO `" + re.escape(t) + r"` \(([^)]*)\) VALUES")
                for t in tablas}
    cols_de = {}
    tabla_actual = None

    with open(ruta, 'r', encoding='utf-8', errors='replace') as f:
        for linea in f:
            if linea.startswith('INSERT INTO'):
                tabla_actual = None
                for t, pat in patrones.items():
                    m = pat.match(linea)
                    if m:
                        cols_de[t] = [c.strip(' `') for c in m.group(1).split(',')]
                        tabla_actual = t
                        trozo = linea.split('VALUES', 1)[1]
                        break
                if tabla_actual is None:
                    continue
            elif tabla_actual and linea.lstrip().startswith('('):
                trozo = linea
            else:
                tabla_actual = None
                continue

            cols = cols_de[tabla_actual]
            recibir = tablas[tabla_actual]
            i, n = 0, len(trozo)
            while i < n:
                if trozo[i] != '(':
                    i += 1
                    continue
                j, prof, en_str = i + 1, 1, False
                while j < n and prof:
                    c = trozo[j]
                    if en_str:
                        if c == BARRA:
                            j += 2
                            continue
                        if c == "'":
                            en_str = False
                    elif c == "'":
                        en_str = True
                    elif c == '(':
                        prof += 1
                    elif c == ')':
                        prof -= 1
                    j += 1
                vals = _partir_fila(trozo[i + 1:j - 1])
                if len(vals) == len(cols):
                    recibir(dict(zip(cols, vals)))
                i = j
