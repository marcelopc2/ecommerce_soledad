# LMS + Autenticación + Panel CMS — Diseño

**Proyecto:** IngenioBlocks · **Fecha:** 2026-07-01 · **Estado:** aprobado, en construcción

## Decisiones de producto (acordadas)

| Tema | Decisión |
|---|---|
| Modelo de acceso | Comprar producto **incluye membresía con vencimiento** (N meses configurables por producto) |
| Renovación | **Manual**: al vencer, el cliente compra de nuevo (reusa el pago único ya construido). Sin cobro recurrente. |
| Videos | **Agnóstico**: cada lección guarda una URL de embed (YouTube unlisted / Vimeo / etc. — clienta decide después) |
| Cuenta | **Auto-creada al pagar** + email "define tu contraseña". Checkout sigue sin registro. |
| Alcance del acceso | La membresía da acceso a los cursos **de los productos comprados** (no a todo el catálogo) |
| Gestión de la clienta | **Panel CMS propio en React** (`/panel`, solo staff): CRUD de productos y contenido LMS. El admin de Django queda como herramienta de desarrollo. Futuro: banners, FAQs. |

## Modelo de datos (app `lms`)

- `Course`: título, slug, descripción, imagen (URL), is_active.
- `Lesson`: curso (FK), título, orden, tipo VIDEO|PDF, `video_embed_url` o `pdf_file` (subido a carpeta protegida, NO pública).
- `Membership` (OneToOne con User): `expires_at`, cursos M2M, órdenes de origen. Cada compra **extiende** el vencimiento y agrega cursos.
- `Product.access_months` (int, default 12) y `Product.courses` (M2M) en catalog.

## Autenticación

- Django User (username = email) + **SimpleJWT** (access/refresh).
- Endpoints: `POST /api/auth/login/`, `refresh/`, `GET /api/auth/me/`, `POST /api/auth/set-password/` (uid+token de un solo uso, estándar Django), `POST /api/auth/request-reset/`, `POST /api/auth/change-password/`.
- Emails: framework de Django — **consola en desarrollo**, SMTP de la clienta vía `.env` en producción.

## Otorgamiento al pagar

`lms/services.py::grant_access_for_order(order)` — llamado junto a la emisión de boleta en los 2 puntos donde la orden pasa a PAID. Idempotente (no duplica meses si el webhook repite) y no-bloqueante. Crea/extiende Membership, agrega cursos del producto, envía email de bienvenida (link definir clave) o de extensión.

## Protección de contenido

- PDFs en `protected_media/` (fuera de static/media públicos), servidos SOLO por endpoint autenticado que verifica membresía activa + curso otorgado.
- URLs de video solo se entregan por API autenticada con las mismas verificaciones.
- Membresía vencida: cursos visibles pero bloqueados + botón "Renovar" → checkout normal.

## API del LMS (alumno)

- `GET /api/lms/my-courses/` — cursos + estado membresía (activa/vencida, fecha).
- `GET /api/lms/courses/<slug>/` — lecciones (URLs de video incluidas solo si membresía activa).
- `GET /api/lms/lessons/<id>/pdf/` — descarga protegida del PDF.

## API del CMS (staff only, `IsAdminUser`)

- CRUD productos (+ imágenes por URL, cursos asignados, access_months).
- CRUD cursos y lecciones (subida multipart de PDF, URL de video).
- Lista de membresías (quién, hasta cuándo).

## Frontend (React)

- **Alumno:** `/login`, `/definir-clave/:uid/:token` (también sirve para reset), `/mis-cursos`, `/curso/:slug` (player embed + PDFs), header con estado de sesión.
- **Panel clienta:** `/panel` (guard staff) con sidebar: Productos (lista+form), Cursos (lista+form+lecciones), Membresías. Extensible a banners/FAQs.
- Auth: contexto React + axios interceptor (Bearer token, refresh automático).

## Fuera de alcance
Cobro recurrente, progreso/certificados, cupones, edición de banners/FAQs (fase siguiente del panel).
