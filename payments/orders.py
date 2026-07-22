"""
Construcción de órdenes compartida por las vistas de pago (Webpay y MercadoPago).
Centraliza: parseo de productos, validación del envío, cálculo del total y creación
de la Order (+ Shipment si corresponde).
"""
from catalog.models import Product
from .models import Order
from .serializers import CheckoutSerializer
from shipments.models import Shipment
from shipments.services import get_shipping_quotes, build_package_from_products


def _primer_error(errores):
    """Convierte el dict de errores de DRF en un mensaje legible.

    La vista devuelve un solo string en {'error': ...} y el frontend lo muestra
    tal cual, así que se saca el primer mensaje concreto en vez de mandar la
    estructura anidada (que se vería como un JSON crudo en pantalla).
    """
    if isinstance(errores, dict):
        for valor in errores.values():
            msg = _primer_error(valor)
            if msg:
                return msg
    elif isinstance(errores, (list, tuple)):
        for item in errores:
            msg = _primer_error(item)
            if msg:
                return msg
    elif errores:
        return str(errores)
    return 'Revisa los datos del formulario.'


def build_order_from_request(data, user=None):
    """
    Crea una Order (y su Shipment si la orden tiene productos físicos) desde el payload
    de crear pago. Retorna (order, error_message); si error_message no es None, no se creó nada.

    Seguridad: NO confía en el shipping_cost enviado por el cliente. Re-cotiza en el servidor
    y usa el precio autoritativo del courier elegido. Tampoco confía en que el frontend
    haya bloqueado los productos con requires_login: eso se valida acá con `user`.
    Los campos (correo, teléfono, nombres) se validan con CheckoutSerializer:
    las validaciones del formulario en React se saltan con un POST directo.
    """
    serializer = CheckoutSerializer(data=data)
    if not serializer.is_valid():
        return None, _primer_error(serializer.errors)
    datos = serializer.validated_data

    product_ids = datos['product_ids']
    customer_email = datos['email']
    customer_name = datos['customer_name']
    student_name = datos['student_name']
    customer_phone = datos['phone']
    shipping = datos.get('shipping') or None

    products = list(Product.objects.filter(id__in=product_ids, is_active=True))
    if not products:
        return None, 'Productos no encontrados'

    # Los productos marcados como "Próximamente" aún no se pueden comprar.
    coming_soon = [p for p in products if p.is_coming_soon]
    if coming_soon:
        return None, f'"{coming_soon[0].name}" aún no está disponible para la venta'

    # Productos solo para alumnos (packs de modelos, planes): exigen sesión iniciada.
    # Como la cuenta del LMS solo nace al pagar una compra, tener sesión implica
    # haber comprado antes el kit con las piezas.
    restricted = [p for p in products if p.requires_login]
    if restricted:
        if user is None or not user.is_authenticated:
            return None, (
                f'"{restricted[0].name}" es solo para alumnos: inicia sesión con la cuenta '
                f'que recibiste al comprar tu kit para poder comprarlo.'
            )
        # El acceso se otorga por email (grant_access_for_order), así que la compra
        # se ancla a la cuenta con la sesión iniciada. Si no, alguien logueado podría
        # poner otro correo y el pack terminaría en una cuenta que nunca compró el kit.
        customer_email = user.email or user.username

    # Precio autoritativo del servidor: usa el precio de oferta cuando corresponde.
    products_total = sum(p.effective_price for p in products)
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
        quotes = get_shipping_quotes(
            commune_name=commune_name, commune_id=commune_id,
            package=package, checkout_price=int(products_total),
        )

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
        customer_name=customer_name,
        student_name=student_name,       # va al diploma (ver lms.services._grant)
        customer_phone=customer_phone,
        total_amount=total_amount,
        status='PENDING',
    )
    order.products.set(products)

    if validated:
        s, pkg, q = validated['shipping'], validated['package'], validated['quote']
        Shipment.objects.create(
            order=order,
            # Si no vinieron datos propios del destinatario, se usan los del
            # comprador (que es el caso normal: compra para su propia casa).
            recipient_name=s.get('recipient_name') or customer_name,
            recipient_phone=s.get('recipient_phone') or customer_phone,
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
