# Checklist de despliegue a producción — IngenioBlocks

La seguridad ya está implementada en el código y se activa sola con `DEBUG=False`.
Esto es lo que hay que CONFIGURAR el día del lanzamiento (todo vía `.env`, ver `.env.example`).

## 1. Variables críticas de Django
- [ ] `DEBUG=False`  ← activa HTTPS forzado, HSTS, cookies seguras, API solo JSON
- [ ] `SECRET_KEY=` una nueva generada para producción (NUNCA la de desarrollo)
- [ ] `ALLOWED_HOSTS=` el dominio real (ej: `ingenioblocks.cl,www.ingenioblocks.cl`)
- [ ] `DJANGO_ADMIN_URL=` una ruta secreta (ej: `gestion-x7k2/`) — el admin queda escondido
- [ ] `FRONTEND_URL=https://...` y `BACKEND_PUBLIC_URL=https://...` con el dominio real

## 2. Credenciales reales de la clienta
- [ ] `TBK_ENVIRONMENT=PRODUCCION` + `TBK_API_KEY_ID`/`TBK_API_KEY_SECRET` reales (Transbank los entrega al validar el comercio)
- [ ] `MP_ACCESS_TOKEN=` el token de PRODUCCIÓN de la cuenta MercadoPago de la clienta
- [ ] `SHIPIT_EMAIL`/`SHIPIT_TOKEN` (ya los tenemos) + cuenta habilitada para cotizar por API
- [ ] `OPENFACTURA_API_KEY=` la key real + `OPENFACTURA_API_BASE=https://api.haulmer.com`
- [ ] SMTP real: `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` + host/usuario/clave

## 3. Infraestructura
- [ ] HTTPS con certificado válido (Let's Encrypt / el que dé el hosting) — obligatorio para Webpay/MP
- [ ] Servir Django con gunicorn/uwsgi detrás de nginx (NO runserver)
- [ ] `python manage.py collectstatic` y servir estáticos desde nginx
- [ ] Migrar de SQLite a PostgreSQL (recomendado antes de volumen real de ventas)
- [ ] Respaldos automáticos de la base de datos y de `protected_media/`
- [ ] `python manage.py check --deploy` sin errores en el servidor final

## 4. Verificaciones post-despliegue
- [ ] Compra real de bajo monto con Webpay producción (y anularla)
- [ ] Webhook de MercadoPago llegando al dominio real
- [ ] Boleta real emitida en OpenFactura y visible en el SII
- [ ] Correo "define tu contraseña" llegando a una casilla real
- [ ] Crear envío Shipit real de prueba

## Ya implementado en código (no requiere acción)
- Rate limiting: login 10/min, reset 5/min, pagos 10/min, cotizaciones 30/min, global 120/min
- Validación de contraseñas con los validadores completos de Django
- CORS restringido a orígenes explícitos (nunca abierto)
- Verificación server-side de montos (pagos y envíos) — no se confía en el cliente
- Confirmación de MercadoPago contra su API + webhook (URL de retorno no falsificable)
- Contenido LMS protegido por membresía (PDFs fuera de carpetas públicas)
- Refresh tokens JWT con rotación + blacklist
- Solo PDFs subibles como material de curso
- El server NO arranca en producción sin SECRET_KEY
