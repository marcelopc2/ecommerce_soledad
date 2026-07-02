import os
import requests
from datetime import date
from django.conf import settings

# --- Configuración OpenFactura (Haulmer) ---
# Ambiente de DESARROLLO público de Haulmer: emite boletas SIMULADAS (sin validez SII).
# Producción: https://api.haulmer.com + API key real de la clienta.
OPENFACTURA_DEV_BASE = 'https://dev-api.haulmer.com'
OPENFACTURA_DEV_APIKEY = '928e15a2d14d4a6292345f04960f4bd3'  # key pública de demo (documentada por Haulmer)

TIMEOUT = 30
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


def _build_boleta_payload(order):
    """
    Arma el JSON de una boleta electrónica (DTE 39) para una orden pagada.
    Precios con IVA incluido (así se venden en la tienda): el neto se deriva del total.
    Receptor: consumidor final (RUT genérico 66.666.666-6, estándar SII para boletas).
    """
    org = get_organization()
    giro = (org.get('glosaDescriptiva') or '')[:80]  # SII limita el giro a 80 caracteres

    detalle = []
    line = 0
    for product in order.products.all():
        line += 1
        price = int(product.price)
        detalle.append({
            'NroLinDet': line,
            'NmbItem': product.name[:80],
            'QtyItem': 1,
            'PrcItem': price,
            'MontoItem': price,
        })

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
    neto = round(total / (1 + IVA_RATE))
    iva = total - neto

    return {
        'response': ['FOLIO', 'PDF'],
        'dte': {
            'Encabezado': {
                'IdDoc': {
                    'TipoDTE': 39,
                    'FchEmis': date.today().isoformat(),
                    'IndServicio': 3,  # 3 = boleta de venta de bienes
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
                # Boleta (39): solo MntNeto/IVA/MntTotal — TasaIVA no es parte del esquema de boletas.
                'Totales': {
                    'MntNeto': neto,
                    'IVA': iva,
                    'MntTotal': total,
                },
            },
            'Detalle': detalle,
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
    except Exception as e:
        invoice.status = 'ERROR'
        invoice.error_message = str(e)[:1000]

    invoice.save()
    return invoice
