# EduTrack

Sistema web en español para administrar estudiantes, matrículas, cursos, promotores, cuotas, pagos y seguimiento de llamadas. Usa Django y PostgreSQL, con permisos nativos de Django (grupos y permisos) y acceso limitado por sede.

## Contenido

- [Funcionalidades](#funcionalidades)
- [Roles y permisos](#roles-y-permisos)
- [Requisitos](#requisitos)
- [Inicio con Docker](#inicio-con-docker)
- [Configuración inicial](#configuración-inicial)
- [Desarrollo local sin Docker](#desarrollo-local-sin-docker)
- [Pruebas y calidad](#pruebas-y-calidad)
- [Respaldos y producción](#respaldos-y-producción)

## Funcionalidades

**Académico**

- Estudiantes, cursos y matrículas, con edición y bajas lógicas.
- Un estudiante puede tener varios teléfonos peruanos separados por comas; el documento es el DNI.
- Cada matrícula tiene fecha propia, costos editables y varios promotores. Los costos de inscripción y mensualidad se copian del curso, pero quedan guardados en la matrícula.
- La lista de matrículas muestra pago total, pagos confirmados, deuda, recibos y estado, con filtros y orden. Los nombres de estudiantes llevan a sus matrículas, desde donde también se puede iniciar un pago.

**Caja**

- Cuotas, saldos pendientes y pagos. Los recibos se conservan: al anular un pago, el recibo queda registrado como anulado.
- Los recibos son comprobantes internos; no son comprobantes electrónicos autorizados por SUNAT.
- Cierre de caja diario (`/pagos/cierre-de-caja/`) por cajero, imprimible y exportable a Excel.

**Llamadas**

- Asignación de llamadas a gestores, registro de resultados y notas, con registro rápido desde la lista y botón «Cobrar» por curso con deuda.
- Promesas de pago con fecha («Prometió pago»), con filtro de promesas incumplidas; orden por deuda, días vencidos o último contacto, y filtro de «sin contacto en N días».
- Acciones masivas: reasignar todas las llamadas de un usuario a otro y repartir las matrículas sin asignar en partes iguales.
- Reporte de llamadas por usuario, con avance de asignadas, desglose por respuesta y filtro de fechas. Con `view_all_calls` se ve todo el campus; sin él, solo las propias.

**Reportes**

- Reportes por curso exportables a Excel (una hoja por curso y una tabla por grupo/horario).
- La tabla de matrículas se exporta a Excel respetando filtros y orden.

**Sistema**

- Administración de sedes, usuarios, cursos y promotores desde la aplicación y desde Django Admin.
- Logo opcional por sede, visible según la sede seleccionada.
- Búsqueda global por nombre, DNI, código de ficha o recibo (atajo `/` o `Ctrl+K`).
- Historial de acciones por estudiante y por matrícula (botón «Historial») y fusión de estudiantes duplicados (`/estudiantes/duplicados/`).

**Interfaz**

- Menú lateral único y plano: selector de sede arriba y usuario conectado al pie. Al navegar por el menú solo se recarga el contenido de la derecha.
- Perfil de usuario (`/cuentas/perfil/`) con grupos, sedes, permisos descritos en español y cambio de contraseña.

## Roles y permisos

Los permisos son los nativos de Django; no hay casillas de permiso en el modelo `User`. Un usuario puede pertenecer a varios grupos y acumula sus permisos.

Las migraciones crean seis grupos con los permisos básicos de la matriz de acceso:

| Grupo | Función principal |
|---|---|
| Matrículas | Registrar y consultar estudiantes y matrículas |
| Caja | Registrar y consultar pagos y saldos pendientes |
| Gestor de llamadas | Consultar sus llamadas y registrar resultados y notas |
| Asignador de llamadas | Asignar llamadas a gestores |
| Supervisor de campus | Consulta amplia del campus |
| Administrador general | Consulta y administración completas |

Los permisos que requieren autorización adicional no se conceden por pertenecer al grupo: asígnalos en `/admin/`, a un usuario o a un grupo.

Permisos especiales (aplicación `core`):

| Código | Acción |
|---|---|
| `deactivate_student` | Desactivar estudiantes |
| `deactivate_enrollment` | Desactivar matrículas |
| `change_enrollment_course` | Cambiar el curso de una matrícula |
| `void_payment` | Anular pagos conservando el recibo |
| `view_pending_balances` | Consultar cuotas y saldos pendientes (distinto de ver pagos) |
| `view_financial_reports` | Consultar reportes financieros |
| `view_academic_reports` | Consultar reportes académicos |
| `view_call_reports` | Consultar el reporte de llamadas |
| `edit_call_notes` | Modificar notas de llamadas existentes |
| `assign_calls` | Asignar llamadas a gestores |
| `view_all_calls` | Ver todas las llamadas del campus |
| `export_reports` | Exportar reportes a Excel |
| `manage_user_access` | Administrar usuarios, grupos y permisos |

Los permisos estándar (`view_`, `add_`, `change_`, `delete_`) cubren las operaciones básicas.

Reglas de seguridad:

- Los menús, botones y vistas se muestran solo a quien tiene el permiso correspondiente, y cada vista lo exige también en el servidor.
- Las plantillas comprueban permisos concretos, nunca nombres de grupo.
- Cada usuario solo accede a las sedes que tiene asignadas y a la sede seleccionada.
- Desactivar un estudiante o una matrícula no elimina pagos ni recibos.

## Requisitos

- Docker Desktop con Docker Compose (recomendado), o Python 3.12 o 3.13, uv, PostgreSQL 15 o posterior y Redis para la caché en producción.
- Navegador moderno.

## Inicio con Docker

1. Crea tu archivo local de configuración:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Edita `.env`. Para Docker Compose, el host de la base debe ser `db` (no `127.0.0.1`). Configura una clave secreta propia y contraseñas seguras:

   ```dotenv
   DJANGO_SECRET_KEY=una-clave-larga-aleatoria
   DJANGO_DEBUG=False
   DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
   DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8080,http://127.0.0.1:8080
   GRAFANA_ADMIN_PASSWORD=una-contrasena-segura
   DB_NAME=edutrack_pagos
   DB_USER=edutrack_user
   DB_PASSWORD=una-contrasena-segura
   DB_HOST=db
   DB_PORT=5432
   ```

   Si ya tienes un `.env`, agrega `DJANGO_CSRF_TRUSTED_ORIGINS` y `GRAFANA_ADMIN_PASSWORD`.

3. Construye e inicia los servicios (la compilación usa BuildKit y guarda en caché los paquetes de uv):

   ```powershell
   docker compose up --build -d
   ```

4. Aplica las migraciones y crea el usuario administrador:

   ```powershell
   docker compose exec web python manage.py migrate
   docker compose exec web python manage.py createsuperuser
   ```

5. Abre <http://localhost:8080/>.

### Acceso desde otros equipos de la red

Agrega la IP LAN del servidor a `DJANGO_ALLOWED_HOSTS` y su origen a `DJANGO_CSRF_TRUSTED_ORIGINS`. Por ejemplo, para `192.168.0.107`:

```dotenv
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,192.168.0.107
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8080,http://127.0.0.1:8080,http://192.168.0.107:8080
```

Recrea los servicios con `docker compose up -d --build` y abre <http://192.168.0.107:8080/>. Si no conecta, permite el tráfico TCP entrante por el puerto 8080 en el Firewall de Windows para redes privadas y confirma que todos los equipos estén en la misma red. La IP debe ser la actual del equipo que ejecuta Docker.

### Servicios incluidos

- **Nginx** sirve la aplicación en el puerto 8080 y entrega los archivos estáticos y multimedia.
- **Gunicorn** ejecuta Django; **Redis** proporciona la caché compartida y solo es accesible dentro de Compose.
- **Grafana** está disponible solo localmente en <http://localhost:3000/> (usuario `admin` y la contraseña `GRAFANA_ADMIN_PASSWORD`), con Loki como fuente de datos. En **Explore**, consulta por ejemplo `{service="web"}`.
- **Alloy** recoge los logs de los contenedores del proyecto y **Loki** los conserva 30 días.

Para ver logs de arranque: `docker compose logs -f web nginx redis grafana loki alloy`. Para detener los servicios sin borrar datos: `docker compose down`.

> `docker compose down -v` elimina también el volumen de PostgreSQL y todos sus datos. Úsalo solo cuando quieras borrar la base por completo.

> `runserver_plus` incluye el depurador interactivo de Werkzeug. Es solo para desarrollo: no lo expongas a una LAN ni a Internet, ni lo uses en producción.

## Configuración inicial

1. En `/admin/`, crea las sedes y los cursos.
2. Crea promotores y asigna las sedes donde pueden trabajar; una matrícula admite varios promotores.
3. Crea usuarios, asigna sus sedes y añádelos a uno o varios grupos. Asigna los permisos especiales que correspondan.
4. Inicia sesión con cada usuario y selecciona la sede activa.

La sede de la matrícula se determina en el servidor a partir de la sede seleccionada por el usuario. Al crear una matrícula se generan las cuotas iniciales de inscripción y mensualidad si sus importes son mayores que cero. El primer pago debe cubrir como mínimo la inscripción y no puede exceder la deuda pendiente.

## Desarrollo local sin Docker

Con PostgreSQL en ejecución, instala las dependencias:

```powershell
uv sync
uv run pre-commit install
```

Django lee variables de entorno y no carga `.env` automáticamente fuera de Docker: configura en PowerShell las variables de `.env.example`, con `DB_HOST=127.0.0.1`. Después ejecuta:

```powershell
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver_plus 127.0.0.1:8000
```

Con `DEBUG=True`, Django Debug Toolbar aparece en las páginas HTML. Solo está instalado en el grupo de desarrollo y no se habilita con `DEBUG=False`. Sin `REDIS_URL`, Django usa una caché local en memoria, apropiada para un solo proceso.

## Pruebas y calidad

Con Docker y el servicio PostgreSQL activo:

```powershell
docker compose run --rm web python manage.py test
docker compose run --rm web python manage.py check
docker compose run --rm web python manage.py makemigrations --check --dry-run
```

Revisiones locales: `uv run ruff check .` y `uv run pyright`. Los hooks de pre-commit ejecutan Ruff (lint y formato) sobre los archivos preparados para el commit.

Para ejecutar toda la suite en el contenedor en marcha (PostgreSQL, con `UNACCENT`): `.\scripts\test-postgres.ps1` (acepta etiquetas, p. ej. `calls`). Con SQLite fallan algunas pruebas de búsqueda por esa función.

**Pruebas E2E (Playwright)**: con el sistema levantado, `pip install -r requirements-e2e.txt`, `playwright install chromium` y luego `E2E_USER=... E2E_PASSWORD=... pytest e2e` (opcional `E2E_URL`, por defecto `http://localhost:8080`). Usa un usuario de prueba con acceso a llamadas; sin credenciales solo se ejecuta la comprobación de `/salud/`.

Las dependencias están en `pyproject.toml` y bloqueadas en `uv.lock`; usa `uv add paquete`, `uv remove paquete` o `uv add --dev paquete` para actualizarlas. GitHub Actions instala con uv y ejecuta Ruff, las comprobaciones y las pruebas en cada push y pull request, con PostgreSQL 15, Redis y Python 3.12 y 3.13.

### Seguridad y operación

- `DJANGO_SECRET_KEY` es obligatoria cuando `DJANGO_DEBUG=False`; con la clave de ejemplo la app no arranca. Genérala con `python -c "import secrets;print(secrets.token_urlsafe(50))"`.
- Los archivos de `/media/` (comprobantes y fichas) requieren sesión y pertenecer a la sede; nginx los entrega tras la autorización de Django.
- Tras `LOGIN_MAX_ATTEMPTS` intentos fallidos, el par IP + usuario se bloquea `LOGIN_LOCKOUT_SECONDS` segundos.
- Con HTTPS delante de nginx, define `DJANGO_HTTPS=True` (y opcionalmente `DJANGO_HSTS_SECONDS`).
- `/salud/` devuelve el estado de la app y la base de datos; `web` y `nginx` tienen healthcheck y `web` ejecuta `migrate` al iniciar.
- Respaldos externos: define `BACKUP_OFFSITE_PATH` (carpeta del host) o `BACKUP_RCLONE_REMOTE` con las variables `RCLONE_CONFIG_*`.
- Las alertas de Grafana (errores 5xx, fallos de respaldo, restauración sin verificar) se cargan solas; falta configurar un *contact point* en Grafana > Alerting.
- El CI ya prueba contra PostgreSQL 15. En local con SQLite fallan algunas pruebas por la función `UNACCENT`; no son regresiones.
- En desarrollo sin Docker usa `DJANGO_DEBUG=True` o define `DJANGO_SECRET_KEY`.

## Respaldos y producción

El servicio `backup` respalda cada día la base de datos (`pg_dump`) y los archivos subidos en `./backups/`. Tras cada respaldo restaura el volcado en una base temporal y compara tablas y filas; el resultado queda en `backups/STATUS`. Se conservan los últimos `BACKUP_KEEP` respaldos. Guarda además una copia de `backups/` fuera del servidor.

Variables opcionales: `BACKUP_KEEP` (14), `BACKUP_HOUR_UTC` (7 = 02:00 en Perú), `BACKUP_ON_START` (1).

Respaldo manual inmediato: `docker compose restart backup`.

Restauración (reemplaza los datos actuales):

```powershell
docker compose stop web
docker compose run --rm -e CONFIRM=yes --entrypoint sh backup /scripts/restore.sh /backups/db/ARCHIVO.dump /backups/media/ARCHIVO.tar.gz
docker compose start web
```

El segundo archivo (media) es opcional.

Grafana y Nginx solo publican puertos en loopback; Loki, Alloy, Django y Redis no publican puertos al host. Alloy necesita acceso al socket de Docker para leer los logs: protege el host y no expongas el daemon de Docker.

Antes de exponer el servicio a Internet:

- Cambia `GRAFANA_ADMIN_PASSWORD` y usa un `DJANGO_SECRET_KEY` privado.
- Restringe `DJANGO_ALLOWED_HOSTS` al dominio.
- Configura HTTPS (el Nginx incluido no termina TLS), directamente o con un proxy TLS de confianza.
- Aplica reglas de firewall y prueba el procedimiento de restauración.
