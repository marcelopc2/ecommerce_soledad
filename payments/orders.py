"""
Construcción de órdenes compartida por las vistas de pago (Webpay y MercadoPago).
Centraliza: parseo de productos, validación del envío, cálculo del total y creación
de la Order (+ Shipment si corresponde).
"""
import logging
from django.db import transaction
from catalog.models import Product
from . import coupons
from .models import Order, OrderItem
from .serializers import CheckoutSerializer
from shipments.models import PuntoRetiro, Shipment
from shipments.services import (
    get_shipping_quotes, build_package_from_products, CotizacionNoDisponible,
)

log = logging.getLogger('ingenioblocks.pagos')


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
    products_total = int(sum(p.effective_price for p in products))
    if products_total <= 0:
        return None, 'Monto inválido'

    # Cupón. Va DESPUÉS de resolver el correo definitivo (los packs para alumnos
    # lo reemplazan por el de la sesión), porque el límite "un uso por correo"
    # se mide sobre el correo con el que de verdad queda la compra.
    cupon = None
    descuento = 0
    codigo = (datos.get('coupon_code') or '').strip()
    if codigo:
        cupon = coupons.buscar(codigo)
        if cupon is None:
            return None, 'Ese cupón no existe.'
        descuento, problema = coupons.revisar(cupon, products_total, customer_email)
        if problema:
            return None, problema

    has_physical = any(not p.is_digital for p in products)
    # El retiro solo existe si hay algo físico. Marcarlo en una compra digital
    # no es un error del cliente -el checkout ni siquiera lo ofrece-, así que se
    # normaliza en silencio en vez de rechazar la compra.
    retiro = has_physical and datos.get('delivery_method') == Order.RETIRO

    shipping_cost = 0
    validated = None

    if retiro:
        # Se revalida contra la base y no contra lo que dice el cliente: si la
        # tienda cerró el retiro mientras la persona llenaba el formulario, no
        # se puede aceptar una compra que nadie va a poder entregar.
        punto = PuntoRetiro.cargar()
        if not punto.disponible:
            return None, (
                'El retiro en tienda no está disponible por ahora. '
                'Elige despacho a domicilio.'
            )
    elif has_physical:
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
        try:
            quotes = get_shipping_quotes(
                commune_name=commune_name, commune_id=commune_id,
                package=package, checkout_price=int(products_total),
            )
        except CotizacionNoDisponible as e:
            # Preferimos no vender antes que cobrar un despacho inventado.
            return None, str(e)

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

    # El descuento se resta solo de los productos: el despacho se cobra entero.
    total_amount = (products_total - descuento) + int(shipping_cost)
    if total_amount <= 0:
        # Ni Webpay ni MercadoPago aceptan un cobro de $0. Es preferible decirlo
        # que mandar a la pasarela algo que va a reventar con un error críptico.
        return None, (
            'Ese cupón deja el total en $0 y el sistema de pago no acepta cobros '
            'de $0. Escríbenos y lo resolvemos a mano.'
        )

    # Todo junto o nada: la orden, sus productos y el envío son una sola cosa.
    # Sin esto, un corte entre medio dejaba una orden física SIN envío, con el
    # costo de despacho ya sumado al total que se le iba a cobrar al cliente.
    with transaction.atomic():
        order = Order.objects.create(
            customer_email=customer_email,
            customer_name=customer_name,
            student_name=student_name,       # va al diploma (ver lms.services._grant)
            customer_phone=customer_phone,
            total_amount=total_amount,
            coupon=cupon,
            discount_amount=descuento,
            delivery_method=Order.RETIRO if retiro else Order.DESPACHO,
            status='PENDING',
        )
        order.products.set(products)

        # Una línea por producto, con el nombre y el precio congelados. Es lo
        # que lee la boleta, para que el documento cuadre con lo cobrado aunque
        # el precio del producto cambie después.
        # El descuento se reparte ENTRE LAS LÍNEAS, no se guarda solo en el
        # total: la boleta electrónica exige que el detalle sume exactamente lo
        # cobrado, así que una línea a precio de lista dejaría toda compra con
        # cupón sin poder boletearse (ver invoicing/services.py).
        cobrados = coupons.repartir([int(p.effective_price) for p in products], descuento)
        OrderItem.objects.bulk_create([
            OrderItem(
                order=order, product=p, name=p.name,
                unit_price=precio, quantity=1,
            )
            for p, precio in zip(products, cobrados)
        ])

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

    log.info('Orden %s creada por %s (total %s, %s producto/s%s%s)',
             order.order_id, customer_email, total_amount, len(products),
             f', cupón {cupon.code} -{descuento}' if cupon else '',
             ', retiro en tienda' if retiro else '')
    return order, None
