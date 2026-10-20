# DESTRUCTIVO: reemplaza todos los datos de la base por información ficticia y borra MEDIA_ROOT.
# Uso: powershell -ExecutionPolicy Bypass -File .\scripts\seed-test-data.ps1
docker compose up -d db web
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

docker exec -it django_app python manage.py seed_test_data @args
exit $LASTEXITCODE
