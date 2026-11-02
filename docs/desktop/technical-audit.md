# EduTrack Desktop — Auditoría técnica incremental

Fecha: 2026-10-30
Línea base verificada: `uv run pytest tests -q` → **36 pruebas, todas pasan** (~15 s), sobre el árbol de trabajo actual (incluye cambios sin commitear).

> Alcance vigente: SQLite es la única fuente de verdad operativa; `.edutrack` se usa
> temporalmente para importar y exportar. Desktop administra estudiantes, cursos y
> matrículas. Promotores, códigos e imágenes de fichas pertenecen a EduTrack Web y se
> preservan si ya fueron importados. Pagos y recibos están fuera del alcance.
>
> Las secciones iniciales documentan la línea base histórica; los cambios recientes y
> las decisiones vigentes se registran en las últimas secciones.

---

## 1. Arquitectura actual

El módulo vive en `edutack-desktop/` (nótese la errata histórica en el nombre de la carpeta;
no renombrar: rompería rutas de build y scripts).

```
edutack-desktop/
├── main.py                      # Entrada que delega en presentation.main
├── pyproject.toml               # uv + hatchling; Python >= 3.12
├── build.ps1                    # uv sync + PyInstaller + Inno Setup 6
├── EduTrackDesktop.spec         # PyInstaller onefile (incluye QML, fuentes, migraciones)
├── EduTrackDesktop.iss          # Instalador Windows
├── tests/                       # 8 archivos, 36 pruebas (pytest)
└── src/edutrack_desktop/
    ├── domain/
    │   └── record_service.py    # RecordService: validaciones y mutaciones del manifiesto
    ├── application/
    │   ├── ports.py             # Protocolos: WorkspaceStore, CampusCatalogPort, RecordServicePort
    │   └── presenters.py        # student_rows, enrollment_rows, course_rows, filtros (funciones puras)
    ├── infrastructure/
    │   ├── store.py             # LocalStore (SQLAlchemy async + aiosqlite + NullPool)
    │   ├── models.py            # ORM: Workspace, StudentRecord, CourseRecord, PromoterRecord, EnrollmentRecord
    │   ├── transfer.py          # read_package / write_package / validate_manifest (.edutrack)
    │   ├── schemas.py           # Modelos pydantic de validación (manifiesto, catálogo, sesión)
    │   ├── campus_catalog.py    # Catálogo JSON de sedes locales (campuses.json)
    │   ├── excel_export.py      # Exportación de registro a Excel (openpyxl)
    │   ├── app_settings.py      # DesktopSettings (pydantic-settings, prefijo EDUTRACK_DESKTOP_)
    │   ├── logging_config.py    # structlog + RotatingFileHandler (JSONL) / RichHandler
    │   ├── alembic.ini
    │   └── migrations/versions/ # 0001_local_workspace, 0002_initial_campus
    └── presentation/
        ├── main.py              # Arranque con QtAsyncio, splash, incubación QML
        ├── backend.py           # DesktopBackend (QObject) — 1302 líneas, ~40 slots/properties
        ├── session_settings.py  # Persistencia del estado de sesión QML
        ├── startup_splash.py    # Splash de arranque
        └── qml/
            ├── Main.qml         # Ventana frameless, tema, sesión, navegación raíz
            ├── components/      # AppTheme, StatusBar, WindowTitleBar, overlays…
            ├── dialogs/AppDialogs.qml  # Importar/exportar paquete, reemplazo de sede
            └── pages/           # WorkspacePage (nav), Students, Enrollments, Courses,
                                 # Summary, EnrollmentWizard, EnrollmentEditor, editores…
```

### 1.1 Modelo de datos y flujo de persistencia

- **SQLite es la única fuente de verdad operativa** de estudiantes, cursos y
  matrículas. El manifiesto es una estructura temporal de importación/exportación;
  no se carga como caché ni se usa para consultas o CRUD. Los campos de promotores
  y fichas permanecen por compatibilidad y se conservan cuando vienen de la web.
- `LocalStore` (SQLite, una base por sede) almacena los datos en 5 tablas
  (`desktop_workspaces`, `desktop_students`, `desktop_courses`, `desktop_promoters`,
  `desktop_enrollments`). El CRUD normal actualiza filas específicas; la sincronización
  reemplaza los datos importados dentro de una transacción.
- `LocalStore.initialize()` ejecuta `alembic upgrade head` al abrir y migra el formato
  legado (tabla `workspace` con JSON) sin pérdida de datos (`_migrate_legacy_workspace`).
- El motor usa `NullPool` deliberadamente: el mismo store se usa desde `asyncio.run`
  (worker) y desde el bucle QtAsyncio (no cambiar).
- `DesktopBackend` consulta y modifica los registros operativos mediante operaciones
  SQL específicas; la persistencia del manifiesto se reserva para crear sedes e
  importar paquetes.

### 1.2 Formato `.edutrack` y sincronización con EduTrack Web

- ZIP con `manifest.json` + `attachments/<sha256>.jpg`. Límites: 25 MB por paquete,
  2000 estudiantes / 2000 matrículas, 10 MB por imagen, hash SHA-256 verificado por imagen.
- Versiones soportadas: **2** (sede sincronizada) y **3** (`campus_mode: "new"`, sede nueva
  creada en Desktop, sin IDs web). Constantes en `transfer.py` y en
  `edutrack-web/students/offline_sync.py` (deben mantenerse alineadas).
- Identificadores: `id` local (UUID para estudiantes/matrículas, enteros para cursos/promotores),
  `server_id` (ID web), `base_hash` (huella del estado base para detección de conflictos),
  `bundle_id` (identidad del paquete; se **regenera en cada exportación** de sede sincronizada,
  `backend.py::exportPackage`; la web rechaza `bundle_id` repetidos).
- La **resolución de conflictos de tres vías vive en la web**
  (`offline_sync.py`, compara huella entrante vs. actual vs. `base_hash`). Desktop importa
  el paquete devuelto por la web **reemplazando** el contenido de la base de la sede tras
  verificar `_same_campus` (campus_id o bundle_id).

### 1.3 Arranque

`presentation/main.py`: splash inmediato → inicialización del backend en un `QRunnable`
(logging, settings, apertura de la última sede del catálogo) → incubación asíncrona del QML
→ `QtAsyncio.run()`. Soporta `--smoke-test`.

---

## 2. Componentes y funciones importantes

| Área | Archivo / función | Responsabilidad |
|---|---|---|
| Dominio | `RecordService.save_student` | Normaliza (MAYÚSCULAS), valida teléfonos peruanos (9 dígitos, inicia en 9), longitudes, duplicado exacto por apellidos+nombres |
| Dominio | `RecordService.save_enrollment` | Valida los datos académicos y preserva los valores web-managed existentes; Desktop no crea ni modifica promotores o fichas |
| Dominio | `RecordService.normalize_course_fields` | Identidad de curso única (nombre+horario+grupo), fecha ISO, capacidad entera positiva |
| Dominio | `RecordService.set_student_active`, `remove_unused_attachments` | Activación y limpieza de adjuntos huérfanos |
| Aplicación | `presenters.py` | Proyecciones de filas SQL para QML |
| Infraestructura | `LocalStore` | CRUD incremental en SQLite, importación transaccional, exportación desde SQL, migraciones y legado |
| Infraestructura | `transfer.read_package/write_package/validate_manifest` | Validación estricta del paquete (pydantic + reglas), escritura atómica (tmp + `os.replace`) |
| Infraestructura | `CampusCatalog` | `campuses.json` validado, escritura atómica, sede activa |
| Presentación | `DesktopBackend.saveStudent/saveEnrollment/setStudentActive` | Delegan al store SQL y al servicio de dominio para validar los cambios locales |
| Presentación | `DesktopBackend.openPackage/exportPackage/switchCampus/openLocalDatabase/closeCampus/createWorkspace` | Ciclo de vida de sedes y paquetes |
| Presentación | Modelos de lista y backend | Búsqueda, filtros y paginación consultados desde SQLite |
| Presentación | `DesktopBackend` | No expone operaciones CRUD de promotores ni de fichas |
| QML | `EnrollmentWizardPage.qml` | Asistente para buscar/crear estudiante y registrar matrícula académica |
| QML | `EnrollmentEditorPage.qml` | Edición de matrícula (estudiante, curso, fecha, montos, activa) |
| QML | `SummaryPage.qml` | "Resumen": totales, ocupación de cursos, matrículas recientes, exportar Excel |
| QML | `WorkspacePage.qml` | Navegación lateral: Matrículas / Estudiantes / Cursos / Resumen (carga perezosa) |

---

## 3. Problemas identificados (por gravedad)

La lista siguiente describe la auditoría inicial; las brechas ya resueltas y las
decisiones vigentes deben leerse junto con las últimas secciones de este documento.

### ALTA

| # | Problema | Evidencia |
|---|---|---|
| A1 | **Crear estudiante + matrícula no es atómico en el asistente.** `createStudent()` llama `saveStudent()` (guardado completo de la BD) y luego `saveEnrollment()` en una operación separada. Si la matrícula falla o el usuario cancela en el paso 2, queda un estudiante creado sin matrícula. | `EnrollmentWizardPage.qml::createStudent/saveEnrollment`; `backend.py:1229-1296` |
| A2 | **Cada guardado reescribe toda la base**: `LocalStore._save()` hace `DELETE` de las 5 tablas e inserta todo de nuevo, incluidos los adjuntos JSON del workspace. Con miles de estudiantes el costo por guardado es O(N) y crece con cada registro. | `store.py:217-350` |
| A3 | **La búsqueda del asistente filtra toda la lista en JavaScript**: `matchingStudents` recorre `backendObject.students` (lista completa serializada a QML) en cada pulsación, sin límite de resultados ni debounce. | `EnrollmentWizardPage.qml:16-28` |
| A4 | **Sin respaldos**: no existe mecanismo de backup; `openPackage` reemplaza el contenido de la base de la sede sin copia previa ni rollback más allá de la transacción. | `backend.py::openPackage` |

### MEDIA

| # | Problema | Evidencia |
|---|---|---|
| M1 | El asistente **no permite registrar promotores, código de ficha ni imagen de ficha**, aunque dominio y backend los soportan (se preservan al editar). Tampoco muestra resumen antes de confirmar ni advierte matrículas existentes/duplicados potenciales. | `EnrollmentWizardPage.qml::saveEnrollment` (solo envía student_id, course_id, fecha y montos) |
| M2 | **Sin índices SQL** más allá de las claves primarias; da igual hoy porque todo se carga en memoria, pero bloquea la búsqueda SQL eficiente. | `migrations/versions/0001`, `0002` |
| M3 | `_run_async` con `QEventLoop` anidado **bloquea la interacción** durante guardados/cargas largos (hay overlay, pero el patrón limita paralelismo y es frágil). | `backend.py:441-453` |
| M4 | `backend.py` (1302 líneas) concentra ciclo de vida de sedes, persistencia, selección y presentación; **no hay capa `application` de casos de uso** (solo ports y presenters). | `backend.py` |
| M5 | **Detección de duplicados de estudiante limitada**: solo nombre completo exacto (casefold); no considera documento de identidad ni similitud. | `record_service.py::save_student` |
| M6 | `SummaryPage` calcula indicadores **en JS sobre las listas completas** (`students`, `enrollments`, `courses`) en cada cambio; no hay métrica "matrículas de hoy". | `SummaryPage.qml:14-30` |
| M7 | **Sin historial de importaciones/exportaciones** ni fechas de última sincronización; exportar regenera `bundle_id` sin registrar nada. | `backend.py::exportPackage` |
| M8 | **Sin atajos de teclado** (ningún `Shortcut` en QML). | grep en `qml/` |

### BAJA

| # | Problema | Evidencia |
|---|---|---|
| B1 | `enrollment_rows`/`course_rows` se recalculan en cada acceso a la property (sin caché, a diferencia de `students`). | `backend.py:326-333` |
| B2 | El logger de `store` se fuerza a WARNING y el log por sentencia SQL en DEBUG es muy verboso si se habilita. | `logging_config.py:15-19`, `store.py::_log_statement` |
| B3 | Teléfono obligatorio al crear estudiante (regla web); correcto, pero el asistente no lo comunica hasta el error. | `record_service.py::save_student` |
| B4 | `exportRegister` y exportación de paquete corren en el hilo de UI (aceptable con límites actuales de 2000 registros). | `backend.py::exportRegister/exportPackage` |

---

## 4. Funcionalidades que NO deben modificarse (proteger)

1. **Formato `.edutrack`** (versiones 2 y 3, límites, validaciones, hashes de imagen) y su
   escritura atómica — la web depende de él (`offline_sync.py`, `desktop_import.py`).
2. **Semántica de identificadores**: `id` local, `server_id`, `base_hash`,
   `student_server_id`, regeneración de `bundle_id` al exportar sede sincronizada,
   reglas especiales de versión 3 (sin IDs web, `campus_mode: "new"`, backfill de
   `server_id` de promotores/cursos en `LocalStore._load/_save`).
3. **Migración del workspace legado** (tabla `workspace` JSON) en `LocalStore`.
4. **Catálogo de sedes** (`campuses.json`): una base por sede, sede activa, reapertura.
5. **Reglas de dominio existentes**: normalización a MAYÚSCULAS, teléfonos peruanos,
   `Decimal` 2 decimales, identidad de curso, código de ficha único por fecha,
   PARTICULAR/NN excluyentes, matrículas pendientes (solo estudiante o solo curso),
   preservación de campos no enviados al editar matrícula.
6. **Capacidad de curso informativa** (SummaryPage la muestra; el dominio no la bloquea).
7. **NullPool en el AsyncEngine** (uso mixto `asyncio.run` / QtAsyncio).
8. **Pagos**: fuera de Desktop (responsabilidad de EduTrack Web).
9. **Empaquetado actual**: PyInstaller (spec incluye QML/fuentes/migraciones) + Inno Setup;
   datos del usuario en `AppDataLocation` (no en carpeta de instalación). Correcto, no sustituir.
10. **Comportamiento de `openPackage`**: verificación `_same_campus` y protección contra
    sobrescribir bases ajenas.

---

## 5. Riesgos de compatibilidad

| Riesgo | Mitigación |
|---|---|
| Cambiar `LocalStore.save()` puede romper la carga del manifiesto o el orden (`position`) del que dependen presenters y exportación | Introducir operaciones incrementales **junto a** `save()`, con pruebas de equivalencia (guardar por ambas vías → manifiesto idéntico); no eliminar `save()` en FASE 1 |
| Nuevos índices vía Alembic sobre bases existentes | Migración `0003` solo con `CREATE INDEX` (no destructiva, reversible) |
| El asistente nuevo debe producir exactamente los mismos campos del manifiesto | Reutilizar `RecordService.save_student/save_enrollment` dentro del caso de uso; no duplicar validaciones |
| La web valida `bundle_id` único y límites de 2000 registros | No tocar `exportPackage` ni límites de `transfer.py` |
| Bases creadas por versiones anteriores (migración legada, promotores sin `server_id`) | Mantener `_migrate_legacy_workspace` y la lógica condicional de versión 3; prueba existente `test_legacy_json_workspace_is_migrated_without_data_loss` debe seguir pasando |
| Pruebas actuales usan `defer_initialize` y fábricas inyectadas | Mantener las firmas de `DesktopBackend.__init__` y de los ports |

---

## 6. Dependencias

Runtime: `PySide6-Essentials/Addons >=6.8`, `SQLAlchemy[asyncio] >=2`, `aiosqlite`,
`alembic >=1.13`, `pydantic >=2.10`, `pydantic-settings`, `structlog >=25`, `openpyxl`,
`rich`, `colorama`. Dev: `pytest >=8`, `mypy`, `pyinstaller >=6`. Gestión con **uv**.

No se prevén dependencias nuevas para FASE 1. (`pytest-qt` se evaluará recién en FASE 7
para pruebas de UI; no es necesario para la lógica de FASE 1.)

---

## 7. Pruebas

### Existentes (36, todas pasan)

- `test_backend.py` (19): flujo completo de sedes, estudiantes, matrículas (pendientes,
  códigos de ficha, promotores incompatibles, preservación de campos), cursos (sync y async),
  catálogo multi-sede, importación/reemplazo, paginación de estudiantes.
- `test_transfer.py` (4): round-trip del paquete, rechazo de manifiestos inválidos,
  persistencia del workspace, migración del formato legado.
- `test_presenters.py` (4), `test_excel_export.py` (2), `test_app_settings.py` (2),
  `test_session_settings.py` (3), `test_logging_config.py` (1), `test_store_logging.py` (1).

### Faltantes (se irán cubriendo por fase)

- Dominio directo: pruebas unitarias de `RecordService` sin pasar por el backend (hoy se
  prueban indirectamente).
- **Atomicidad/rollback** de estudiante+matrícula (no existe el caso de uso todavía).
- Guardado incremental y equivalencia con `save()` completo (FASE 2).
- Búsqueda SQL con normalización y límite (FASE 2).
- Rendimiento con 1k/10k/50k estudiantes (FASE 7).
- UI QML (asistente, atajos) — requiere evaluar `pytest-qt` (FASE 7).
- Respaldo/restauración (FASE 5). Historial de sincronización (FASE 4).

### Comandos

```powershell
cd edutack-desktop
uv run pytest tests -q            # suite completa (~15 s)
uv run pytest tests/test_backend.py -q   # solo backend
uv run mypy                       # tipado (configurado en pyproject)
.\build.ps1 -SkipInstaller        # ejecutable Windows sin instalador
```

---

## 8. Plan de implementación — FASE 1 (matrícula)

Principio: el asistente debe seguir funcionando en cada paso; cambios pequeños y verificables.

### Tarea 1.1 — `CreateEnrollmentUseCase` (guardado atómico)
- **Nuevo** `src/edutrack_desktop/application/enrollment.py`:
  caso de uso que recibe el manifiesto, datos opcionales de estudiante nuevo y datos de
  matrícula; opera sobre una **copia** del manifiesto, llama a
  `RecordService.save_student` (si corresponde) y `RecordService.save_enrollment`,
  y solo si ambos pasan devuelve el manifiesto resultante + IDs. Cualquier `ValueError`
  descarta la copia (rollback en memoria; el guardado físico sigue siendo una única
  transacción de `LocalStore.save`).
- **Modificar** `application/ports.py`: tipo del resultado si hace falta.
- **Modificar** `presentation/backend.py`: nuevo slot
  `createEnrollment(studentFields, enrollmentFields) -> QVariantMap` que delega en el caso
  de uso y hace **un solo** `_save()`; no se tocan `saveStudent`/`saveEnrollment` existentes
  (siguen sirviendo para ediciones).
- **Pruebas**: nuevo `tests/test_enrollment_use_case.py` (dominio/aplicación directo:
  éxito con estudiante nuevo, éxito con existente, fallo de matrícula no crea estudiante,
  fallo de estudiante no crea nada) + prueba de backend (un único guardado físico).

### Tarea 1.2 — Búsqueda de estudiantes desde Python para el asistente
- **Modificar** `presentation/backend.py`: slot `searchStudents(query, limit=20)` que use
  las cachés existentes (`_matching_student_rows`) y devuelva resultados limitados con
  normalización (`casefold`), incluyendo bandera `has_enrollments` para advertencias.
  (La versión SQL con índices llega en FASE 2; la interfaz queda estable desde ya.)
- **Modificar** `EnrollmentWizardPage.qml`: eliminar el filtro JS `matchingStudents`;
  usar `searchStudents` con `Timer` de debounce (~250 ms) y botón "mostrar más".
- **Pruebas**: backend (`searchStudents` limita, normaliza, ordena, marca matrículas).

### Tarea 1.3 — Paso 2 completo del asistente
- **Modificar** `EnrollmentWizardPage.qml`: añadir promotores (desde `promoterOptions`),
  código de ficha, imagen de ficha (`attachEnrollmentImage`/`clearEnrollmentImage`,
  slots ya existentes), resumen previo a confirmar y pantalla de resultado
  (estudiante, curso, horario, grupo, fecha, código, confirmación local).
  Los costos se precargan del curso (comportamiento actual) y siguen siendo editables.
- Sin cambios de dominio: `save_enrollment` ya valida todo esto.
- **Pruebas**: backend con campos completos vía `createEnrollment`.

### Tarea 1.4 — Advertencias y duplicados en el paso 1
- **Modificar** `backend.py`/`presenters.py`: exponer en los resultados de búsqueda las
  matrículas activas del estudiante (advertencia "ya tiene N matrículas").
- **Modificar** `record_service.py` *solo si se aprueba*: advertencia (no bloqueo) por
  documento repetido al crear estudiante; el bloqueo por nombre exacto se conserva.
- **Pruebas**: dominio + backend.

### Dependencias entre tareas

```
1.1 (caso de uso atómico)  ──► 1.3 (asistente completo usa createEnrollment)
1.2 (searchStudents)       ──► 1.4 (advertencias usan los resultados de búsqueda)
1.1 y 1.2 son independientes entre sí.
```

### Fuera del alcance de FASE 1 (fases posteriores)
- Guardado incremental, índices Alembic `0003`, búsqueda SQL → FASE 2.
- Dashboard, componentes QML reutilizables, atajos → FASE 3.
- Centro de sincronización, historial, vista previa de importación → FASE 4.
- Respaldos (API de backup de SQLite) → FASE 5.

---

## 9. Estado de implementación — FASE 1 (completada)

Verificación: `uv run pytest tests -q` → **45 pruebas pasan** (36 base + 9 nuevas);
mypy sin errores nuevos (los 8 reportados son preexistentes); `pyside6-qmllint` sin
errores en el asistente; flujo completo validado en runtime (plataforma offscreen).

| Tarea | Cambios |
|---|---|
| 1.1 Guardado atómico | Nuevo `application/enrollment.py` (`CreateEnrollmentUseCase`: opera sobre copia del manifiesto; si falla cualquier validación, no queda estudiante parcial). Nuevo slot `DesktopBackend.createEnrollment(studentFields, enrollmentFields)` con una única persistencia; `saveStudent`/`saveEnrollment` se conservan para ediciones. Pruebas en `tests/test_enrollment_use_case.py` (8). |
| 1.2 Búsqueda desde Python | Nuevo slot `DesktopBackend.searchStudents(query, limit=20)` (normaliza, limita a 20–100, reutiliza cachés, más recientes primero). Prueba en `test_backend.py`. |
| 1.3 Asistente completo | La implementación histórica incorporó búsqueda con debounce, resumen, matrícula atómica y datos de ficha/promotores. Por la delimitación de responsabilidades vigente, Desktop conserva el flujo académico y ya no ofrece controles para crear o editar esos campos web-managed; véase la sección 55. |
| 1.4 Advertencias | En el paso 1 se advierte si el estudiante seleccionado tiene matrículas activas y, al crear uno nuevo, se listan posibles duplicados (vía `searchStudents`); el bloqueo por nombre exacto del dominio se conserva. |

---

## 10. Estado de implementación — FASE 2

Verificación final: `uv run pytest tests -q` → **50 pruebas pasan**. `pyside6-qmllint`
reporta 0 errores para el asistente. `uv run mypy` mantiene 8 errores preexistentes en
`excel_export.py`, `logging_config.py` y el contrato `RecordServicePort.set_student_active`;
no se reportan errores nuevos en los cambios de FASE 2.

| Tarea | Cambios |
|---|---|
| Guardado incremental general | `LocalStore.save()` se conserva, pero `_save()` ahora sincroniza por ID en una transacción: inserta/cambia solo filas distintas y elimina únicamente IDs ausentes del manifiesto confirmado. Preserva IDs, posiciones, relaciones, `server_id`, `base_hash` y comportamiento de versiones 2/3. Valida referencias antes de aplicar y hace rollback ante referencias inválidas. |
| Operaciones comunes específicas | `LocalStore.save_records()` recibe snapshots de los registros modificados junto con su posición, evitando recorrer todo el manifiesto para localizarlos. Upserts y validaciones de referencias se agrupan por tipo de registro dentro de una transacción; el alta conjunta de estudiante y matrícula se conserva. Los flujos de importación completa siguen usando `save()` como ruta de compatibilidad. |
| Búsqueda/indexación | Migración Alembic `0003_search_indexes`: claves normalizadas (casefold + eliminación de diacríticos) para apellidos, nombres y documento, retrocompatibles con backfill. `0005_course_search` añade y rellena el texto normalizado del curso; `student_page()` lo consulta con `EXISTS` en SQLite, sin transferir todos los cursos a Python. |
| Búsqueda SQL | Nuevo `LocalStore.search_students()` consulta SQLite por prefijo y palabras, ordena por posición reciente, limita a 100 y carga solo las matrículas activas de los estudiantes seleccionados. `DesktopBackend.searchStudents` delega en el store (no filtra `backend.students`); mantiene forma de resultados para el asistente y admite búsqueda insensible a mayúsculas y acentos. |
| Compatibilidad probada | Tests verifican que un cambio unitario no elimina filas de otras tablas, una eliminación deliberada solo borra las filas ausentes, rollback, validaciones de referencias agrupadas, mapeo compartido, índices y uso del índice en el plan SQLite, búsqueda normalizada y upgrade con backfill desde `0002_initial_campus`. El round-trip del manifiesto y la migración JSON legada siguen pasando. |

### Evaluación de operaciones en segundo plano

Ya existían `QRunnable` para inicialización y guardado asíncrono de cursos; el guardado
asíncrono de curso ahora usa `save_records()` y no recorre tablas ajenas. Importación de
paquetes sigue ejecutando validación ZIP/hashes y escritura SQLite en el flujo actual de
UI; exportación `.edutrack` y Excel también son síncronas. Sus límites actuales (25 MB por
paquete, 10 MB por adjunto, 2000 estudiantes/matrículas) acotan el trabajo, pero no
demuestran que el hilo UI no se bloquee. Se pospone mover esos flujos a workers hasta la
FASE 4, donde se incorporarán vista previa, backup y confirmación de importación; hacerlo
ahora y rehacerlo allí duplicaría la coordinación y podría romper el orden de validación.
La carga/hash de una imagen (hasta 10 MB) también queda identificada para medir y evaluar
en esa integración. No se afirma una mejora de rendimiento cuantificada: las mediciones
con conjuntos representativos pertenecen a FASE 7.

---

## 11. Estado de implementación — FASE 3

Verificación final: `uv run pytest tests -q` → **53 pruebas pasan**;
`pyside6-qmllint` termina sin errores para los QML modificados; el arranque
`--smoke-test` en modo offscreen termina con código 0.

| Área | Cambios |
|---|---|
| Dashboard local | `application.presenters.dashboard_summary()` reúne métricas, ocupación y seis matrículas recientes en una sola proyección. `DesktopBackend.dashboardSummary` cachea el resultado hasta que cambian los datos; el dashboard solicita una actualización diaria sin recorrer registros en cada evaluación visual. |
| Actualización | `DesktopBackend.refreshWorkspace()` vuelve a cargar la sede activa desde SQLite, conserva selecciones válidas y emite errores visibles cuando no puede completar la operación. F5 invoca esta ruta. |
| Listados | Estudiantes y cursos consultan SQLite mediante modelos `QAbstractListModel` paginados; cursos filtra en SQL por texto normalizado y fecha, y el recuento de estudiantes activos se agrega en la consulta. `course_week_groups()` agrupa las fechas fuera de QML. Matrículas mantiene su paginación y filtros. |
| Matrícula de estudiantes | Se habilita crear desde Estudiantes, reutilizando `saveStudent` y sus validaciones; el mismo editor admite alta y edición. Ctrl+N abre el alta y Ctrl+M inicia el asistente de matrícula. |
| Accesibilidad/atajos | Ctrl+F enfoca la búsqueda contextual; Ctrl+S guarda los formularios activos; Ctrl+E abre la exportación; Esc cancela/cierra editores, asistente y detalles. |
| Alcance de navegación | Se conservan las cuatro secciones funcionales existentes (Resumen, Estudiantes, Matrículas y Cursos). No se añadieron entradas vacías para promotores, sincronización, base de datos o configuración: las funciones de sincronización/respaldos se incorporarán en sus fases y no existe aún una página funcional de administración de promotores. |
| Pruebas | Nuevas pruebas de la proyección del dashboard (incluidos pendientes y registros de hoy), caché, recarga desde SQLite y workspace vacío. No se afirma una mejora cuantificada de rendimiento; esa medición corresponde a FASE 7. |

---

## 12. Estado de implementación — FASE 4

Verificación final: Desktop `uv run pytest tests -q` → **61 pruebas pasan**;
pruebas Web `students.test_offline_sync` → **12 pasan** con SQLite temporal;
`ruff check` pasa en los archivos modificados, `mypy` no detecta errores en
`application/sync.py` (el chequeo de `backend.py` conserva el error preexistente del
contrato `RecordServicePort.set_student_active`), y el arranque `--smoke-test` offscreen
termina con código 0. `pyside6-qmllint` termina con código 0; `SyncPage.qml` no emite
avisos, mientras `WorkspacePage.qml` emite avisos de acceso QML no calificado. `makemigrations --check --dry-run` no detecta migraciones pendientes y
`git diff --check` pasa.

| Área | Cambios |
|---|---|
| Vista previa | `application/sync.py::build_import_preview` compara registros por `server_id` e ID local, aplica huellas de estudiantes/matrículas y considera el primer retorno de una sede Desktop. Conflictos bloquean la importación; los cambios en cursos/promotores y los cambios de imagen se marcan para atención en la vista previa. |
| Identidad Web/Desktop | Web agrega `DesktopRecordIdentity` y migración `0002_desktop_record_identity` para conservar correspondencias entre IDs locales y remotos. El paquete del primer retorno incluye `desktop_bundle_id`; los formatos `.edutrack` y sus versiones existentes se mantienen. |
| Centro de sincronización | `presentation/qml/pages/SyncPage.qml` ofrece exportación, selección/validación del paquete, vista previa, confirmación y consulta de historial. Exportar informa explícitamente que no equivale a completar la sincronización. |
| Importación confirmada | `DesktopBackend.preparePackageImport/confirmPackageImport` procesa validación en worker, vuelve a comparar con el manifiesto actual, crea/verifica respaldo SQLite y persiste manifiesto e historial dentro de una transacción. Paquetes ya importados se detectan antes de guardar. |
| Respaldos e historial | `infrastructure/backup.py` usa la API de backup de SQLite y valida el resultado. La migración `0004_sync_history` añade historial sin información personal; la ruta de reemplazo confirmada heredada también crea respaldo, registra la importación atómicamente y rechaza paquetes repetidos. |
| Compatibilidad y cobertura | Pruebas cubren clasificación de cambios/conflictos, primer retorno con IDs Web, imágenes normalizadas, respaldo, historial atómico, rollback y reemplazo confirmado. `openPackage` se conserva para importar una sede o reemplazar explícitamente una base registrada; no sustituye la vista previa detallada del Centro de sincronización, que es el flujo recomendado para sincronizaciones regulares. |

### Límites confirmados

- EduTrack Web normaliza las imágenes al almacenarlas. Si solo cambia la imagen de ficha,
  Desktop la señala como actualización que requiere atención, no como conflicto
  silencioso.
- No se añadió sincronización automática ni conexión de red entre las aplicaciones.
- El entorno de pruebas Web usa SQLite temporal; no se validó contra PostgreSQL local
  porque sus credenciales no están disponibles en este entorno.

---

## 13. Estado de implementación — FASE 5

Verificación final: `uv run pytest tests -q` → **64 pruebas pasan**;
`ruff check` pasa en los módulos y pruebas modificados; `mypy` no reporta errores en
`infrastructure/backup.py`; `pyside6-qmllint` no reporta avisos en `BackupsPage.qml`
(WorkspacePage conserva avisos de acceso QML no calificado); el arranque
`--smoke-test` offscreen termina con código 0 y `git diff --check` pasa.

| Área | Cambios |
|---|---|
| Respaldo manual | La sección Respaldos crea copias SQLite mediante la API `backup`; cada nombre incluye fecha, hora y token único, y la creación no sobrescribe copias anteriores. |
| Inventario/verificación | `verify_sqlite_backup` comprueba `quick_check`, las relaciones foráneas, las tablas centrales y que exista un espacio de trabajo EduTrack. El inventario muestra fecha UTC, tamaño, integridad y compatibilidad con la sede activa; los archivos inválidos o de otra sede no se pueden restaurar. |
| Restauración segura | El backend valida que el archivo seleccionado pertenezca a la carpeta `backups` de la base activa y a la misma sede. Prepara una copia temporal, la abre con `LocalStore` para verificar/migrar su esquema, crea un respaldo `pre-restore` de la base actual y reemplaza el archivo mediante `os.replace` tras cerrar las conexiones. |
| Recuperación ante fallos | Si falla la carga posterior al reemplazo, se intenta restaurar el punto `pre-restore`; si también falla el rollback, se registra el error crítico y se muestra la ruta del respaldo para recuperación manual. La UI solicita confirmación antes de reemplazar los datos. |
| Interfaz/documentación | Se agrega la sección Respaldos al sidebar y la página `BackupsPage.qml`. `edutack-desktop/README.md` documenta ubicación, creación, restauración y conservación de una copia externa. |
| Pruebas | Se cubre integridad/corrupción, no sobrescritura, reemplazo de base, compatibilidad de sede, punto de recuperación y actualización del manifiesto después de restaurar. |

Los respaldos se almacenan junto a cada archivo SQLite, en `<carpeta de la base>/backups`.
La restauración se limita intencionalmente a respaldos de esa misma sede; no es una
herramienta para importar bases distintas ni sustituye la sincronización de paquetes.

---

## 14. Estado de implementación — FASE 6

Verificación final: `uv run pytest tests -q` → **66 pruebas pasan**; `ruff check
src/edutrack_desktop tests` pasa; el arranque `--smoke-test` offscreen termina con
código 0; `git diff --check` pasa. El chequeo acotado de mypy no termina limpio:
señala que faltan stubs de `colorama` y un tipo incompatible en la lista de
procesadores de Structlog. No se añadieron dependencias para silenciar esos resultados.

| Área | Cambios |
|---|---|
| Configuración | `logging_config.py` instala un `RotatingFileHandler` JSONL de 1 MB con tres archivos históricos cuando `stderr` no está disponible, incluso si ya hay otros handlers; al reconfigurar, cierra sus handlers administrados anteriores. SQLAlchemy y aiosqlite quedan en WARNING, y el logger SQL del store no emite sentencias ni parámetros por defecto. |
| Diagnóstico | El inicio, apertura de base, actualizaciones de esquema, guardados completos/incrementales, workers, importaciones/exportaciones, respaldos/restauraciones y rechazos de validación emiten eventos estructurados. Los contadores son agregados; las fallas registran tipo de excepción y operación, no el mensaje ingresado por el usuario ni rutas/valores personales. |
| Interfaz y privacidad | Los errores completos continúan mostrándose en la interfaz para facilitar la recuperación; los logs de inicio y backend registran detalles sanitizados. Los logs de validación contienen únicamente la operación y la clase de error. |
| Pruebas y documentación | `test_store_logging.py` comprueba que las consultas SQL/valores privados no se registren, que JSONL rote en modo headless y que un rechazo de validación no escriba datos del usuario. `edutack-desktop/README.md` documenta ubicación, rotación y contenido de los logs. |

El chequeo de mypy queda como limitación conocida para corregir al revisar la
configuración global de tipado y las dependencias de desarrollo; no se incorporó
un paquete adicional únicamente para esta fase.

---

## 15. Estado de implementación — FASE 7

Verificación final: `uv run pytest tests -q` → **75 pruebas pasan**;
`ruff check src/edutrack_desktop tests` pasa; `pyside6-qmllint` termina con código 0
para `Main.qml` y `EnrollmentWizardPage.qml`, con avisos QML existentes. Se añadieron
casos para referencias inactivas al crear matrículas, paquetes `.edutrack` corruptos
e interacciones QML. La cobertura existente también verifica validaciones,
guardado/rollback, migración desde el esquema anterior, índices, historial,
importación repetida, backups y restauración.

### Mediciones locales

Comando: `uv run python tests/benchmark_desktop.py`. Entorno observado: Windows 11,
Python 3.14.4. Las bases se generaron en directorios temporales; cada operación de
búsqueda, carga completa, guardado incremental y transferencia se repitió cinco veces
para calcular medianas. El primer guardado incluye la inicialización y migraciones; la
apertura incluye comprobación del esquema y carga. Los paquetes se midieron con el
límite actual de 2.000 estudiantes.

| Estudiantes | Guardado inicial + migraciones (ms) | Apertura + carga (ms) | Carga completa mediana (ms) | Búsqueda indexada mediana (ms) | Guardado de 1 registro mediano (ms) |
|---:|---:|---:|---:|---:|---:|
| 1.000 | 551,20 | 150,15 | 56,99 | 19,32 | 34,84 |
| 10.000 | 1.855,77 | 377,70 | 327,77 | 12,55 | 25,72 |
| 50.000 | 4.936,80 | 1.221,56 | 1.350,68 | 12,44 | 32,23 |

| Caso de transferencia | Tamaño del paquete | Exportación mediana | Importación mediana |
|---|---:|---:|---:|
| 2.000 estudiantes | 69.584 bytes | 22,46 ms | 21,20 ms |

Son mediciones de una ejecución local, no objetivos de rendimiento ni una comparación
antes/después: no se conservó una línea base de tiempos anterior a las fases de
optimización. El script repetible está en `edutack-desktop/tests/benchmark_desktop.py`;
no se incluyen datos personales ni archivos de benchmark en el repositorio.

### Límites de cobertura

- `pytest-qt` no está instalado. Las pruebas QML usan las APIs `QGuiApplication` y
  `QtTest` incluidas con PySide6. Hypothesis está en el grupo de desarrollo y prueba
  propiedades de normalización y backfill de migraciones.
- `test_qml_enrollment_wizard.py` carga el QML real en modo offscreen y comprueba búsqueda
  con debounce, selección, pasos, validación, advertencia de duplicados, alta de estudiante,
  guardado con Ctrl+S, cancelación con Esc y el atajo global Ctrl+M con carga diferida de
  `Main.qml`. No cubre visualmente todos los tamaños/temas ni todos los atajos globales.
- `Main.qml` carga con `Loader` las pantallas de sede y espacio de trabajo, y crea los
  diálogos globales y editores de estudiantes/cursos solo cuando se solicitan. Las
  pruebas verifican la carga diferida desde el flujo real de la ventana.
- `test_qml_enrollment_editor.py` activa **Editar** en la lista real y espera al editor
  del `Loader` asíncrono. Verifica que abrirlo no materializa todos los estudiantes y que
  el selector consulta por búsqueda con un límite inicial de 20.
- No se afirma una mejora porcentual ni se fija un umbral de latencia: falta acordar
  objetivos y medir una línea base comparable en equipos representativos.

---

## 16. Estado de implementación — FASE 8

Se verificó el empaquetado existente sin cambiar PySide6, QML, SQLite, PyInstaller
ni Inno Setup. El ejecutable autocontenido se construyó con PyInstaller 6.22.3
en Windows 11 y Python 3.14.4; el instalador se compiló con Inno Setup 6.7.3.

La primera ejecución empaquetada detectó `ModuleNotFoundError: aiosqlite`: SQLAlchemy
carga dinámicamente el dialecto `sqlalchemy.dialects.sqlite.aiosqlite`, por lo que
PyInstaller no incluía el driver. `EduTrackDesktop.spec` declara ahora el módulo del
dialecto y `aiosqlite` como imports ocultos. Tras reconstruir, el ejecutable y el
instalador pasaron estas verificaciones:

- `EduTrackDesktop.exe --smoke-test` inició la interfaz, aplicó Alembic y creó una
  base de datos de 94.208 bytes bajo `EDUTRACK_DESKTOP_DATABASE_PATH`.
- El instalador se ejecutó en una carpeta temporal; el ejecutable instalado pasó
  el mismo smoke test y creó su base de datos fuera de la carpeta de instalación.
  Después se desinstaló el paquete de prueba y se eliminaron sus datos temporales.
- El ejecutable generado mide 143.736.564 bytes y el instalador
  `EduTrackDesktop-Setup-0.1.0.exe` mide 143.879.699 bytes.

La ejecución directa de `build.ps1` fue bloqueada por la política de ejecución de
PowerShell del equipo. No se modificó esa política: se ejecutaron manualmente sus
pasos de PyInstaller e Inno Setup y ambos terminaron correctamente. PyInstaller
reportó módulos opcionales ausentes de Qt y la herramienta de despliegue de PySide6;
no impidieron construir, iniciar ni instalar la aplicación. Conviene repetir la
prueba en una máquina virtual Windows limpia antes de distribuir el instalador.

## 17. Búsqueda y paginación del listado de estudiantes

El listado de estudiantes consulta SQLite por página y aplica en la consulta los
filtros de texto, estado y curso. Solo las filas visibles se proyectan al
`QAbstractListModel`; cambiar de página, buscar o filtrar no necesita reconstruir
la lista completa desde el manifiesto. La búsqueda QML espera 250 ms desde la
última pulsación. La presentación cambia a tarjetas compactas cuando el ancho del
listado es inferior a 820 px.
La lista limita su ancho al contenedor para evitar que las acciones queden fuera
del área visible en la ventana mínima; la prueba QML verifica mediante clic real
que Editar abre el formulario.
`CourseListModel` consulta `LocalStore.course_page()` por páginas de 50 cursos.
SQLite busca en `search_text` normalizado (nombre, horario y grupo) y en la fecha;
cada término puede coincidir con cualquiera de esos campos. La consulta calcula
el número de estudiantes activos por curso, sin reconstruir todas las filas desde
el manifiesto. La migración `0005_course_search` rellena el campo normalizado en
bases existentes. El modelo agrupa semanas con `course_week_groups()` usando
fechas `date` de Python; valores ISO inválidos quedan en "Semana no definida".
Las tarjetas toman su punto de corte compacto del ancho del área visible, no del
ancho implícito de su contenido, y la prueba QML comprueba que Editar quede dentro
del listado en la ventana mínima.

Se amplió `tests/benchmark_desktop.py` para medir la consulta paginada con los
mismos conjuntos de 1.000, 10.000 y 50.000 estudiantes. En Windows 11 / Python
3.14.4, con cinco repeticiones, las medianas de búsqueda SQL paginada fueron
14,39 ms, 23,30 ms y 70,48 ms; las medianas de carga completa fueron 27,57 ms,
193,10 ms y 1.107,48 ms. El guardado incremental de un estudiante tuvo medianas
de 15,18 ms, 13,01 ms y 14,34 ms. La búsqueda por curso midió 10,06 ms, 11,66 ms
y 10,54 ms con 1.000, 10.000 y 50.000 cursos respectivamente. Son mediciones
locales comparativas, no garantías de latencia.
El benchmark optativo de `course_page()` mide además la búsqueda SQL paginada
para los mismos tamaños de listado. En esta ejecución, sus medianas fueron
8,46 ms, 12,55 ms y 35,17 ms para 1.000, 10.000 y 50.000 cursos.

La suite Desktop pasa con 111 pruebas (17 benchmarks optativos excluidos).
Las pruebas validan la búsqueda de cursos sin acentos, búsqueda por fecha,
recuento de estudiantes activos, paginación, orden semanal, límites de año y
fechas inválidas. La prueba QML verifica también que el botón de edición no se
desborde en la ventana mínima. No se modificó el formato `.edutrack`.

## 18. Matrículas, consultas asíncronas y cambios sin guardar

`LocalStore.enrollment_page()` filtra, cuenta, ordena y pagina matrículas en
SQLite, incluyendo búsqueda y filtros de estado/curso. El listado QML ya no
necesita materializar todas las matrículas para mostrar una página. El benchmark
optativo `enrollment-list-page` valida la paginación y mide la consulta con
1.000, 10.000 y 50.000 matrículas. En esta máquina, las medianas de búsqueda
fueron 20,14 ms, 39,78 ms y 155,40 ms respectivamente; son mediciones
comparativas, no garantías de latencia.

Los listados paginados y las búsquedas de estudiantes usadas en el asistente y
el editor ejecutan sus consultas fuera del hilo de UI mediante workers
compartidos de `QThreadPool`. Cada consulta comunica resultado o error a su
modelo; las respuestas obsoletas se descartan mediante generaciones/IDs de
solicitud. Los listados muestran un estado de carga cuando todavía no tienen
filas que mostrar. Se conserva `NullPool` para el motor async: los workers
ejecutan operaciones con `asyncio.Runner` y un `SelectorEventLoop` dedicado.
Esto evita que un worker seleccione el loop de Qt cuando la aplicación ya está
ejecutando `QtAsyncio.run()`; el mismo store puede seguir utilizándose desde
loops diferentes gracias a `NullPool`.

Los formularios de estudiante, curso y matrícula, el asistente y el cierre de
la ventana advierten antes de descartar cambios sin guardar. La vista previa
manual de sincronización expone diferencias por campo entre Desktop y Web,
incluidas relaciones de matrícula e imágenes descritas por presencia/hash. No
se altera el formato `.edutrack` ni se incorpora sincronización automática.
La lista de respaldos conserva las fechas ISO para orden y almacenamiento, y
las presenta en hora local con el formato `dd/MM/yyyy HH:mm`.

La validación anterior pasó 54 pruebas de almacenamiento/backend/sincronización,
12 pruebas QML de asistente y editor y tres casos del benchmark de matrículas.
La regresión del loop se reprodujo en un `QRunnable` bajo `QtAsyncio` y se
verificó corregida con el loop selector. El fixture de pruebas mantiene activa
la aplicación Qt al cerrar y reabrir ventanas; la prueba QML de matrículas
espera también a que el modelo y su delegado estén listos. La última suite
completa pasó: 115 pruebas, con 20 benchmarks optativos excluidos.

## 19. Reauditoría de fuente de verdad y línea base (2026-11-01)

Esta revisión se realizó sobre el árbol actual, sin cambios de código funcional.
La suite Desktop ejecutada con `uv run pytest tests -q` pasó **116 pruebas** y
excluyó **20 benchmarks** por la configuración normal de pytest. También se
ejecutó `uv run python tests/benchmark_desktop.py` en Windows 11 / Python
3.14.4; los valores siguientes son medianas de cinco repeticiones, no objetivos
ni una comparación antes/después:

| Estudiantes | Guardado inicial + migraciones (ms) | Apertura + carga completa (ms) | Carga completa (ms) | Búsqueda directa SQL (ms) | Página SQL con búsqueda (ms) | Guardado incremental de 1 registro (ms) |
|---:|---:|---:|---:|---:|---:|---:|
| 1.000 | 286,59 | 76,55 | 31,23 | 8,84 | 15,28 | 17,85 |
| 10.000 | 1.173,62 | 242,25 | 231,16 | 8,42 | 35,34 | 18,98 |
| 50.000 | 5.445,05 | 1.067,22 | 1.076,20 | 7,86 | 87,42 | 15,37 |

La búsqueda SQL de cursos midió 11,73 / 12,22 / 12,87 ms para 1.000 /
10.000 / 50.000 cursos. El paquete de 2.000 estudiantes ocupó 69.572 bytes y
su exportación/importación midió 21,33 / 20,31 ms. Las cifras varían respecto
de ejecuciones históricas de este documento; no deben interpretarse como una
mejora o regresión porcentual entre máquinas o revisiones.

### Estado observado del manifiesto

SQLite ya conserva las tablas de estudiantes, cursos, promotores y matrículas;
`LocalStore.save_records()` escribe mutaciones seleccionadas en una transacción,
y los listados paginados y la búsqueda del asistente consultan SQLite. Sin
embargo, el manifiesto **sigue siendo una copia operativa permanente en memoria**
y el requisito de SQLite como única fuente de verdad todavía no se cumple:

| Uso | Clasificación | Estado y dirección de migración |
|---|---|---|
| `transfer.py`: leer, validar y escribir `.edutrack` | Importación/exportación | Uso correcto; conservar versiones 2/3, identidades, hashes y validación. |
| `backend.py::initialize`, `refreshWorkspace`, `openPackage` y cambios de sede | Operativo | `store.load()` reconstruye todos los registros y los asigna a `self.manifest`. Sustituir cargas de operación normal por metadatos/consultas acotadas; mantener lectura completa solo en flujos de intercambio y compatibilidad. |
| `backend.py` CRUD y `domain/record_service.py` | Operativo | Estudiantes, cursos y matrículas se validan y modifican en el manifiesto; `save_records()` persiste después las mutaciones. Mover validación/orquestación a servicios que reciban IDs/datos y ejecuten repositorios SQL en transacciones. |
| `application/enrollment.py::CreateEnrollmentUseCase` | Operativo | Copia el manifiesto con `deepcopy`, usa `RecordService` y persiste estudiante y matrícula mediante `save_records()`. La atomicidad ya está cubierta por pruebas; conservar reglas y transacción al sustituir la copia por operaciones SQL. |
| `application/presenters.py` y properties de `backend.py` | Operativo | Presenters y dashboard recorren las colecciones completas; selección de filas también busca en memoria. Trasladar proyecciones, conteos y selección a consultas SQL. Los modelos paginados existentes ya son una base reutilizable. |
| `backend.py` importación/sincronización | Estado local + intercambio | El paquete entrante puede ser temporal, pero el snapshot local se copia desde el manifiesto. En la migración, obtener el estado local necesario desde SQLite y preservar preview, revalidación, backup e historial atómico. |
| `backend.py` exportación de paquete y `excel_export.py` | Exportación | Actualmente ambos parten del manifiesto retenido. Generar el snapshot de salida bajo demanda desde consultas SQLite y liberarlo al terminar. |
| `campus_catalog.py` | Configuración local persistente | `campuses.json` registra rutas/nombres y sede activa; no duplica filas de negocio, pero se debe decidir si entra en la definición estricta de configuración operativa. Si migra, importar el catálogo existente sin perder ni reubicar bases. |

`Workspace` conserva metadatos del formato/paquete y adjuntos JSON; `SyncHistoryRecord`
persiste el historial. La aplicación Desktop no tiene modelos ni flujo de pagos:
la auditoría anterior los considera responsabilidad de EduTrack Web. Incorporar
pagos al cliente offline ampliaría el modelo/sincronización y requiere decisión
de alcance antes de modificar el contrato actual.

### Hallazgos priorizados y dependencias

1. **P1 — Fuente de verdad no conforme:** `backend.py` mantiene el manifiesto
   completo desde el inicio; `store.py::_load()` materializa todas las tablas;
   los servicios de dominio y presenters dependen de la misma estructura.
   Consecuencia medida: abrir/cargar 50.000 estudiantes tomó 1.067 ms y una
   carga completa repetida 1.076 ms. La búsqueda directa sí se mantuvo entre
   7,86 y 8,84 ms; la página con búsqueda pasó de 15,28 a 87,42 ms. Migrar
   primero los contratos Store/servicios y los CRUD, y después dashboard,
   selección, sincronización y exportación.
2. **P1 — Búsqueda parcialmente escalable:** la consulta dedicada tiene buen
   comportamiento en esta medición, pero la búsqueda paginada contiene
   condiciones `LIKE` con comodín inicial. Revisar `EXPLAIN QUERY PLAN` sobre
   los casos reales antes de cambiar índices o añadir FTS5; no afirmar que los
   índices B-tree aceleran búsquedas por subcadena.
3. **P2 — Operaciones síncronas y asíncronas mixtas:** los listados usan
   `AsyncQueryWorker`, `QThreadPool`, `asyncio.Runner` y descartan resultados
   obsoletos. En cambio, `_run_async()` ejecuta operaciones de slots dentro de
   un `QEventLoop` anidado. Mantener `NullPool`, medir bloqueos/reentrancia y
   migrar operaciones pesadas a workers sin compartir `AsyncSession`.
4. **P2 — Datos persistentes fuera de SQLite:** el catálogo de sedes está en
   JSON; confirmar si debe migrarse junto con la configuración persistente. El
   `.coverage` de la raíz también estaba versionado y sin regla de exclusión;
   se añadió a `.gitignore` y se retiró del índice sin borrar la copia local.
5. **P2 — Alcance de pagos:** no hay persistencia ni operaciones de pagos en
   Desktop. No añadir tablas ni inventar compatibilidad de sincronización sin
   definir cómo se integran con Web.

### Comportamiento que se conserva y compatibilidad

- La creación conjunta de estudiante y matrícula ya tiene operación, guardado
  transaccional y pruebas para rollback; el problema pendiente es su dependencia
  del manifiesto, no la atomicidad actual.
- Se conservan las tablas/migraciones existentes, la migración del workspace
  JSON legado, `NullPool`, la búsqueda paginada, los backups verificados y el
  historial de sincronización.
- La importación confirmada revalida el snapshot y el `bundle_id`, crea backup
  y guarda los registros con el historial en la ruta transaccional existente.
- No cambiar el archivo `.edutrack` ni sus versiones. Las pruebas de round-trip,
  versiones, duplicados, conflictos, rollback, backups y formularios QML deben
  seguir pasando en cada etapa.

### Orden recomendado de implementación

1. Añadir pruebas arquitectónicas que fallen si el inicio carga todas las
   colecciones o si CRUD depende de `self.manifest`; mantener el baseline de
   benchmarks y añadir medición de memoria con datasets escalables.
2. Introducir operaciones SQL específicas en `WorkspaceStore` y sus servicios;
   migrar CRUD de estudiantes, cursos y matrículas, empezando por matrícula
   atómica. Mantener `load/save` solo para compatibilidad de importación,
   exportación y bases legadas durante la transición.
3. Migrar presenters, dashboard, selecciones, sincronización y Excel para
   consultar SQLite bajo demanda; generar manifiestos temporales únicamente en
   los límites de transferencia.
4. Resolver explícitamente configuración/catálogo y alcance de pagos antes de
   alterar su persistencia o contrato.
5. Comparar pruebas y benchmarks bajo el mismo comando, máquina y tamaños;
   ampliar a 100.000 registros antes de afirmar soporte de ese volumen.

## 20. Fase 2 incremental — resumen SQL (2026-11-01)

El dashboard ya obtiene sus métricas directamente de `LocalStore.dashboard_summary()`.
SQLite calcula los conteos y cursos completos; la consulta de ocupación ordena y
limita a seis cursos, y la de matrículas recientes devuelve seis filas. No se
materializan todas las colecciones para esta vista. El backend usa
`AsyncQueryWorker` y una señal de notificación propia, de modo que la carga no
ocupa el hilo de UI ni provoca la recarga incidental de los modelos de listas.
Las respuestas antiguas se ignoran por ID de solicitud.

Se añadieron pruebas que comparan la proyección SQL con la presentación previa
para matrículas normales y pendientes, y que verifican que el resumen sigue
leyendo SQLite cuando `backend.manifest` es `None`. La prueba QML que verifica
la fila de matrícula espera ahora a que el delegado visual se cree; mantiene
sus aserciones de cantidad y estado del modelo.

Validación tras este cambio: suite Desktop **118 pruebas pasadas, 20 benchmarks
optativos excluidos**; `ruff check` pasa; `mypy` pasa para `store.py`,
`backend.py` y `ports.py`.

El benchmark existente compara cinco ejecuciones del resumen SQL con cinco de
la proyección en memoria sobre el mismo manifiesto, en Windows 11 / Python
3.14.4:

| Registros | Resumen SQL en worker (ms) | Proyección Python sobre manifiesto ya cargado (ms) |
|---:|---:|---:|
| 1.000 | 13,71 | 0,23 |
| 10.000 | 19,02 | 3,07 |
| 50.000 | 29,83 | 19,15 |

En esta ejecución la consulta SQL fue más lenta que proyectar un manifiesto que
ya está en memoria; **no se afirma una mejora de latencia**. La ventaja medida
en diseño es acotar el resultado transferido y ejecutar el agregado fuera del
hilo de UI. El benchmark no mide memoria ni incluye el coste de cargar el
manifiesto para la proyección Python. Se debe conservar ambas mediciones al
optimizar la consulta. Este cambio solo migra el dashboard: la inicialización,
CRUD, selección, sincronización y exportación todavía mantienen dependencias
operativas del manifiesto, así que SQLite aún no es la única fuente de verdad.

## 21. Fase 2 incremental — búsqueda SQL sin manifiesto (2026-11-01)

`searchStudents()` y `searchStudentsAsync()` ya no requieren que el backend
mantenga `self.manifest`: solo necesitan el store abierto y consultan
`LocalStore.search_students()` en SQLite. Se conserva el comportamiento de
límite, resultados de matrículas activas y entrega asíncrona existente. La
prueba arquitectónica cubre una búsqueda por documento con
`backend.manifest = None`; también se verifica desde el asistente QML que la
búsqueda asíncrona encuentra al estudiante bajo la misma condición.

La suite completa pasó **119 pruebas, 20 benchmarks optativos excluidos**;
Ruff y mypy pasan para los módulos revisados. La prueba QML del asistente
también espera a que el delegado tenga dimensiones utilizables antes de hacer
clic, evitando interactuar con un item visible pero todavía sin ancho durante
el layout. Su estado de diagnóstico se captura antes del clic porque QML puede
destruir el delegado al seleccionar.

Este corte no elimina la carga completa ni las dependencias de manifiesto del
CRUD restante, selección, sincronización o exportación. No cambia el esquema
SQLite ni el formato `.edutrack`.

## 22. Fase 2 incremental — creación SQL de matrícula (2026-11-01)

`CreateEnrollmentUseCase` ahora puede persistir una matrícula a través de
`WorkspaceStore.create_enrollment()`. La operación consulta en SQLite solo el
estudiante seleccionado o candidatos con el mismo nombre normalizado, el curso,
los promotores seleccionados y matrículas que puedan entrar en conflicto. Con
ese contexto acotado reutiliza las validaciones de `RecordService` y escribe el
nuevo estudiante (si aplica) y la matrícula en una transacción SQLAlchemy única.
Los listados paginados tampoco requieren que `backend.manifest` esté cargado.

Las pruebas cubren creación con `manifest=None`, matrícula de un estudiante ya
persistido, rechazo de duplicado y rollback de estudiante y matrícula cuando un
trigger de SQLite rechaza el INSERT. Se conserva temporalmente la proyección en
memoria cuando el manifiesto ya está cargado, porque selección y otras
superficies todavía dependen de él; retirarla requiere migrar esas lecturas y
exportación/sincronización, no simplemente dejarla desactualizada.

Validación: suite Desktop **124 pruebas pasadas, 20 benchmarks optativos
excluidos**; Ruff y mypy pasan en los módulos afectados. No se midió rendimiento
en este corte y no se afirma una mejora de latencia. La carga completa al inicio,
el CRUD restante, las lecturas de selección y los flujos de transferencia aún
impiden considerar SQLite como única fuente de verdad.

## 23. Fase 2 incremental — snapshots SQL para transferencia (2026-11-01)

La exportación de paquetes carga el snapshot desde `WorkspaceStore` en el worker
de `exportPackageAsync`; el método síncrono `exportPackage` también genera su
snapshot desde SQLite. La previsualización de importación obtiene el snapshot
local dentro del worker, y la confirmación conserva su relectura y comparación
antes de guardar. Así, estos límites de intercambio no necesitan que
`backend.manifest` esté presente. Se conserva el formato y las versiones
existentes de `.edutrack`.

Las pruebas validan exportación síncrona y asíncrona con `manifest=None`, el
registro del fallo de escritura en el historial y el rechazo de una importación
si SQLite cambia después de la vista previa. El snapshot completo sigue siendo
materializado temporalmente para construir el paquete o comparar una
importación; las lecturas de formularios, selección, CRUD restante y Excel aún
dependen de la copia en memoria. El método síncrono de exportación tampoco se
ejecuta en worker; la ruta usada por QML sí es asíncrona.

Validación de esta etapa: suite Desktop **128 pruebas pasadas, 20 benchmarks
optativos excluidos**; Ruff y mypy pasan en los módulos fuente y pruebas
afectados. No se midió rendimiento en este corte y no se afirma una mejora.

## 24. Fase 2 incremental — exportación de registro desde SQLite (2026-11-01)

`exportRegister` ya no requiere `backend.manifest` ni ejecuta consultas o
generación del libro en el hilo de Qt. El worker obtiene una proyección
específica desde `WorkspaceStore.register_export_data()`: cursos, matrículas
asociadas, estudiantes referenciados y promotores usados. No carga adjuntos ni
otras tablas operativas, y el estado de actividad y el resultado se notifican
al backend/QML. El formato y contenido del libro se mantienen mediante
`export_register`.

La prueba de integración exporta con `manifest=None`, compara los valores de
las hojas con la exportación de referencia y confirma que no se llama a
`WorkspaceStore.load()`. También se cubre el error de escritura. La proyección
necesita materializar los registros que aparecen en el libro; no se midió el
rendimiento y no se afirma una mejora. El CRUD restante y el inicio siguen
dependiendo del manifiesto, por lo que SQLite aún no es la única fuente
operativa.

Validación de esta etapa: suite Desktop **129 pruebas pasadas, 20 benchmarks
optativos excluidos**; Ruff y mypy pasan en los módulos fuente afectados.

## 25. Fase 2 incremental — escritura SQL de cursos (2026-11-01)

`createCourse`, `saveCourse` y `saveCourseAsync` ya no requieren el manifiesto
ni llaman a `save_records`. `WorkspaceStore.create_course` y
`WorkspaceStore.update_course` obtienen el contexto de cursos desde SQLite,
conservan la normalización y validación de duplicados de `RecordService`, y
persisten cada cambio dentro de una transacción. La ruta usada por el editor
QML corre con `AsyncQueryWorker`; los adaptadores síncronos se conservan para
compatibilidad y no deben usarse para consultas voluminosas desde la interfaz.
La proyección en memoria solo se sincroniza tras confirmar la escritura cuando
aún está cargada. No se modifican el esquema ni `.edutrack`.

Las pruebas cubren creación y actualización con `manifest=None`, persistencia,
rechazo de duplicados y manejo de errores; el editor QML conserva su señal de
finalización. El inicio y otras operaciones CRUD todavía dependen del
manifiesto.

Validación de esta etapa: suite Desktop **132 pruebas pasadas, 20 benchmarks
optativos excluidos**; Ruff y mypy pasan en los módulos fuente afectados. No se
midió rendimiento en este corte.

## 26. Fase 2 incremental — escritura SQL de estudiantes (2026-11-01)

`saveStudent` y `setStudentActive` ya escriben directamente en SQLite y pueden
operar con `backend.manifest=None`. `WorkspaceStore.save_student` consulta los
candidatos por nombre mediante las columnas de búsqueda normalizadas y entrega
solo ese contexto a `RecordService` para conservar las reglas de duplicados y
validación; `set_student_active` actualiza el registro seleccionado. Ambas
escrituras usan transacciones, y la proyección en memoria solo se sincroniza
después de confirmar el cambio cuando ya estaba cargada. `_run_store_write`
mantiene los estados y señales de guardado para estas rutas síncronas.

`EXPLAIN QUERY PLAN` para la consulta de candidatos confirmó el uso de
`ix_desktop_students_first_name_search`; el apellido se aplica como filtro
adicional. Esto verifica el índice usado por el plan, pero no mide latencia. Las
pruebas cubren alta, edición, duplicados, activación y operación sin manifiesto.
La edición de matrículas, promotores, adjuntos, el inicio y otras lecturas CRUD
aún dependen del manifiesto.

Validación de esta etapa: suite Desktop **133 pruebas pasadas, 20 benchmarks
optativos excluidos**; Ruff y mypy pasan en los módulos fuente afectados. No se
midió rendimiento en este corte.

## 27. Fase 2 incremental — edición SQL de matrículas

`saveEnrollment` ya crea y actualiza matrículas mediante `WorkspaceStore` y una
transacción SQLite, incluso con `backend.manifest=None`. Para mantener las
reglas de `RecordService`, el store construye un contexto acotado con el
estudiante, curso, promotores, matrícula objetivo y candidatos de conflicto
consultados en SQL; no reconstruye el manifiesto completo. La proyección cargada
solo se actualiza después del commit. Al quitar el código de ficha, la limpieza
de referencias e `attachment_data` también se persiste en la misma transacción.

Se añadieron regresiones para alta, edición, matrícula duplicada, rechazo de
datos inválidos sin cambio parcial y limpieza de adjuntos con el manifiesto
desconectado. Se conserva el formato de intercambio y las reglas de negocio. La
selección y otras operaciones de matrícula aún tienen dependencias del
manifiesto; el inicio todavía lo carga, por lo que SQLite no es aún la única
fuente operativa en toda la aplicación.

Validación: suite Desktop **134 pruebas pasadas, 20 benchmarks optativos
excluidos**; mypy pasa en los tres módulos fuente modificados y Ruff pasa para
los códigos E4/E7/E9/F en los archivos afectados. El chequeo Ruff completo de
esos archivos informa 15 hallazgos de estilo/modernización fuera de esta ruta.
El chequeo mypy completo sigue informando siete errores en `excel_export.py` y
`logging_config.py` (stubs externos y tipado del procesador); no se modificaron
en esta etapa. No se midió rendimiento.

## 28. Fase 2 incremental — adjuntos SQL de matrículas

`attachEnrollmentImage` y `clearEnrollmentImage` ya operan mediante
`WorkspaceStore.update_enrollment_image`, sin exigir un manifiesto cargado. La
imagen validada se codifica temporalmente para persistir su contenido en
`Workspace.attachment_data` y la referencia/hash en `EnrollmentRecord`, dentro
de una única transacción. Al quitar una imagen, se consultan en SQL las demás
referencias antes de eliminar el contenido compartido, conservando adjuntos
referenciados por otras matrículas. Si el manifiesto está cargado, su proyección
se actualiza únicamente después del commit. El formato `.edutrack` no cambia.

Las pruebas cubren adjuntar y quitar imágenes con `manifest=None`, limpieza al
quitar el código de ficha y conservación del contenido mientras otra matrícula
comparte la misma imagen.

Validación: suite Desktop **134 pruebas pasadas, 20 benchmarks optativos
excluidos**; mypy pasa en los módulos fuente afectados y Ruff pasa para E4/E7/E9/F.
No se midió rendimiento. La carga inicial del manifiesto y otras operaciones
operativas siguen pendientes de migración.

## 29. Fase 2 incremental — creación SQL de promotores

`createPromoter` ya valida y persiste el nuevo promotor mediante
`WorkspaceStore.create_promoter` en una transacción SQLite, aun con
`backend.manifest=None`. `RecordService` conserva la normalización, detección de
duplicados y asignación del identificador. El store deriva `campus_mode` de la
versión persistida: se conserva la restricción que permite crear promotores
solo en sedes nuevas. Si el manifiesto está cargado, se actualiza su proyección
después del commit.

Las pruebas cubren creación sin manifiesto, duplicados, persistencia, la
restricción de sedes existentes y compatibilidad de exportación. La propiedad
`promoterOptions` y la carga inicial todavía dependen del manifiesto; esta etapa
no completa la migración de las lecturas operativas.

Validación: suite Desktop **136 pruebas pasadas, 20 benchmarks optativos
excluidos**; mypy pasa en los módulos fuente afectados y Ruff pasa para E4/E7/E9/F.
No se midió rendimiento ni se modificó el formato `.edutrack`.

## 30. Fase 2 incremental — nómina de curso desde SQLite

La propiedad `courseStudents` ya no filtra la copia completa del manifiesto.
`LocalStore.course_students` consulta en SQL las matrículas activas del curso,
une únicamente a los estudiantes activos, elimina duplicados y conserva el
orden previo de la nómina. El backend ejecuta la consulta con `AsyncQueryWorker`,
descarta resultados obsoletos cuando cambia el curso y notifica a la vista de
detalle al recibir el resultado; así evita bloquear el hilo de Qt.

Las pruebas cubren la nómina con `manifest=None` y la actualización de la vista
de detalle. La carga inicial y otras propiedades operativas todavía dependen
del manifiesto; no se afirma que SQLite sea aún la única fuente en toda la app.

Validación: suite Desktop **137 pruebas pasadas, 20 benchmarks optativos
excluidos**; mypy pasa en los módulos fuente afectados y Ruff pasa para E4/E7/E9/F.
No se midió rendimiento.

## 31. Fase 2 incremental — opciones y filtros de cursos desde SQLite

`WorkspaceStore.course_options()` consulta en SQLite únicamente los campos
necesarios para seleccionar y filtrar cursos. El backend carga esa proyección
con `AsyncQueryWorker` y expone `courseOptions`,
`courseFilterOptions` y `activeEnrollmentCourses` desde el mismo resultado.
El editor de matrícula, el asistente y los filtros de estudiantes y matrículas
ya no leen `backend.courses` ni requieren `backend.manifest` para sus opciones.
La interfaz distingue el estado de carga del estado vacío, y las opciones en
caché se invalidan cuando cambian los datos.

Las pruebas cubren cursos activos e inactivos, el orden, la consulta con
`manifest=None` y la integración QML. La proyección sigue materializando todas
las opciones de curso en memoria; para volúmenes grandes, debe evolucionar a
búsqueda/paginación SQL. La propiedad general `courses` y el inicio todavía
cargan el manifiesto.

Validación: suite Desktop **138 pruebas pasadas, 20 benchmarks optativos
excluidos**; mypy pasa en los tres módulos fuente afectados y Ruff pasa para
E4/E7/E9/F en los archivos Python revisados. No se midió rendimiento.

## 32. Fase 2 incremental — búsqueda SQL de cursos en matrícula

El selector del asistente de matrícula ya no recibe la lista completa de cursos.
`WorkspaceStore.search_course_options()` filtra cursos activos directamente en
SQLite por nombre, horario, grupo o fecha y limita cada resultado; el backend lo
ejecuta fuera del hilo Qt. QML aplica debounce, descarta respuestas obsoletas y
copia al formulario los costos del curso seleccionado. La prueba QML verifica
la búsqueda con `backend.manifest=None`; otra prueba comprueba el filtro de
activos y el límite de resultados.

Los filtros generales de estudiantes/matrículas todavía usan la proyección
completa `course_options()`, y el inicio continúa cargando el manifiesto. No se
modificó el esquema ni el formato `.edutrack`, y no se midió rendimiento.

Validación: suite Desktop **139 pruebas pasadas, 20 benchmarks optativos
excluidos**; mypy pasa en los tres módulos fuente afectados, Ruff pasa para
E4/E7/E9/F y Pylance confirmó la compatibilidad de los cuatro sitios de
llamada con la API original de búsqueda SQL de cursos, generalizada en la
sección 33.

## 33. Fase 2 incremental — selector SQL del editor de matrículas

El editor ya no filtra la proyección completa `backend.courseOptions`: al abrir
el selector o escribir una búsqueda, consulta SQLite con un límite de 50
opciones y debounce, y descarta respuestas de solicitudes anteriores. Esta
consulta incluye cursos inactivos para que el editor pueda mostrarlos sin
permitir seleccionar uno inactivo distinto del curso que ya tiene la matrícula.
La fila SQL de matrícula ahora incluye el estado `course_active`, de modo que el
curso actual conserva su etiqueta y condición aunque no aparezca en la búsqueda
actual o esté inactivo/no disponible.

La búsqueda genérica también es usada por el asistente de matrícula con filtro
de activos. No se modifica el esquema ni el formato `.edutrack`. Los filtros
generales de estudiantes y matrículas todavía materializan opciones completas
de curso, y el inicio aún carga el manifiesto.

Validación: `tests/test_backend.py` **41 pruebas pasadas** y Ruff pasa para los
archivos Python afectados. Las pruebas QML focalizadas no pudieron validar la
interfaz en esta máquina: Qt no cargó
`qtquickcontrols2materialstyleplugin.dll` ("No se puede encontrar el módulo
especificado"). Mypy reportó errores en ubicaciones preexistentes fuera de los
métodos modificados después de instalar SQLAlchemy 2.1.6; por ello ese chequeo
no se considera aprobado en este entorno.

## 34. Fase 2 incremental — filtros de curso con búsqueda SQL

Los filtros de estudiantes y matrículas usan ahora el componente reutilizable
`CourseFilterPicker`: la lista solo se consulta cuando se abre el selector o se
escribe una búsqueda, con debounce, descarte de respuestas obsoletas y un
límite de 50 resultados. La consulta incluye cursos activos e inactivos para
conservar la posibilidad de filtrar matrículas históricas. El identificador
seleccionado se conserva al cambiar las opciones visibles.

Se eliminaron `LocalStore.course_options()`, su contrato en `WorkspaceStore` y
la caché/proyección completa de cursos del backend. Por tanto, los filtros ya no
materializan el catálogo completo. El inicio sigue cargando el manifiesto y
otras operaciones todavía dependen de él; no se modificó el esquema ni el
formato `.edutrack`.

Validación: `tests/test_backend.py` **40 pruebas pasadas**; Ruff y
`git diff --check` pasan. Las pruebas y compilación QML continúan bloqueadas por
fallos al cargar los plugins Qt Quick Controls de esta instalación; no se
consideran validadas visualmente.

## 35. Fase 2 incremental — inicio y respaldo con metadatos SQL

La inicialización ya no llama a `LocalStore.load()`. `LocalStore.workspace_info()`
obtiene desde SQLite los metadatos de sede, conteos SQL y el primer ID de curso;
el backend usa ese resultado para nombre/estado de sede, catálogo, selección
inicial y resumen de sincronización, manteniendo `manifest=None` en el arranque.
`refreshWorkspace()` vuelve a consultar metadatos y modelos SQL sin reconstruir
las colecciones. Los cambios de datos actualizan estos metadatos mediante un
worker y las respuestas antiguas se descartan por ID.

También se retiró la dependencia del manifiesto de las comprobaciones y la
restauración de backups: se valida la sede candidata/restaurada con metadatos
SQL y la base restaurada queda activa sin cargar todas sus filas a memoria.
Una prueba de backend prohíbe `load()` durante el arranque y verifica metadatos
y búsqueda con SQLite; `test_transfer.py` comprueba que `workspace_info()` no
usa `_load()`.

Validación: `tests/test_backend.py tests/test_sync.py` **56 pasaron**;
`tests/test_transfer.py` **17 pasaron**; `compileall` pasó. Ruff y
`git diff --check` pasaron para los archivos Python modificados. Las operaciones
de importación/exportación y varios flujos heredados todavía crean o consultan
manifiestos temporales; no se cambió el esquema ni el formato `.edutrack`.

## 36. Fase 2 incremental — alta de matrícula sin duplicar registros en memoria

El alta del asistente ya no agrega el estudiante ni la matrícula guardados a
`backend.manifest`. `LocalStore.create_enrollment()` persiste ambos registros en
una única transacción y devuelve únicamente sus identificadores y si se creó el
estudiante; el backend conserva las señales de actualización de los modelos SQL.
Las pruebas verifican los datos persistidos consultando SQLite y que un
manifiesto previamente cargado no cambie durante el alta. No se modificó el
formato `.edutrack` ni el esquema.

Validación: `tests/test_enrollment_use_case.py` **15 pasaron**; Ruff,
`compileall` y `git diff --check` pasaron. Las dos pruebas QML focalizadas no
pudieron cargar `AppTheme.qml` porque falta una dependencia del plugin
Qt Quick Controls Material en este entorno.

## 37. Fase 2 incremental — creación de promotores sin proyección de manifiesto

La creación de promotores ya persiste en SQLite y devuelve únicamente el ID.
Se retiró la copia al manifiesto y la propiedad `promoterOptions`, que no tenía
consumidores en el QML actual; la creación sigue notificando cambios para
refrescar metadatos/modelos. Una prueba verifica que el manifiesto cargado no
cambia y que el promotor está en la base. No se modificó el esquema ni el
formato `.edutrack`.

Validación: `tests/test_backend.py` **42 pasaron**; Ruff,
`compileall`, compatibilidad de firma Pylance y `git diff --check` pasaron.

## 38. Fase 2 incremental — contexto reducido al crear promotores

`LocalStore.create_promoter()` ya no materializa los registros ORM completos.
Lee solo la columna de nombres, necesaria para conservar la validación
Unicode/casefold de duplicados, y obtiene el próximo ID y la posición con
agregaciones SQL. `RecordService` mantiene la normalización y la validación; la
API directa del servicio conserva sus valores por defecto para los flujos que
aún operan sobre manifiestos temporales.

Validación: `tests/test_backend.py tests/test_enrollment_use_case.py` **58
pasaron**; Ruff, `compileall`, compatibilidad de firma Pylance y
`git diff --check` pasaron.

## 39. Fase 2 incremental — contexto acotado al guardar cursos

`LocalStore.create_course()` y `update_course()` ya no materializan toda la
tabla de cursos para invocar `RecordService`. Primero normalizan los campos con
el servicio de dominio y usan el `search_text` normalizado para consultar solo
posibles duplicados; la edición agrega al contexto únicamente el curso objetivo.
La creación obtiene el siguiente ID y la posición con agregaciones SQL. La
validación final de identidad sigue en `RecordService`, que conserva el
comportamiento por defecto para los flujos que aún usan snapshots temporales.
No se modificaron el esquema ni el formato `.edutrack`.

Validación: `tests/test_backend.py` **44 pasaron**, `tests/test_transfer.py`
**17 pasaron** y `tests/test_enrollment_use_case.py` **15 pasaron**; Ruff,
`compileall`, compatibilidad de firma Pylance y `git diff --check` pasaron.

## 40. Fase 2 incremental — listado de cursos sin proyección de manifiesto

Se retiró la propiedad heredada `backend.courses` y su caché, que derivaban
filas desde el manifiesto y podían quedar desactualizadas después de una
escritura SQL. La pantalla de cursos ya usa `CourseListModel`, que obtiene las
filas paginadas y el conteo de estudiantes desde `LocalStore.course_page()`.
Las pruebas que necesitaban un curso ahora lo consultan mediante ese modelo o
el store SQL. No se modificaron el esquema ni el formato `.edutrack`.

Validación: `tests/test_backend.py tests/test_enrollment_use_case.py` **59
pasaron**; Ruff, `compileall` y `git diff --check` pasaron. Dos pruebas QML
focalizadas no pudieron validarse porque Qt no carga el plugin
`QtQuick.Controls.Material` (`qtquickcontrols2materialstyleplugin.dll` no
encuentra una dependencia en este entorno).

## 41. Fase 2 incremental — retirada de getters heredados sin consumidores

Se eliminaron `backend.enrollments` y `backend.selectedCourse`, junto con la
caché que materializaba todas las matrículas desde el manifiesto. La búsqueda
en QML confirmó que ninguna pantalla dependía de esas propiedades; cursos y
matrículas siguen consultándose mediante sus modelos paginados respaldados por
SQLite. No se modificaron el esquema ni el formato `.edutrack`.

Validación: `tests/test_backend.py tests/test_enrollment_use_case.py` **59
pasaron**; Ruff, `compileall` y `git diff --check` pasaron.

## 42. Fase 2 incremental — selección de matrícula desde escrituras SQL

`selectedEnrollment` ya no busca registros en el manifiesto: conserva solo el
registro individual devuelto por `LocalStore` al guardar la matrícula o su
imagen, y se limpia al cambiar de matrícula o de sede. `enrollmentImageName`
mantiene así la etiqueta del adjunto en `EnrollmentWizardPage.qml`. Las
operaciones de matrícula e imagen dejaron de copiar al backend la colección
completa `_attachment_data`; los adjuntos siguen persistidos en SQLite y se
exportan por las rutas de transferencia. Ninguna escritura modifica el
manifiesto operativo.

Validación: `tests/test_backend.py tests/test_enrollment_use_case.py
tests/test_transfer.py` **76 pasaron**; Ruff, `compileall` y
`git diff --check` pasaron.

## 43. Fase 2 incremental — escrituras de cursos sin proyección

Las operaciones de creación y edición de cursos ya no copian ni actualizan
registros en `backend.manifest`; conservan únicamente el ID seleccionado y
notifican a los modelos, que vuelven a consultar SQLite. Se ajustó la prueba de
preservación de `server_id` para preparar ese dato en el store y comprobar que
una escritura normal no altera el manifiesto en memoria.

Validación: `tests/test_backend.py tests/test_enrollment_use_case.py
tests/test_transfer.py` **76 pasaron**; Ruff, `compileall` y
`git diff --check` pasaron.

## 44. Fase 2 incremental — apertura local con metadatos SQL

`switchCampus()` y `openLocalDatabase()` ahora consultan
`LocalStore.workspace_info()` en vez de cargar `LocalStore.load()` para abrir
una base existente. El backend recibe conteos y metadatos de la sede, conserva
`manifest=None` y selecciona el primer curso usando el ID devuelto por SQL.
Una prueba sustituye `store.load()` por un error para comprobar que ambos
flujos no materializan los registros operativos.

Validación: `tests/test_backend.py` **44 pasaron**, `tests/test_enrollment_use_case.py
tests/test_transfer.py` **32 pasaron**, y la prueba focalizada de apertura pasó;
Ruff, `compileall` y `git diff --check` pasaron.

## 45. Fase 2 incremental — manifiesto temporal tras crear/importar

Al finalizar la creación de una sede o la importación de un paquete,
`_finish_database_change()` conserva únicamente los metadatos de la sede y deja
`manifest=None`; el objeto recibido para persistencia/transferencia no queda
retenido como copia operativa. La protección para no quitar una sede activa del
catálogo ahora consulta `_workspace_info` en lugar de depender de que el
manifiesto esté cargado.

Validación: `tests/test_backend.py` **44 pasaron**,
`tests/test_enrollment_use_case.py` **15 pasaron**, `tests/test_sync.py`
**15 pasaron** y `tests/test_transfer.py` **17 pasaron**; Ruff, `compileall` y
`git diff --check` pasaron.

## 46. Fase 2 incremental — lista y escrituras de estudiantes desde SQLite

Se retiraron los getters y la caché heredados de estudiantes, que duplicaban
filas del manifiesto: la interfaz activa usa `StudentListModel` y consulta
SQLite. Las escrituras conservan como máximo el registro individual seleccionado
y notifican a los modelos para refrescar desde SQL. También se retiraron
`_save()` y `_mutation_for_record()`, sin referencias de código, que formaban
parte de la ruta heredada para persistir mutaciones del manifiesto. La
persistencia de manifiestos se mantiene para creación e importación.

Validación: `tests/test_backend.py` **44 pasaron**,
`tests/test_enrollment_use_case.py` **15 pasaron**, `tests/test_sync.py`
**15 pasaron** y `tests/test_transfer.py` **17 pasaron**; Ruff, `compileall` y
`git diff --check` pasaron. Las pruebas QML siguen sin validarse por el bloqueo
conocido del plugin `QtQuick.Controls.Material` en este entorno.

## 47. Fase 2 incremental — auditoría de importación y brechas de dominio

La importación rutinaria retiene el paquete y el snapshot local solo durante la
vista previa. Al confirmar, vuelve a leer la sede, comprueba que no cambió,
revalida sede, paquete y conflictos, crea un respaldo y guarda los registros
junto con el historial dentro de una transacción SQL. Los conflictos bloquean
la confirmación y deben resolverse en EduTrack Web; la ruta `openPackage()` se
mantiene separada para importaciones/reemplazos explícitos, con confirmación en
la interfaz.

La cobertura comprueba que una vista previa conflictiva no permite confirmar
ni modifica la base, el historial o los respaldos. Además, la última
comparación del snapshot ahora se ejecuta dentro de la misma transacción que
guarda los datos y el historial. La validación entre conexiones independientes
se documenta en la sección 49.

Los pagos y recibos están fuera del alcance de EduTrack Desktop y no deben
implementarse en esta aplicación; las tarifas de cursos/matrículas son datos
académicos, no registros de pagos.

Validación: `tests/test_sync.py` **18 pasaron**, `tests/test_backend.py`
**44 pasaron**, `tests/test_transfer.py` **17 pasaron** y
`tests/test_enrollment_use_case.py` **15 pasaron**; Ruff, `compileall` y
`git diff --check` pasaron.

## 48. Retirada de ruta heredada de guardado

Se eliminó `_WorkspaceSaveWorker`, que no tenía instancias ni llamadas, junto
con la bifurcación de `_persist_manifest()` para `save_records()`. Las
operaciones normales ya escriben directamente en SQLite; la persistencia del
manifiesto queda limitada a guardar snapshots de creación e importación.
La comprobación de compatibilidad confirmó las dos llamadas restantes de
`_persist_manifest()`.

Validación: `tests/test_backend.py` **44 pasaron**; Pylance confirmó que las
dos llamadas son compatibles con la firma actual y `git diff --check` pasó.

## 49. Serialización de importaciones concurrentes

La prueba con dos `LocalStore` independientes en modo WAL mostró que una
transacción SQLite diferida podía leer el snapshot esperado y, después de que
otra conexión confirmara una escritura, continuar con una importación basada
en un snapshot obsoleto sin rechazarla. Para cerrar esa ventana, `_save()`
inicia con `BEGIN IMMEDIATE` cuando recibe `expected_snapshot`; así la lectura de
revalidación y la escritura quedan serializadas frente a otros escritores.

La prueba inicia dos importaciones desde el mismo snapshot en conexiones
independientes: la primera confirma y la segunda detecta el snapshot obsoleto,
falla sin sobrescribir los datos y no registra un historial de éxito.

## 50. Ejecución de pruebas QML en Windows

Las pruebas QML no podían cargar los plugins de Qt porque Windows no tenía
registrada la carpeta de DLL de PySide6 en la búsqueda de bibliotecas. El
`conftest.py` de pruebas ahora registra esa carpeta y conserva el handle
durante la ejecución, sin cambiar la configuración de la aplicación.
También se normaliza `QJSValue` en la aserción del estudiante seleccionado.

La suite QML completa pasó: **33 pruebas**. Para el diálogo de cierre, el
runner offscreen no activó el botón superior con `QTest.mouseClick`; la prueba
invoca el método `click()` del botón y valida el mismo flujo QML. Queda una
validación manual del clic físico en Windows.

## 51. Retirada del alta de matrícula basada en manifiesto

`CreateEnrollmentUseCase` ya no expone la ruta `execute(manifest, ...)`, que
copiaba y mutaba el manifiesto para crear estudiantes y matrículas. El flujo
activo queda en `execute_and_persist()`, que delega en la operación transaccional
de `LocalStore.create_enrollment()`. Las pruebas de referencias inactivas y
estudiantes inexistentes ahora preparan y consultan los datos en SQLite.

Validación: `tests/test_enrollment_use_case.py` **12 pasaron**.

## 52. CRUD operativo exclusivamente en SQLite

Se retiró `LocalStore.save_records()` y su declaración en `WorkspaceStore`: no
tenía consumidores de producción y aceptaba manifiestos para persistir
mutaciones parciales, manteniendo una ruta CRUD heredada. Las pruebas y
benchmarks asociados ahora actualizan estudiantes y matrículas mediante
`save_student()` y `save_enrollment()`, que validan con el servicio de dominio y
escriben los registros seleccionados directamente en SQLite. El guardado de
manifiestos queda reservado a importación/exportación.

## 53. Ediciones de estudiantes con referencias obsoletas

`save_student()` podía interpretar un ID de edición inexistente como un alta:
el servicio de dominio no encontraba la fila en el contexto SQL y generaba un
ID nuevo, que el store insertaba. Ahora el store rechaza explícitamente los
IDs no vacíos que no corresponden a un estudiante existente; el backend muestra
el error y la prueba de regresión verifica que SQLite queda sin cambios.

## 54. Capacidad de cursos informativa

Se confirmó que la capacidad es un indicador, no un límite que bloquee
matrículas. El conteo de ocupación considera estudiantes activos asociados a
matrículas activas; las reservas sin estudiante no cuentan como alumnos. Una
prueba cubre el guardado al superar la capacidad, la presencia del curso en la
búsqueda y el indicador de curso completo. Esta decisión también queda
aclarada en el README para evitar que la ocupación se convierta en una
validación de escritura por accidente.

## 55. Promotores y fichas administrados desde EduTrack Web

Desktop ya no crea promotores, no asigna promotores a matrículas y no permite
crear, adjuntar, reemplazar o quitar fichas. Se retiraron las operaciones del
store, los puertos, el servicio de dominio, el backend y los controles del
asistente; las sedes nuevas tampoco siembran los promotores `PARTICULAR` y
`NN`. La validación SQL rechaza cambios no vacíos de esos campos durante altas
y ediciones, pero conserva los valores y adjuntos que ya existían en registros
importados. El esquema y el formato `.edutrack` se mantienen para importar,
exportar y sincronizar esos datos sin pérdida.

Pagos y recibos también permanecen fuera del alcance de Desktop.

## 56. Validación integrada del CRUD SQLite

Se agregó una regresión para confirmar que intentar editar una matrícula cuyo ID
ya no existe devuelve un error y no inserta una matrícula nueva. La suite
completa de Desktop, ejecutada con `uv run pytest tests -vv -x`, terminó con
**142 pruebas aprobadas**; los **20 benchmarks** quedaron excluidos por el
marcador `performance` configurado en pytest. Ejecutados por separado con
`uv run pytest tests/test_performance_benchmarks.py -m performance -q`, los
**20 benchmarks** también pasaron (33,91 s).

## 57. Cierre de ventana durante operaciones activas

Cuando se solicita cerrar la ventana mientras el backend está ocupado, el
`closeEvent` se pospone y `DatabaseSavingOverlay` permanece visible con su
indicador animado y el mensaje de finalización. Al terminar la operación se
retira el estado de espera y se cierra la ventana. Las pruebas QML cubren el
cierre diferido y el cierre normal durante la pantalla de inicio.
