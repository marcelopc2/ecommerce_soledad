"""
Construcción de órdenes compartida por las vistas de pago (Webpay y MercadoPago).
Centraliza: parseo de productos, validación del envío, cálculo del total y creación
de la Order (+ Shipment si corresponde).
"""
from catalog.models import Product
from .models import Order
from shipments.models import Shipment
from shipments.services import get_shipping_quotes, build_package_from_products


def build_order_from_request(data):
    """
    Crea una Order (y su Shipment si la orden tiene productos físicos) desde el payload
    de crear pago. Retorna (order, error_message); si error_message no es None, no se creó nada.

    Seguridad: NO confía en el shipping_cost enviado por el cliente. Re-cotiza en el servidor
    y usa el precio autoritativo del courier elegido.
    """
    product_ids = data.get('product_ids', [])
    customer_email = data.get('email', '')
    shipping = data.get('shipping') or None

    if not product_ids or not customer_email:
        return None, 'Faltan productos o email'

    products = list(Product.objects.filter(id__in=product_ids))
    if not products:
        return None, 'Productos no encontrados'

    products_total = sum(p.price for p in products)
    if products_total <= 0:
        return None, 'Monto inválido'

    has_physical = any(not p.is_digital for p in products)

    shipping_cost = 0
    validated = None

    if has_physical:
        if not shipping:
            return None, 'Faltan los datos de envío para un producto físico'

        commune_name = shipping.get('commune')
        commune_id = shipping.get('commune_id')
        chosen_courier = shipping.get('courier')
        chosen_service = shipping.get('service_name', '')

        if not commune_name and not commune_id:
            return None, 'Falta la comuna de destino'
        if not chosen_courier:
            return None, 'Falta el courier elegido'

        package = build_package_from_products(products)
        quotes = get_shipping_quotes(commune_name=commune_name, commune_id=commune_id, package=package)

        # Precio autoritativo: buscamos el courier elegido en la cotización del servidor.
        match = None
        for q in quotes:
            if q['courier'] == chosen_courier and (not chosen_service or q['service'] == chosen_service):
                match = q
                break
        if match is None:
            return None, 'El courier elegido no está disponible para este destino'

        shipping_cost = int(match['price'])
        validated = {'package': package, 'quote': match, 'shipping': shipping}

    total_amount = int(products_total) + int(shipping_cost)

    order = Order.objects.create(
        customer_email=customer_email,
        total_amount=total_amount,
        status='PENDING',
    )
    order.products.set(products)

    if validated:
        s, pkg, q = validated['shipping'], validated['package'], validated['quote']
        Shipment.objects.create(
            order=order,
            recipient_name=s.get('recipient_name', ''),
            recipient_phone=s.get('recipient_phone', ''),
            recipient_email=s.get('recipient_email', '') or customer_email,
            region=s.get('region', ''),
            commune=s.get('commune', ''),
            commune_id=s.get('commune_id'),
            address_street=s.get('address_street', ''),
            address_number=s.get('address_number', ''),
            address_detail=s.get('address_detail', ''),
            courier=q['courier'],
            service_name=q['service'],
            shipping_cost=shipping_cost,
            estimated_days=q.get('days', ''),
            weight_kg=pkg['weight_kg'],
            width_cm=pkg['width_cm'],
            height_cm=pkg['height_cm'],
            length_cm=pkg['length_cm'],
            status='PENDING_DISPATCH',
        )

    return order, None
