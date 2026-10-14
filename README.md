# EduTrack

Sistema web para administrar estudiantes, matrículas, cursos, promotores, cuotas y pagos. Está construido con Django y PostgreSQL, con interfaz en español y permisos separados por función y sede.

## Funcionalidades

- Gestión de estudiantes, cursos y matrículas, con edición y bajas lógicas.
- Un estudiante puede registrar varios teléfonos peruanos separados por comas; el documento se identifica como DNI.
- Cada matrícula puede tener fecha propia, costos editables y varios promotores.
- Los costos de inscripción y mensualidad se copian inicialmente del curso, pero quedan guardados en la matrícula.
- Las matrículas muestran pago total, pagos confirmados, deuda, recibos y su estado; permiten filtrar y ordenar.
- Los nombres de estudiantes llevan a una lista de sus matrículas. Desde esta también se puede iniciar un pago.
- Los recibos se conservan: al anular un pago, el recibo queda registrado como anulado.
- Reportes por curso exportables a Excel, con una hoja por nombre de curso y una tabla por grupo/horario.
- La tabla de matrículas se puede exportar a Excel respetando filtros y orden.
- Administración de sedes, usuarios, cursos y promotores desde Django Admin.

## Requisitos

- Docker Desktop con Docker Compose (recomendado), o Python 3.11/3.12 y PostgreSQL 15 o posterior.
- Navegador moderno.

## Inicio con Docker

1. En PowerShell, crea tu archivo local de configuración:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Edita `.env`. Para Docker Compose, el host de la base debe ser `db` (no `127.0.0.1`). Configura también una clave secreta propia y una contraseña de base de datos:

   ```dotenv
   DJANGO_SECRET_KEY=una-clave-larga-aleatoria
   DJANGO_DEBUG=True
   DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
   DB_NAME=edutrack_pagos
   DB_USER=edutrack_user
   DB_PASSWORD=una-contrasena-segura
   DB_HOST=db
   DB_PORT=5432
   ```

3. Construye e inicia los servicios:

   ```powershell
   docker compose up --build -d
   ```

4. Aplica las migraciones y crea el usuario administrador:

   ```powershell
   docker compose exec web python manage.py migrate
   docker compose exec web python manage.py createsuperuser
   ```

5. Abre <http://localhost:8000/> e inicia sesión. Compose arranca Django con `runserver_plus` y expone el puerto solo en `localhost`. Para revisar los logs usa `docker compose logs -f web`; para detener los servicios sin borrar los datos, `docker compose down`.

> `docker compose down -v` elimina también el volumen de PostgreSQL y todos sus datos. Úsalo únicamente cuando quieras borrar la base por completo.

> `runserver_plus` incluye el depurador interactivo de Werkzeug. Es exclusivamente para desarrollo: el puerto queda limitado a localhost y no debe exponerse a una LAN, Internet ni usarse en producción.

## Configuración inicial

1. En `/admin/`, crea las sedes y los cursos.
2. Crea promotores y asigna las sedes donde pueden trabajar; una matrícula admite varios promotores.
3. Crea usuarios y asigna sedes y permisos: **Puede registrar alumnos y matrículas** y/o **Puede registrar pagos**.
4. Inicia sesión con cada usuario y selecciona la sede activa correspondiente.

La sede de la matrícula se determina en el servidor a partir de la sede seleccionada por el usuario. Al crear una matrícula, se generan las cuotas iniciales de inscripción y mensualidad si sus importes son mayores que cero. El primer pago debe cubrir como mínimo la inscripción y no puede exceder la deuda pendiente.

## Desarrollo local sin Docker

Con PostgreSQL instalado y ejecutándose, crea y activa un entorno virtual, e instala las dependencias:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Configura las variables de `.env.example` en el entorno de PowerShell: Django lee variables de entorno y no carga `.env` automáticamente fuera de Docker. Usa `DB_HOST=127.0.0.1` para PostgreSQL local. Después ejecuta:

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver_plus 127.0.0.1:8000
```

El depurador de `runserver_plus` permite inspeccionar errores durante el desarrollo. No lo uses con datos reales ni en producción.

## Pruebas y migraciones

Con Docker y el servicio PostgreSQL activo:

```powershell
docker compose run --rm web python manage.py test
docker compose run --rm web python manage.py check
docker compose run --rm web python manage.py makemigrations --check --dry-run
```

GitHub Actions ejecuta estos controles y la suite de pruebas en PostgreSQL 15 con Python 3.11 y 3.12 en cada push y pull request.

## Respaldos y producción

Haz respaldos regulares de PostgreSQL y guarda una copia fuera del servidor. Ejemplo con los valores de base incluidos en `.env.example`:

```powershell
docker compose exec -T db pg_dump -U edutrack_user -d edutrack_pagos > backup_edutrack.sql
```

Antes de usar datos reales, define `DJANGO_DEBUG=False`, usa secretos privados y `ALLOWED_HOSTS` restringido, configura HTTPS, un servidor WSGI/ASGI de producción, reglas de firewall y un procedimiento probado de restauración. `runserver` es solo para desarrollo.

Los recibos emitidos por la aplicación son comprobantes internos; no son comprobantes electrónicos tributarios autorizados por SUNAT.
