"""Validación del payload del checkout.

Estas validaciones se ejecutan en el SERVIDOR. Las del frontend son solo para
que la persona vea el error al instante; cualquiera puede saltárselas mandando
un POST directo, así que lo que decide es esto.
"""
import re

from rest_framework import serializers


def _solo_digitos(texto):
    return re.sub(r'\D', '', texto or '')


def validar_telefono_chileno(valor):
    """Acepta los formatos con que la gente realmente escribe su número:
    +56 9 1234 5678, 56912345678, 9 1234 5678, 912345678, 22 123 4567…

    Se normaliza a 9 dígitos (sin el 56 del país). Móviles parten en 9;
    los fijos en 2-8 según la zona.
    """
    d = _solo_digitos(valor)
    if d.startswith('56'):
        d = d[2:]
    if len(d) != 9:
        raise serializers.ValidationError(
            'Escribe un teléfono chileno válido, por ejemplo +56 9 1234 5678.'
        )
    if d[0] == '0':
        raise serializers.ValidationError('El número no puede empezar en 0.')
    return f'+56{d}'          # se guarda normalizado


def validar_nombre(valor, campo='nombre'):
    """Nombre de persona: sin dígitos y con al menos 2 letras.

    No se exige apellido: hay gente que solo pone el nombre de pila del niño,
    y rechazar eso sería más molesto que útil.
    """
    v = ' '.join((valor or '').split())        # colapsa espacios de más
    if len(v) < 2:
        raise serializers.ValidationError(f'Escribe el {campo} completo.')
    if any(c.isdigit() for c in v):
        raise serializers.ValidationError(f'El {campo} no puede tener números.')
    return v


class ShippingSerializer(serializers.Serializer):
    """Datos de envío. Solo se exigen si la orden trae algo físico."""
    recipient_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    recipient_phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    recipient_email = serializers.EmailField(required=False, allow_blank=True)
    region = serializers.CharField(max_length=120)
    commune = serializers.CharField(max_length=120)
    commune_id = serializers.IntegerField(required=False, allow_null=True)
    address_street = serializers.CharField(max_length=255)
    address_number = serializers.CharField(max_length=30)
    address_detail = serializers.CharField(max_length=255, required=False, allow_blank=True)
    courier = serializers.CharField(max_length=80)
    service_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    # shipping_cost llega del cliente pero NO se usa: el costo se re-cotiza en
    # el servidor (ver payments/orders.py). Se acepta para no romper el payload.
    shipping_cost = serializers.IntegerField(required=False)

    def validate_address_street(self, v):
        v = ' '.join((v or '').split())
        if len(v) < 3:
            raise serializers.ValidationError('Escribe el nombre de la calle.')
        return v

    def validate_address_number(self, v):
        v = (v or '').strip()
        if not v:
            raise serializers.ValidationError('Falta el número de la dirección.')
        return v


class CheckoutSerializer(serializers.Serializer):
    """Payload de creación de pago (Webpay y MercadoPago comparten este formato)."""
    product_ids = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=False,
        error_messages={'empty': 'No hay productos en la compra.'},
    )
    email = serializers.EmailField(
        error_messages={'invalid': 'Escribe un correo válido, por ejemplo nombre@correo.cl.'},
    )
    customer_name = serializers.CharField(max_length=200)
    # El nombre del niño/a es OBLIGATORIO: el diploma se emite a su nombre.
    student_name = serializers.CharField(max_length=200)
    phone = serializers.CharField(max_length=30)
    shipping = ShippingSerializer(required=False, allow_null=True)

    def validate_customer_name(self, v):
        return validar_nombre(v, 'nombre del apoderado')

    def validate_student_name(self, v):
        return validar_nombre(v, 'nombre del niño o niña')

    def validate_phone(self, v):
        return validar_telefono_chileno(v)

    def validate_email(self, v):
        return (v or '').lower().strip()
