# Despliegue — servidor de pruebas

Servidor: Hetzner · https://ecommercesoledad.duckdns.org
Rama: `redesign-figma`

Sigue siendo un entorno de **pruebas**: las pasarelas apuntan a sus ambientes de
integración, no se mueve plata real y las boletas son simuladas (sin validez
ante el SII).

---

## Primera instalación

```bash
# 1. Paquetes del sistema
sudo apt update
sudo apt install -y python3-venv python3-pip nginx git sqlite3 certbot python3-certbot-nginx
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# 2. Código
sudo mkdir -p /srv/ingenioblocks /srv/respaldos
sudo chown -R $USER:$USER /srv/ingenioblocks /srv/respaldos
git clone -b redesign-figma https://github.com/marcelopc2/ecommerce_soledad.git /srv/ingenioblocks
cd /srv/ingenioblocks
mkdir -p logs

# 3. Entorno de Python
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. Configuración
cp deploy/env.pruebas.example .env
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
nano .env          # pegar la SECRET_KEY y completar lo marcado con <<< >>>
chmod 600 .env

# 5. Base de datos y estáticos
python manage.py migrate
python manage.py collectstatic --no-input
python manage.py createsuperuser

# 6. Frontend
cd frontend && npm ci && npm run build && cd ..

# 7. Servicio
sudo cp deploy/ingenioblocks.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ingenioblocks
sudo systemctl status ingenioblocks

# 8. nginx + certificado
sudo cp deploy/nginx.conf /etc/nginx/sites-available/ingenioblocks
sudo ln -sf /etc/nginx/sites-available/ingenioblocks /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d ecommercesoledad.duckdns.org

# 9. Permisos (el servicio corre como www-data)
sudo chown -R www-data:www-data /srv/ingenioblocks
sudo chmod 600 /srv/ingenioblocks/.env

# 10. Tareas programadas
chmod +x deploy/*.sh
crontab -e
```

Dos líneas, las dos necesarias:

```cron
# Respaldo diario de la base y los archivos subidos (4:15 AM)
15 4 * * * /srv/ingenioblocks/deploy/respaldar.sh >> /srv/ingenioblocks/logs/respaldos.log 2>&1

# Avisos del goteo semanal (9:00 AM). SIN ESTO el alumno nunca se entera de que
# se liberó su modelo nuevo, que es la promesa central del plan mensual.
0 9 * * * cd /srv/ingenioblocks && venv/bin/python manage.py enviar_avisos_desbloqueo >> logs/avisos.log 2>&1
```

Para ver qué haría sin mandar nada:

```bash
cd /srv/ingenioblocks && venv/bin/python manage.py enviar_avisos_desbloqueo --simular
```

Cada alumno tiene su propio calendario contado desde **su** fecha de compra: el
que compró un miércoles recibe su modelo nuevo los miércoles. El comando es
idempotente (lleva registro en `UnlockNotice`), así que correrlo dos veces el
mismo día no manda correos repetidos.

---

## Actualizaciones

```bash
cd /srv/ingenioblocks && ./deploy/desplegar.sh
```

Respalda, trae los cambios, migra, compila, reinicia y **comprueba que la API
responda 200** antes de darse por terminado. Si algo falla, muestra el log y
sale con error.

---

## Comprobaciones después de desplegar

```bash
sudo systemctl status ingenioblocks
curl -s -o /dev/null -w '%{http_code}\n' https://ecommercesoledad.duckdns.org/api/catalog/products/
tail -f logs/ingenioblocks.log
tail -f logs/pagos.log        # todo lo que toca plata
```

En el navegador:

- La portada carga y el menú de celular abre (achicar la ventana bajo 1200px).
- `/gestion/` pide contraseña y entra.
- **`/protected_media/loquesea` debe dar 404.** Si descarga un archivo, nginx lo
  está sirviendo directo y el contenido pagado quedó abierto a cualquiera.
- Con `DEBUG=False`, una URL inventada muestra la página 404 de la marca y
  **ningún traceback**.

---

## Volver atrás

```bash
cd /srv/ingenioblocks
git log --oneline -10
git checkout <commit-anterior>
./deploy/desplegar.sh
```

Para restaurar la base (detener el servicio primero):

```bash
sudo systemctl stop ingenioblocks
gunzip -c /srv/respaldos/base-AAAAMMDD-HHMMSS.sqlite3.gz > db.sqlite3
sudo chown www-data:www-data db.sqlite3
sudo systemctl start ingenioblocks
```

---

## Cosas que se rompen fácil

**El `.env` no se carga y el sitio arranca en modo depuración.** No debería
pasar: `DEBUG` tiene `False` por defecto justamente para eso. Pero conviene
comprobarlo después de cada instalación provocando un 404 y confirmando que no
aparece un traceback.

**nginx sirviendo `protected_media/`.** Es el error más caro: publica gratis el
contenido que se vende. La configuración lo bloquea explícitamente; no agregar
un `alias` a esa carpeta por ningún motivo.

**`PROXY_COUNT` mal puesto.** En 0 detrás de nginx, django-axes ve siempre la IP
del proxy y al quinto intento fallido de cualquiera **bloquea a todo el mundo**.
Debe ir en 1, y nginx debe sobrescribir `X-Forwarded-For` con `$remote_addr`
(no `$proxy_add_x_forwarded_for`, que conserva lo que mandó el cliente y se
puede falsificar).

**`media/` se pierde al redesplegar.** Hoy está versionado porque solo tiene el
contenido semilla de la portada. En cuanto la clienta suba sus propias imágenes
en el servidor hay que sacarlo del repositorio y respaldarlo aparte.

---

## Lo que falta antes de vender de verdad

- Contraseña de aplicación de Gmail (hoy los correos se escriben en el log, no
  se envían).
- Credenciales de producción de Transbank, MercadoPago y OpenFactura.
- ~~El cron del goteo semanal~~ ya existe (`enviar_avisos_desbloqueo`), pero no
  sirve de nada hasta que el correo salga de verdad (falta la clave de Gmail).
- Términos y condiciones, política de privacidad y el derecho a retracto de 10
  días. El sitio pide el nombre de un menor de edad para el diploma.
- Copiar `/srv/respaldos` fuera del servidor.
- Migrar a Postgres si se espera algo de tráfico.
