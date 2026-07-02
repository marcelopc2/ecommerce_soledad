# Integración de Envíos con Shipit — Diseño

**Proyecto:** IngenioBlocks (ecommerce Django REST + React)
**Fecha:** 2026-07-01
**Estado:** Diseño aprobado, pendiente de implementación

---

## 1. Contexto y objetivo

La tienda vende juegos de bloques educativos (productos físicos) y packs digitales
(PDFs/cursos). Los pagos con Webpay (Transbank) y MercadoPago ya están construidos y
verificados end-to-end, incluyendo verificación segura del pago contra la API.

Falta el **despacho**: cotizar envíos en vivo con Shipit, sumar el costo al total que se
cobra, guardar la dirección/tracking, y permitir a la clienta generar la etiqueta.

### Decisiones de producto (acordadas)

| Tema | Decisión |
|---|---|
| Cobro del envío | Tarifa **real de Shipit en vivo** (no plana, no gratis) |
| Opciones de entrega | **Solo courier** (sin retiro en tienda) |
| Creación del envío en Shipit | **Manual** desde el admin de Django (no automático al pagar) |
| Productos digitales | **No se envían** (no requieren dirección ni Shipment) |
| Alcance del carrito | **Un producto por orden** (como hoy); carrito multi-ítem queda fuera |

### Estado actual del código (punto de partida)

- App `shipments`: endpoint `POST /api/shipping/quote/` que hoy devuelve tarifas **mock**
  (Starken/Bluexpress/Chilexpress simuladas). Sin modelos.
- App `shipping`: vacía y sin uso → **se elimina** (duplica el nombre de `shipments`).
- `Order` (app payments): no guarda datos de envío; `total_amount` es solo el precio del producto.
- Frontend: una sola vista, sin carrito, sin dirección, sin router.
- Productos ya traen `weight_kg`, `width_cm`, `height_cm`, `length_cm` e `is_digital`.

### Bloqueo conocido del lado de la cuenta Shipit

Credenciales reales ya en `.env` (`SHIPIT_EMAIL=srodriguez@bbureau.cl`). El token
**autentica correctamente** contra `POST https://api.shipit.cl/v/rates`, pero la cuenta
devuelve `{prices:[], message:"Sin Precios, Tarifas de Emergencia no Configuradas", state:error}`
para toda comuna/versión. Es **configuración de la cuenta** (couriers/tarifas no habilitados
para cotización por API, o faltan tarifas de emergencia), no del código.

**Acción externa pendiente:** la clienta/usuario debe resolverlo con soporte Shipit
(ayuda@shipit.cl) o en el panel. Mientras tanto se construye contra el **mock** (fallback ya
previsto); al habilitarse la cuenta, el token real —ya funcional— toma el control sin cambios de código.

---

## 2. Modelo de datos

Nuevo modelo `Shipment` en la app `shipments`, ligado 1:1 a `Order`. La orden sigue enfocada
en el pago; el envío vive aparte.

```python
# shipments/models.py
class Shipment(models.Model):
    order = OneToOneField(Order, related_name='shipment', on_delete=CASCADE)

    # Destinatario
    recipient_name   = CharField
    recipient_phone  = CharField          # Shipit lo exige
    recipient_email  = EmailField         # por defecto = order.customer_email

    # Destino
    region           = CharField
    commune          = CharField
    commune_id       = IntegerField       # id interno de Shipit
    address_street   = CharField
    address_number   = CharField
    address_detail   = CharField(blank=True)   # depto/oficina/referencia

    # Cotización elegida (se guarda al checkout)
    courier          = CharField
    service_name     = CharField
    shipping_cost    = IntegerField       # CLP; se suma a Order.total_amount
    estimated_days   = CharField

    # Snapshot del paquete (al cotizar)
    weight_kg, width_cm, height_cm, length_cm = DecimalField...

    # Despacho (lo llena la clienta desde el admin)
    shipit_reference = CharField(blank=True)
    tracking_number  = CharField(blank=True)
    label_url        = URLField(blank=True)    # PDF de la etiqueta
    status           = CharField(choices=STATUS, default='PENDING_DISPATCH')

    created_at, dispatched_at = DateTimeField...
```

**Estados (`status`):**
`PENDING_DISPATCH` (pagado, sin crear en Shipit) → `CREATED` (etiqueta generada) →
`IN_TRANSIT` → `DELIVERED`; más `ERROR` si Shipit falla al crear.

**Reglas:**
- Se crea `Shipment` **solo si la orden tiene ≥1 producto físico**. Orden 100% digital → sin `Shipment`, sin dirección.
- `shipping_cost` se suma a `Order.total_amount` para cobrar producto + envío juntos.
- Paquete = suma de peso/alto de los productos + máximo de ancho/largo (como el mock actual),
  con fallback a **paquete por defecto configurable** (10×10×10 cm, 1 kg) si falta algún dato
  — igual que el plugin WooCommerce de la clienta.

---

## 3. Servicios Shipit y endpoints

Toda la lógica de Shipit en `shipments/services.py`.

**Servicios:**
1. `get_shipping_quotes(commune_id, package)` — llamada real a Shipit (`POST /v/rates`, headers
   `X-Shipit-Email` / `X-Shipit-Access-Token`). Devuelve opciones de courier (precio, días).
   **Fallback al mock** si no hay credenciales o si Shipit no devuelve precios.
2. `create_shipit_shipment(shipment)` — crea el envío real (`POST /v/shipments`); devuelve
   referencia + tracking + URL de etiqueta. Se llama desde el admin.
3. `get_communes()` — regiones→comunas con `commune_id` de Shipit para el selector del frontend.
   Se **cachea** (no cambia seguido); lista estática de respaldo si falla.

**Endpoints (app `shipments`):**

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/shipping/communes/` | Regiones y comunas para el selector |
| `POST` | `/api/shipping/quote/` | `product_ids` + `commune_id` → arma paquete → opciones de courier |

**Detalle del `quote`:** si todos los productos son digitales → responde
`{ "shipping_required": false }` y el frontend salta el paso de envío. Si hay ≥1 físico → arma
el paquete y cotiza.

**Notas:** confirmar endpoints/versión exacta contra la doc vigente de Shipit al implementar.
Confirmar si Shipit ofrece ambiente sandbox antes de probar `create_shipit_shipment`
(la creación de envío usa saldo real y genera etiqueta real; la cotización es solo lectura).

---

## 4. Integración con la orden y el pago

El frontend cotiza y el cliente elige courier **antes** de pagar; esa selección viaja al
endpoint de crear pago (Webpay/MercadoPago), que ahora acepta un objeto `shipping` opcional:

```json
{
  "product_ids": [1],
  "email": "cliente@correo.cl",
  "shipping": {
    "recipient_name": "...", "recipient_phone": "...",
    "region": "...", "commune": "Providencia", "commune_id": 123,
    "address_street": "...", "address_number": "...", "address_detail": "",
    "courier": "Chilexpress", "service_name": "Normal", "shipping_cost": 3990
  }
}
```

**Seguridad — no confiar en el `shipping_cost` del cliente:**
El backend **re-cotiza** con Shipit el mismo paquete+comuna, ubica el courier elegido y usa
**ese** precio autoritativo (no el enviado por el cliente) para el total. Impide manipular el
costo de envío. Mismo criterio que la verificación del monto de pago ya implementada.

**Cálculo del total:**
```
total_amount = suma(precios de productos) + shipping_cost_validado
```
`total_amount` es lo que ya cobran Webpay/MercadoPago (esa parte no cambia). Orden 100% digital
→ sin `shipping`, sin `Shipment`, total = solo productos.

**Refactor de paso:** las vistas de crear pago (Webpay y MP) hoy duplican la lógica de armar la
orden y el total. Se extrae un helper compartido `build_order_from_request()` que parsea
productos, valida el envío, calcula el total y crea `Order` + `Shipment`. Ambas vistas lo usan.

---

## 5. Admin — crear el envío

La clienta opera desde `/admin` (Django). En `shipments/admin.py`:

- Registrar `Shipment` con `list_display`: nº orden, cliente, comuna, courier, estado, tracking,
  link a etiqueta. Filtros por estado y courier; búsqueda por tracking/email/orden.
- **Acción "Crear envío en Shipit"** (sobre uno o varios envíos seleccionados):
  1. Verifica orden **pagada** y `Shipment` en `PENDING_DISPATCH`.
  2. Llama `create_shipit_shipment()` → guarda referencia + tracking + `label_url`, estado `CREATED`.
  3. **Errores:** si Shipit falla → estado `ERROR` + mensaje en el admin (Django `messages`); no se cae.
  4. **Idempotente:** si ya está `CREATED`, no vuelve a crear (evita etiquetas y cobros duplicados).

**Flujo de la clienta:** `/admin` → Envíos → filtra "pagados, pendientes de despacho" →
selecciona → acción "Crear envío en Shipit" → descarga etiquetas (PDF) → imprime, empaqueta, despacha.

Enviar el tracking por email al cliente queda como **opcional futuro** (no hay backend de email aún).

---

## 6. Frontend — checkout con envío

Se introduce **React Router**. Nueva vista `/checkout` en 3 pasos:

1. **Contacto:** nombre, email, teléfono (reemplaza el email hardcodeado actual).
2. **Entrega** *(solo si el producto es físico):*
   - Selector **Región → Comuna** desde `GET /api/shipping/communes/`.
   - Dirección: calle, número, detalle.
   - Botón **"Cotizar envío"** → `POST /api/shipping/quote/` → opciones de courier seleccionables.
   - Elegir courier actualiza el **total**.
3. **Pagar:** botones Webpay / MercadoPago, enviando contacto + `shipping` al endpoint de crear pago.

- Producto **digital** → salta el paso 2 (solo contacto + pagar).
- **Resumen del pedido** siempre visible (producto, envío, total).
- **Validación:** no se paga sin contacto completo y —si físico— courier elegido. Loading al
  cotizar; mensaje amable si no hay tarifas (con el mock siempre habrá).
- **De paso:** reemplazar el `alert()` por páginas reales `/checkout/success` y `/checkout/failed`.

---

## 7. Fuera de alcance (YAGNI)

- Carrito multi-ítem (se mantiene un producto por orden).
- Retiro en tienda.
- Envío automático del tracking por email al cliente.
- Creación automática del envío al pagar (es manual desde el admin).
- Webhooks de tracking de Shipit (actualización automática de estado en tránsito).

---

## 8. Dependencias / bloqueos externos

- **Cuenta Shipit:** habilitar cotización por API / tarifas de emergencia (soporte Shipit).
  Hasta entonces se trabaja con el mock. No bloquea la construcción.
- **Confirmar sandbox de Shipit** antes de probar creación real de envíos.
