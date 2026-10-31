# EduTrack Desktop — Auditoría técnica (FASE 0)

Fecha: 2026-10-30
Línea base verificada: `uv run pytest tests -q` → **36 pruebas, todas pasan** (~15 s), sobre el árbol de trabajo actual (incluye cambios sin commitear).

> Objetivo: documentar la arquitectura real, los problemas encontrados, los riesgos de
> compatibilidad y el plan incremental de la FASE 1, **sin modificar código todavía**.

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

- La **fuente de verdad en memoria es el "manifiesto"**: un `dict` con claves
  `format`, `version`, `bundle_id`, `campus_id`, `campus_name`, `campus_address`,
  `students[]`, `enrollments[]`, `courses[]`, `promoters[]` y opcionales
  `_attachment_data{}` y `campus_mode`.
- `LocalStore` (SQLite, una base por sede) materializa el manifiesto en 5 tablas
  (`desktop_workspaces`, `desktop_students`, `desktop_courses`, `desktop_promoters`,
  `desktop_enrollments`). **`_save()` borra todas las filas y reescribe el manifiesto
  completo en una sola transacción** (`store.py:217-221`).
- `LocalStore.initialize()` ejecuta `alembic upgrade head` al abrir y migra el formato
  legado (tabla `workspace` con JSON) sin pérdida de datos (`_migrate_legacy_workspace`).
- El motor usa `NullPool` deliberadamente: el mismo store se usa desde `asyncio.run`
  (worker) y desde el bucle QtAsyncio (no cambiar).
- `DesktopBackend` guarda con dos mecanismos:
  - `_persist_manifest()` → `_run_async()` (bucle anidado `QEventLoop`) para la mayoría
    de operaciones (estudiante, matrícula, importación…), con overlay "Guardando…".
  - `_WorkspaceSaveWorker` (`QRunnable` + `asyncio.run`) solo para `saveCourseAsync`.

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
| Dominio | `RecordService.save_enrollment` | Valida estudiante/curso/fecha/montos (`Decimal` con 2 decimales vía `_amount`), código de ficha (único por fecha), promotores (activos, sin repetir, PARTICULAR/NN excluyentes), calidad de imagen; preserva valores existentes si el campo no viene; soporta matrículas "pendientes" (solo estudiante o solo curso) |
| Dominio | `RecordService.normalize_course_fields` | Identidad de curso única (nombre+horario+grupo), fecha ISO, capacidad entera positiva |
| Dominio | `RecordService.set_student_active`, `remove_unused_attachments` | Activación y limpieza de adjuntos huérfanos |
| Aplicación | `presenters.py` | Proyección manifiesto→filas para QML (labels, orden, filtro en memoria) |
| Infraestructura | `LocalStore.load/save/initialize/dispose` | Carga/guardado completo + migraciones + legado |
| Infraestructura | `transfer.read_package/write_package/validate_manifest` | Validación estricta del paquete (pydantic + reglas), escritura atómica (tmp + `os.replace`) |
| Infraestructura | `CampusCatalog` | `campuses.json` validado, escritura atómica, sede activa |
| Presentación | `DesktopBackend.saveStudent/saveEnrollment/setStudentActive` | Delegan a RecordService + `_save()` (guardado completo) |
| Presentación | `DesktopBackend.openPackage/exportPackage/switchCampus/openLocalDatabase/closeCampus/createWorkspace` | Ciclo de vida de sedes y paquetes |
| Presentación | `DesktopBackend.studentPage/matchingStudentCount` | Paginación con caché en memoria (usada por StudentsPage; **no** por el asistente) |
| Presentación | `DesktopBackend.attachEnrollmentImage/clearEnrollmentImage` | Adjuntar imagen de ficha (slots existentes; **sin UI que los invoque actualmente**) |
| QML | `EnrollmentWizardPage.qml` | Asistente de 2 pasos (buscar/crear estudiante → datos de matrícula) |
| QML | `EnrollmentEditorPage.qml` | Edición de matrícula (estudiante, curso, fecha, montos, activa) |
| QML | `SummaryPage.qml` | "Resumen": totales, ocupación de cursos, matrículas recientes, exportar Excel |
| QML | `WorkspacePage.qml` | Navegación lateral: Matrículas / Estudiantes / Cursos / Resumen (carga perezosa) |

---

## 3. Problemas identificados (por gravedad)

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
| 1.3 Asistente completo | `EnrollmentWizardPage.qml` reescrito: búsqueda con debounce de 250 ms y "Mostrar más"; paso 2 con curso, fecha, costos precargados editables, código de ficha y promotores (multi-selección); resumen antes de confirmar; pantalla de resultado con confirmación local y adjuntado de imagen de ficha (reutiliza `attachEnrollmentImage`). El estudiante nuevo ya no se guarda por separado: viaja con la matrícula vía `createEnrollment`. |
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
| Operaciones comunes específicas | Nuevo `LocalStore.save_records(manifest, changes)` para upsert de estudiantes, matrículas, cursos y promotores concretos. Los slots CRUD de `DesktopBackend` y el worker de guardado de curso lo usan; el alta conjunta de estudiante y matrícula persiste ambas en una sola transacción. Los flujos de importación completa conservan `save()` como ruta de compatibilidad. |
| Búsqueda/indexación | Migración Alembic `0003_search_indexes`: claves normalizadas (casefold + eliminación de diacríticos) para apellidos, nombres y documento, retrocompatibles con backfill; índices en esas claves, IDs de estudiante/curso y estado de matrícula, nombre/estado de curso y nombre de promotor. Los IDs ya cubiertos por PK no reciben índices redundantes. |
| Búsqueda SQL | Nuevo `LocalStore.search_students()` consulta SQLite por prefijo y palabras, ordena por posición reciente, limita a 100 y carga solo las matrículas activas de los estudiantes seleccionados. `DesktopBackend.searchStudents` delega en el store (no filtra `backend.students`); mantiene forma de resultados para el asistente y admite búsqueda insensible a mayúsculas y acentos. |
| Compatibilidad probada | Tests verifican que un cambio unitario no elimina filas de otras tablas, una eliminación deliberada solo borra las filas ausentes, rollback, uso de la ruta específica, índices y uso del índice en el plan SQLite, búsqueda normalizada y upgrade con backfill desde `0002_initial_campus`. El round-trip del manifiesto y la migración JSON legada siguen pasando. |

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
| Listados | Los presenters de cursos y matrículas se cachean con la misma invalidación de los estudiantes. Cursos incorpora búsqueda local con debounce por nombre, horario, grupo y fecha; estudiantes ya tenía paginación y búsqueda del backend, y matrículas ya tenía paginación y filtros. |
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

- `pytest-qt` e Hypothesis no están instalados. Las pruebas usan las APIs `QGuiApplication`
  y `QtTest` incluidas con PySide6, sin dependencia adicional; no se añadieron pruebas
  property-based porque los invariantes clave tienen casos de regresión explícitos.
- `test_qml_enrollment_wizard.py` carga el QML real en modo offscreen y comprueba búsqueda
  con debounce, selección, pasos, validación, advertencia de duplicados, alta de estudiante,
  guardado con Ctrl+S, cancelación con Esc y el atajo global Ctrl+M con carga diferida de
  `Main.qml`. No cubre visualmente todos los tamaños/temas ni todos los atajos globales.
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
