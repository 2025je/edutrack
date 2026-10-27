# Ejecuta toda la suite de pruebas en el contenedor `web` con PostgreSQL (soporta UNACCENT).
# Uso: .\scripts\test-postgres.ps1 [etiqueta_de_prueba ...]   p. ej. .\scripts\test-postgres.ps1 calls
docker compose up -d db web
docker exec django_app python manage.py test --noinput @args
exit $LASTEXITCODE
