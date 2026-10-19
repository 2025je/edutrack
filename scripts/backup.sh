#!/bin/sh
# Respaldo programado de PostgreSQL y de los archivos subidos (media).
#
# Se ejecuta dentro del servicio `backup` de docker-compose.yml. Cada ciclo:
#   1. Genera un volcado comprimido (pg_dump -Fc) y una copia de media.
#   2. Prueba la restauración: restaura el volcado en una base temporal y compara
#      las tablas y sus filas con la base real.
#   3. Conserva solo los últimos BACKUP_KEEP respaldos de cada tipo.
#
# Variables (todas opcionales): BACKUP_DIR, BACKUP_KEEP (14), BACKUP_HOUR_UTC (7 = 02:00 en Perú),
# BACKUP_ON_START (1: respalda también al arrancar el servicio).
set -u

BACKUP_DIR=${BACKUP_DIR:-/backups}
KEEP=${BACKUP_KEEP:-14}
AT_HOUR=${BACKUP_HOUR_UTC:-7}
ON_START=${BACKUP_ON_START:-1}
MEDIA_DIR=${MEDIA_DIR:-/srv/media}
export PGHOST="${DB_HOST:-db}" PGPORT="${DB_PORT:-5432}" PGUSER="$DB_USER" PGPASSWORD="$DB_PASSWORD"
SCRATCH="${DB_NAME}_verify"

log() { echo "[backup $(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

prune() {
  # $1 = carpeta, $2 = patrón. Borra los más antiguos y deja KEEP.
  ls -1t "$1"/$2 2>/dev/null | tail -n +"$((KEEP + 1))" | while read -r old; do
    rm -f "$old" && log "Eliminado respaldo antiguo: $old"
  done
}

count_rows() {
  psql -At -d "$1" -c "SELECT count(*) FROM public.\"$2\"" 2>/dev/null
}

verify_dump() {
  dump="$1"
  psql -d postgres -qAt -c "DROP DATABASE IF EXISTS \"$SCRATCH\"" >/dev/null || return 1
  psql -d postgres -qAt -c "CREATE DATABASE \"$SCRATCH\"" >/dev/null || return 1
  if ! pg_restore --no-owner --no-privileges --exit-on-error -d "$SCRATCH" "$dump"; then
    log "ERROR: pg_restore falló al probar la restauración."
    psql -d postgres -qAt -c "DROP DATABASE IF EXISTS \"$SCRATCH\"" >/dev/null
    return 1
  fi
  status=0
  tables=$(psql -At -d "$DB_NAME" -c "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1")
  total=0
  for t in $tables; do
    live=$(count_rows "$DB_NAME" "$t")
    restored=$(count_rows "$SCRATCH" "$t")
    if [ -z "$restored" ]; then
      log "ERROR: la tabla $t no existe en la restauración."
      status=1
    elif [ "$live" != "$restored" ]; then
      # Puede haber escrituras entre el volcado y la verificación.
      log "AVISO: $t tiene $live filas en vivo y $restored restauradas."
    fi
    total=$((total + ${restored:-0}))
  done
  psql -d postgres -qAt -c "DROP DATABASE IF EXISTS \"$SCRATCH\"" >/dev/null
  [ "$status" -eq 0 ] && log "Restauración verificada: $total filas en $(echo "$tables" | wc -w) tablas."
  return "$status"
}

backup_once() {
  stamp=$(date -u +%Y%m%d_%H%M%S)
  mkdir -p "$BACKUP_DIR/db" "$BACKUP_DIR/media"
  file="$BACKUP_DIR/db/${DB_NAME}_$stamp.dump"

  if ! pg_dump -Fc -d "$DB_NAME" -f "$file.partial"; then
    rm -f "$file.partial"
    log "ERROR: pg_dump falló."
    echo "FALLIDO $stamp pg_dump" > "$BACKUP_DIR/STATUS"
    return 1
  fi
  mv "$file.partial" "$file"
  log "Base de datos respaldada: $file ($(du -h "$file" | cut -f1))."

  if [ -d "$MEDIA_DIR" ] && [ -n "$(ls -A "$MEDIA_DIR" 2>/dev/null)" ]; then
    media="$BACKUP_DIR/media/media_$stamp.tar.gz"
    if tar -czf "$media.partial" -C "$MEDIA_DIR" .; then
      mv "$media.partial" "$media"
      log "Archivos subidos respaldados: $media."
    else
      rm -f "$media.partial"
      log "ERROR: no se pudo respaldar media."
    fi
  fi

  if verify_dump "$file"; then
    echo "OK $stamp $file" > "$BACKUP_DIR/STATUS"
  else
    echo "FALLIDO $stamp verificacion" > "$BACKUP_DIR/STATUS"
    return 1
  fi
  prune "$BACKUP_DIR/db" "*.dump"
  prune "$BACKUP_DIR/media" "*.tar.gz"
}

seconds_until_next_run() {
  h=$(date -u +%H); m=$(date -u +%M); s=$(date -u +%S)
  now=$(( ${h#0} * 3600 + ${m#0} * 60 + ${s#0} ))
  echo $(( (AT_HOUR * 3600 - now + 86400) % 86400 ))
}

log "Servicio de respaldos iniciado (diario a las ${AT_HOUR}:00 UTC, se conservan $KEEP)."
until pg_isready -q; do sleep 2; done
[ "$ON_START" = "1" ] && backup_once
while true; do
  wait_s=$(seconds_until_next_run)
  [ "$wait_s" -lt 60 ] && wait_s=$((wait_s + 86400))
  log "Próximo respaldo en ${wait_s}s."
  sleep "$wait_s"
  backup_once
done
