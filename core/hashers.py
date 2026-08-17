"""Verificación de contraseñas heredadas de WordPress.

Los clientes que vienen de la tienda vieja entran con la MISMA clave que ya
tenían: no se les pide cambiarla ni se les manda un correo para redefinirla. La
primera vez que uno entra bien, Django reescribe su contraseña con su propio
cifrado (PBKDF2) y este hasher no vuelve a usarse para esa cuenta. O sea, el
formato de WordPress se va apagando solo a medida que la gente entra.

Cómo se guarda
--------------
WordPress guarda algo como `$P$B7xVn...`. Ese texto NO se puede guardar tal cual
en Django: Django reconoce el algoritmo por lo que viene antes del primer `$`, y
ahí no hay nada. Por eso el importador lo guarda con un prefijo propio:

    wordpress$$P$B7xVn...

Formatos que entiende
---------------------
- `$wp$2y$` — bcrypt, el formato de WordPress 6.8 en adelante. Es el que trae
  el export de IngenioBlocks: las 357 cuentas están en este formato, ninguna en
  phpass.
- `$P$` y `$H$` — phpass, el formato clásico de WordPress. No aparece en este
  export, pero se conserva por si alguna cuenta vieja reaparece.
- MD5 pelado (32 caracteres hex) — cuentas muy viejas, de antes de phpass.

El detalle del formato `$wp$`
-----------------------------
WordPress no le pasa la contraseña directamente a bcrypt, porque bcrypt corta a
los 72 bytes y una clave larga quedaría truncada. Primero la resume con
HMAC-SHA384 y codifica ese resumen en base64 (64 caracteres, bajo el límite), y
recién eso va a bcrypt. Al hash resultante le pega el prefijo `$wp` adelante.
Para verificar hay que repetir los mismos pasos.

Seguridad
---------
bcrypt es sólido, pero phpass (MD5 iterado) es débil para los estándares de hoy.
Por eso importa que el reemplazo por PBKDF2 sea automático en el primer login, y
que las cuentas que nunca vuelvan a entrar terminen con la clave expirada en vez
de quedar para siempre con un hash malo.
"""
import base64
import hashlib
import hmac

from django.contrib.auth.hashers import BasePasswordHasher
from django.utils.crypto import constant_time_compare

#: Alfabeto propio de phpass. No es base64 estándar: el orden es distinto.
ITOA64 = './0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'


def _encode64(entrada, contador):
    """El base64 de phpass, que no es el base64 de siempre."""
    salida = []
    i = 0
    while i < contador:
        valor = entrada[i]
        i += 1
        salida.append(ITOA64[valor & 0x3F])

        if i < contador:
            valor |= entrada[i] << 8
        salida.append(ITOA64[(valor >> 6) & 0x3F])
        if i >= contador:
            break
        i += 1

        if i < contador:
            valor |= entrada[i] << 16
        salida.append(ITOA64[(valor >> 12) & 0x3F])
        if i >= contador:
            break
        i += 1

        salida.append(ITOA64[(valor >> 18) & 0x3F])
    return ''.join(salida)


def _phpass(password, ajuste):
    """Recalcula el hash phpass de `password` usando la sal y las vueltas que
    vienen dentro del hash guardado."""
    if len(ajuste) < 12:
        return ''
    # El 4º carácter dice cuántas vueltas de MD5 se dieron, como potencia de 2.
    log2 = ITOA64.find(ajuste[3])
    if log2 < 7 or log2 > 30:
        return ''
    vueltas = 1 << log2
    sal = ajuste[4:12].encode('utf-8', 'ignore')
    if len(sal) != 8:
        return ''

    clave = password.encode('utf-8')
    resumen = hashlib.md5(sal + clave).digest()
    for _ in range(vueltas):
        resumen = hashlib.md5(resumen + clave).digest()

    return ajuste[:12] + _encode64(resumen, 16)


def _resumen_para_bcrypt(password):
    """El paso previo de WordPress 6.8: HMAC-SHA384 en base64.

    Se hace para que las claves largas no queden truncadas por el límite de 72
    bytes de bcrypt. El `strip()` no es un capricho nuestro: WordPress aplica
    `trim()` antes de cifrar, así que una clave con espacios al borde tiene que
    tratarse igual acá o el cliente no podría entrar.
    """
    digest = hmac.new(b'wp-sha384', password.strip().encode('utf-8'), hashlib.sha384).digest()
    return base64.b64encode(digest)


class WordPressPasswordHasher(BasePasswordHasher):
    """Deja entrar con la clave que el cliente ya usaba en WordPress."""

    algorithm = 'wordpress'

    def salt(self):
        # Nunca se generan hashes nuevos con este formato: solo se verifican los
        # que llegaron en la migración.
        raise NotImplementedError(
            'El formato de WordPress es solo de lectura. Las claves nuevas las '
            'cifra Django con su hasher por omisión.'
        )

    def encode(self, password, salt):
        raise NotImplementedError(
            'El formato de WordPress es solo de lectura.'
        )

    def verify(self, password, encoded):
        try:
            algoritmo, wp_hash = encoded.split('$', 1)
        except ValueError:
            return False
        if algoritmo != self.algorithm or not wp_hash:
            return False

        # WordPress 6.8+: bcrypt sobre el resumen, con `$wp` pegado adelante.
        if wp_hash.startswith('$wp$'):
            import bcrypt

            try:
                return bcrypt.checkpw(_resumen_para_bcrypt(password), wp_hash[3:].encode('ascii'))
            except (ValueError, TypeError):
                # Hash mal formado: es una credencial inválida, no un error del
                # sistema. No debe tumbar el login de nadie más.
                return False

        if wp_hash.startswith(('$P$', '$H$')):
            calculado = _phpass(password, wp_hash)
            return bool(calculado) and constant_time_compare(calculado, wp_hash)

        # MD5 pelado de WordPress muy antiguo.
        if len(wp_hash) == 32 and all(c in '0123456789abcdef' for c in wp_hash.lower()):
            calculado = hashlib.md5(password.encode('utf-8')).hexdigest()
            return hmac.compare_digest(calculado, wp_hash.lower())

        return False

    def must_update(self, encoded):
        # Siempre: en cuanto entra bien, Django reescribe la clave con PBKDF2 y
        # esta cuenta deja de depender del hash viejo.
        return True

    def safe_summary(self, encoded):
        from django.contrib.auth.hashers import mask_hash
        from django.utils.translation import gettext_noop as _

        _algoritmo, wp_hash = encoded.split('$', 1)
        return {
            _('algorithm'): self.algorithm,
            _('hash'): mask_hash(wp_hash),
        }

    def harden_runtime(self, password, encoded):
        # phpass ya es de costo fijo y conocido; no hay nada que emparejar.
        pass
