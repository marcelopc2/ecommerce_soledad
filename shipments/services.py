import os
import requests
from decimal import Decimal
from django.conf import settings

# --- Configuración Shipit ---
SHIPIT_API_BASE = getattr(settings, 'SHIPIT_API_BASE', 'https://api.shipit.cl')
SHIPIT_ACCEPT = 'application/vnd.shipit.v2'
SHIPIT_TIMEOUT = 20  # segundos

# Paquete por defecto cuando faltan dimensiones/peso del producto (igual que el plugin WooCommerce).
DEFAULT_PACKAGE = getattr(settings, 'DEFAULT_PACKAGE', {
    'width_cm': 10, 'height_cm': 10, 'length_cm': 10, 'weight_kg': 1,
})

_COMMUNES_CACHE = None  # cache en memoria de proceso para la lista de comunas


def _shipit_credentials():
    return os.environ.get('SHIPIT_EMAIL', ''), os.environ.get('SHIPIT_TOKEN', '')


def _has_credentials():
    email, token = _shipit_credentials()
    return bool(email and token and token != 'test_token_here')


def _shipit_headers():
    email, token = _shipit_credentials()
    return {
        'Content-Type': 'application/json',
        'Accept': SHIPIT_ACCEPT,
        'X-Shipit-Email': email,
        'X-Shipit-Access-Token': token,
    }


# ---------------------------------------------------------------------------
# Armado del paquete a partir de los productos
# ---------------------------------------------------------------------------
def build_package_from_products(products):
    """
    Arma las dimensiones del paquete: suma peso y alto, toma el máximo de ancho/largo.
    Cae al paquete por defecto si falta algún dato. Solo considera productos físicos.
    """
    physical = [p for p in products if not p.is_digital]
    if not physical:
        return None

    def _val(value, fallback):
        return float(value) if value else float(fallback)

    total_weight = sum(_val(p.weight_kg, DEFAULT_PACKAGE['weight_kg']) for p in physical)
    total_height = sum(_val(p.height_cm, DEFAULT_PACKAGE['height_cm']) for p in physical)
    max_width = max(_val(p.width_cm, DEFAULT_PACKAGE['width_cm']) for p in physical)
    max_length = max(_val(p.length_cm, DEFAULT_PACKAGE['length_cm']) for p in physical)

    return {
        'weight_kg': round(total_weight, 2) or DEFAULT_PACKAGE['weight_kg'],
        'height_cm': round(total_height, 2) or DEFAULT_PACKAGE['height_cm'],
        'width_cm': round(max_width, 2) or DEFAULT_PACKAGE['width_cm'],
        'length_cm': round(max_length, 2) or DEFAULT_PACKAGE['length_cm'],
    }


# ---------------------------------------------------------------------------
# Cotización (rates) — solo lectura
# ---------------------------------------------------------------------------
def get_shipping_quotes(commune_name=None, commune_id=None, package=None):
    """
    Devuelve opciones de courier para un destino. Intenta cotizar en Shipit real;
    si no hay credenciales o Shipit no devuelve precios, cae al mock.
    Cada opción: {courier, service, price, days}.
    """
    package = package or DEFAULT_PACKAGE

    if _has_credentials():
        try:
            quotes = _shipit_rates(commune_name, package)
            if quotes:
                return quotes
        except Exception:
            pass  # cualquier fallo de red/parseo → caemos al mock

    return _mock_quotes(package)


def _shipit_rates(commune_name, package):
    """Llama al endpoint real de cotización de Shipit (POST /v/rates). Solo lectura."""
    payload = {
        'parcel': {
            'width': package['width_cm'],
            'height': package['height_cm'],
            'length': package['length_cm'],
            'weight': package['weight_kg'],
            'commune_name': commune_name,
        }
    }
    resp = requests.post(
        f'{SHIPIT_API_BASE}/v/rates',
        json=payload,
        headers=_shipit_headers(),
        timeout=SHIPIT_TIMEOUT,
    )
    data = resp.json()
    return _normalize_shipit_prices(data.get('prices', []))


def _normalize_shipit_prices(prices):
    """
    Normaliza la respuesta de Shipit a nuestro contrato {courier, service, price, days}.
    NOTA: la forma exacta de cada item se confirmará cuando la cuenta devuelva precios
    (hoy responde vacío por configuración de la cuenta). Parser defensivo mientras tanto.
    """
    normalized = []
    for item in prices or []:
        price = item.get('price') or item.get('total_price') or item.get('cost')
        if price is None:
            continue
        normalized.append({
            'courier': item.get('courier') or item.get('courier_name') or item.get('provider', 'Courier'),
            'service': item.get('service') or item.get('service_name') or '',
            'price': int(round(float(price))),
            'days': item.get('sla') or item.get('days') or item.get('estimated_days', ''),
        })
    return normalized


def _mock_quotes(package):
    """Tarifas simuladas para desarrollo (se usan hasta que Shipit devuelva precios reales)."""
    base_price = 3000
    weight_surcharge = float(package.get('weight_kg', 1)) * 500
    return [
        {'courier': 'Starken', 'service': 'Normal',
         'price': int(base_price + weight_surcharge), 'days': '2 a 3 días hábiles'},
        {'courier': 'Bluexpress', 'service': 'Prioritario',
         'price': int(base_price + weight_surcharge + 1500), 'days': '1 a 2 días hábiles'},
        {'courier': 'Chilexpress', 'service': 'Día Hábil Siguiente',
         'price': int(base_price + weight_surcharge + 3000), 'days': '1 día hábil'},
    ]


# ---------------------------------------------------------------------------
# Comunas (para el selector del frontend) — solo lectura
# ---------------------------------------------------------------------------
def get_communes():
    """
    Lista de regiones→comunas para el selector. Intenta traerla de Shipit y la cachea;
    si falla, usa una lista estática de respaldo.
    """
    global _COMMUNES_CACHE
    if _COMMUNES_CACHE is not None:
        return _COMMUNES_CACHE

    communes = None
    if _has_credentials():
        try:
            resp = requests.get(
                f'{SHIPIT_API_BASE}/v/communes',
                headers=_shipit_headers(),
                timeout=SHIPIT_TIMEOUT,
            )
            data = resp.json()
            communes = _normalize_communes(data)
        except Exception:
            communes = None

    if not communes:
        communes = _STATIC_COMMUNES

    _COMMUNES_CACHE = communes
    return communes


def _normalize_communes(data):
    """
    Normaliza la respuesta de Shipit a [{region, communes:[{id, name}]}].
    NOTA: confirmar la forma exacta con la doc de Shipit; parser defensivo por ahora.
    """
    if not isinstance(data, list) or not data:
        return None
    by_region = {}
    for c in data:
        region = c.get('region') or c.get('region_name') or 'Chile'
        by_region.setdefault(region, []).append({
            'id': c.get('id'),
            'name': c.get('name') or c.get('commune_name'),
        })
    return [{'region': r, 'communes': cs} for r, cs in by_region.items()]


# Respaldo estático (subset). Se reemplaza automáticamente por la lista real de Shipit
# cuando la cuenta responda. commune_id queda null; la cotización usa commune_name.
_STATIC_COMMUNES = [
    {'region': 'Región Metropolitana', 'communes': [
        {'id': None, 'name': 'Santiago'}, {'id': None, 'name': 'Providencia'},
        {'id': None, 'name': 'Las Condes'}, {'id': None, 'name': 'Ñuñoa'},
        {'id': None, 'name': 'Maipú'}, {'id': None, 'name': 'La Florida'},
        {'id': None, 'name': 'Puente Alto'}, {'id': None, 'name': 'Vitacura'},
        {'id': None, 'name': 'La Reina'}, {'id': None, 'name': 'Macul'},
    ]},
    {'region': 'Valparaíso', 'communes': [
        {'id': None, 'name': 'Valparaíso'}, {'id': None, 'name': 'Viña del Mar'},
        {'id': None, 'name': 'Quilpué'}, {'id': None, 'name': 'Villa Alemana'},
        {'id': None, 'name': 'Concón'},
    ]},
    {'region': 'Biobío', 'communes': [
        {'id': None, 'name': 'Concepción'}, {'id': None, 'name': 'Talcahuano'},
        {'id': None, 'name': 'Los Ángeles'}, {'id': None, 'name': 'Chiguayante'},
    ]},
    {'region': "O'Higgins", 'communes': [
        {'id': None, 'name': 'Rancagua'}, {'id': None, 'name': 'San Fernando'},
    ]},
    {'region': 'Maule', 'communes': [
        {'id': None, 'name': 'Talca'}, {'id': None, 'name': 'Curicó'},
        {'id': None, 'name': 'Linares'},
    ]},
    {'region': 'Araucanía', 'communes': [
        {'id': None, 'name': 'Temuco'}, {'id': None, 'name': 'Padre Las Casas'},
    ]},
    {'region': 'Los Lagos', 'communes': [
        {'id': None, 'name': 'Puerto Montt'}, {'id': None, 'name': 'Osorno'},
        {'id': None, 'name': 'Castro'},
    ]},
    {'region': 'Coquimbo', 'communes': [
        {'id': None, 'name': 'La Serena'}, {'id': None, 'name': 'Coquimbo'},
        {'id': None, 'name': 'Ovalle'},
    ]},
    {'region': 'Antofagasta', 'communes': [
        {'id': None, 'name': 'Antofagasta'}, {'id': None, 'name': 'Calama'},
    ]},
]


# ---------------------------------------------------------------------------
# Crear envío (POST /v/shipments) — TIENE EFECTO REAL (usa saldo, genera etiqueta)
# ---------------------------------------------------------------------------
def create_shipit_shipment(shipment):
    """
    Crea el envío real en Shipit y devuelve {reference, tracking_number, label_url}.
    OJO: gasta saldo y genera una etiqueta real. Se llama desde la acción del admin.

    NOTA: el payload y el endpoint exactos deben confirmarse contra la doc vigente de
    Shipit (y probar primero en sandbox si existe). Implementación de referencia.
    """
    if not _has_credentials():
        raise RuntimeError("Faltan credenciales de Shipit en el .env (SHIPIT_EMAIL / SHIPIT_TOKEN).")

    payload = {
        'shipment': {
            'reference': str(shipment.order.order_id)[:26],
            'full_name': shipment.recipient_name,
            'email': shipment.recipient_email or shipment.order.customer_email,
            'cellphone': shipment.recipient_phone,
            'street': shipment.address_street,
            'number': shipment.address_number,
            'complement': shipment.address_detail,
            'commune_id': shipment.commune_id,
            'commune_name': shipment.commune,
            'courier_for_client': shipment.courier,
            'items_count': shipment.order.products.count(),
            'parcel': {
                'weight': float(shipment.weight_kg),
                'width': float(shipment.width_cm),
                'height': float(shipment.height_cm),
                'length': float(shipment.length_cm),
            },
        }
    }

    resp = requests.post(
        f'{SHIPIT_API_BASE}/v/shipments',
        json=payload,
        headers=_shipit_headers(),
        timeout=SHIPIT_TIMEOUT,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Shipit respondió {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    return {
        'reference': str(data.get('id') or data.get('reference', '')),
        'tracking_number': data.get('tracking_number') or data.get('tracking', ''),
        'label_url': data.get('label_url') or data.get('labels', '') or data.get('label', ''),
    }
