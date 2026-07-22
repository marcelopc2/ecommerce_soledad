import logging
import os
import requests
from django.conf import settings

log = logging.getLogger('ingenioblocks.pagos')

# --- Configuración Shipit ---
SHIPIT_API_BASE = getattr(settings, 'SHIPIT_API_BASE', 'https://api.shipit.cl')
SHIPIT_ACCEPT = 'application/vnd.shipit.v2'
# 8s y no 20: esta llamada corre dentro del checkout, con el cliente esperando.
SHIPIT_TIMEOUT = int(os.environ.get('SHIPIT_TIMEOUT', '8'))

# Comuna DESDE la que despacha la tienda (destiny_id/origin_id de Shipit son IDs
# de comuna, no nombres). Default 308 = Las Condes. Configurable por si la
# tienda cambia de bodega. Se saca del panel de Shipit o de GET /v/communes.
SHIPIT_ORIGIN_COMMUNE_ID = int(os.environ.get('SHIPIT_ORIGIN_COMMUNE_ID', '308'))

# Paquete por defecto cuando faltan dimensiones/peso del producto (igual que el plugin WooCommerce).
DEFAULT_PACKAGE = getattr(settings, 'DEFAULT_PACKAGE', {
    'width_cm': 10, 'height_cm': 10, 'length_cm': 10, 'weight_kg': 1,
})

_COMMUNES_CACHE = None       # cache en memoria de la lista de comunas
_COMMUNE_ID_BY_NAME = None   # cache nombre(normalizado) -> id, para resolver destino


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
class CotizacionNoDisponible(Exception):
    """No se pudo obtener una tarifa real de Shipit.

    Existe para que el checkout pueda responder "no podemos calcular el
    despacho ahora" en vez de inventar un precio. Ver get_shipping_quotes().
    """


def get_shipping_quotes(commune_name=None, commune_id=None, package=None, checkout_price=0):
    """
    Devuelve opciones de courier para un destino, cotizadas en Shipit.
    Cada opción: {courier, service, price, days}.

    Shipit cotiza por `destiny_id` (ID de comuna), NO por nombre. Se usa el
    commune_id recibido; si no vino (el frontend mandó solo el nombre), se
    resuelve el nombre → id contra la lista de comunas de Shipit.

    Si no se puede cotizar de verdad:
      - en desarrollo (DEBUG=True) devuelve tarifas de mentira, para poder
        probar el checkout sin depender de Shipit;
      - en producción lanza CotizacionNoDisponible.

    Esa distinción es deliberada: el precio que sale de acá es el que se le
    COBRA al cliente. Antes cualquier fallo de Shipit caía al mock en silencio
    y la tienda seguía vendiendo con tarifas inventadas — si el envío real
    costaba $8.000 y se cobró $3.500, la diferencia la absorbía la tienda sin
    que nadie se enterara.
    """
    package = package or DEFAULT_PACKAGE

    if _has_credentials():
        destiny_id = commune_id or _resolve_commune_id(commune_name)
        if destiny_id:
            try:
                quotes = _shipit_rates(int(destiny_id), package, checkout_price)
                if quotes:
                    return quotes
                log.error('Shipit no devolvió tarifas para la comuna %s (id %s)',
                          commune_name, destiny_id)
            except Exception:
                log.exception('Falló la cotización en Shipit para la comuna %s (id %s)',
                              commune_name, destiny_id)
        else:
            log.error('No se pudo resolver el id de comuna de "%s" en Shipit', commune_name)
    else:
        log.warning('Shipit sin credenciales configuradas (SHIPIT_EMAIL / SHIPIT_TOKEN)')

    if settings.DEBUG:
        return _mock_quotes(package)

    raise CotizacionNoDisponible(
        'No pudimos calcular el costo de despacho en este momento. '
        'Intenta nuevamente en unos minutos o escríbenos por WhatsApp.'
    )


def _shipit_rates(destiny_id, package, checkout_price=0):
    """Llama al endpoint real de cotización de Shipit (POST /v/rates). Solo lectura.

    El payload lleva TODOS los campos que exige Shipit (confirmado con su
    soporte, ticket de julio 2026). El mínimo `{width, height, length, weight,
    commune_name}` devolvía 400 'Sin Precios'; lo que faltaba eran los IDs de
    comuna (origin/destiny) y los flags de la cotización.
    """
    payload = {
        'parcel': {
            'length': package['length_cm'],
            'width': package['width_cm'],
            'height': package['height_cm'],
            'weight': package['weight_kg'],
            'destiny_id': destiny_id,                    # comuna de destino
            'origin_id': SHIPIT_ORIGIN_COMMUNE_ID,       # comuna de la tienda
            'is_payable': False,                         # no es pago contra entrega
            'destiny': 'Domicilio',                      # entrega a domicilio (no sucursal)
            'courier_selected': False,                   # queremos TODAS las tarifas
            'courier_for_client': '',
            'request_from': 'custom',                    # identifica el origen de la integración
            'checkout_price': int(checkout_price or 0),  # valor declarado (para el seguro)
        }
    }
    resp = requests.post(
        f'{SHIPIT_API_BASE}/v/rates',
        json=payload,
        headers=_shipit_headers(),
        timeout=SHIPIT_TIMEOUT,
    )
    data = resp.json()
    return _normalize_shipit_prices(data.get('prices', []) if isinstance(data, dict) else [])


# Nombre legible del tipo de servicio que devuelve Shipit.
_SERVICE_LABELS = {
    'next_day': 'Día hábil siguiente',
    'same_day': 'Mismo día',
    'normal': 'Normal',
    'express': 'Express',
}


def _normalize_shipit_prices(prices):
    """
    Normaliza la respuesta real de Shipit a nuestro contrato {courier, service,
    price, days}. Cada item trae `courier` como OBJETO (no string): el nombre
    está en courier.display_name; `price` ya viene con descuentos aplicados;
    `days` es el SLA y `service_type` el tipo de servicio.
    """
    normalized = []
    for item in prices or []:
        # Shipit puede marcar una tarifa como no despachable a ese destino.
        if item.get('available_to_shipping') is False:
            continue
        price = item.get('price')
        if price is None:
            continue

        courier = item.get('courier') or {}
        nombre = (courier.get('display_name') or courier.get('name') or 'Courier')
        dias = item.get('days')
        normalized.append({
            'courier': nombre.title(),                   # "chilexpress" → "Chilexpress"
            'service': _SERVICE_LABELS.get(item.get('service_type'), ''),
            'price': int(round(float(price))),
            'days': (f'{dias} día hábil' if dias == 1
                     else f'{dias} días hábiles' if dias else ''),
        })
    # Más barato primero: es lo que el cliente espera ver arriba.
    normalized.sort(key=lambda q: q['price'])
    return normalized


def _resolve_commune_id(name):
    """Devuelve el ID de comuna de Shipit para un nombre, o None. Usa la lista
    de comunas cacheada (misma que alimenta el selector del checkout)."""
    if not name:
        return None
    global _COMMUNE_ID_BY_NAME
    if _COMMUNE_ID_BY_NAME is None:
        _COMMUNE_ID_BY_NAME = {}
        for region in get_communes():
            for c in region['communes']:
                if c.get('id') is not None:
                    _COMMUNE_ID_BY_NAME[_norm(c['name'])] = c['id']
    return _COMMUNE_ID_BY_NAME.get(_norm(name))


def _norm(texto):
    """Normaliza un nombre de comuna para comparar (sin tildes, minúsculas)."""
    import unicodedata
    t = unicodedata.normalize('NFD', (texto or '').strip().lower())
    return ''.join(c for c in t if unicodedata.category(c) != 'Mn')


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
    Lista de regiones→comunas para el selector. Intenta traerla de Shipit y la
    cachea; si falla, usa una lista estática de respaldo SIN cachearla.

    Lo de no cachear el respaldo es importante: la lista estática trae las
    comunas con `id: None`, y sin id de comuna no se puede cotizar de verdad.
    Si Shipit fallaba en la primera petición después de un despliegue, el worker
    se quedaba pegado con esa lista hasta que alguien reiniciara el proceso, y
    todas las cotizaciones de ese worker quedaban rotas. Ahora un fallo puntual
    se reintenta en la petición siguiente.
    """
    global _COMMUNES_CACHE
    if _COMMUNES_CACHE is not None:
        return _COMMUNES_CACHE

    if _has_credentials():
        try:
            resp = requests.get(
                f'{SHIPIT_API_BASE}/v/communes',
                headers=_shipit_headers(),
                timeout=SHIPIT_TIMEOUT,
            )
            communes = _normalize_communes(resp.json())
            if communes:
                _COMMUNES_CACHE = communes   # solo se cachea la lista BUENA
                return communes
            log.error('Shipit devolvió una lista de comunas vacía o ilegible')
        except Exception:
            log.exception('No se pudo traer la lista de comunas de Shipit')

    return _STATIC_COMMUNES


def _normalize_communes(data):
    """
    Normaliza la respuesta real de Shipit a [{region, communes:[{id, name}]}].

    OJO: Shipit trae `region` como OBJETO ({'id':13,'name':'Los Lagos'}) y
    además `region_name` como string. Hay que usar el string: si se agrupa por
    el objeto (no hasheable de forma útil), reviéntala y todo caía a la lista
    estática con id=None, y sin id la cotización real es imposible.
    """
    if not isinstance(data, list) or not data:
        return None
    by_region = {}
    for c in data:
        region = c.get('region_name')
        if not region:
            reg = c.get('region')
            region = reg.get('name') if isinstance(reg, dict) else (reg or 'Chile')
        by_region.setdefault(region, []).append({
            'id': c.get('id'),
            'name': c.get('name') or c.get('commune_name'),
        })
    # Comunas ordenadas alfabéticamente dentro de cada región (para el selector).
    return [
        {'region': r, 'communes': sorted(cs, key=lambda x: x['name'] or '')}
        for r, cs in sorted(by_region.items())
    ]


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
