# Propuesta de Desarrollo — Tienda Online + Plataforma de Cursos "IngenioBlocks"

**Preparado para:** [Nombre de la clienta] — [Empresa / RUT]
**Preparado por:** [Tu nombre] — [RUT / correo / teléfono]
**Fecha:** [__ / __ / 2026]
**Validez de esta propuesta:** 30 días corridos

---

## 1. Resumen

Desarrollo de una **tienda online moderna, propia y liviana** (sin depender de WordPress/WooCommerce) para la venta de los productos de bloques educativos, integrada con los servicios que usa el negocio en Chile (pago, despacho y boleta electrónica) y con una **plataforma de cursos (LMS)**: al comprar un producto, el cliente accede automáticamente a videos y documentos asociados.

El sistema incluye además un **panel de administración a medida** para que la clienta gestione sus productos y contenidos por sí misma, sin necesidad de conocimientos técnicos ni de entrar al panel técnico del sistema.

---

## 2. Alcance — Qué incluye

### Tienda (frontend en React)
- Catálogo de productos con página de detalle.
- Carrito / checkout en pasos (datos, despacho, pago).
- Diseño propio, rápido y responsivo (se ve bien en celular y computador).

### Medios de pago
- **Transbank Webpay Plus** (tarjetas de crédito/débito).
- **MercadoPago**.
- Verificación de cada pago en el servidor (no se confía en el navegador del cliente) y confirmación por webhook: un pago rechazado nunca da acceso ni se marca como pagado.

### Despacho
- Integración con **Shipit** para cotizar el envío según comuna y peso del paquete.
- Cálculo del costo de despacho sumado al total, con selección de courier por parte del cliente.

### Boleta electrónica
- Emisión automática de **boleta electrónica (OpenFactura / Haulmer, DTE 39)** al confirmarse el pago, con descarga del PDF.

### Plataforma de cursos (LMS)
- Cursos con lecciones en **video** y **documentos PDF protegidos** (solo accesibles para quien compró).
- **Membresía automática**: al pagar, se crea la cuenta del cliente y se le da acceso a los cursos del producto por el tiempo definido.
- Ingreso con **usuario y contraseña**, correo de bienvenida, y recuperación/cambio de clave.

### Panel de administración para la clienta (CMS a medida)
- Crear/editar/eliminar **productos** y categorías.
- Gestionar **cursos y lecciones** (subir PDFs, agregar videos).
- Ver las **membresías** de los clientes.
- (Ampliable a futuro: banners, preguntas frecuentes, etc.)

### Seguridad y puesta en marcha
- Medidas de seguridad estándar (límites contra ataques de fuerza bruta, validación de contraseñas, HTTPS obligatorio, protección de datos y sesiones).
- Instalación y configuración en servidor con **certificado SSL (HTTPS)** y base de datos profesional.

---

## 3. Qué NO incluye (fuera de alcance)

Para evitar malentendidos, esta propuesta **no** contempla, salvo que se cotice aparte:

- Creación de contenido (textos, fotos de productos, grabación/edición de los videos de los cursos).
- Diseño de logo / identidad de marca.
- Campañas de marketing, SEO avanzado o publicidad.
- Integración con marketplaces (Mercado Libre, Falabella, etc.).
- App móvil nativa.
- Migración masiva de datos desde la tienda actual (se puede cotizar por separado).
- Costos de terceros (ver sección 6).

---

## 4. Requisitos de parte de la clienta

Para poner el sistema en producción se necesita que la clienta provea:

- Credenciales **reales de producción** de Transbank (comercio validado).
- Token **real de producción** de MercadoPago.
- API key **real** de OpenFactura/Haulmer (para boletas con validez ante el SII).
- Cuenta de **Shipit** habilitada para cotizar por API *(actualmente pendiente de configuración con soporte de Shipit)*.
- Un **dominio** (ej. www.ingenioblocks.cl) y una casilla de correo para los envíos automáticos.
- Los contenidos: fotos, descripciones, videos y PDFs de los cursos.

---

## 5. Inversión

| Ítem | Valor (CLP) |
|---|---|
| **Desarrollo completo + puesta en producción** (todo lo descrito en la sección 2) | **$7.900.000** |

> Valores en pesos chilenos. [Agregar según cómo emitas: + IVA 19% / afecto a retención de boleta de honorarios / exento.]

**Forma de pago sugerida:**
- 40% al aceptar la propuesta (inicio).
- 30% al tener el sistema funcionando en ambiente de prueba (demo).
- 30% contra la puesta en producción con las credenciales reales.

**Garantía:** 30 días desde la puesta en producción para corrección de errores sobre lo entregado, sin costo.

---

## 6. Costos de terceros (los asume la clienta)

Estos costos son de proveedores externos y **no** forman parte del valor del desarrollo:

- **Comisiones por venta** de Transbank y MercadoPago (un % de cada transacción).
- **Plan de Shipit** (o Envíame) y el costo de cada despacho.
- **Plan de OpenFactura / Haulmer** para la boleta electrónica.
- **Hosting** del servidor (muy económico, del orden de €5–20/mes) y el **dominio** (~$10.000/año).

---

## 7. Mantención y soporte (mensual, opcional pero recomendado)

Las integraciones dependen de servicios externos (Transbank, MercadoPago, Shipit, SII) que cambian con el tiempo. Para mantener todo funcionando y contar con soporte:

| Plan | Incluye | Valor mensual (CLP) |
|---|---|---|
| **Mantención** | Monitoreo, actualizaciones de seguridad, ajustes ante cambios de las APIs, respaldos, y hasta [X] horas de soporte al mes | **$290.000** |

Fuera del plan, las nuevas funcionalidades se cotizan por separado o con un pack de horas.

---

## 8. Plazos

- Ambiente de prueba (demo funcional): **[ya disponible / X semanas]**.
- Puesta en producción: **[X] días hábiles** una vez recibidas las credenciales reales y los contenidos.

---

## 9. Condiciones

- El código y el sistema quedan de propiedad de la clienta una vez pagado el total.
- Esta propuesta no incluye cambios de alcance; nuevas funcionalidades se cotizan aparte.
- Los tiempos dependen de la entrega oportuna de credenciales y contenidos por parte de la clienta.

---

*Quedo a disposición para revisar cualquier punto y ajustar el alcance según lo que necesites.*

**[Tu nombre]**
[correo] · [teléfono]
