import logging
import os
import requests
from datetime import date
from django.conf import settings

log = logging.getLogger('ingenioblocks.pagos')

# --- Configuración OpenFactura (Haulmer) ---
# Ambiente de DESARROLLO público de Haulmer: emite boletas SIMULADAS (sin validez SII).
# Producción: https://api.haulmer.com + API key real de la clienta.
OPENFACTURA_DEV_BASE = 'https://dev-api.haulmer.com'
OPENFACTURA_DEV_APIKEY = '928e15a2d14d4a6292345f04960f4bd3'  # key pública de demo (documentada por Haulmer)

# 8s y no 30: la emisión corre dentro del retorno del pago, y este timeout se
# gasta DOS veces (consultar el emisor + emitir). Con 30s el peor caso superaba
# el timeout de gunicorn y mataba al worker con el cliente esperando en pantalla.
TIMEOUT = int(os.environ.get('OPENFACTURA_TIMEOUT', '8'))
IVA_RATE = 0.19

_ORG_CACHE = None


def _config():
    """
    Devuelve (base_url, api_key). Si la key del .env es un placeholder,
    usa el ambiente de desarrollo público de Haulmer (boletas simuladas).
    """
    api_key = os.environ.get('OPENFACTURA_API_KEY', '')
    base = os.environ.get('OPENFACTURA_API_BASE', '')

    if not api_key or api_key == 'test_api_key_here':
        return OPENFACTURA_DEV_BASE, OPENFACTURA_DEV_APIKEY

    return (base or 'https://api.haulmer.com'), api_key


def _headers():
    _, api_key = _config()
    return {'apikey': api_key, 'Content-Type': 'application/json'}


def get_organization():
    """
    Datos del emisor (la empresa) según la API key. Se usan para el bloque Emisor
    de cada boleta, así no hay que hardcodear el RUT/giro de la clienta. Cacheado.
    """
    global _ORG_CACHE
    if _ORG_CACHE is not None:
        return _ORG_CACHE

    base, _ = _config()
    resp = requests.get(f'{base}/v2/dte/organization', headers=_headers(), timeout=TIMEOUT)
    if resp.status_code >= 400:
        raise RuntimeError(f"OpenFactura organization {resp.status_code}: {resp.text[:200]}")

    _ORG_CACHE = resp.json()
    return _ORG_CACHE


def _es_exento(product):
    """¿Esta línea va exenta de IVA?

    Un producto borrado o una línea sin producto se tratan como EXENTOS, que es
    lo que vende esta empresa: equivocarse hacia el otro lado significaría
    cobrarle IVA al cliente en una venta que no lo lleva.
    """
    return getattr(product, 'exento_iva', True)


def _build_boleta_payload(order):
    """
    Arma el JSON de una boleta electrónica (DTE 39) para una orden pagada.

    La empresa es de servicios educativos y sus productos van EXENTOS de IVA;
    el DESPACHO no, porque es un servicio del courier. Así que una boleta con
    envío lleva las dos cosas a la vez: una parte exenta y una afecta.

    Los precios se manejan con IVA incluido -es como se venden en la tienda-,
    así que el neto del despacho se deriva hacia atrás desde lo cobrado.

    Receptor: consumidor final (RUT genérico 66.666.666-6, estándar SII para boletas).
    """
    org = get_organization()
    giro = (org.get('glosaDescriptiva') or '')[:80]  # SII limita el giro a 80 caracteres

    detalle = []
    line = 0
    # OrderItem trae el nombre y el precio CONGELADOS al momento de la compra:
    # es lo que realmente se cobró, no el precio actual del producto. Las
    # órdenes creadas antes de que existiera OrderItem caen al M2M (fallback).
    #: Lo exento se suma aparte del resto: el SII lo quiere en su propio total
    #: (MntExe) y no mezclado con el neto afecto.
    monto_exento = 0

    items = list(order.items.all())
    if items:
        for item in items:
            line += 1
            linea = {
                'NroLinDet': line,
                'NmbItem': item.name[:80],
                'QtyItem': item.quantity,
                'PrcItem': int(item.unit_price),
                'MontoItem': item.subtotal,
            }
            # IndExe 1 es lo que hace que en el PDF salga "**Producto o servicio
            # es exento o no afecto" bajo el nombre, y que el monto vaya a
            # MntExe en vez de al neto afecto.
            if _es_exento(item.product):
                linea['IndExe'] = 1
                monto_exento += item.subtotal
            detalle.append(linea)
    else:
        for product in order.products.all():
            line += 1
            price = int(product.effective_price)
            linea = {
                'NroLinDet': line,
                'NmbItem': product.name[:80],
                'QtyItem': 1,
                'PrcItem': price,
                'MontoItem': price,
            }
            if _es_exento(product):
                linea['IndExe'] = 1
                monto_exento += price
            detalle.append(linea)

    # El envío se cobra al cliente → va como línea de la boleta.
    shipment = getattr(order, 'shipment', None)
    if shipment and shipment.shipping_cost:
        line += 1
        detalle.append({
            'NroLinDet': line,
            'NmbItem': f'Despacho ({shipment.courier})'[:80],
            'QtyItem': 1,
            'PrcItem': int(shipment.shipping_cost),
            'MontoItem': int(shipment.shipping_cost),
        })

    total = int(order.total_amount)

    # Un DTE cuyo detalle no suma el total es un documento tributario inválido.
    # Mejor no emitirlo y que quede el registro, que mandarle al SII algo que no
    # cuadra (o peor, entregarle al cliente una boleta que no calza con su cobro).
    suma_detalle = sum(d['MontoItem'] for d in detalle)
    if suma_detalle != total:
        raise ValueError(
            f'El detalle de la boleta suma {suma_detalle} pero la orden '
            f'{order.order_id} cobró {total}. Revisar precios de los productos '
            f'y el costo de despacho antes de emitir.'
        )

    # Lo AFECTO es todo lo que no es exento: en la práctica, el despacho. Su
    # precio ya viene con IVA incluido (es lo que se le cobró al cliente), así
    # que el neto se deriva hacia atrás y el IVA es la diferencia. Se calcula
    # por resta y no con `round(afecto * 0.19)` para que neto + IVA dé EXACTO lo
    # cobrado: si no, la boleta se cae por un peso de redondeo.
    afecto_con_iva = total - monto_exento
    neto = round(afecto_con_iva / (1 + IVA_RATE))
    iva = afecto_con_iva - neto

    totales = {'MntTotal': total}
    if monto_exento:
        totales['MntExe'] = monto_exento
    # Una compra 100% exenta (un plan digital sin despacho) no lleva neto ni IVA.
    # Mandarlos en 0 no es lo mismo que omitirlos: el SII los interpreta como
    # "hay una parte afecta que suma cero", que es otra cosa.
    if afecto_con_iva:
        totales['MntNeto'] = neto
        totales['IVA'] = iva

    return {
        'response': ['FOLIO', 'PDF'],
        'dte': {
            'Encabezado': {
                'IdDoc': {
                    'TipoDTE': 39,
                    'FchEmis': date.today().isoformat(),
                    'IndServicio': 3,  # 3 = boleta de venta y servicios
                },
                'Emisor': {
                    'RUTEmisor': org.get('rut', ''),
                    'RznSocEmisor': (org.get('razonSocial') or '')[:100],
                    'GiroEmisor': giro,
                    'DirOrigen': (org.get('direccion') or '')[:60],
                    'CmnaOrigen': org.get('comuna', ''),
                },
                'Receptor': {
                    'RUTRecep': '66666666-6',  # consumidor final
                    'RznSocRecep': 'Cliente e-commerce',
                    'DirRecep': 'Chile',
                    'CmnaRecep': 'Chile',
                },
                # Boleta (39): MntExe/MntNeto/IVA/MntTotal — TasaIVA no es parte
                # del esquema de boletas.
                'Totales': totales,
            },
            'Detalle': detalle,
            # Igual que en las boletas que la clienta emite hoy a mano: deja el
            # número de pedido impreso en el documento. Es lo que permite que
            # alguien con la boleta en la mano encuentre la compra en el panel.
            'Referencia': [{
                'NroLinRef': 1,
                'RazonRef': 'Orden de compra N°%s - Fecha %s' % (
                    str(order.order_id)[:8], order.created_at.date().isoformat(),
                ),
            }],
        },
    }


def emit_boleta(order):
    """
    Emite la boleta en OpenFactura y devuelve {folio, token, pdf_base64, raw}.
    Lanza excepción con el detalle si OpenFactura rechaza el documento.
    """
    base, _ = _config()
    payload = _build_boleta_payload(order)

    resp = requests.post(f'{base}/v2/dte/document', json=payload, headers=_headers(), timeout=TIMEOUT)
    data = resp.json() if resp.content else {}

    if resp.status_code >= 400:
        err = data.get('error') if isinstance(data, dict) else None
        detail = err.get('message') if isinstance(err, dict) else resp.text[:300]
        details_list = err.get('details') if isinstance(err, dict) else None
        if details_list:
            detail = f"{detail} | {details_list}"
        raise RuntimeError(f"OpenFactura {resp.status_code}: {detail}")

    return {
        'folio': str(data.get('FOLIO', '')),
        'token': str(data.get('TOKEN', '')),
        'pdf_base64': data.get('PDF', '') or '',
        'raw': data,
    }


def issue_invoice_for_order(order):
    """
    Punto de entrada desde pagos: emite la boleta para una orden recién pagada.
    - Idempotente: si la orden ya tiene boleta emitida, no re-emite.
    - No-bloqueante: NUNCA lanza excepción (el pago no debe romperse por facturación).
      Si falla, deja la Invoice en ERROR para reintentar desde el admin.
    """
    from django.utils import timezone
    from .models import Invoice

    invoice, _created = Invoice.objects.get_or_create(order=order)
    if invoice.status == 'ISSUED':
        return invoice

    try:
        result = emit_boleta(order)
        invoice.folio = result['folio']
        invoice.token = result['token']
        invoice.pdf_base64 = result['pdf_base64']
        invoice.status = 'ISSUED'
        invoice.error_message = ''
        invoice.issued_at = timezone.now()
        log.info('Boleta folio %s emitida para la orden %s', invoice.folio, order.order_id)
    except Exception as e:
        invoice.status = 'ERROR'
        invoice.error_message = str(e)[:1000]
        log.exception('No se pudo emitir la boleta de la orden %s', order.order_id)

    invoice.save()
    return invoice
