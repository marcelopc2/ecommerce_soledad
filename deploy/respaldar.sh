#!/usr/bin/env bash
# ============================================================================
# Respaldo de la base y de los archivos subidos.
#
# A mano:   ./deploy/respaldar.sh
# Diario:   crontab -e  ->  15 4 * * * /srv/ingenioblocks/deploy/respaldar.sh
#
# Guarda los últimos RETENCION días y borra los más viejos.
#
# IMPORTANTE: esto respalda DENTRO del mismo servidor. Sirve para recuperarse
# de un error propio (una migración mala, un borrado), pero NO de que se caiga
# el servidor o se pierda el disco. Para eso hay que copiar /srv/respaldos a
# otra parte (rsync a otra máquina, un bucket, o snapshots del proveedor).
# ============================================================================
set -euo pipefail

RAIZ="${RAIZ:-/srv/ingenioblocks}"
DESTINO="${DESTINO:-/srv/respaldos}"
RETENCION="${RETENCION:-14}"       # días que se conservan
FECHA=$(date +%Y%m%d-%H%M%S)

mkdir -p "$DESTINO"
cd "$RAIZ"

# --- Base de datos ---
if [ -n "${DB_NAME:-}" ]; then
    # Postgres
    PGPASSWORD="${DB_PASSWORD:-}" pg_dump \
        -h "${DB_HOST:-127.0.0.1}" -U "${DB_USER:-ingenioblocks}" "$DB_NAME" \
        | gzip > "$DESTINO/base-$FECHA.sql.gz"
    echo "Base (Postgres) -> base-$FECHA.sql.gz"
elif [ -f db.sqlite3 ]; then
    # SQLite: se usa .backup y NO cp, porque copiar el archivo mientras hay
    # escrituras puede dejar una copia corrupta.
    sqlite3 db.sqlite3 ".backup '$DESTINO/base-$FECHA.sqlite3'"
    gzip -f "$DESTINO/base-$FECHA.sqlite3"
    echo "Base (SQLite) -> base-$FECHA.sqlite3.gz"
else
    echo "AVISO: no se encontró ninguna base que respaldar."
fi

# --- Archivos subidos ---
# protected_media son los PDF e imágenes de los modelos: es el producto que se
# vende y no está en git. media son las fotos de la portada.
tar czf "$DESTINO/archivos-$FECHA.tar.gz" \
    $( [ -d protected_media ] && echo protected_media ) \
    $( [ -d media ] && echo media ) 2>/dev/null || true
echo "Archivos -> archivos-$FECHA.tar.gz"

# --- Limpieza de los viejos ---
find "$DESTINO" -name 'base-*' -mtime +"$RETENCION" -delete
find "$DESTINO" -name 'archivos-*' -mtime +"$RETENCION" -delete

echo "Respaldos guardados en $DESTINO (se conservan $RETENCION días):"
ls -lh "$DESTINO" | tail -6
