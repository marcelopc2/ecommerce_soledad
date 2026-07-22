# Informe de estado — Ingenio Blocks

Fecha: 22 de julio de 2026 · Rama `redesign-figma`

Auditoría completa: UI/UX, seguridad, backend, calidad de código y preparación para
producción. Todo lo que aparece acá está verificado contra el código, no inferido.

---

## Resumen en una página

**Lo bueno, y es bastante:** el trabajo hecho es de buena calidad. El sistema visual es
coherente y bonito, el checkout tiene las tres protecciones clásicas que casi nadie pone
(precio autoritativo en el servidor, verificación del pago contra la API de MercadoPago,
control de acceso por sesión), el LMS protege bien los archivos, los correos son mejores
que los de la mayoría del comercio chileno, y los comentarios del código explican el *por
qué*. Nada de esto hay que rehacerlo.

**El problema no es el código escrito, es lo que falta alrededor.** Y hay tres cosas que
hoy impiden lanzar, en este orden:

1. **El proyecto no arranca desde cero.** Hay 78 archivos sin commitear, incluida la app
   `panel/` completa. Si el disco falla hoy, se pierde todo el trabajo del panel.
2. **La base de datos está vacía de contenido.** 5 productos, **0 cursos, 0 lecciones,
   0 productos con cursos asignados**. Una compra hecha hoy cobra la plata y no entrega
   nada: el LMS nunca se ha ejecutado de punta a punta.
3. **Hay bugs en el camino del dinero** que cobran de más, cobran de menos, o cobran y no
   entregan. Detallados abajo.

Además hay un **vacío legal** (sin términos y condiciones, sin política de privacidad, sin
el derecho a retracto de SERNAC) que en un sitio que vende a familias y trata datos de
menores de edad no es opcional.

**Cero tests automatizados.** Los 5 archivos `tests.py` están vacíos.

---

## 1. Lo que hay que arreglar antes de cobrar el primer peso

### 1.1 — Un fallo de red después del cobro deja al cliente pagado y sin nada

`payments/views.py:89`

```python
except Exception as e:
    order.status = 'FAILED'
    order.save()
```

El `commit` de Transbank **cobra**. Si la red se corta después de que Transbank autorizó,
este `except` marca la orden como fallida. El token es de un solo uso: no hay forma de
re-confirmar. La excepción ni siquiera se registra (`e` no se usa en ninguna parte).

Resultado: plata cobrada, sin boleta, sin acceso, y sin ningún rastro para reconciliar.

**Qué hacer:** un estado `EN_REVISION` para el caso "no sé si se cobró", registrar el
error, y un comando que reconcilie contra `tx.status(token)` de Transbank. Nunca marcar
FAILED por una excepción de red.

### 1.2 — Si Shipit no responde, se le cobra al cliente una tarifa inventada

`shipments/services.py:97` → `return _mock_quotes(package)`

Cualquier fallo (Shipit caído, token vencido, comuna no resuelta) cae a un mock que
calcula `3000 + peso*500`. Ese precio inventado se cobra de verdad y se guarda en el envío.
Si el despacho real cuesta $8.000 y se cobró $3.500, la diferencia la paga la tienda, en
silencio.

**Qué hacer:** el mock solo con `DEBUG=True`. En producción, sin cotización real → error
503 al checkout. Son 5 líneas.

### 1.3 — La boleta se emite con precios de lista, no con lo cobrado

`invoicing/services.py:68` → `price = int(product.price)`

Usa `price`, no `effective_price`. Con cualquier producto en oferta, la suma del detalle no
cuadra con el total. Es un documento tributario mal armado.

Peor: lee el precio **actual** del producto. Si mañana suben el precio, las boletas
antiguas re-emitidas salen con el precio nuevo.

### 1.4 — La orden no guarda qué se compró ni a qué precio

`payments/models.py:20` — `products = models.ManyToManyField(Product)`

Un M2M pelado, sin cantidad, sin precio pagado, sin nombre congelado. **Borrar un producto
desde el panel vacía las órdenes históricas** que lo contenían.

**Qué hacer:** un modelo `OrderItem(order, product, nombre_snapshot, precio_unitario,
cantidad)`. Hacerlo ahora que hay 0 ventas reales es infinitamente más barato que después.

### 1.5 — Cero logging en todo el proyecto

Ni un `logger` en 5.742 líneas de Python. Sin `LOGGING` en settings. Hay 5 bloques
`except Exception` que se tragan el error sin dejar rastro.

Cuando un cliente reclame "pagué y no me llegó nada", **no hay forma de saber qué pasó**.
Esto es lo que convierte cualquiera de los otros bugs en irresoluble. Es lo primero que hay
que hacer, porque hace visible todo lo demás.

### 1.6 — Cero `transaction.atomic`

Crear una orden son 3 escrituras sueltas (Order + productos + Shipment). Si el proceso
muere en medio, queda una orden física sin envío con el costo ya cobrado. En `_grant`, si
falla entre guardar la membresía y marcarla, un reintento vuelve a sumar los meses.

### 1.7 — `DEBUG` por defecto en `True`

`core/settings.py:10` — `os.environ.get('DEBUG', 'True')`

Si el `.env` no se carga en el servidor por cualquier motivo, el sitio arranca con DEBUG=True
y expone la `SECRET_KEY`, los tokens de Transbank y las credenciales SMTP en cualquier
traceback. **Invertir el default es una línea.**

### 1.8 — Encabezado `X-Forwarded-For` falsificable

Un atacante que controle ese encabezado rota su IP en cada petición y **anula tanto el
throttling de DRF como el bloqueo de django-axes**. Todo el trabajo de axes queda inutilizado.

**Qué hacer:** configurar nginx para sobrescribir (no agregar a) ese encabezado, y fijar
el conteo de proxies.

### 1.9 — Cambiar la contraseña no invalida las sesiones abiertas

Si a alguien le roban la cuenta, cambiar la clave no expulsa al atacante: los JWT ya
emitidos siguen siendo válidos hasta que expiren.

### 1.10 — El retorno del pago hace hasta 3 llamadas HTTP sin presupuesto de tiempo

Boleta (30s + 30s de timeout) y correos (sin `EMAIL_TIMEOUT` definido) corren **dentro** de
la petición que Transbank redirige. Peor caso >60s; gunicorn corta a los 30s. El worker
muere, el cliente ve un error aunque el pago se completó.

### 1.11 — Todo sin commitear

78 archivos, incluida la app `panel/` completa, `templates/`, y migraciones. Un clon del
repositorio hoy **no arranca**. Y no hay respaldo de nada.

### 1.12 — Migraciones con rutas de Windows escritas a fuego

`lms/migrations/0001`, `0002` y `0005` contienen:

```python
pathlib.PureWindowsPath('C:/Users/MarceloYoga/Desktop/Proyectos/ecommerce/protected_media')
```

En un servidor Linux estas migraciones fallan o crean rutas absurdas. Bloquea el despliegue.

### 1.13 — Vacío legal

Sin términos y condiciones, sin política de privacidad, sin el **derecho a retracto de 10
días** que exige la ley del consumidor chilena para compras a distancia. Y el sitio recoge
**el nombre de un menor de edad** (para el diploma) sin ninguna base legal declarada.

---

## 2. UI/UX

### 2.1 — Hay texto Lorem ipsum en la portada

`frontend/src/pages/Landing.jsx:580` — la sección "Concurso" muestra
*"Lorem ipsum dolor sit amet…"* en producción, justo antes de las preguntas frecuentes.

Es la señal más fuerte posible de "sitio a medio hacer" para alguien que está decidiendo
una compra de decenas de miles de pesos.

### 2.2 — No hay menú en móvil. Ni en tablet. Ni en notebook.

`landing.css:1308` — `@media (max-width: 1200px) { .lp-nav { display: none } }`

Bajo 1200px la navegación desaparece entera y **no hay ningún reemplazo**: no existe
hamburguesa ni menú en todo el proyecto. Y el header no es sticky, así que una vez que
bajas no queda ningún botón de compra a la vista.

El público objetivo compra desde el celular, y hoy tiene que hacer scroll ciego por 10
secciones para encontrar el precio. **Es la mejora de conversión más grande disponible.**

### 2.3 — Después de pagar, el cliente cae en el diseño viejo

`/checkout/success` y `/checkout/failed` son del prototipo anterior: tarjeta gris, emoji,
"Volver a la tienda". No dicen nada de que va a llegar un correo para crear la contraseña,
ni del Aula Virtual, ni cuándo llega el kit.

Es el instante de mayor ansiedad del flujo ("¿me cobraron?, ¿y ahora qué?"). Si el correo
cae en spam, el cliente queda sin ninguna instrucción.

Lo mismo con `/tienda`, que sigue siendo el prototipo viejo — y es el destino del botón
**"Renovar"** de un cliente que quiere volver a pagar.

### 2.4 — El Aula Virtual le dice "no compraste" a quien sí compró

`MyCourses.jsx:59` — con la base vacía (situación actual), alguien que **acaba de pagar**
entra y lee: *"Aún no tienes cursos. Compra un kit en la tienda"*.

Y si la API falla, se ve exactamente igual que si estuviera vacía (`catch(() => setData(...))`),
así que un corte de red se lee como "perdí mi compra".

### 2.5 — Un curso bloqueado muestra una fecha que ya pasó

El desbloqueo tiene dos condiciones (que llegue la fecha **y** que el curso anterior esté
completo), pero la tarjeta solo muestra `🔒 Disponible el {fecha}`. Si el niño no terminó
el modelo 3, el 4 sigue bloqueado mostrando una fecha de hace un mes.

El apoderado concluye "pagué y no funciona". Es el reclamo más caro que existe.

### 2.6 — Sin Open Graph ni meta description

`frontend/index.html` no tiene ninguna de las dos (verificado: 0 coincidencias).

Este producto se distribuye por **WhatsApp entre apoderadas**. Hoy ese link se pega como
una URL pelada, sin imagen ni descripción. Media hora de trabajo, probablemente el mejor
retorno de toda esta lista.

### 2.7 — El diploma se descarga como archivo `.html`

El botón dice "Descargar diploma" pero entrega un HTML que el usuario debe imprimir a mano.
En Android muchas veces ni se abre. El diploma es el momento emocional del producto — lo
que se pega en el refrigerador y se sube a Instagram.

### 2.8 — Otros

- Errores de pago mostrados con `alert()` del navegador (`Checkout.jsx:250`).
- Enlace de contraseña vencido → callejón sin salida (te manda a iniciar sesión, pero
  todavía no tienes contraseña).
- El formulario de contacto no tiene etiquetas (`<label>`), solo placeholders.
- Casi no hay estilos de foco: navegando con Tab no se ve dónde estás.
- Contraste insuficiente en textos secundarios (`#94a3b8` sobre blanco = 2.6:1, falla AA).
- Inputs de menos de 16px → **iOS hace zoom automático en pleno checkout**.
- Los botones flotantes (WhatsApp y subir) tapan el botón de pagar en móvil.
- 1,4 MB de imágenes sin optimizar; `video-taladro.png` pesa 722 KB para mostrarse a 200px.
- Ninguna imagen tiene `loading`, `width` ni `height` → saltos de layout.
- "Recursos" es jerga: un niño de 8 años no sabe qué es. Mejor "pasos" o "clases".

---

## 3. Panel de la clienta

Está claramente por encima del promedio: modal de confirmación propio, drag & drop,
explicaciones en cada tabla, advertencias en los "restaurar por defecto". Pero:

- **El botón de basurero de cursos borra el progreso de todos los alumnos** con una
  confirmación genérica. La clienta no es técnica y ese botón tiene el mismo peso visual
  que "Editar".
- **Trampa de YouTube:** el campo de las lecciones exige formato `/embed/`, pero no
  normaliza. Si copia el link normal de la barra del navegador, el video queda **en blanco
  para el alumno** y en el panel no aparece ningún error. (Para los videos de la portada
  esto sí está resuelto con `extract_youtube_id` — falta aplicarlo acá.)
- Campos técnicos sin traducir: "Slug", "LMS", "ribbon". La portada de curso y del diploma
  se piden como **URL**, no como archivo subible — una persona no técnica no tiene dónde
  hospedar una imagen.
- No hay botón "ver el sitio" para comprobar los cambios.

---

## 4. Rendimiento y escala

- **Ninguna lista tiene paginación.** `/gestion/pedidos/` renderiza todas las órdenes
  históricas. A los 6 meses no carga.
- **N+1 severo en membresías:** con 200 alumnos y 24 cursos son ~5.000 consultas por
  carga de página.
- **Sin índices** en `Order.status`, `created_at`, `customer_email` ni `tbk_token` — este
  último además sin unicidad: dos órdenes con el mismo token = error 500 en pleno pago.
- **Las órdenes abandonadas se acumulan para siempre.** Sin estado `EXPIRADA` ni limpieza.
  Con 60-70% de abandono típico en checkout, la tabla se llena de basura.
- **PDFs de boletas guardados en base64 dentro de la base de datos** (~200 KB por fila).

---

## 5. Lo que falta por completo

| Falta | Por qué importa |
|---|---|
| **Contenido del LMS** | 0 cursos, 0 lecciones. Una compra hoy no entrega nada. |
| **El cron del goteo semanal** | No existe `lms/management/`. El alumno nunca se entera de que se liberó su modelo — y es la promesa central del plan mensual. Hay un comentario en el código que afirma que sí existe. |
| **4 de 8 correos** | `compra_confirmada`, `envio_despachado`, `curso_desbloqueado` y `diploma_obtenido` están escritos pero **nadie los llama**. |
| **Respaldos** | Ninguno, de nada. |
| **Proceso de despliegue** | No hay. Hoy es manual y no reproducible. |
| **Tests** | Cero. Los 5 `tests.py` están vacíos. |
| **Observabilidad** | Sin logs, sin Sentry, sin alertas. |
| **Términos, privacidad, retracto** | Obligatorio por ley. |
| **Migración a Postgres** | Sin resolver. |
| **Contraseña de aplicación de Gmail** | Los correos no salen (error 535). |
| **Probar Shipit de verdad** | `create_shipit_shipment` nunca se ejecutó contra la API real; el propio código lo dice. |
| **Reconciliación de pagos** | Sin ella, un cobro perdido no se detecta nunca. |

---

## 6. Lo que está bien hecho

Vale la pena decirlo con nombre y apellido, porque es más de lo habitual:

- **Las tres protecciones clásicas del comercio chileno están puestas:** no confiar en el
  costo de envío que manda el cliente, verificar el pago contra la API de MercadoPago (con
  chequeo de monto) en vez de creerle al `?status` de la URL, y validar `requires_login`
  en el servidor anclando la compra a la cuenta de la sesión.
- **El control de acceso del LMS está bien pensado:** archivos fuera del árbol público y
  triple verificación (membresía activa + curso otorgado + curso desbloqueado). El
  comentario que explica el ataque que previene es exactamente el correcto.
- **django-axes bien configurado**, incluido el detalle del conteo de proxies que casi todos
  se equivocan.
- **Cero XSS.** Ni un `dangerouslySetInnerHTML`, ni un `|safe` mal puesto.
- **Idempotencia real** donde importa: boletas, otorgamiento de acceso, progreso.
- **Los correos transaccionales** son de calidad profesional: tablas para Outlook, estilos
  en línea, versión de texto plano, logo incrustado.
- **Las páginas de error** con CSS incrustado a propósito (para que funcionen aunque los
  estáticos fallen) y con voz de marca.
- **El checkout**: validación por campo que no hostiliza, buscador de 727 comunas con
  tildes normalizadas, y usa `effective_price` para que lo mostrado coincida con lo cobrado.
- **Los comentarios explican el porqué**, no el qué. Eso es raro y ahorra horas.

---

## 7. Orden sugerido

### Semana 1 — que no se pierda nada
1. Commitear todo y subirlo a un remoto. Hoy.
2. Sacar las rutas de Windows de las 3 migraciones.
3. `DEBUG` por defecto en `False`.
4. Logging + Sentry. **Primero esto**, porque hace visible todo lo demás.

### Semana 2 — que no se pierda plata
5. Arreglar el `except` que marca FAILED tras cobrar + estado de revisión.
6. Matar el fallback a tarifas de envío inventadas.
7. `transaction.atomic` en orden, otorgamiento y verificación de pago.
8. Sacar boleta y correos del request de pago (o bajar los timeouts a 8s).
9. Arreglar `X-Forwarded-For` en nginx.
10. 8-10 tests sobre los caminos de dinero.

### Semana 3 — que el producto exista
11. **Cargar los cursos y lecciones reales**, y hacer una compra completa de prueba de
    punta a punta. Ahí van a aparecer cosas que ninguna lectura estática detecta.
12. El cron del goteo + conectar los 4 correos huérfanos.
13. `OrderItem` con snapshot de precio + arreglar la boleta.
14. Probar Shipit de verdad con un envío real.

### Semana 4 — que se pueda vender
15. Borrar el Lorem ipsum.
16. Menú móvil + header sticky.
17. Rediseñar `/checkout/success` como "qué pasa ahora"; redirigir `/tienda` a `/#kits`.
18. Open Graph + meta description.
19. Arreglar el estado vacío y el mensaje de bloqueo del Aula Virtual.
20. Términos, privacidad y retracto.
21. Respaldos automáticos + despliegue reproducible.

### Después
Paginación, índices, N+1, fechas en hora de Chile (hoy se calculan en UTC, así que el
"lunes" del goteo empieza el domingo a las 21:00), diploma en PDF real, accesibilidad,
optimización de imágenes.

---

## Una última cosa

El código está bien escrito. Lo que le falta al proyecto no es programación: es **contenido
cargado, una prueba de punta a punta con plata real, y la infraestructura alrededor**
(respaldos, logs, despliegue, legal).

El dato que más me preocupa: con 0 cursos en la base, `grant_access_for_order` termina en
`if not courses or months <= 0: return None` para **toda** compra actual. Es decir, todo el
LMS —membresías, goteo, diplomas, correos— **nunca se ha ejecutado de verdad ni una sola
vez**. Antes de lanzar hay que hacer al menos una compra completa con un producto que sí
otorgue cursos.
