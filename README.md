# EduTrack Pagos

Sistema local de matrícula, cuotas y pagos de estudiantes con Django y PostgreSQL. Interfaz en español, acceso multiusuario y recibos internos imprimibles.

## Incluye en esta versión inicial

- Cuentas individuales con permisos separados para registrar alumnos/matrículas y registrar pagos; un usuario puede tener ambos permisos.
- Sedes y asignación de sedes a usuarios.
- Registro y búsqueda de estudiantes.
- Cursos y matrículas.
- Generación de cuota inicial de matrícula y mensualidad inicial.
- Registro de pagos parciales, aplicados a las cuotas pendientes más antiguas.
- Recibo interno imprimible.
- Consulta de pagos y saldos.
- Administración de sedes, cursos, usuarios y cuotas.
- Restricción de acceso por sede en las vistas principales.

## Permisos operativos

Desde Administración → Usuarios, asigna a cada cuenta los permisos “Puede registrar alumnos y matrículas” y/o “Puede registrar pagos”. El dashboard, los accesos rápidos y la navegación se ajustan a esos permisos. El administrador/superusuario conserva acceso completo.

## Requisitos

- Python 3.11 o 3.12.
- PostgreSQL 15 o posterior.
- Navegador moderno.
- Para que varias computadoras lo usen, una computadora debe actuar como servidor y permanecer encendida.

## Instalación en Windows

1. Instala Python y PostgreSQL.
2. Crea en PostgreSQL una base `edutrack_pagos` y un usuario `edutrack_user` con contraseña.
3. Abre PowerShell en la carpeta del proyecto.
4. Crea un entorno e instala dependencias:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

5. Copia `.env.example` a `.env` y configura las variables. Esta versión lee variables del entorno; para una instalación simple puedes definirlas en PowerShell antes de arrancar:

   ```powershell
   $env:DJANGO_SECRET_KEY="reemplazar-por-una-clave-segura"
   $env:DJANGO_DEBUG="True"
   $env:DJANGO_ALLOWED_HOSTS="127.0.0.1,localhost,192.168.1.50"
   $env:DB_NAME="edutrack_pagos"
   $env:DB_USER="edutrack_user"
   $env:DB_PASSWORD="tu-clave-postgres"
   $env:DB_HOST="127.0.0.1"
   $env:DB_PORT="5432"
   ```

6. Genera tablas y crea el usuario administrador:

   ```powershell
   python manage.py makemigrations core students payments
   python manage.py migrate
   python manage.py createsuperuser
   ```

7. Inicia en modo de prueba:

   ```powershell
   python manage.py runserver 127.0.0.1:8000
   ```

   Abre `http://127.0.0.1:8000/`.

## Acceso desde otras computadoras de la LAN

1. Asigna una IP fija o una reserva DHCP al servidor, por ejemplo `192.168.1.50`.
2. Agrega esa IP a `DJANGO_ALLOWED_HOSTS`.
3. Para una prueba dentro de la LAN, arranca con:

   ```powershell
   python manage.py runserver 0.0.0.0:8000
   ```

4. Permite el puerto TCP 8000 en el firewall solo para el perfil/red privada.
5. En los demás equipos, abre `http://192.168.1.50:8000/`.

**Importante:** `runserver` es solo para pruebas en red local. Antes de usar datos reales, configura un servidor WSGI/ASGI de producción, `DEBUG=False`, `SECRET_KEY` segura, HTTPS si corresponde, restricciones de firewall y backups verificados.

## Configuración inicial

1. En `/admin/`, crea las sedes.
2. Crea usuarios cajeros, marca `Es cajero`, y asigna las sedes permitidas. Para que puedan iniciar sesión, marca su cuenta como activa. No es necesario darles permisos de staff para utilizar las pantallas normales.
3. Crea cursos para cada sede.
4. Registra estudiantes y matrículas desde la aplicación.
5. En cada matrícula se crean automáticamente las cuotas iniciales de matrícula y mensualidad cuando sus importes son mayores que cero. Las siguientes mensualidades se agregan desde Administración > Cuotas.

## Limitaciones deliberadas de esta versión

- El número de recibo usa fecha y hora de alta con restricción única; para numeración fiscal o estrictamente correlativa por sede/caja, implementar una secuencia transaccional antes de producción.
- El sistema genera recibos **internos**, no comprobantes electrónicos tributarios.
- Los usuarios no administradores solo tienen permisos por sede en las pantallas de la aplicación; el acceso al admin de Django debe reservarse a personal de confianza.
- Los importes se aplican FIFO a las cuotas de la matrícula seleccionada y no permiten cobrar por encima del saldo pendiente.
- Los formularios de matrícula generan las dos primeras cuotas; no crean automáticamente todo un calendario anual.
- La exportación Excel, cierre de caja, anulaciones desde interfaz, control de turnos y reportes detallados quedan para la siguiente etapa.
- El resumen de pagos es acumulado histórico, no el total del día/mes.

## Copias de seguridad

Programa un backup diario de PostgreSQL y guarda una copia en otro dispositivo. Ejemplo de exportación manual:

```bash
pg_dump -U edutrack_user -h 127.0.0.1 edutrack_pagos > backup_edutrack.sql
```

Prueba periódicamente la restauración del respaldo.

## Selección de sede por cajero

Después de iniciar sesión, el usuario debe elegir una sede activa en **Sedes → Seleccionar sede** (o mediante el botón de sede de la barra superior). Solo se muestran las sedes activas asignadas al usuario; el superusuario puede elegir cualquier sede activa. La sede seleccionada se guarda en la sesión y limita las pantallas de estudiantes, matrículas, pagos, recibos y cuotas. Se puede cambiar desde la barra superior.

Para asignar sedes a un cajero, entra como superusuario en `/admin/`, abre **Usuarios** y marca las sedes en **Sedes asignadas**. Activa la casilla **Es cajero** si corresponde a la función del usuario.

Al crear una matrícula, los costos de inscripción y mensualidad se cargan al seleccionar el curso desde los valores definidos en el curso, pero se guardan en la matrícula como importes propios. El sistema también bloquea una segunda matrícula del mismo estudiante en el mismo curso, aunque cambie el horario o grupo.

> Nota: este proyecto es una base inicial. Antes de usarlo con datos reales, instala dependencias, genera y aplica las migraciones, ejecuta las pruebas y configura copias de seguridad y un servidor de producción apropiado. No uses `runserver` como servidor de producción.


## Cambios de esta versión

- La fecha de inicio del programa se configura en el curso y se usa para generar las cuotas iniciales de las matrículas.
- Se quitó el campo de método de pago del formulario, modelo, administración y recibo impreso.
- Los importes de inscripción y mensualidad siguen guardándose por matrícula, precargados desde el curso y editables.


## Reportes incluidos

- **Deudas pendientes** (`/pagos/deudas-pendientes/`): tabla con estudiante, código, celular, curso/grupo, concepto, vencimiento, importe, total abonado y saldo pendiente. Permite buscar e imprimir.
- **Alumnos por curso** (`/estudiantes/reportes/alumnos-por-curso/`): presenta una tabla separada por cada curso activo de la sede seleccionada, con código, nombre, documento, celular y fecha de matrícula. Permite buscar por curso/horario/grupo e imprimir.
- Ambos reportes se filtran automáticamente por la sede seleccionada en la sesión.


## Formularios sin campo de sede

En el registro de estudiantes y matrículas ya no se solicita la sede. La aplicación toma la sede seleccionada en la sesión del usuario y la asigna en el servidor al guardar. En matrículas, los selectores de estudiante y curso muestran únicamente registros de esa sede. La sede no se acepta desde los datos enviados por el navegador.


## Permisos operativos por usuario

En Administración → Usuarios, configura por separado **Puede registrar alumnos y matrículas** y **Puede registrar pagos**. Un usuario puede tener ambos permisos. El superusuario conserva acceso completo. Los permisos se validan en el servidor y también controlan qué secciones aparecen en el menú. Los usuarios deben tener asignada la sede correspondiente.

## Código de ficha y promotor

Cada matrícula puede guardar un **Código de ficha** opcional y un **Promotor** opcional. Los promotores se crean en Administración → Promotores y pueden asignarse a una o más sedes. El comprobante interno de pago muestra ambos datos.

## Regla del primer pago

El primer pago confirmado de una matrícula debe ser como mínimo igual al costo de matrícula de esa inscripción.
