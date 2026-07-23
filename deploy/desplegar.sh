#!/usr/bin/env bash
# ============================================================================
# Despliegue de Ingenio Blocks en el servidor de pruebas.
#
#   ssh usuario@servidor
#   cd /srv/ingenioblocks && ./deploy/desplegar.sh
#
# Es idempotente: se puede correr las veces que haga falta.
# Antes de tocar nada respalda la base, así que si algo sale mal se puede
# volver atrás con deploy/restaurar.sh.
# ============================================================================
set -euo pipefail

RAIZ="${RAIZ:-/srv/ingenioblocks}"
RAMA="${RAMA:-redesign-figma}"
SERVICIO="${SERVICIO:-ingenioblocks}"
# Dominio contra el que se comprueba al final. Mientras el DNS de ingenioblocks.com
# no apunte al servidor, correr con:  DOMINIO=ecommercesoledad.duckdns.org ./deploy/desplegar.sh
DOMINIO="${DOMINIO:-ingenioblocks.com}"

cd "$RAIZ"

echo "==> 1/7  Respaldando antes de empezar"
./deploy/respaldar.sh

echo "==> 2/7  Trayendo los cambios de la rama $RAMA"
git fetch --all --prune
git checkout "$RAMA"
git pull --ff-only origin "$RAMA"

echo "==> 3/7  Dependencias de Python"
source venv/bin/activate
pip install -q -r requirements.txt

echo "==> 4/7  Migraciones"
python manage.py migrate --no-input

echo "==> 5/7  Estáticos"
python manage.py collectstatic --no-input --clear

echo "==> 6/7  Compilando el frontend"
cd frontend
npm ci --silent
npm run build
cd "$RAIZ"

echo "==> 7/7  Reiniciando el servicio"
sudo systemctl restart "$SERVICIO"
sleep 3
sudo systemctl is-active --quiet "$SERVICIO" || {
    echo "ERROR: el servicio no quedó arriba. Últimas líneas del log:"
    sudo journalctl -u "$SERVICIO" -n 40 --no-pager
    exit 1
}

# Comprobación real: que el sitio responda, no solo que el proceso exista.
CODIGO=$(curl -s -o /dev/null -w '%{http_code}' "https://$DOMINIO/api/catalog/products/")
if [ "$CODIGO" != "200" ]; then
    echo "ERROR: la API en $DOMINIO respondió HTTP $CODIGO (se esperaba 200)."
    echo "  Si el DNS de $DOMINIO todavía no apunta al servidor, repite con:"
    echo "  DOMINIO=ecommercesoledad.duckdns.org ./deploy/desplegar.sh"
    sudo journalctl -u "$SERVICIO" -n 40 --no-pager
    exit 1
fi

echo
echo "Listo. La API responde 200 y el servicio está activo."
echo "   Sitio:  https://$DOMINIO"
echo "   Panel:  https://$DOMINIO/gestion/"
