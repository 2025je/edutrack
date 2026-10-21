# DESTRUCTIVO: borra las llamadas registradas, las reservas de la cola y las marcas de WhatsApp.
# Conserva sublistas, plantillas y teléfonos. Pide escribir una confirmación.
# Uso: powershell -ExecutionPolicy Bypass -File .\scripts\clear-calls.ps1 [-Campus <id>]
param([int]$Campus = 0)

docker compose up -d db web
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$extra = @()
if ($Campus -gt 0) { $extra += @("--campus", $Campus) }
docker exec -it django_app python manage.py clear_calls @extra
exit $LASTEXITCODE
