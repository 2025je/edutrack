# EduTrack Desktop

Aplicación de escritorio offline hecha con Python, PySide6 y QML. `PySide6.QtAsyncio` integra los bucles de Qt y asyncio; SQLAlchemy 2.x usa `AsyncSession` y `aiosqlite` para la base SQLite local, con migraciones de esquema mediante Alembic. Estudiantes, matrículas, cursos y promotores se guardan en tablas separadas; no se necesita conexión durante el registro.

## Varias sedes y bases de datos

Desktop permite tener varias sedes abiertas en el mismo equipo. Al crear una sede o importar un paquete por primera vez, elige la ubicación y el nombre del archivo SQLite; cada sede queda en su propia base de datos. Usa el selector de la barra superior para cambiar entre las sedes registradas. El botón **Cerrar sede** cierra la activa sin borrar su archivo ni quitarla del catálogo. También puedes abrir una base SQLite existente para agregarla al catálogo local.

En cada tarjeta de sede puedes quitarla de la lista y confirmar la acción. Esto solo elimina su referencia del catálogo: la base SQLite y sus datos se conservan. Primero debes cerrar la sede activa; para volver a mostrar una sede quitada, usa **Abrir base local**.

El catálogo de rutas se guarda como `campuses.json` en la carpeta de datos de la aplicación. La base local que ya existía se conserva y se registra automáticamente si contiene una sede. Si mueves una base a otra carpeta, vuelve a abrirla desde Desktop para actualizar su ubicación en el catálogo.

Al volver a abrir Desktop, se restaura la sede activa, la sección, el tema, la posición y el tamaño de la ventana, las selecciones y los formularios que estaban abiertos, incluidos sus datos aún no guardados. Este estado de sesión se conserva en la configuración local del usuario y no se incluye en la base SQLite ni en los paquetes de sincronización.

## Respaldos y recuperación

Abre **Respaldos** en la navegación para crear una copia manual, ver su fecha y tamaño, y comprobar su integridad. Los respaldos se guardan en la carpeta `backups` junto a la base SQLite de cada sede; las copias existentes no se sobrescriben. Desktop también crea un respaldo verificado antes de importar paquetes de sincronización.

Para recuperar datos, selecciona un respaldo válido de la misma sede y confirma la operación. Antes de reemplazar la base activa, Desktop conserva un punto de recuperación de su estado actual. La restauración se valida y se aplica mediante un reemplazo atómico; si algo falla después del reemplazo, Desktop intenta volver al punto de recuperación. Si tampoco puede completar ese rollback, muestra la ubicación de esa copia para una recuperación manual. Conserva además una copia en otra ubicación si necesitas protección frente a fallos del equipo o del disco.

## Flujo de sincronización

### Cuando la sede ya existe en la web

1. En la web, selecciona una sede y descarga **Datos de esta sede** desde Estudiantes → Importar desktop offline.
2. En Desktop, importa el archivo `.edutrack` y elige una ubicación SQLite para esa sede. El paquete incluye estudiantes, matrículas, cursos y promotores.
3. Usa el sidebar para cambiar entre estudiantes, matrículas y cursos. Estudiantes muestra la lista; selecciona un registro para editar sus apellidos, nombres, DNI o celulares. Para crear un estudiante, puedes hacerlo desde el asistente de matrícula. Los asistentes para matrículas y cursos guían el registro paso a paso; en Cursos también puedes consultar los estudiantes matriculados y editar el curso seleccionado.
4. Los cambios se guardan automáticamente en la base SQLite del dispositivo. Genera un archivo `.edutrack` y súbelo en la misma sección de la web.
5. Revisa la vista previa y confirma los cursos nuevos junto con estudiantes y matrículas. Para crear cursos, la persona que confirma necesita permiso para agregar cursos. Si un registro cambió en la web mientras trabajabas sin conexión, resuelve el conflicto eligiendo qué versión conservar.
6. Después de sincronizar, importa el archivo canónico descargado desde la web y selecciona la misma base SQLite de esa sede. Desktop pide confirmación antes de reemplazar sus datos locales y verifica que el paquete corresponda a esa sede.

La sincronización no elimina registros que no estén en el archivo. Las imágenes de fichas se incluyen y pueden adjuntarse o reemplazarse en Desktop; los pagos no se copian al equipo. Si se borra el código de ficha en Desktop, también se elimina esa ficha y su imagen en la web.

Los registros de Desktop siguen las validaciones de la web: estudiantes con nombres únicos por sede y uno o más celulares peruanos válidos sin repetir; cursos con identidad única, grupo entero positivo, fecha, capacidad e importes válidos; y matrículas sin duplicar la pareja estudiante-curso. Desktop no solicita ficha ni promotor al crear o editar matrículas; si esos datos ya existen en una matrícula importada, se conservan al editarla. El asistente permite registrar una matrícula pendiente sin curso (con costos en cero) o reservar un cupo sin estudiante.

### Cuando la sede todavía no existe en la web

1. En Desktop, crea la sede con su nombre y, si hace falta, su dirección.
2. Agrega los cursos y promotores con sus asistentes; después registra estudiantes y matrículas sin conexión. El asistente de matrícula permite buscar un estudiante existente o crearlo antes de completar la inscripción.
3. Exporta el **paquete inicial de sede** y súbelo en Estudiantes → Importar desktop offline. Un usuario con permisos para crear sedes y registrar estudiantes y matrículas debe revisar y confirmar la importación.
4. La web crea la sede, sus catálogos y los registros en una única operación. Al terminar, descarga el archivo canónico desde la web y ábrelo en Desktop para continuar con la sincronización normal.

El paquete inicial conserva un identificador para impedir que se importe dos veces. Si la importación falla, no se crea parcialmente la sede ni sus registros.

## Ejecutar en desarrollo

Requiere Python 3.12 o posterior. Al iniciar, la aplicación aplica las migraciones locales pendientes. Si encuentra la base anterior que guardaba todo el espacio de trabajo en una sola fila JSON, la convierte automáticamente al esquema ORM sin borrar sus datos.

```powershell
cd edutack-desktop
uv sync --group dev
uv run edutrack-desktop
```

La base de datos local se crea en la carpeta de datos de la aplicación del usuario. Mantén respaldado el archivo de sede y el archivo SQLite si necesitas conservar el trabajo local.
La configuración puede sobrescribirse con las variables de entorno `EDUTRACK_DESKTOP_DATA_DIR`, `EDUTRACK_DESKTOP_DATABASE_PATH`, `EDUTRACK_DESKTOP_CAMPUS_CATALOG_PATH`, `EDUTRACK_DESKTOP_QT_MATERIAL_VARIANT` (`Dense` o `Normal`) y `EDUTRACK_DESKTOP_LOG_LEVEL`. Las rutas de base de datos y catálogo, si se definen, tienen prioridad sobre las ubicaciones predeterminadas. Los eventos se registran en formato JSON; en el ejecutable de Windows se guardan en `logs\edutrack-desktop.jsonl` dentro de la carpeta de datos de la aplicación. Cuando no hay consola, el archivo rota al alcanzar 1 MB y conserva hasta tres archivos anteriores. Los logs usan tipos de error y contadores agregados; no registran nombres, documentos, teléfonos ni mensajes de excepción que puedan contener datos ingresados por el usuario.
El código de aplicación vive en `src/edutrack_desktop/`, organizado por capas: `domain/` contiene reglas, `application/` los puertos y proyecciones, `infrastructure/` la persistencia, configuración y formatos externos, y `presentation/` el adaptador Qt y los recursos QML. La interfaz principal está en `src/edutrack_desktop/presentation/qml/Main.qml`; el tema y los asistentes se encuentran en `presentation/qml/components/`. Las fuentes, licencias e iconos están bajo `presentation/qml/fonts/` y `presentation/qml/icons/`. El comando `edutrack-desktop` inicia la interfaz; `main.py` en la raíz también funciona como punto de entrada para PyInstaller.

## Pruebas y mediciones

Desde `edutack-desktop`, ejecuta `uv run pytest tests -q` para la suite, incluidas las pruebas QML en modo offscreen del asistente, del atajo global Ctrl+M y de la edición de matrículas con búsqueda limitada de estudiantes. El benchmark reproducible de búsqueda, carga, guardado incremental y paquetes se ejecuta con `uv run python tests/benchmark_desktop.py`; crea sus bases temporales y reporta el tamaño de datos, la plataforma y la mediana de cinco operaciones. Las mediciones dependen del equipo y no son una comparación antes/después.

## Crear el instalador de Windows

En Windows, instala [Inno Setup 6](https://jrsoftware.org/isinfo.php) en el equipo de compilación. No hace falta instalarlo en los equipos donde se usará la aplicación. Después, ejecuta desde PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
```

El script compila un ejecutable autocontenido con PyInstaller y crea `dist\installer\EduTrackDesktop-Setup-<versión>.exe`. El instalador permite elegir la instalación para el usuario actual, agrega accesos directos y permite desinstalar la app. El paquete incluye Python, Qt/PySide6, los módulos QML, iconos, fuentes, migraciones y los DLL de runtime necesarios; el equipo de destino no necesita instalar Python, uv, Qt ni el redistribuible de Visual C++ por separado. El instalador es para Windows x64 10 o posterior. No incluye ni borra las bases SQLite de las sedes, que permanecen en la ubicación elegida por el usuario.

Para compilar únicamente el ejecutable, sin generar el instalador:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build.ps1 -SkipInstaller
```

Distribuye el instalador generado, no los archivos de `build\`. Se recomienda probarlo en una PC Windows limpia o una máquina virtual antes de entregarlo a usuarios.

El workflow **EduTrack Desktop Windows Installer** compila el instalador en Windows al cambiar `edutack-desktop/` o al ejecutarlo manualmente. Instala el paquete en el runner, inicia el ejecutable en modo de prueba para comprobar que Qt, QML y sus DLL cargan, y publica el instalador como artefacto de la ejecución.

## Ejecutar las pruebas

```powershell
uv run pytest
uv run mypy
```
