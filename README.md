# EduTrack

EduTrack es una aplicación web en español para administrar estudiantes, sedes, cursos, matrículas, cuotas, pagos y llamadas. Está construida con Django y PostgreSQL, y aplica permisos de Django junto con el acceso limitado por sede.

## Funcionalidades

- **Estudiantes:** registro por apellidos y nombres, DNI, teléfonos peruanos independientes, búsqueda, importación desde Excel e historial.
- **Cursos y matrículas:** costos y fechas propios de cada matrícula, promotores, fichas, cambio de curso, bajas lógicas y restauración.
- **Caja:** cuotas y saldos pendientes, pagos parciales, recibos, anulaciones que conservan el historial y cierres diarios.
- **Llamadas:** asignación a gestores, notas, promesas de pago, plantillas de WhatsApp y reportes.
- **Reportes:** consultas y exportaciones a Excel según los permisos del usuario.
- **Sedes y usuarios:** campus, usuarios, grupos, permisos, logos y volantes por sede.
- **Auditoría:** historial de actividades y de cada estudiante.

La asignación de sublistas de llamadas está en `/llamadas/asignacion/` y requiere `core.assign_calls`; las rutas anteriores `/llamadas/alumnos/` y `/llamadas/asignaciones/` redirigen allí. La antigua vista de seguimiento ya no tiene acceso desde rutas, menú ni búsqueda. Los gestores siguen trabajando desde la cola de llamadas.

El informe **Matrículas por promotor** reparte cada matrícula entre todos sus promotores: una ficha compartida por cuatro aporta `0.25` a cada uno. El reparto también se aplica a las columnas «Con estudiante» y «Vacantes reservadas», tanto en pantalla como en Excel. Se acumulan las fracciones antes de redondear a dos decimales; la fila de totales cuenta matrículas únicas, por lo que puede diferir de la suma de los valores individuales ya redondeados.

Los recibos son comprobantes internos; no son comprobantes electrónicos autorizados por SUNAT.

## Grupos y permisos

Los permisos se acumulan: un usuario recibe los permisos de todos sus grupos y de los permisos asignados directamente. Las vistas comprueban autorización en el servidor; ocultar un enlace del menú no sustituye el permiso.

Las migraciones crean estos siete grupos. La tabla muestra los permisos que cada grupo recibe por defecto después de aplicar las migraciones actuales:

| Grupo | Permisos asignados |
|---|---|
| **Matrículas** | `students.view_student`, `students.view_course`, `students.view_enrollment`, `students.add_student`, `students.change_student`, `students.add_enrollment`, `students.change_enrollment`, `core.view_academic_reports` |
| **Caja** | `students.view_course`, `payments.view_payment`, `payments.add_payment`, `core.view_pending_balances`, `core.view_financial_reports` |
| **Gestor de llamadas** | `calls.view_callnote`, `calls.add_callnote`, `core.view_call_reports` |
| **Asignador de llamadas** | `calls.view_callnote`, `core.assign_calls` |
| **Supervisor de campus** | `students.view_student`, `students.view_course`, `students.view_enrollment`, `students.view_promoter`, `calls.view_callnote`, `core.view_all_calls`, `core.view_academic_reports` |
| **Administrador general** | `students.view_student`, `students.view_course`, `students.view_enrollment`, `students.view_promoter`, `payments.view_payment`, `payments.add_payment`, `core.view_pending_balances`, `calls.view_callnote`, `core.view_all_calls`, `core.view_academic_reports`, `core.view_call_reports`, `core.view_financial_reports`, `core.export_reports`, `core.view_user`, `core.manage_user_access`, `core.view_campus`, `core.add_campus`, `core.change_campus`, `auth.view_group`, `auth.add_group`, `auth.change_group`, `auth.view_permission` |
| **Gestor de catálogo académico** | `students.view_course`, `students.add_course`, `students.change_course`, `students.view_promoter`, `students.add_promoter`, `students.change_promoter` |

**Administrador general no equivale a superusuario.** Un superusuario de Django tiene acceso global; el grupo Administrador general solo recibe los permisos indicados y sigue sujeto a la selección y al alcance de campus de la aplicación.

### Permisos estándar de Django

Django genera `view`, `add`, `change` y `delete` para cada modelo. Los permisos estándar de la aplicación corresponden a estos modelos:

- `students`: `student`, `studentphone`, `course`, `schedule`, `promoter`, `enrollment`, `ficha`.
- `payments`: `payment`, `installment`, `paymentallocation`, `cashclosing`.
- `calls`: `callnote`, `calllist`, `calllistmember`, `whatsapptemplate`.
- `core`: `user`, `campus`, `campusflyer`, `activitylog`.
- `auth`: `group`, `permission`.

Por ejemplo, `students.add_course` permite registrar cursos y `payments.change_payment` permite editar pagos. No todos estos permisos se asignan a un grupo inicial; los que no aparecen en la matriz se asignan manualmente si son necesarios. Los modelos internos de Django también pueden tener permisos estándar.

### Permisos especiales de `core`

| Permiso | Acción | Grupo inicial |
|---|---|---|
| `core.deactivate_student` | Dar de baja un estudiante conservando sus registros. | Ninguno |
| `core.deactivate_enrollment` | Dar de baja una matrícula conservando su historial. | Ninguno |
| `core.change_enrollment_course` | Cambiar el curso de una matrícula. | Ninguno |
| `core.void_payment` | Anular un pago sin borrar su recibo ni su historial. | Ninguno |
| `core.edit_call_notes` | Editar notas de llamadas existentes. | Ninguno |
| `core.assign_calls` | Crear sublistas de llamadas y asignarlas a usuarios (cada usuario solo puede estar en una). Los gestores de la sublista piden su siguiente llamada en «Pedir llamada» (`/llamadas/cola/`); el equipo ve en vivo a quién llama cada compañero y el reclamo expira a los 15 min. | Asignador de llamadas |
| `core.view_all_calls` | Consultar las llamadas de todos los gestores del campus. | Supervisor de campus, Administrador general |
| `core.view_financial_reports` | Consultar reportes financieros. | Caja, Administrador general |
| `core.view_pending_balances` | Consultar cuotas y saldos pendientes. | Caja, Administrador general |
| `core.view_academic_reports` | Consultar reportes académicos. | Matrículas, Supervisor de campus, Administrador general |
| `core.view_call_reports` | Consultar reportes de llamadas propias; supervisores con `core.view_all_calls` consultan las de todo el campus. | Gestor de llamadas, Administrador general |
| `core.close_cash` | Cerrar la caja de una fecha. | Ninguno |
| `core.export_reports` | Exportar reportes a Excel. | Administrador general |
| `core.manage_user_access` | Administrar usuarios, grupos y sedes asignadas. | Administrador general |

Los permisos con grupo **Ninguno** requieren asignación explícita desde la administración de accesos. Cerrar una caja bloquea la edición y anulación de pagos de esa fecha; solo un superusuario puede reabrirla.

### Acceso por sede

Asigna a cada usuario las sedes en las que puede trabajar. El usuario selecciona una sede activa al iniciar sesión; las consultas y operaciones se limitan a esa sede. Los usuarios normales solo pueden seleccionar campus activos que tienen asignados. El superusuario puede consultar y administrar todos los campus, incluidos los inactivos.

## Inicio con Docker Compose

Requisitos: Docker Desktop con Docker Compose.

1. Crea `.env` en la raíz del proyecto. Usa una clave secreta larga y contraseñas propias; no compartas ni subas el archivo:

   ```dotenv
   DJANGO_SECRET_KEY=clave-larga-aleatoria
   DJANGO_DEBUG=False
   DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
   DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8080,http://127.0.0.1:8080
   DB_NAME=edutrack_pagos
   DB_USER=edutrack_user
   DB_PASSWORD=contrasena-segura
   DB_HOST=db
   DB_PORT=5432
   GRAFANA_ADMIN_PASSWORD=contrasena-segura
   ```

2. Construye e inicia los servicios:

   ```powershell
   docker compose up --build -d
   ```

3. Crea el primer usuario administrador:

   ```powershell
   docker compose exec web python manage.py createsuperuser
   ```

4. Abre <http://localhost:8080/>.

La aplicación ejecuta migraciones al iniciar el contenedor web. Para revisar los registros:

```powershell
docker compose logs -f web ws nginx
```

Para detener los servicios sin borrar los datos:

```powershell
docker compose down
```

> `docker compose down -v` también elimina el volumen de PostgreSQL y todos sus datos.

### Acceso desde la red local

Incluye la IP del servidor en `DJANGO_ALLOWED_HOSTS` y `DJANGO_CSRF_TRUSTED_ORIGINS`, recrea los servicios y permite TCP 8080 en el firewall para redes privadas. El servidor y el cliente deben estar en la misma red.

## Configuración inicial

1. En `/admin/`, crea los campus y cursos.
2. Crea los promotores y asígnalos a sus campus.
3. Crea usuarios, asígnales campus y agrégalos a los grupos adecuados.
4. Asigna por separado los permisos especiales que requiera cada función.
5. Inicia sesión y selecciona el campus activo.

La sede se determina en el servidor mediante el campus seleccionado; no se confía en un campus enviado por el formulario. Las cuotas iniciales se generan a partir de los costos de la matrícula. El primer pago debe cubrir al menos el costo de inscripción y no puede exceder la deuda pendiente.

## Desarrollo local

Requisitos: Python 3.12 o 3.13, `uv` y PostgreSQL. La aplicación requiere PostgreSQL para las consultas de búsqueda con `UNACCENT` y para probar el bloqueo concurrente de pagos.

```powershell
uv sync
uv run pre-commit install
```

Configura en PowerShell las mismas variables de entorno de `.env`, usando `DB_HOST=127.0.0.1`. Django no carga `.env` automáticamente al ejecutarse directamente desde el equipo.

```powershell
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver_plus 127.0.0.1:8000
```

El archivo `docker-compose.dev.yml` permite activar la recarga automática del servidor en el contenedor:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d web ws
```

`runserver_plus` y `DEBUG=True` son solo para desarrollo; no expongas el depurador a Internet ni a una red compartida.

### Tiempo real (Django Channels)

La cola de llamadas recibe los cambios del equipo por WebSocket (`/ws/llamadas/cola/`). En Docker, Gunicorn sigue atendiendo HTTP y el servicio `ws` (Uvicorn/ASGI) atiende solo `/ws/`; nginx enruta cada ruta y ambos procesos se comunican mediante Redis (`CHANNEL_LAYERS`). La conexión requiere sesión, permiso y pertenencia a una sublista activa de la sede seleccionada. El WebSocket solo avisa que algo cambió: la página vuelve a pedir `/llamadas/cola/estado/`, que aplica los permisos. La página envía un heartbeat cada 25 segundos; cada ping renueva la pertenencia al grupo Redis y, si no hay respuesta, el navegador cierra y reconecta con espera incremental. Si el WebSocket no está disponible, consulta el estado cada 4 segundos.

El servicio WebSocket no procesa `X-Forwarded-*`; Uvicorn no habilita `--proxy-headers` ni confía en todos los contenedores. nginx conserva esos encabezados para el servicio HTTP Gunicorn. El healthcheck de `ws` ejecuta `check_channel_layer`, que envía y recibe un mensaje de prueba a través del backend Redis; las conexiones y desconexiones se registran en los logs de Django sin incluir nombres de usuario.

Con el stack levantado (`docker compose up --build -d`), ejecuta la prueba de humo desde la raíz. Verifica Redis/Channels, la salud HTTP y los estáticos a través de nginx, y que el proxy rechaza una conexión WebSocket anónima. No modifica datos de la aplicación:

```powershell
uv run python scripts/test_channels.py
```

Para un host distinto de `127.0.0.1:8080`, define `$env:EDUTRACK_BASE_URL` antes de ejecutar el script. La prueba positiva de autorización y notificaciones se cubre en las pruebas Django; en producción también puedes verificar que una conexión autenticada devuelve `101 Switching Protocols` desde las herramientas de red del navegador.

`runserver_plus` no atiende WebSockets (la cola usa la consulta periódica). Para probarlos en local, ejecuta todo con Uvicorn. La opción `--env-file .env` de `uv` carga las variables antes de iniciar Django; en desarrollo, activa `DEBUG` para que el ASGI sirva también los archivos estáticos. Sin ello, la página puede cargar sin el CSS ni las imágenes locales. Sin `REDIS_URL` se usa una capa en memoria válida solo para un proceso:

```powershell
$env:DJANGO_DEBUG = "True"
$env:DB_HOST = "127.0.0.1"
uv run --env-file .env uvicorn config.asgi:application --host 127.0.0.1 --port 8000 --reload
```

Limita el servidor de desarrollo a tu equipo y no uses `DEBUG=True` en producción. El nombre `db` solo se resuelve dentro de Docker. Las variables ya exportadas en la terminal tienen prioridad sobre `.env`.

## Pruebas y calidad

Con PostgreSQL activo y la configuración de entorno cargada:

```powershell
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py test
uv run ruff check .
uv run pyright
```

También puedes ejecutar pruebas en el contenedor con PostgreSQL:

```powershell
.\scripts\test-postgres.ps1
```

El script acepta etiquetas de pruebas, por ejemplo `.\scripts\test-postgres.ps1 payments`.

### GitHub Actions

El CI prueba Python **3.12 y 3.13**, conforme a `requires-python = ">=3.12,<3.14"`; Python 3.14 no se declara compatible. Los workflows adicionales son:

- **Docker y Playwright** ([docker-e2e.yml](./.github/workflows/docker-e2e.yml)): levanta un stack aislado con PostgreSQL y Redis, crea datos ficticios, prueba nginx/Channels y ejecuta las pruebas de navegador. Los artefactos del navegador se guardan solo si falla.
- **Respaldos** ([backup-restore.yml](./.github/workflows/backup-restore.yml)): semanalmente y en PR/cambios relevantes, genera un respaldo en una base efímera, verifica la restauración PostgreSQL y extrae/compara el archivo multimedia. No usa ni guarda datos reales.
- **Auditoría de dependencias** ([dependency-audit.yml](./.github/workflows/dependency-audit.yml)): analiza dependencias de producción al cambiar `uv.lock`/`pyproject.toml` y cada semana.
- **CodeQL** ([codeql.yml](./.github/workflows/codeql.yml)): analiza Python y JavaScript en push, PR y semanalmente.
- **Publicación de imagen** ([publish-image.yml](./.github/workflows/publish-image.yml)): al subir una etiqueta `vMAJOR.MINOR.PATCH`, vuelve a probar el proyecto, construye la imagen, analiza vulnerabilidades críticas/altas y solo entonces promueve la imagen en GHCR.
- **Despliegue** ([deploy.yml](./.github/workflows/deploy.yml)): manual desde GitHub Actions, con el entorno `production` para aprobación y rollback del contenedor si falla la verificación.

El workflow de Docker crea `.env` temporal con credenciales ficticias y elimina los volúmenes al terminar. Los usuarios y la contraseña E2E se crean solo en esa base de datos efímera.

#### Preparar el despliegue manual

1. Configura el entorno GitHub `production` en **Settings → Environments** y añade revisores requeridos; el workflow no despliega hasta que se apruebe.
2. Añade estas variables del entorno: `DEPLOY_HOST`, `DEPLOY_USER` y `DEPLOY_PATH` (ruta absoluta del Compose en el servidor).
3. Añade estos secretos: `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS`, `GHCR_READ_USERNAME` y `GHCR_READ_TOKEN` con permiso `read:packages`.
4. Prepara `.env` en esa ruta del servidor, instala Docker Compose v2.17 o posterior y `rsync`, y confirma que el host puede acceder a los volúmenes persistentes actuales.
5. Publica una versión con una etiqueta como `v1.2.3`; después ejecuta **Actions → Deploy production image** e indica la etiqueta publicada.

La app y el servicio WebSocket usan la misma imagen publicada; el código ya no se monta desde el directorio del servidor en producción. El Compose de desarrollo sí monta el código local para permitir recarga. El rollback revierte la imagen, no las migraciones de base de datos: mantén las migraciones compatibles con la versión anterior y conserva un respaldo antes de desplegar.

### Datos completos de demostración

Para reemplazar los datos actuales con un conjunto ficticio que cubre los flujos de estudiantes,
matrículas, cuotas, pagos, recibos anulados, llamadas, permisos y sedes, ejecuta desde PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\seed-test-data.ps1
```

El comando es **destructivo**: pide escribir `BORRAR Y CREAR DATOS`, luego solicita una contraseña
común para las cuentas `demo_admin`, `demo_matriculas`, `demo_caja`, `demo_gestor`,
`demo_asignador`, `demo_supervisor`, `demo_administrador` y `demo_catalogo`. Borra también los archivos multimedia
subidos; conserva los grupos, permisos y el historial de migraciones del sistema. Haz un respaldo
antes de confirmar y úsalo únicamente en una base de datos de desarrollo o pruebas.

Puedes elegir qué crear. Sin opciones muestra un menú (Enter = todo); también:

```powershell
.\scripts\seed-test-data.ps1 --list                              # elementos y dependencias
.\scripts\seed-test-data.ps1 --only students,payments            # solo lo elegido
.\scripts\seed-test-data.ps1 --all
```

Las dependencias se añaden solas: por ejemplo `payments` incluye `installments`,
`enrollments`, `students`, `courses`, `users` y `campuses`. El superusuario `demo_admin`
se crea siempre.

## Operación y seguridad

- Mantén `.env`, la clave secreta y las contraseñas fuera del control de versiones.
- Restringe `DJANGO_ALLOWED_HOSTS` y configura HTTPS en producción. Para HTTPS detrás de un proxy de confianza, usa `DJANGO_HTTPS=True`.
- Los archivos multimedia privados requieren sesión y autorización para el campus correspondiente.
- El servicio de respaldo conserva copias de la base de datos y de los archivos multimedia en `backups/`. Mantén también una copia fuera del servidor.
- Antes de producción, cambia todas las contraseñas, configura el firewall y prueba la restauración de un respaldo.
- El cierre de caja y las operaciones sensibles deben asignarse solo a usuarios autorizados.

Para restaurar un respaldo se reemplazan los datos actuales; detén el servicio web y verifica los archivos y la confirmación requeridos por `scripts/restore.sh` antes de proceder.
