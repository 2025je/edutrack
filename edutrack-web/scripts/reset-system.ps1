# DESTRUCTIVO: elimina todos los usuarios y datos del sistema y crea un superusuario nuevo.
# Pide solo nombre y contraseña. Conserva los grupos de roles. Borra también los archivos subidos
# salvo que se use -KeepMedia.
# Uso: powershell -ExecutionPolicy Bypass -File .\scripts\reset-system.ps1 [-KeepMedia]
param([switch]$KeepMedia)

docker compose up -d db web
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$extra = @()
if ($KeepMedia) { $extra += "--keep-media" }
docker exec -it django_app python manage.py reset_system @extra
exit $LASTEXITCODE
