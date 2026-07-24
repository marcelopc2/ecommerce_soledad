# Despliegue

Dominio: **https://ingenioblocks.com**
Rama: `redesign-figma`

Las pasarelas de pago SIGUEN en sus ambientes de integración: no se mueve plata
real y las boletas son simuladas (sin validez ante el SII). Antes de vender de
verdad hay que poner las credenciales reales (ver el final de este archivo).

## Antes de empezar: el DNS

El dominio `ingenioblocks.com` tiene que apuntar al servidor. En el panel DNS
del dominio, crear:

```
A     @      <IP del servidor>
A     www    <IP del servidor>
```

La propagación tarda de minutos a unas horas. Recién cuando `ping ingenioblocks.com`
responda con la IP del servidor se puede emitir el certificado (paso 9).

---

## Primera instalación

```bash
# 1. Paquetes del sistema
sudo apt update
sudo apt install -y python3-venv python3-pip nginx git certbot python3-certbot-nginx \
                    postgresql postgresql-contrib libpq-dev
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

# 5. Crear la base en Postgres
#    (la clave que pongas acá es la que va en DB_PASSWORD del .env)
sudo -u postgres psql <<'SQL'
CREATE USER ingenioblocks WITH PASSWORD 'la-clave-que-elegiste';
CREATE DATABASE ingenioblocks OWNER ingenioblocks;
SQL

# Comprobar que la app se conecta ANTES de migrar. Si responde "postgresql",
# el .env quedó bien; si dice "sqlite3", falta DB_NAME y hay que corregirlo.
python -c "import django,os;os.environ['DJANGO_SETTINGS_MODULE']='core.settings';django.setup();from django.db import connection;print(connection.vendor)"

# 6. Migraciones y estáticos
python manage.py migrate
python manage.py collectstatic --no-input
python manage.py createsuperuser

# 7. Frontend
cd frontend && npm ci && npm run build && cd ..

# 8. Servicio
sudo cp deploy/ingenioblocks.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ingenioblocks
sudo systemctl status ingenioblocks

# 9. nginx + certificado
sudo cp deploy/nginx.conf /etc/nginx/sites-available/ingenioblocks
sudo ln -sf /etc/nginx/sites-available/ingenioblocks /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d ingenioblocks.com -d www.ingenioblocks.com

# 10. Permisos (el servicio corre como www-data)
sudo chown -R www-data:www-data /srv/ingenioblocks
sudo chmod 600 /srv/ingenioblocks/.env

# 11. Tareas programadas
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
curl -s -o /dev/null -w '%{http_code}\n' https://ingenioblocks.com/api/catalog/products/
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

# El respaldo borra y recrea la base, así que primero hay que soltarla.
sudo -u postgres psql -c "DROP DATABASE ingenioblocks;"
sudo -u postgres psql -c "CREATE DATABASE ingenioblocks OWNER ingenioblocks;"
gunzip -c /srv/respaldos/base-AAAAMMDD-HHMMSS.sql.gz | \
  PGPASSWORD='<clave>' psql -h 127.0.0.1 -U ingenioblocks ingenioblocks

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

- **DNS de ingenioblocks.com apuntando al servidor** + certificado (certbot).
- **Credenciales de producción** de Transbank, MercadoPago y OpenFactura (hoy
  son de integración: no mueven plata y las boletas son simuladas).
- **La contraseña de aplicación de Gmail** en el `.env` del servidor. Ya está
  probada localmente; en el servidor va en `EMAIL_HOST_PASSWORD` (sin espacios).
- **Revisar los textos legales con un abogado** y completar los datos de la
  empresa (`[ ]` en `frontend/src/pages/Legal.jsx`): el sitio pide el nombre de
  un menor para el diploma, así que esto no es opcional.
- Copiar `/srv/respaldos` fuera del servidor (los respaldos actuales viven en el
  mismo disco: sirven para un error propio, no para una caída del servidor).
- Registrar el sitio en Google Search Console y mandarle el sitemap
  (`https://ingenioblocks.com/sitemap.xml`).
