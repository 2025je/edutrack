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
- `calls`: `callnote`, `callassignment`, `whatsapptemplate`.
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
| `core.assign_calls` | Asignar llamadas a gestores. | Asignador de llamadas |
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
docker compose logs -f web nginx
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
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d web
```

`runserver_plus` y `DEBUG=True` son solo para desarrollo; no expongas el depurador a Internet ni a una red compartida.

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
