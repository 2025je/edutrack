# EduTrack Desktop

Aplicación de escritorio offline hecha con Python, PySide6 y QML. SQLAlchemy 2.x administra la base SQLite local, con migraciones de esquema mediante Alembic. Estudiantes, matrículas, cursos y promotores se guardan en tablas separadas; no se necesita conexión durante el registro.

## Flujo de sincronización

### Cuando la sede ya existe en la web

1. En la web, selecciona una sede y descarga **Datos de esta sede** desde Estudiantes → Importar desktop offline.
2. En Desktop, abre el archivo `.edutrack`. Incluye los estudiantes, las matrículas, los cursos y los promotores de esa sede.
3. Usa el sidebar para cambiar entre estudiantes, matrículas y cursos. Los botones para crear estudiantes, matrículas y cursos abren asistentes paso a paso; las vistas de gestión siguen disponibles para consultar y modificar registros existentes. En Cursos también puedes consultar los estudiantes matriculados.
4. Los cambios se guardan automáticamente en la base SQLite del dispositivo. Genera un archivo `.edutrack` y súbelo en la misma sección de la web.
5. Revisa la vista previa y confirma los cursos nuevos junto con estudiantes y matrículas. Para crear cursos, la persona que confirma necesita permiso para agregar cursos. Si un registro cambió en la web mientras trabajabas sin conexión, resuelve el conflicto eligiendo qué versión conservar.
6. Para otra sesión offline, descarga y abre un archivo de sede nuevo. Así Desktop recibe los identificadores y las huellas actualizadas de los registros recién sincronizados.

La sincronización no elimina registros que no estén en el archivo. Las imágenes de fichas se incluyen y pueden adjuntarse o reemplazarse en Desktop; los pagos no se copian al equipo. Si se borra el código de ficha en Desktop, también se elimina esa ficha y su imagen en la web.

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
La interfaz principal está en `edutrack_desktop/Main.qml`; el tema global está separado en `edutrack_desktop/components/AppTheme.qml`, y los asistentes de estudiantes, cursos y matrículas en componentes QML dentro de `edutrack_desktop/components/`. La navegación y las acciones principales usan iconos SVG propios, con modo claro/oscuro. La fuente Roboto se incluye en `edutrack_desktop/fonts/` y se distribuye bajo la licencia SIL Open Font License incluida junto a ella. El comando `edutrack-desktop` inicia la interfaz. `main.py` en la raíz también funciona como punto de entrada para PyInstaller.

## Crear el ejecutable de Windows

Con el entorno virtual y las dependencias de desarrollo instaladas:

```powershell
.\build.ps1
```

PyInstaller genera el ejecutable autocontenido en `dist\EduTrackDesktop.exe`. El paquete incluye QML, módulos Qt Quick y las migraciones Alembic; no requiere Python instalado en el equipo de destino.

## Ejecutar las pruebas

```powershell
uv run pytest
```
