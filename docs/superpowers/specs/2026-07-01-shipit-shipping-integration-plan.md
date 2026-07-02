# Plan de Implementación — Envíos con Shipit

Basado en [el diseño](2026-07-01-shipit-shipping-integration-design.md). Fases incrementales,
cada una construible y testeable por separado. Se construye contra el **mock** (fallback);
al habilitarse la cuenta Shipit, el token real toma el control sin cambios.

---

## Fase 1 — Modelo de datos y limpieza (backend)
1. Eliminar la app `shipping` vacía (quitar de `INSTALLED_APPS`, borrar carpeta).
2. Crear modelo `Shipment` en `shipments/models.py` (campos + estados del diseño).
3. `makemigrations shipments` + `migrate`.
4. Registrar `Shipment` en `shipments/admin.py` (list_display básico, filtros, búsqueda).

**Test:** crear un `Shipment` de prueba desde el shell y verlo en `/admin`.

## Fase 2 — Servicios Shipit (con fallback al mock)
5. Agregar `DEFAULT_PACKAGE` (10×10×10 / 1kg) a `settings.py`.
6. Reescribir `get_shipping_quotes()` → llamada real a `POST /v/rates`; fallback al mock si no
   hay credenciales o si Shipit no devuelve precios.
7. Agregar `get_communes()` (real + lista estática de respaldo, cacheada).
8. Agregar `create_shipit_shipment(shipment)` (aún sin usar; se prueba en Fase 5).

**Test:** `get_shipping_quotes` devuelve mock sin token y datos reales con token (cuando la
cuenta lo permita); `get_communes` devuelve la lista.

## Fase 3 — Endpoints de lectura
9. `GET /api/shipping/communes/` (view + url).
10. Actualizar `POST /api/shipping/quote/`: armar paquete desde `product_ids`; si todo es
    digital → `{shipping_required: false}`; si hay físico → cotizar.

**Test:** `curl` a ambos endpoints; caso digital y caso físico.

## Fase 4 — Integración con orden y pago
11. Extraer helper `build_order_from_request()` (parsea productos, valida `shipping` re-cotizando,
    calcula total, crea `Order` + `Shipment`).
12. Conectar las vistas de crear pago Webpay y MercadoPago al helper.
13. Verificar: total = productos + envío validado; orden digital → sin `Shipment`.

**Test:** `curl` crear pago con `shipping` → total correcto; intento de `shipping_cost` falso →
el backend usa el precio autoritativo, no el del cliente.

## Fase 5 — Acción de admin "Crear envío en Shipit"
14. Acción de admin idempotente, con transiciones de estado y manejo de errores.

**Test:** confirmar primero si Shipit tiene sandbox; probar con cuidado (crea envío real).

## Fase 6 — Frontend (checkout con envío)
15. Agregar React Router; rutas `/`, `/checkout`, `/checkout/success`, `/checkout/failed`.
16. Vista Checkout: paso contacto, paso entrega (selector región→comuna + dirección + cotizar +
    elegir courier), paso pagar. Digital → salta entrega. Resumen del pedido visible.
17. Reemplazar el `alert()` por las páginas de éxito/fallo.

**Test:** flujo completo en navegador con el mock (producto físico y digital).

## Fase 7 — Preparación producción (más adelante)
- Resolver config de cuenta Shipit (soporte), confirmar sandbox, pasar de mock a real.
- Credenciales reales de la clienta y URLs de dominio real.

---

**Orden sugerido de construcción:** Fases 1→6 en secuencia. Las Fases 1-4 son backend puro y se
prueban con `curl`/shell. La Fase 5 requiere cuidado (efecto real en Shipit). La Fase 6 es el frontend.
