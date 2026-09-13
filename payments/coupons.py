"""Cupones de descuento: buscar uno por código y decidir si se puede usar.

Vive aparte del modelo porque son dos cosas distintas: el modelo guarda las
reglas que configuró la administradora, y esto las APLICA a una compra concreta.
La misma función la usan el checkout (para mostrar el descuento antes de pagar)
y la creación de la orden (que es la que manda). Si estuviera duplicada, el
cliente podría ver un descuento que después no se le cobra.
"""
from django.db.models import Q
from django.utils import timezone

from .models import Coupon

#: El descuento NUNCA se aplica al despacho, solo a los productos. El envío es
#: plata que se le paga al courier, no margen de la tienda: un 50% sobre el
#: total dejaría cada despacho a pérdida.


def normalizar(codigo):
    """Los códigos se comparan en mayúsculas y sin espacios.

    La gente los copia y pega de un mail o de Instagram y se trae espacios
    invisibles al final, o los escribe en minúscula. Rechazar por eso sería
    una fuente de reclamos evitable.
    """
    return (codigo or '').strip().upper()


def buscar(codigo):
    """El cupón con ese código, o None si no existe."""
    codigo = normalizar(codigo)
    if not codigo:
        return None
    return Coupon.objects.filter(code=codigo).first()


def revisar(cupon, subtotal, email=''):
    """¿Se puede usar este cupón en esta compra? Devuelve (descuento, error).

    Si `error` no es None, el cupón NO se aplica y ese texto es lo que ve la
    persona: está escrito para el cliente, no para el log.

    `subtotal` es el total de los PRODUCTOS, sin despacho.
    """
    ahora = timezone.now()

    if not cupon.is_active:
        return 0, 'Ese cupón ya no está disponible.'

    if cupon.starts_at and ahora < cupon.starts_at:
        return 0, 'Ese cupón todavía no está vigente.'

    if cupon.ends_at and ahora > cupon.ends_at:
        return 0, 'Ese cupón ya venció.'

    if cupon.min_purchase and subtotal < cupon.min_purchase:
        falta = cupon.min_purchase - subtotal
        return 0, (
            f'Ese cupón es para compras desde ${cupon.min_purchase:,.0f}. '
            f'Te faltan ${falta:,.0f}.'
        ).replace(',', '.')

    if cupon.max_uses is not None and cupon.usos >= cupon.max_uses:
        return 0, 'Ese cupón ya se agotó.'

    # Un uso por correo. Se mira sobre compras PAGADAS: una orden que quedó a
    # medio pagar no puede quemarle el cupón a nadie.
    if cupon.once_per_email and email:
        ya_uso = cupon.orders.filter(
            status='PAID', customer_email__iexact=email.strip(),
        ).exists()
        if ya_uso:
            return 0, 'Ese cupón ya lo usaste en una compra anterior.'

    descuento = cupon.descuento_sobre(subtotal)
    if descuento <= 0:
        return 0, 'Ese cupón no aplica a esta compra.'

    return descuento, None


def repartir(precios, descuento):
    """Reparte el descuento entre las líneas, a prorrata de su precio.

    Hace falta porque la boleta electrónica exige que la suma del detalle sea
    EXACTAMENTE el total cobrado (ver invoicing/services.py): si el descuento
    se guardara solo en la orden y las líneas quedaran al precio de lista, no
    se podría emitir la boleta de ninguna compra con cupón.

    El redondeo se acumula y lo absorbe la última línea, así la suma calza al
    peso. Devuelve la lista de precios ya rebajados, en el mismo orden.
    """
    total = sum(precios)
    if total <= 0 or descuento <= 0:
        return list(precios)

    descuento = min(descuento, total)
    rebajados = []
    repartido = 0
    for i, precio in enumerate(precios):
        if i == len(precios) - 1:
            parte = descuento - repartido      # la última se lleva el resto
        else:
            parte = int(precio * descuento / total)
            repartido += parte
        rebajados.append(max(0, precio - parte))
    return rebajados
