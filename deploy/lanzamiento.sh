#!/usr/bin/env bash
# ============================================================================
# Lanzamiento de ingenioblocks.com en este servidor. Tres pasos, en orden:
#
#   bash deploy/lanzamiento.sh importar /root/wp-final.sql
#       Con WordPress YA en mantenimiento y sus renovaciones de Transbank
#       APAGADAS. Respalda, rehace alumnos/membresías/avance/historial desde el
#       volcado final, trae las suscripciones y tarjetas, y borra el volcado.
#
#   bash deploy/lanzamiento.sh dominio
#       Cuando el DNS de ingenioblocks.com y www ya apunta a este servidor.
#       Saca el certificado, instala deploy/nginx-produccion.conf, cambia el
#       .env al dominio real y verifica que responda.
#       Ojo: desde acá los cobros quedan PERMITIDOS por código; igual siguen
#       apagados hasta prenderlos en Ajustes → Interruptores. Los correos a
#       clientes siguen EN PAUSA (interruptor "Correos a clientes").
#
#   bash deploy/lanzamiento.sh tareas
#       Programa las tareas diarias: cobro de suscripciones y avisos de modelo
#       nuevo (los avisos respetan la pausa de correos).
#
# Cada paso se puede repetir sin romper nada.
# ============================================================================
set -euo pipefail
RAIZ=/srv/ingenioblocks
cd "$RAIZ"
PY="sudo -u www-data venv/bin/python"

paso_importar() {
    local volcado="${1:?Falta la ruta del volcado .sql}"
    [ -f "$volcado" ] || { echo "No encuentro $volcado"; exit 1; }
    # www-data no puede leer dentro de /root: el volcado se pasa a una carpeta
    # propia, legible solo por root y www-data, y se borra al terminar.
    mkdir -p /srv/lanzamiento && chown root:www-data /srv/lanzamiento && chmod 750 /srv/lanzamiento
    if [ "$(dirname "$(realpath "$volcado")")" != /srv/lanzamiento ]; then
        mv "$volcado" /srv/lanzamiento/ && volcado="/srv/lanzamiento/$(basename "$volcado")"
    fi
    chown root:www-data "$volcado" && chmod 640 "$volcado"
    echo "==> Respaldo antes de importar"
    # El mismo que corre el cron: carga las claves de Postgres del .env.
    /usr/local/bin/ingenioblocks-respaldo
    echo "==> Correos a clientes: confirmando la PAUSA"
    $PY manage.py shell -c "
from comunicaciones.models import AjustesCorreos
a = AjustesCorreos.obtener(); a.pausar_correos_a_clientes = True; a.save()
print('pausa de correos:', a.pausar_correos_a_clientes)" 2>&1 | grep -v 'INFO\|objects imported'
    echo "==> Reimportando desde WordPress (alumnos, membresías, vencimientos, avance, historial)"
    $PY manage.py rehacer_migracion --dump "$volcado" --medios /tmp/medios-lanzamiento --sin-fotos --sin-respaldo --aplicar 2>&1 \
        | grep -v 'INFO' | grep -v "^    [^ ]*@" | tail -25
    echo "==> Suscripciones y tarjetas Oneclick"
    $PY manage.py importar_suscripciones_wordpress --dump "$volcado" --aplicar 2>&1 | grep -v 'INFO' | tail -8
    rm -f "$volcado"
    echo "==> Listo. Volcado borrado del servidor."
}

paso_dominio() {
    echo "==> Certificado para ingenioblocks.com y www"
    certbot certonly --webroot -w /var/www/html -d ingenioblocks.com -d www.ingenioblocks.com \
        --non-interactive --agree-tos --keep-until-expiring -m contacto@ingenioblocks.com
    echo "==> nginx del dominio real"
    cp deploy/nginx-produccion.conf /etc/nginx/sites-available/ingenioblocks-produccion
    ln -sf /etc/nginx/sites-available/ingenioblocks-produccion /etc/nginx/sites-enabled/ingenioblocks-produccion
    nginx -t
    systemctl reload nginx
    echo "==> .env al dominio real (respaldo en .env.antes-del-lanzamiento)"
    [ -f .env.antes-del-lanzamiento ] || cp .env .env.antes-del-lanzamiento
    sed -i 's#^FRONTEND_URL=.*#FRONTEND_URL=https://ingenioblocks.com#' .env
    sed -i 's#^BACKEND_PUBLIC_URL=.*#BACKEND_PUBLIC_URL=https://ingenioblocks.com#' .env
    sed -i 's#^ALLOWED_HOSTS=.*#ALLOWED_HOSTS=ingenioblocks.com,www.ingenioblocks.com,pre.ingenioblocks.com#' .env
    systemctl restart ingenioblocks
    sleep 3
    systemctl is-active --quiet ingenioblocks || { journalctl -u ingenioblocks -n 30 --no-pager; exit 1; }
    echo "==> Verificando"
    curl -sf -o /dev/null -w "  API:            %{http_code}\n" https://ingenioblocks.com/api/health/
    curl -s -o /dev/null -w "  www -> apex:    %{http_code} %{redirect_url}\n" https://www.ingenioblocks.com/
    if curl -sI https://ingenioblocks.com/ | grep -qi 'x-robots-tag'; then
        echo "  OJO: la portada todavía le dice a Google que no la indexe"; exit 1
    fi
    echo "  Google:         puede indexar la portada"
    $PY manage.py shell -c "
from django.conf import settings
from comunicaciones.freno import correos_a_clientes
print('  correos a clientes:', 'SALEN' if correos_a_clientes() else 'en pausa')
print('  cobros permitidos por código:', settings.COBROS_AUTOMATICOS, '(se prenden en Ajustes → Interruptores)')" 2>&1 | grep -v 'INFO\|objects imported'
}

paso_tareas() {
    cat > /etc/cron.d/ingenioblocks-diarias <<'CRON'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
# Instalado por deploy/lanzamiento.sh. Como www-data, igual que los masivos.
# 09:00 avisos de modelo nuevo (respetan la pausa de "Correos a clientes").
# 10:00 cobro de suscripciones (solo cobra si "Cobros automáticos" está prendido
#       en Ajustes → Interruptores, y las de WordPress solo con su interruptor).
0 9 * * * www-data cd /srv/ingenioblocks && flock -n /tmp/ib-avisos.lock venv/bin/python manage.py enviar_avisos_desbloqueo 2>&1 | grep -v 'AXES: BEGIN' >> logs/avisos.log
0 10 * * * www-data cd /srv/ingenioblocks && flock -n /tmp/ib-cobros.lock venv/bin/python manage.py cobrar_suscripciones 2>&1 | grep -v 'AXES: BEGIN' >> logs/cobros.log
CRON
    chmod 644 /etc/cron.d/ingenioblocks-diarias
    echo "==> Tareas diarias programadas:"
    grep -v '^#' /etc/cron.d/ingenioblocks-diarias | grep www-data
}

case "${1:-}" in
    importar) paso_importar "${2:-}" ;;
    dominio)  paso_dominio ;;
    tareas)   paso_tareas ;;
    *) echo "Uso: bash deploy/lanzamiento.sh importar <volcado.sql> | dominio | tareas"; exit 1 ;;
esac
