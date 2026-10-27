#!/bin/sh
# Restaura un respaldo sobre la base real. DESTRUCTIVO: reemplaza los datos actuales.
#
#   docker compose stop web
#   docker compose run --rm -e CONFIRM=yes --entrypoint sh backup \
#       /scripts/restore.sh /backups/db/ARCHIVO.dump [/backups/media/ARCHIVO.tar.gz]
#   docker compose start web
set -eu

DUMP="${1:-}"
MEDIA_ARCHIVE="${2:-}"
MEDIA_DIR=${MEDIA_DIR:-/srv/media}

if [ -z "$DUMP" ] || [ ! -f "$DUMP" ]; then
  echo "Uso: restore.sh /backups/db/ARCHIVO.dump [/backups/media/ARCHIVO.tar.gz]" >&2
  echo "Respaldos disponibles:" >&2
  ls -1t /backups/db 2>/dev/null >&2 || true
  exit 2
fi
if [ "${CONFIRM:-}" != "yes" ]; then
  echo "Esto reemplaza todos los datos de ${DB_NAME}. Repite con -e CONFIRM=yes para continuar." >&2
  exit 3
fi

export PGHOST="${DB_HOST:-db}" PGPORT="${DB_PORT:-5432}" PGUSER="$DB_USER" PGPASSWORD="$DB_PASSWORD"

echo "Cerrando conexiones abiertas a ${DB_NAME}..."
psql -d postgres -qAt -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${DB_NAME}' AND pid <> pg_backend_pid()" >/dev/null

echo "Restaurando ${DUMP}..."
pg_restore --clean --if-exists --no-owner --no-privileges --exit-on-error -d "$DB_NAME" "$DUMP"
echo "Base de datos restaurada."

if [ -n "$MEDIA_ARCHIVE" ]; then
  [ -f "$MEDIA_ARCHIVE" ] || { echo "No existe $MEDIA_ARCHIVE" >&2; exit 4; }
  tar -xzf "$MEDIA_ARCHIVE" -C "$MEDIA_DIR"
  echo "Archivos subidos restaurados."
fi
