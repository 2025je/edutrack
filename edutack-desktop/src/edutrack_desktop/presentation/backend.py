import asyncio
import base64
import hashlib
import re
import sqlite3
import uuid
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Coroutine

from PySide6.QtCore import (
    QEventLoop,
    QObject,
    QRunnable,
    QStandardPaths,
    QThreadPool,
    QUrl,
    Signal,
    Slot,
)
from sqlalchemy.exc import SQLAlchemyError
import structlog

from ..application.enrollment import CreateEnrollmentUseCase
from ..application.ports import (
    CampusCatalogFactory,
    CampusCatalogPort,
    RecordServicePort,
    StoreFactory,
    WorkspaceStore,
)
from ..application.presenters import (
    course_rows,
    course_students,
    dashboard_summary,
    enrollment_rows,
    filter_student_rows,
    student_rows,
)
from ..application.sync import build_import_preview
from ..domain.record_service import RecordMutation, RecordService
from ..infrastructure.app_settings import DesktopSettings
from ..infrastructure.backup import (
    create_sqlite_backup,
    restore_sqlite_backup,
    verify_sqlite_backup,
)
from ..infrastructure.campus_catalog import CampusCatalog, CampusCatalogError
from ..infrastructure.excel_export import export_register
from ..infrastructure.store import LocalStore
from ..infrastructure.transfer import (
    INITIAL_CAMPUS_VERSION,
    PACKAGE_FORMAT,
    PackageError,
    read_package,
    write_package,
)
from .list_models import CourseListModel, EnrollmentListModel, StudentListModel

logger = structlog.get_logger(__name__)


def _create_local_store(path: Path) -> WorkspaceStore:
    return LocalStore(path)


class _WorkspaceSaveWorkerSignals(QObject):
    finished = Signal(bool, object, str)


class _WorkspaceSaveWorker(QRunnable):
    def __init__(
        self,
        store: WorkspaceStore,
        manifest: dict[str, Any],
        record_changes: dict[str, list[RecordMutation]] | None = None,
    ):
        super().__init__()
        self.setAutoDelete(False)
        self._store = store
        self._manifest = manifest
        self._record_changes = record_changes
        self.signals = _WorkspaceSaveWorkerSignals()

    def run(self):
        try:
            operation = (
                self._store.save(self._manifest)
                if self._record_changes is None
                else self._store.save_records(
                    self._manifest, self._record_changes
                )
            )
            asyncio.run(operation)
        except (
            OSError,
            RuntimeError,
            SQLAlchemyError,
            ValueError,
            KeyError,
            TypeError,
        ) as exc:
            logger.error(
                "workspace.save_failed",
                error_type=exc.__class__.__name__,
            )
            self.signals.finished.emit(
                False,
                None,
                str(exc) or exc.__class__.__name__,
            )
            return
        self.signals.finished.emit(True, self._manifest, "")


class _SyncOperationWorkerSignals(QObject):
    finished = Signal(str, bool, object, str)


class _SyncOperationWorker(QRunnable):
    def __init__(self, operation_name: str, operation: Callable[[], object]):
        super().__init__()
        self.setAutoDelete(False)
        self._operation_name = operation_name
        self._operation = operation
        self.signals = _SyncOperationWorkerSignals()

    def run(self):
        try:
            result = self._operation()
        except (
            OSError,
            RuntimeError,
            SQLAlchemyError,
            sqlite3.Error,
            PackageError,
            ValueError,
            KeyError,
            TypeError,
        ) as exc:
            event = (
                "backup.operation_failed"
                if self._operation_name.startswith("backup_")
                else "sync.operation_failed"
            )
            logger.error(
                event,
                operation=self._operation_name,
                error_type=exc.__class__.__name__,
            )
            self.signals.finished.emit(
                self._operation_name,
                False,
                None,
                str(exc) or exc.__class__.__name__,
            )
            return
        if self._operation_name == "preview" and isinstance(result, dict):
            preview = result.get("preview", {})
            logger.info(
                "sync.package_preview_ready",
                new_count=preview.get("new", 0),
                updated_count=preview.get("updated", 0),
                conflict_count=preview.get("conflicts", 0),
                attention_count=preview.get("attention", 0),
            )
        elif self._operation_name == "import" and isinstance(result, dict):
            logger.info(
                "sync.package_imported",
                affected_counts=result.get("affected_counts", {}),
            )
        elif self._operation_name == "export" and isinstance(result, dict):
            logger.info(
                "sync.package_exported",
                history_saved=not result.get("history_error", False),
            )
        elif self._operation_name == "backup_list" and isinstance(result, list):
            logger.info(
                "backup.inventory_loaded",
                backup_count=len(result),
                invalid_count=sum(not item["valid"] for item in result),
            )
        elif self._operation_name == "backup_create" and isinstance(result, dict):
            logger.info(
                "backup.created",
                backup_type="manual",
                size_bytes=result.get("size_bytes", 0),
            )
        elif self._operation_name == "backup_restore" and isinstance(result, dict):
            manifest = result.get("manifest", {})
            logger.info(
                "backup.restored",
                student_count=len(manifest.get("students", [])),
                enrollment_count=len(manifest.get("enrollments", [])),
                course_count=len(manifest.get("courses", [])),
                promoter_count=len(manifest.get("promoters", [])),
            )
        self.signals.finished.emit(self._operation_name, True, result, "")


if TYPE_CHECKING:
    def Property(
        *args: Any, **kwargs: Any
    ) -> Callable[[Callable[..., Any]], property]: ...
else:
    from PySide6.QtCore import Property


class DesktopBackend(QObject):
    dataChanged = Signal()
    selectionChanged = Signal()
    errorChanged = Signal()
    syncStateChanged = Signal()
    syncPreviewFinished = Signal(bool, object, str)
    syncImportFinished = Signal(bool, object, str)
    syncExportFinished = Signal(bool, str)
    backupStateChanged = Signal()
    backupDirectoryChanged = Signal()
    backupOperationFinished = Signal(str, bool, object, str)
    courseSaveStateChanged = Signal()
    courseSaveFinished = Signal(bool)
    savingStateChanged = Signal()
    activityStateChanged = Signal()

    def __init__(
        self,
        store_path=None,
        catalog_path=None,
        settings=None,
        *,
        store_factory: StoreFactory | None = None,
        catalog_factory: CampusCatalogFactory | None = None,
        record_service: RecordServicePort | None = None,
        defer_initialize: bool = False,
    ):
        super().__init__()
        self._save_pool = QThreadPool(self)
        self._save_in_progress = False
        self._course_save_worker: _WorkspaceSaveWorker | None = None
        self._course_save_task: asyncio.Task[None] | None = None
        self._course_save_in_progress = False
        self._pending_course_save_id: int | None = None
        self._load_in_progress = False
        self._sync_in_progress = False
        self._sync_worker: _SyncOperationWorker | None = None
        self._sync_operation_metadata: dict[str, Any] = {}
        self._pending_import_manifest: dict[str, Any] | None = None
        self._pending_import_snapshot: dict[str, Any] | None = None
        self._pending_import_preview: dict[str, Any] = {}
        self._sync_history_cache: list[dict[str, Any]] | None = None
        self._backup_items: list[dict[str, Any]] = []
        self._activity_message = ""
        self.settings = settings or DesktopSettings()
        if store_factory is None:
            self._store_factory: StoreFactory = _create_local_store
        else:
            self._store_factory = store_factory
        self._catalog_factory: CampusCatalogFactory = (
            catalog_factory if catalog_factory is not None else CampusCatalog
        )
        self._record_service = (
            record_service if record_service is not None else RecordService()
        )
        self._create_enrollment_use_case = CreateEnrollmentUseCase(
            self._record_service
        )
        uses_default_path = store_path is None
        if store_path is None:
            store_path = self.settings.database_path
            if store_path is None:
                data_dir = self.settings.data_dir or Path(
                    QStandardPaths.writableLocation(
                        QStandardPaths.StandardLocation.AppDataLocation
                    )
                )
                store_path = data_dir / "edutrack-desktop.sqlite3"
        default_store_path = Path(store_path).expanduser().resolve()
        if catalog_path is None:
            catalog_path = self.settings.campus_catalog_path
            if catalog_path is None and uses_default_path:
                catalog_path = default_store_path.parent / "campuses.json"
        self.catalog: CampusCatalogPort | None = (
            self._catalog_factory(catalog_path) if catalog_path is not None else None
        )

        selected_path = default_store_path
        startup_error = ""
        # A persisted inactive catalog may intentionally be empty after removals.
        closed_on_start = bool(
            self.catalog
            and self.catalog.path.is_file()
            and not self.catalog.active_path
        )
        self.store: WorkspaceStore | None = None
        self.manifest: dict[str, Any] | None = None
        self._student_rows_cache: list[dict[str, Any]] | None = None
        self._student_filter_cache_query: str | None = None
        self._student_filter_cache_rows: list[dict[str, Any]] = []
        self._enrollment_rows_cache: list[dict[str, Any]] | None = None
        self._course_rows_cache: list[dict[str, Any]] | None = None
        self._dashboard_summary_cache: dict[str, Any] | None = None
        if self.catalog and self.catalog.records and not closed_on_start:
            candidates = [self.catalog.active_path] + [
                record["path"]
                for record in self.catalog.records
                if record["path"] != self.catalog.active_path
            ]
            selected_path = next(
                (
                    Path(path)
                    for path in candidates
                    if Path(path).is_file() and self._is_local_database(path)
                ),
                default_store_path,
            )
            if selected_path == default_store_path and not any(
                Path(path).is_file() and self._is_local_database(path)
                for path in candidates
            ):
                startup_error = (
                    "No se encontró ninguna base de datos registrada. "
                    "Selecciona o importa una sede para continuar."
                )

        self._selected_store_path = selected_path
        self._default_store_path = default_store_path
        self._closed_on_start = closed_on_start
        self._startup_error = startup_error
        self._initialized = False
        self._error_message = startup_error
        self._selected_student_id = ""
        self._selected_enrollment_id = ""
        self._selected_course_id: int | None = None
        self._student_list_model = StudentListModel(
            self._student_page_rows,
            parent=self,
        )
        self._course_list_model = CourseListModel(
            self._course_page_rows,
            parent=self,
        )
        self._enrollment_list_model = EnrollmentListModel(
            self._all_enrollment_rows,
            parent=self,
        )
        self.dataChanged.connect(self._refresh_list_models)
        if not defer_initialize:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(self.initialize())

    async def initialize(self):
        if self._initialized:
            return
        if self._closed_on_start:
            self._initialized = True
            return

        logger.info("database.open_started")
        try:
            self.store = self._store_factory(self._selected_store_path)
        except (OSError, RuntimeError, SQLAlchemyError, ValueError) as exc:
            if self._selected_store_path == self._default_store_path:
                raise
            self._startup_error = f"No se pudo abrir la sede registrada: {exc}"
            self.store = self._store_factory(self._default_store_path)

        self.manifest = await self.store.load()
        logger.info(
            "database.opened",
            workspace_loaded=self.manifest is not None,
            student_count=(
                len(self.manifest.get("students", [])) if self.manifest else 0
            ),
            enrollment_count=(
                len(self.manifest.get("enrollments", [])) if self.manifest else 0
            ),
            course_count=(
                len(self.manifest.get("courses", [])) if self.manifest else 0
            ),
            promoter_count=(
                len(self.manifest.get("promoters", [])) if self.manifest else 0
            ),
        )
        self._error_message = self._startup_error
        if self.catalog and self.manifest and self.store:
            try:
                self.catalog.register(
                    self.store.path,
                    self.manifest["campus_name"],
                    activate=True,
                )
            except CampusCatalogError as exc:
                self._error_message = str(exc)
        courses = self.manifest.get("courses", []) if self.manifest else []
        self._selected_course_id = courses[0]["id"] if courses else None
        self._initialized = True
        self._refresh_list_models()

    @Property(str, notify=dataChanged)
    def campusName(self):
        return (
            self.manifest.get("campus_name", "Sin archivo de sede")
            if self.manifest
            else "Sin archivo de sede"
        )

    @Property(bool, notify=dataChanged)
    def hasWorkspace(self):
        return self.manifest is not None

    @Property(bool, notify=dataChanged)
    def isNewCampus(self):
        return bool(self.manifest and self.manifest.get("campus_mode") == "new")

    @Property("QVariantList", notify=dataChanged)
    def campuses(self):
        if not self.catalog:
            return []
        return [dict(record) for record in self.catalog.records]

    @Slot(str, result=str)
    def suggestedDatabaseFileName(self, campus_name):
        safe_name = re.sub(
            r'[\s<>:"/\\|?*\x00-\x1f]+',
            "-",
            campus_name.strip(),
        ).strip(" .-_")
        return f"edutrack-{safe_name or 'sede'}.sqlite3"

    @Property(str, notify=dataChanged)
    def activeDatabasePath(self):
        return str(self.store.path) if self.store and self.manifest else ""

    @Property(int, notify=dataChanged)
    def activeCampusIndex(self):
        if not self.catalog or not self.store or not self.manifest:
            return -1
        active_path = str(self.store.path)
        return next(
            (
                index
                for index, record in enumerate(self.catalog.records)
                if record["path"] == active_path
            ),
            -1,
        )

    @Property("QVariantList", notify=dataChanged)
    def students(self):
        return self._all_student_rows()

    @Property(QObject, constant=True)
    def studentListModel(self):
        return self._student_list_model

    @Property(QObject, constant=True)
    def enrollmentListModel(self):
        return self._enrollment_list_model

    @Property(QObject, constant=True)
    def courseListModel(self):
        return self._course_list_model

    def _refresh_list_models(self) -> None:
        self._student_list_model.refreshIfLoaded()
        self._course_list_model.refreshIfLoaded()
        self._enrollment_list_model.refreshIfLoaded()

    def _all_student_rows(self) -> list[dict[str, Any]]:
        if self._student_rows_cache is None:
            self._student_rows_cache = student_rows(self.manifest)
        return self._student_rows_cache

    def _student_page_rows(
        self,
        query: str,
        status_filter_index: int,
        course_filter_id: int,
        page_index: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int, int] | None:
        if not self.manifest or self.store is None:
            return [], 0, 0
        try:
            return self._run_async(
                self.store.student_page(
                    query,
                    status_filter_index,
                    course_filter_id,
                    page_index,
                    page_size,
                )
            )
        except (
            OSError,
            RuntimeError,
            SQLAlchemyError,
            ValueError,
            KeyError,
            TypeError,
        ) as exc:
            logger.error(
                "workspace.student_page_failed",
                error_type=exc.__class__.__name__,
            )
            self._set_error(
                "No se pudo cargar la lista de estudiantes desde la base local."
            )
            return None

    def _course_page_rows(
        self,
        query: str,
        page_index: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int, int] | None:
        if not self.manifest or self.store is None:
            return [], 0, 0
        try:
            return self._run_async(
                self.store.course_page(query, page_index, page_size)
            )
        except (
            OSError,
            RuntimeError,
            SQLAlchemyError,
            ValueError,
            KeyError,
            TypeError,
        ) as exc:
            logger.error(
                "workspace.course_page_failed",
                error_type=exc.__class__.__name__,
            )
            self._set_error(
                "No se pudo cargar la lista de cursos desde la base local."
            )
            return None

    def _matching_student_rows(self, query: str) -> list[dict[str, Any]]:
        normalized_query = query.strip().casefold()
        if normalized_query != self._student_filter_cache_query:
            self._student_filter_cache_query = normalized_query
            self._student_filter_cache_rows = filter_student_rows(
                self._all_student_rows(),
                normalized_query,
            )
        return self._student_filter_cache_rows

    def _invalidate_student_rows(self) -> None:
        self._student_rows_cache = None
        self._student_filter_cache_query = None
        self._student_filter_cache_rows = []
        self._enrollment_rows_cache = None
        self._course_rows_cache = None
        self._dashboard_summary_cache = None

    @Slot(str, result=int)
    def matchingStudentCount(self, query):
        return len(self._matching_student_rows(query))

    @Slot(str, int, int, result="QVariantList")
    def studentPage(self, query, page, page_size):
        if page < 0 or page_size < 1 or page_size > 100:
            self._set_error("La página de estudiantes solicitada no es válida.")
            return []
        rows = self._matching_student_rows(query)
        start = page * page_size
        return rows[start : start + page_size]

    @Slot(str, result="QVariantList")
    @Slot(str, int, result="QVariantList")
    def searchStudents(self, query, limit=20):
        if not self.manifest or self.store is None:
            return []
        if isinstance(limit, bool) or limit < 1 or limit > 100:
            limit = 20
        try:
            return self._run_async(self.store.search_students(query, limit))
        except (
            OSError,
            RuntimeError,
            SQLAlchemyError,
            ValueError,
            KeyError,
            TypeError,
        ) as exc:
            logger.error(
                "workspace.student_search_failed",
                error_type=exc.__class__.__name__,
            )
            self._set_error("No se pudo buscar estudiantes en la base local.")
            return []

    @Property("QVariantList", notify=dataChanged)
    def enrollments(self):
        return self._all_enrollment_rows()

    def _all_enrollment_rows(self) -> list[dict[str, Any]]:
        if self._enrollment_rows_cache is None:
            self._enrollment_rows_cache = enrollment_rows(self.manifest)
        return self._enrollment_rows_cache

    @Property("QVariantList", notify=dataChanged)
    def courses(self):
        if self._course_rows_cache is None:
            self._course_rows_cache = course_rows(self.manifest)
        return self._course_rows_cache

    @Property("QVariantMap", notify=dataChanged)
    def dashboardSummary(self):
        if self._dashboard_summary_cache is None:
            self._dashboard_summary_cache = dashboard_summary(self.manifest)
        return self._dashboard_summary_cache

    @Slot(result=bool)
    def refreshDashboardSummary(self):
        if (
            self._dashboard_summary_cache is None
            or self._dashboard_summary_cache["summary_date"]
            == date.today().isoformat()
        ):
            return False
        self._dashboard_summary_cache = dashboard_summary(self.manifest)
        self.dataChanged.emit()
        return True

    @Property("QVariantList", notify=selectionChanged)
    def courseStudents(self):
        if not self.manifest or self._selected_course_id is None:
            return []
        return course_students(self.manifest, self._selected_course_id)

    @Property("QVariantList", notify=dataChanged)
    def studentOptions(self):
        return [{"id": "", "label": "Sin estudiante"}] + self.students

    @Property("QVariantList", notify=dataChanged)
    def courseOptions(self):
        if not self.manifest:
            return []
        return [{"id": "", "label": "Pendiente de curso"}] + [
            {
                "id": course["id"],
                "label": (
                    f"{course['name']} · {course['schedule']} · Grupo {course['group']}"
                    + ("" if course["active"] else " (inactivo)")
                ),
            }
            for course in self.courses
        ]

    @Property("QVariantList", notify=dataChanged)
    def promoterOptions(self):
        return self.manifest["promoters"] if self.manifest else []

    @Property(str, notify=selectionChanged)
    def enrollmentImageName(self):
        image_path = self.selectedEnrollment.get("record_image")
        return Path(image_path).name if image_path else "Sin imagen de ficha"

    @Property("QVariantMap", notify=selectionChanged)
    def selectedStudent(self):
        if not self.manifest:
            return {}
        return next(
            (
                item
                for item in self.manifest["students"]
                if item["id"] == self._selected_student_id
            ),
            {},
        )

    @Property("QVariantMap", notify=selectionChanged)
    def selectedEnrollment(self):
        if not self.manifest:
            return {}
        return next(
            (
                item
                for item in self.manifest["enrollments"]
                if item["id"] == self._selected_enrollment_id
            ),
            {},
        )

    @Property("QVariantMap", notify=selectionChanged)
    def selectedCourse(self):
        if not self.manifest:
            return {}
        return next(
            (
                item
                for item in self.manifest["courses"]
                if item["id"] == self._selected_course_id
            ),
            {},
        )

    @Property(str, notify=errorChanged)
    def errorMessage(self):
        return self._error_message

    @Property(bool, notify=courseSaveStateChanged)
    def courseSaveInProgress(self):
        return self._course_save_in_progress

    @Property(bool, notify=savingStateChanged)
    def isSaving(self):
        return self._save_in_progress

    @Property(bool, notify=activityStateChanged)
    def isBusy(self):
        return (
            self._save_in_progress
            or self._load_in_progress
            or self._sync_in_progress
        )

    @Property(str, notify=activityStateChanged)
    def activityMessage(self):
        return self._activity_message

    @Property(bool, notify=syncStateChanged)
    def syncInProgress(self):
        return self._sync_in_progress

    @Property("QVariantMap", notify=syncStateChanged)
    def pendingImportPreview(self):
        return self._pending_import_preview

    @Property("QVariantList", notify=syncStateChanged)
    def syncHistory(self):
        return self._sync_history_cache or []

    @Property("QVariantList", notify=backupStateChanged)
    def backupItems(self):
        return [dict(item) for item in self._backup_items]

    @Property(str, notify=backupDirectoryChanged)
    def backupDirectory(self):
        if self.store is None:
            return ""
        return str(self.store.path.parent / "backups")

    @Property("QVariantMap", notify=dataChanged)
    def syncWorkspaceInfo(self):
        manifest = self.manifest
        return {
            "campus_name": manifest.get("campus_name", "") if manifest else "",
            "workspace_id": (
                str(manifest.get("campus_id") or manifest.get("bundle_id", ""))
                if manifest
                else ""
            ),
            "students": len(manifest.get("students", [])) if manifest else 0,
            "enrollments": len(manifest.get("enrollments", [])) if manifest else 0,
            "courses": len(manifest.get("courses", [])) if manifest else 0,
            "promoters": len(manifest.get("promoters", [])) if manifest else 0,
        }

    @Property(str, notify=syncStateChanged)
    def lastSyncExportDate(self):
        return self._last_sync_date("export")

    @Property(str, notify=syncStateChanged)
    def lastSyncImportDate(self):
        return self._last_sync_date("import")

    def _last_sync_date(self, operation: str) -> str:
        return next(
            (
                item["created_at"]
                for item in self.syncHistory
                if item["operation"] == operation and item["status"] == "success"
            ),
            "",
        )

    @Slot(result=bool)
    def refreshSyncHistory(self):
        if self.store is None:
            self._sync_history_cache = []
            self.syncStateChanged.emit()
            return True
        try:
            self._sync_history_cache = self._run_async(
                self.store.list_sync_history()
            )
        except (
            OSError,
            RuntimeError,
            SQLAlchemyError,
            sqlite3.Error,
            ValueError,
            TypeError,
        ) as exc:
            logger.error(
                "workspace.sync_history_load_failed",
                error_type=exc.__class__.__name__,
            )
            self._set_error("No se pudo consultar el historial de sincronización.")
            return False
        self.syncStateChanged.emit()
        return True

    @staticmethod
    def _new_backup_path(store: WorkspaceStore, purpose: str) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        token = uuid.uuid4().hex[:8]
        return (
            store.path.parent
            / "backups"
            / f"{store.path.stem}-{purpose}-{timestamp}-{token}.sqlite3"
        )

    @Slot(result=bool)
    def refreshBackups(self):
        if self.store is None or self.manifest is None:
            self._set_error("Primero abre una sede local.")
            return False
        if self.isBusy:
            self._set_error("Espera a que termine la operación en curso.")
            return False

        store = self.store
        manifest = deepcopy(self.manifest)
        backup_directory = store.path.parent / "backups"

        def list_backups():
            if not backup_directory.exists():
                return []
            root = backup_directory.resolve()
            items = []
            for path in backup_directory.iterdir():
                if (
                    path.suffix.lower() != ".sqlite3"
                    or path.is_symlink()
                    or not path.is_file()
                    or path.resolve().parent != root
                ):
                    continue
                try:
                    file_stat = path.stat()
                    backup_info = verify_sqlite_backup(path)
                    compatible = self._same_campus(manifest, backup_info)
                    message = (
                        ""
                        if compatible
                        else "El respaldo pertenece a otra sede."
                    )
                    valid = True
                except (OSError, sqlite3.Error, ValueError) as exc:
                    file_stat = None
                    compatible = False
                    valid = False
                    message = str(exc) or "No se pudo verificar el respaldo."
                items.append(
                    {
                        "path": str(path),
                        "name": path.name,
                        "size_bytes": file_stat.st_size if file_stat else 0,
                        "modified_at": (
                            datetime.fromtimestamp(
                                file_stat.st_mtime, timezone.utc
                            ).isoformat(timespec="seconds")
                            if file_stat
                            else ""
                        ),
                        "valid": valid,
                        "compatible": compatible,
                        "message": message,
                    }
                )
            items.sort(key=lambda item: item["modified_at"], reverse=True)
            return items

        return self._start_sync_operation(
            "backup_list",
            list_backups,
            "Verificando respaldos disponibles…",
        )

    @Slot(result=bool)
    def createBackup(self):
        if self.store is None or self.manifest is None:
            self._set_error("Primero abre una sede local.")
            return False
        if self.isBusy:
            self._set_error("Espera a que termine la operación en curso.")
            return False

        store = self.store

        def create_backup():
            path = store.create_backup(self._new_backup_path(store, "manual"))
            info = verify_sqlite_backup(path)
            file_stat = path.stat()
            return {
                "path": str(path),
                "name": path.name,
                "size_bytes": file_stat.st_size,
                "modified_at": datetime.fromtimestamp(
                    file_stat.st_mtime, timezone.utc
                ).isoformat(timespec="seconds"),
                "campus_name": info["campus_name"],
            }

        return self._start_sync_operation(
            "backup_create",
            create_backup,
            "Creando y verificando respaldo…",
        )

    @Slot(str, result=bool)
    def restoreBackup(self, backup_path):
        if self.store is None or self.manifest is None:
            self._set_error("Primero abre una sede local.")
            return False
        if self.isBusy:
            self._set_error("Espera a que termine la operación en curso.")
            return False

        store = self.store
        local_path = store.path
        local_manifest = deepcopy(self.manifest)
        backup_directory = (local_path.parent / "backups").resolve()
        selected_path = Path(self._local_path(backup_path)).expanduser()
        if selected_path.is_symlink():
            self._set_error("Selecciona un respaldo de la sede activa.")
            return False
        selected_path = selected_path.resolve()
        if selected_path.parent != backup_directory:
            self._set_error("Selecciona un respaldo de la sede activa.")
            return False

        def restore_backup():
            backup_info = verify_sqlite_backup(selected_path)
            if not self._same_campus(local_manifest, backup_info):
                raise ValueError("El respaldo pertenece a otra sede.")

            staging_path = local_path.with_name(
                f".{local_path.name}.{uuid.uuid4().hex}.candidate.sqlite3"
            )
            candidate_store = None
            restored_store = None
            recovery_path = None
            destination_replaced = False
            try:
                create_sqlite_backup(selected_path, staging_path)
                candidate_store = self._store_factory(staging_path)
                candidate_manifest = asyncio.run(candidate_store.load())
                if candidate_manifest is None:
                    raise ValueError(
                        "El respaldo no contiene una sede recuperable."
                    )
                if not self._same_campus(local_manifest, candidate_manifest):
                    raise ValueError("El respaldo pertenece a otra sede.")
                asyncio.run(candidate_store.dispose())
                candidate_store = None

                recovery_path = self._new_backup_path(store, "pre-restore")
                store.create_backup(recovery_path)
                asyncio.run(store.dispose())
                restore_sqlite_backup(staging_path, local_path)
                destination_replaced = True

                restored_store = self._store_factory(local_path)
                restored_manifest = asyncio.run(restored_store.load())
                if restored_manifest is None or not self._same_campus(
                    local_manifest, restored_manifest
                ):
                    raise RuntimeError(
                        "La base restaurada no corresponde a la sede activa."
                    )
                return {
                    "store": restored_store,
                    "manifest": restored_manifest,
                    "recovery_backup": str(recovery_path),
                }
            except (
                OSError,
                RuntimeError,
                SQLAlchemyError,
                sqlite3.Error,
                ValueError,
                KeyError,
                TypeError,
            ) as exc:
                dispose_error = None
                if restored_store is not None:
                    try:
                        asyncio.run(restored_store.dispose())
                    except (
                        RuntimeError,
                        SQLAlchemyError,
                        sqlite3.Error,
                    ) as close_error:
                        dispose_error = close_error
                if destination_replaced and recovery_path is not None:
                    try:
                        restore_sqlite_backup(recovery_path, local_path)
                    except (OSError, sqlite3.Error, ValueError) as rollback_error:
                        logger.critical(
                            "workspace.backup_restore_rollback_failed",
                            error_type=rollback_error.__class__.__name__,
                        )
                        raise RuntimeError(
                            f"{exc} No se pudo revertir automáticamente; "
                            f"el respaldo de recuperación está en {recovery_path}."
                        ) from rollback_error
                if dispose_error is not None:
                    raise RuntimeError(
                        f"{exc} No se pudo cerrar completamente la base restaurada."
                    ) from dispose_error
                raise
            finally:
                if candidate_store is not None:
                    asyncio.run(candidate_store.dispose())
                staging_path.unlink(missing_ok=True)
                Path(f"{staging_path}-wal").unlink(missing_ok=True)
                Path(f"{staging_path}-shm").unlink(missing_ok=True)

        return self._start_sync_operation(
            "backup_restore",
            restore_backup,
            "Validando y restaurando respaldo…",
        )

    def _set_error(self, message):
        self._error_message = message
        self.errorChanged.emit()

    @staticmethod
    def _log_validation_failure(operation: str, error: ValueError) -> None:
        logger.warning(
            "validation.rejected",
            operation=operation,
            error_type=error.__class__.__name__,
        )

    @staticmethod
    def _sync_history_event(
        operation: str,
        bundle_id: str | None,
        status: str,
        affected_counts: dict[str, int] | None = None,
        message: str = "",
    ) -> dict[str, Any]:
        return {
            "operation": operation,
            "bundle_id": bundle_id,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "status": status,
            "affected_counts": affected_counts or {},
            "message": message[:500],
        }

    def _record_sync_history_event(self, event: dict[str, Any]) -> bool:
        if self.store is None:
            return False
        try:
            self._run_async(self.store.record_sync_history(event))
        except (
            OSError,
            RuntimeError,
            SQLAlchemyError,
            sqlite3.Error,
            ValueError,
            TypeError,
        ) as exc:
            logger.error(
                "workspace.sync_history_save_failed",
                operation=event["operation"],
                error_type=exc.__class__.__name__,
            )
            return False
        return self.refreshSyncHistory()

    def _start_sync_operation(
        self,
        operation_name: str,
        operation: Callable[[], object],
        activity_message: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        if self.isBusy:
            self._set_error("Ya hay otra operación en curso.")
            return False
        self._sync_in_progress = True
        self._activity_message = activity_message
        self._sync_operation_metadata = metadata or {}
        logger.info("desktop.operation_started", operation=operation_name)
        self.activityStateChanged.emit()
        self.syncStateChanged.emit()
        worker = _SyncOperationWorker(operation_name, operation)
        worker.signals.finished.connect(self._finish_sync_operation)
        self._sync_worker = worker
        self._save_pool.start(worker)
        return True

    @Slot(str, bool, object, str)
    def _finish_sync_operation(
        self,
        operation_name: str,
        succeeded: bool,
        result: object,
        error: str,
    ) -> None:
        metadata = self._sync_operation_metadata
        self._sync_operation_metadata = {}
        self._sync_worker = None
        self._sync_in_progress = False
        self._activity_message = ""
        self.activityStateChanged.emit()
        self.syncStateChanged.emit()

        if operation_name in ("backup_list", "backup_create", "backup_restore"):
            if not succeeded:
                message = f"No se pudo completar la operación de respaldo: {error}"
                self._set_error(message)
                self.backupStateChanged.emit()
                self.backupOperationFinished.emit(
                    operation_name, False, {}, message
                )
                return

            if operation_name == "backup_list":
                if not isinstance(result, list):
                    message = "La lista de respaldos recibida no es válida."
                    self._set_error(message)
                    self.backupOperationFinished.emit(
                        operation_name, False, {}, message
                    )
                    return
                self._backup_items = result
                self.backupStateChanged.emit()
                self.backupOperationFinished.emit(
                    operation_name, True, result, ""
                )
                return

            if operation_name == "backup_create":
                if not isinstance(result, dict):
                    message = "El resultado de creación del respaldo no es válido."
                    self._set_error(message)
                    self.backupOperationFinished.emit(
                        operation_name, False, {}, message
                    )
                    return
                self.backupOperationFinished.emit(
                    operation_name, True, result, ""
                )
                return

            if (
                not isinstance(result, dict)
                or not isinstance(result.get("manifest"), dict)
                or result.get("store") is None
            ):
                message = "El resultado de restauración no es válido."
                self._set_error(message)
                self.backupOperationFinished.emit(
                    operation_name, False, {}, message
                )
                return
            recovery_backup = result["recovery_backup"]
            self._finish_database_change(
                result["store"],
                result["manifest"],
                (
                    "Respaldo restaurado correctamente. "
                    f"Punto de recuperación: {recovery_backup}"
                ),
            )
            self.backupStateChanged.emit()
            self.backupOperationFinished.emit(
                operation_name,
                True,
                {"recovery_backup": recovery_backup},
                "",
            )
            return

        if not succeeded:
            operation = "import" if operation_name in ("preview", "import") else "export"
            event = metadata.get("history_event")
            if event is None and operation_name == "preview":
                event = self._sync_history_event(
                    "import",
                    None,
                    "failed",
                    message="No se pudo validar el paquete seleccionado.",
                )
            elif event is not None:
                event = {
                    **event,
                    "status": "failed",
                    "message": (
                        "No se pudo importar el paquete."
                        if operation == "import"
                        else "No se pudo exportar el paquete."
                    ),
                    "created_at": datetime.now(timezone.utc).isoformat(
                        timespec="seconds"
                    ),
                }
            if event is not None:
                self._record_sync_history_event(event)

            if operation_name == "preview":
                self._pending_import_manifest = None
                self._pending_import_snapshot = None
                self._pending_import_preview = {"error": error}
                self.syncPreviewFinished.emit(False, {}, error)
            elif operation_name == "import":
                self._pending_import_manifest = None
                self._pending_import_snapshot = None
                self._pending_import_preview = {}
                self._set_error(f"No se pudo importar el paquete: {error}")
                self.syncImportFinished.emit(False, {}, error)
            elif operation_name == "export":
                self._set_error(f"No se pudo exportar el paquete: {error}")
                self.syncExportFinished.emit(False, error)
            self.syncStateChanged.emit()
            return

        if operation_name == "preview":
            payload = result
            if not isinstance(payload, dict):
                message = "La vista previa del paquete no es válida."
                self._pending_import_manifest = None
                self._pending_import_snapshot = None
                self._pending_import_preview = {"error": message}
                self._set_error(message)
                self.syncStateChanged.emit()
                self.syncPreviewFinished.emit(False, {}, message)
                return
            self._pending_import_manifest = payload["manifest"]
            self._pending_import_snapshot = payload["local_snapshot"]
            self._pending_import_preview = payload["preview"]
            self.syncStateChanged.emit()
            self.syncPreviewFinished.emit(True, payload["preview"], "")
            return

        if operation_name == "import":
            payload = result
            if not isinstance(payload, dict) or self.store is None:
                self._set_error("El resultado de la importación no es válido.")
                self.syncImportFinished.emit(
                    False, {}, "El resultado de la importación no es válido."
                )
                return
            manifest = payload["manifest"]
            self._pending_import_manifest = None
            self._pending_import_snapshot = None
            self._pending_import_preview = {}
            self._finish_database_change(
                self.store,
                manifest,
                "Paquete importado correctamente tras guardar un respaldo local.",
            )
            self.refreshSyncHistory()
            result_data = {
                "backup_path": payload["backup_path"],
                "bundle_id": payload["bundle_id"],
                "affected_counts": payload["affected_counts"],
            }
            self.syncStateChanged.emit()
            self.syncImportFinished.emit(True, result_data, "")
            return

        if operation_name == "export":
            payload = result
            self.refreshSyncHistory()
            if isinstance(payload, dict) and payload.get("history_error"):
                message = (
                    "El paquete se creó, pero no se pudo guardar el historial "
                    "local de exportación."
                )
                self._set_error(message)
                self.syncExportFinished.emit(True, message)
                return
            message = "Paquete de sincronización generado correctamente."
            self._set_error(message)
            self.syncExportFinished.emit(True, message)

    def _dispose_store(self, store: WorkspaceStore):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(store.dispose())
            return

        task = loop.create_task(store.dispose())
        task.add_done_callback(lambda finished: self._finish_store_dispose(finished, store))

    def _run_async(
        self, operation: Coroutine[Any, Any, Any]
    ) -> Any:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(operation)

        task = loop.create_task(operation)
        nested_loop = QEventLoop(self)
        task.add_done_callback(lambda _: nested_loop.quit())
        nested_loop.exec()
        return task.result()

    @staticmethod
    def _finish_store_dispose(task, store: WorkspaceStore):
        try:
            task.result()
        except (OSError, RuntimeError, SQLAlchemyError, ValueError) as exc:
            logger.error(
                "workspace.dispose_failed",
                error_type=exc.__class__.__name__,
            )

    @staticmethod
    def _is_local_database(path):
        database_uri = f"{Path(path).resolve().as_uri()}?mode=ro"
        try:
            with sqlite3.connect(database_uri, uri=True) as connection:
                row = connection.execute(
                    "SELECT 1 FROM sqlite_master "
                    "WHERE type = 'table' AND name IN ('desktop_workspaces', 'workspace') "
                    "LIMIT 1"
                ).fetchone()
        except sqlite3.Error:
            return False
        return row is not None

    def _save(self, record_changes=None):
        if self.store is None or self.manifest is None:
            self._set_error("No hay una sede abierta para guardar los cambios.")
            return False
        succeeded, error = self._persist_manifest(
            self.store, self.manifest, record_changes
        )
        if not succeeded:
            self._set_error(
                f"No se pudieron guardar los cambios localmente: {error}"
            )
            return False
        self._invalidate_student_rows()
        self.dataChanged.emit()
        return True

    @staticmethod
    def _mutation_for_record(
        manifest: dict[str, Any], collection: str, record: dict[str, Any]
    ) -> RecordMutation:
        position = next(
            (
                index
                for index, item in enumerate(manifest[collection])
                if item is record
            ),
            None,
        )
        if position is None:
            raise RuntimeError(
                f"El registro modificado ya no existe en {collection}."
            )
        return RecordMutation(position, record)

    def _persist_manifest(
        self, store, manifest, record_changes=None, history_event=None
    ):
        if self.isBusy:
            return False, "Ya hay un guardado en curso."

        self._save_in_progress = True
        self._activity_message = "Guardando cambios en la base de datos..."
        self.savingStateChanged.emit()
        self.activityStateChanged.emit()
        try:
            if history_event is not None:
                operation = store.save_with_sync_history(
                    deepcopy(manifest), history_event
                )
            elif record_changes is None:
                operation = store.save(deepcopy(manifest))
            else:
                operation = store.save_records(manifest, record_changes)
            self._run_async(operation)
        except (
            OSError,
            RuntimeError,
            SQLAlchemyError,
            ValueError,
            KeyError,
            TypeError,
        ) as exc:
            logger.error(
                "workspace.save_failed",
                error_type=exc.__class__.__name__,
            )
            return False, str(exc) or exc.__class__.__name__
        finally:
            self._save_in_progress = False
            self._activity_message = ""
            self.savingStateChanged.emit()
            self.activityStateChanged.emit()
        return True, ""

    def _load_manifest(self, store):
        if self.isBusy:
            return False, None, "Ya hay otra operación en curso."

        self._load_in_progress = True
        self._activity_message = "Cargando los datos de la sede..."
        self.activityStateChanged.emit()
        try:
            return True, self._run_async(store.load()), ""
        except (
            OSError,
            RuntimeError,
            SQLAlchemyError,
            ValueError,
            KeyError,
            TypeError,
        ) as exc:
            logger.error(
                "workspace.load_failed",
                error_type=exc.__class__.__name__,
            )
            return False, None, str(exc) or exc.__class__.__name__
        finally:
            self._load_in_progress = False
            self._activity_message = ""
            self.activityStateChanged.emit()

    @Slot(str, str, result=bool)
    @Slot(str, str, str, result=bool)
    def createWorkspace(self, campus_name, campus_address, store_path=""):
        campus_name = campus_name.strip()
        campus_address = campus_address.strip()
        if not campus_name or len(campus_name) > 120 or len(campus_address) > 200:
            self._set_error(
                "Ingresa un nombre de sede válido y una dirección de hasta 200 caracteres."
            )
            return False
        if store_path:
            target_path = Path(self._local_path(store_path)).expanduser().resolve()
        elif self.store:
            target_path = self.store.path
        else:
            self._set_error("Elige dónde guardar la base de datos de la nueva sede.")
            return False
        if self.store and target_path == self.store.path and self.manifest:
            self._set_error(
                "Elige una ubicación nueva para la base de datos de esta sede."
            )
            return False
        if self.catalog and self.catalog.contains(target_path):
            self._set_error(
                "Esa base ya está registrada. Selecciónala en el catálogo de sedes."
            )
            return False
        if target_path.exists() and (
            self.store is None or target_path != self.store.path
        ):
            is_empty_placeholder = (
                target_path.is_file() and target_path.stat().st_size == 0
            )
            if not is_empty_placeholder:
                self._set_error(
                    "El archivo seleccionado ya existe. Elige una ubicación nueva."
                )
                return False

        manifest = {
            "format": PACKAGE_FORMAT,
            "version": INITIAL_CAMPUS_VERSION,
            "campus_mode": "new",
            "bundle_id": str(uuid.uuid4()),
            "campus_id": None,
            "campus_name": campus_name,
            "campus_address": campus_address,
            "students": [],
            "enrollments": [],
            "courses": [],
            "promoters": [
                {"id": 1, "server_id": None, "name": "PARTICULAR", "active": True},
                {"id": 2, "server_id": None, "name": "NN", "active": True},
            ],
        }
        target_store = (
            self.store
            if self.store is not None and target_path == self.store.path
            else None
        )
        try:
            if target_store is None:
                target_store = self._store_factory(target_path)
        except (OSError, RuntimeError, SQLAlchemyError, ValueError) as exc:
            if target_store is not None and target_store is not self.store:
                self._dispose_store(target_store)
            self._set_error(str(exc))
            return False
        succeeded, error = self._persist_manifest(target_store, manifest)
        if not succeeded:
            if target_store is not self.store:
                self._dispose_store(target_store)
            self._set_error(error)
            return False
        return self._finish_database_change(
            target_store,
            manifest,
            "Sede creada correctamente en este dispositivo.",
        )

    @Slot(str, str, result=bool)
    @Slot(str, str, bool, result=bool)
    def openPackage(self, package_path, store_path, replace_existing=False):
        try:
            manifest = read_package(self._local_path(package_path))
        except (PackageError, OSError, ValueError) as exc:
            logger.warning(
                "sync.package_import_rejected",
                error_type=exc.__class__.__name__,
            )
            self._set_error(str(exc))
            return False
        target_path = Path(self._local_path(store_path)).expanduser().resolve()
        is_registered = bool(self.catalog and self.catalog.contains(target_path))
        target_file_exists = target_path.is_file()
        is_empty_placeholder = target_file_exists and target_path.stat().st_size == 0
        target_exists = target_file_exists and not is_empty_placeholder
        if target_exists and not self._is_local_database(target_path):
            self._set_error(
                "El archivo seleccionado no es una base de datos de EduTrack Desktop."
            )
            return False
        empty_current_store = bool(
            self.store and target_path == self.store.path and self.manifest is None
        )
        if target_exists and not (
            (replace_existing and is_registered) or empty_current_store
        ):
            self._set_error(
                "El archivo seleccionado ya existe. Elige una ubicación nueva."
            )
            return False
        if target_path.exists() and not target_file_exists:
            self._set_error(
                "La ubicación seleccionada no es un archivo de base de datos."
            )
            return False
        target_store = (
            self.store
            if self.store is not None and target_path == self.store.path
            else None
        )
        try:
            if target_store is None:
                target_store = self._store_factory(target_path)
        except (OSError, RuntimeError, SQLAlchemyError, ValueError) as exc:
            if target_store is not None and target_store is not self.store:
                self._dispose_store(target_store)
            logger.error(
                "sync.package_import_failed",
                error_type=exc.__class__.__name__,
            )
            self._set_error(f"No se pudo guardar la sede importada: {exc}")
            return False
        existing_manifest = None
        if target_exists:
            loaded, existing_manifest, error = self._load_manifest(target_store)
            if not loaded:
                if target_store is not self.store:
                    self._dispose_store(target_store)
                logger.error("sync.package_import_failed", operation="load")
                self._set_error(f"No se pudo guardar la sede importada: {error}")
                return False
        if (
            target_exists
            and not empty_current_store
            and (
                existing_manifest is None
                or not self._same_campus(existing_manifest, manifest)
            )
        ):
            if target_store is not self.store:
                self._dispose_store(target_store)
            self._set_error(
                "El paquete no pertenece a la sede guardada en la base seleccionada."
            )
            return False

        bundle_id = str(manifest["bundle_id"])
        backup_path: Path | None = None
        if target_exists and not empty_current_store:
            try:
                if self._run_async(target_store.has_imported_bundle(bundle_id)):
                    if target_store is not self.store:
                        self._dispose_store(target_store)
                    self._set_error("Este paquete ya se importó en esta sede.")
                    return False
                backup_token = hashlib.sha256(bundle_id.encode("utf-8")).hexdigest()[:12]
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                backup_path = (
                    target_store.path.parent
                    / "backups"
                    / f"{target_store.path.stem}-{timestamp}-{backup_token}.sqlite3"
                )
                target_store.create_backup(backup_path)
                logger.info(
                    "backup.created",
                    backup_type="pre-import",
                    size_bytes=backup_path.stat().st_size,
                )
            except (
                OSError,
                RuntimeError,
                SQLAlchemyError,
                sqlite3.Error,
                ValueError,
            ) as exc:
                if target_store is not self.store:
                    self._dispose_store(target_store)
                logger.error(
                    "sync.package_import_failed",
                    operation="pre-import-backup",
                    error_type=exc.__class__.__name__,
                )
                self._set_error(f"No se pudo respaldar la sede antes de importar: {exc}")
                return False

        preview = (
            build_import_preview(existing_manifest, manifest)
            if existing_manifest is not None and not empty_current_store
            else {
                "new": sum(
                    len(manifest[collection])
                    for collection in ("students", "enrollments", "courses", "promoters")
                ),
                "updated": 0,
                "unchanged": 0,
                "conflicts": 0,
            }
        )
        history_event = self._sync_history_event(
            "import",
            bundle_id,
            "success",
            {
                key: preview[key]
                for key in ("new", "updated", "unchanged", "conflicts")
            },
            (
                "Paquete confirmado e importado en la sede existente."
                if target_exists and not empty_current_store
                else "Paquete importado en una base local."
            ),
        )
        succeeded, error = self._persist_manifest(
            target_store, manifest, history_event=history_event
        )
        if not succeeded:
            if target_store is not self.store:
                self._dispose_store(target_store)
            logger.error("sync.package_import_failed", operation="persist")
            self._set_error(f"No se pudo guardar la sede importada: {error}")
            return False
        message = (
            (
                "Datos sincronizados actualizados. Respaldo: "
                f"{backup_path}"
            )
            if backup_path is not None
            else "Sede importada correctamente en una base de datos independiente."
        )
        succeeded = self._finish_database_change(
            target_store,
            manifest,
            message,
        )
        if succeeded:
            logger.info(
                "sync.package_imported",
                student_count=len(manifest["students"]),
                enrollment_count=len(manifest["enrollments"]),
                course_count=len(manifest["courses"]),
                promoter_count=len(manifest["promoters"]),
                backup_created=backup_path is not None,
            )
            self.refreshSyncHistory()
        else:
            logger.error("sync.package_import_failed", operation="activate")
        return succeeded

    @staticmethod
    def _same_campus(existing, incoming):
        initial_bundle_id = incoming.get("desktop_bundle_id")
        if (
            initial_bundle_id is not None
            and existing.get("bundle_id") == initial_bundle_id
        ):
            return True
        existing_id = existing.get("campus_id")
        incoming_id = incoming.get("campus_id")
        if existing_id is not None and incoming_id is not None:
            return existing_id == incoming_id
        if existing_id is None and initial_bundle_id is not None:
            return existing.get("bundle_id") == initial_bundle_id
        existing_bundle = existing.get("bundle_id")
        incoming_bundle = incoming.get("bundle_id")
        return bool(existing_bundle and existing_bundle == incoming_bundle)

    @Slot(str, result=bool)
    def preparePackageImport(self, package_path):
        if self.store is None or self.manifest is None:
            self._set_error("Primero abre una sede local.")
            return False
        if self.isBusy:
            self._set_error("Espera a que termine la operación en curso.")
            return False

        local_snapshot = deepcopy(self.manifest)
        store = self.store
        local_path = self._local_path(package_path)
        self._pending_import_manifest = None
        self._pending_import_snapshot = None
        self._pending_import_preview = {}

        def prepare():
            incoming = read_package(local_path)
            if not self._same_campus(local_snapshot, incoming):
                raise PackageError(
                    "El paquete no pertenece a la sede local actualmente abierta."
                )
            bundle_id = str(incoming["bundle_id"])
            if asyncio.run(store.has_imported_bundle(bundle_id)):
                raise PackageError("Este paquete ya fue importado anteriormente.")
            preview = build_import_preview(local_snapshot, incoming)
            preview["bundle_id"] = bundle_id
            preview["campus_name"] = incoming["campus_name"]
            return {
                "manifest": incoming,
                "local_snapshot": local_snapshot,
                "preview": preview,
            }

        return self._start_sync_operation(
            "preview",
            prepare,
            "Validando paquete y preparando vista previa…",
        )

    @Slot(result=bool)
    def confirmPackageImport(self):
        if (
            self.store is None
            or self._pending_import_manifest is None
            or self._pending_import_snapshot is None
        ):
            self._set_error("Primero valida un paquete de sincronización.")
            return False
        if self.isBusy:
            self._set_error("Espera a que termine la operación en curso.")
            return False
        if not self._pending_import_preview.get("can_import", False):
            self._set_error(
                "Resuelve los conflictos indicados antes de importar el paquete."
            )
            return False

        incoming = deepcopy(self._pending_import_manifest)
        preview = deepcopy(self._pending_import_preview)
        snapshot = deepcopy(self._pending_import_snapshot)
        store = self.store
        bundle_id = str(incoming["bundle_id"])
        event = self._sync_history_event(
            "import",
            bundle_id,
            "success",
            {
                "new": int(preview["new"]),
                "updated": int(preview["updated"]),
                "unchanged": int(preview["unchanged"]),
            },
            "Paquete validado e importado.",
        )
        self._pending_import_manifest = None
        self._pending_import_snapshot = None
        self._pending_import_preview = {}

        def import_package():
            current = asyncio.run(store.load())
            if current is None or current != snapshot:
                raise ValueError(
                    "La sede cambió después de la vista previa. Valida el paquete otra vez."
                )
            if not self._same_campus(current, incoming):
                raise PackageError(
                    "El paquete ya no corresponde a la sede local abierta."
                )
            if asyncio.run(store.has_imported_bundle(bundle_id)):
                raise PackageError("Este paquete ya fue importado anteriormente.")
            current_preview = build_import_preview(current, incoming)
            if not current_preview["can_import"]:
                raise ValueError(
                    "La vista previa detectó conflictos que impiden importar."
                )

            backup_token = hashlib.sha256(bundle_id.encode("utf-8")).hexdigest()[:12]
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            backup_path = (
                store.path.parent
                / "backups"
                / f"{store.path.stem}-{timestamp}-{backup_token}.sqlite3"
            )
            store.create_backup(backup_path)
            asyncio.run(store.save_with_sync_history(incoming, event))
            return {
                "manifest": incoming,
                "backup_path": str(backup_path),
                "bundle_id": bundle_id,
                "affected_counts": event["affected_counts"],
            }

        return self._start_sync_operation(
            "import",
            import_package,
            "Creando respaldo e importando paquete…",
            {"history_event": event},
        )

    @Slot()
    def cancelPackageImport(self):
        if self._sync_in_progress:
            self._set_error("Espera a que termine la validación del paquete.")
            return
        self._pending_import_manifest = None
        self._pending_import_snapshot = None
        self._pending_import_preview = {}
        self.syncStateChanged.emit()

    @Slot(str, result=bool)
    def exportPackageAsync(self, path):
        if self.store is None or self.manifest is None:
            self._set_error(
                "Primero abre una sede o crea una nueva en este dispositivo."
            )
            return False
        if self.isBusy:
            self._set_error("Espera a que termine la operación en curso.")
            return False

        output = deepcopy(self.manifest)
        if not self.isNewCampus:
            output["bundle_id"] = str(uuid.uuid4())
        bundle_id = str(output["bundle_id"])
        event = self._sync_history_event(
            "export",
            bundle_id,
            "success",
            {
                "students": len(output["students"]),
                "enrollments": len(output["enrollments"]),
                "courses": len(output["courses"]),
                "promoters": len(output["promoters"]),
            },
            "Paquete de sincronización exportado.",
        )
        local_path = self._local_path(path)
        store = self.store

        def export_package():
            write_package(local_path, output)
            try:
                asyncio.run(store.record_sync_history(event))
            except (
                OSError,
                RuntimeError,
                SQLAlchemyError,
                sqlite3.Error,
                ValueError,
                TypeError,
            ):
                return {"history_error": True}
            return {"history_error": False, "bundle_id": bundle_id}

        return self._start_sync_operation(
            "export",
            export_package,
            "Generando paquete de sincronización…",
            {"history_event": event},
        )

    @Slot(str, result=bool)
    def isRegisteredDatabase(self, path):
        return bool(
            self.catalog
            and self.catalog.contains(
                Path(self._local_path(path)).expanduser().resolve()
            )
        )

    @Slot(str, result=bool)
    def removeCampusFromList(self, path):
        if self.catalog is None:
            self._set_error("No hay un catálogo local de sedes.")
            return False
        try:
            target_path = Path(self._local_path(path)).expanduser().resolve()
            if (
                self.store is not None
                and self.manifest is not None
                and target_path == self.store.path
            ):
                self._set_error(
                    "Cierra la sede activa antes de quitarla de la lista."
                )
                return False
            if not self.catalog.remove(target_path):
                self._set_error("La sede ya no está guardada en la lista.")
                return False
        except (
            CampusCatalogError,
            OSError,
            RuntimeError,
            ValueError,
        ) as exc:
            self._set_error(f"No se pudo quitar la sede de la lista: {exc}")
            return False

        self.dataChanged.emit()
        logger.info("campus.removed_from_list")
        self._set_error(
            "Sede quitada de la lista. Su base y sus datos locales se conservaron."
        )
        return True

    @Slot(str, result=bool)
    def switchCampus(self, path):
        target_path = Path(self._local_path(path)).expanduser().resolve()
        if self.catalog is None or not self.catalog.contains(target_path):
            self._set_error(
                "La sede seleccionada no está registrada en el catálogo local."
            )
            return False
        if self.store is not None and target_path == self.store.path:
            self._set_error("")
            return True
        if not target_path.is_file():
            self._set_error(
                f"No se encontró la base de datos de la sede: {target_path}"
            )
            return False
        if not self._is_local_database(target_path):
            self._set_error(
                "El archivo registrado no contiene una base de datos de EduTrack Desktop."
            )
            return False
        target_store = None
        try:
            target_store = self._store_factory(target_path)
        except (OSError, RuntimeError, SQLAlchemyError, ValueError) as exc:
            self._set_error(f"No se pudo abrir la sede seleccionada: {exc}")
            return False
        loaded, manifest, error = self._load_manifest(target_store)
        if not loaded:
            self._dispose_store(target_store)
            self._set_error(f"No se pudo abrir la sede seleccionada: {error}")
            return False
        if manifest is None:
            self._dispose_store(target_store)
            self._set_error(
                "La base seleccionada no contiene una sede de EduTrack."
            )
            return False
        try:
            self.catalog.activate(target_path)
        except (
            CampusCatalogError,
            OSError,
            RuntimeError,
            SQLAlchemyError,
            ValueError,
        ) as exc:
            self._dispose_store(target_store)
            self._set_error(f"No se pudo abrir la sede seleccionada: {exc}")
            return False
        return self._finish_database_change(
            target_store,
            manifest,
            f"Sede {manifest['campus_name']} abierta.",
            register=False,
        )

    @Slot(str, result=bool)
    def openLocalDatabase(self, path):
        target_path = Path(self._local_path(path)).expanduser().resolve()
        if not target_path.is_file():
            self._set_error("Selecciona un archivo de base de datos existente.")
            return False
        if not self._is_local_database(target_path):
            self._set_error(
                "El archivo seleccionado no es una base de datos de EduTrack Desktop."
            )
            return False
        if self.store is not None and target_path == self.store.path:
            self._set_error("")
            return True
        target_store = None
        try:
            target_store = self._store_factory(target_path)
        except (CampusCatalogError, OSError, RuntimeError, SQLAlchemyError, ValueError) as exc:
            self._set_error(f"No se pudo abrir la base seleccionada: {exc}")
            return False
        loaded, manifest, error = self._load_manifest(target_store)
        if not loaded:
            self._dispose_store(target_store)
            self._set_error(f"No se pudo abrir la base seleccionada: {error}")
            return False
        if manifest is None:
            self._dispose_store(target_store)
            self._set_error(
                "La base seleccionada no contiene una sede de EduTrack."
            )
            return False
        try:
            if self.catalog:
                self.catalog.register(
                    target_path,
                    manifest["campus_name"],
                    activate=True,
                )
        except (
            CampusCatalogError,
            OSError,
            RuntimeError,
            SQLAlchemyError,
            ValueError,
        ) as exc:
            self._dispose_store(target_store)
            self._set_error(f"No se pudo abrir la base seleccionada: {exc}")
            return False
        return self._finish_database_change(
            target_store,
            manifest,
            f"Sede {manifest['campus_name']} abierta.",
            register=False,
        )

    @Slot(result=bool)
    def refreshWorkspace(self):
        if self.store is None or self.manifest is None:
            self._set_error("No hay una sede abierta para actualizar.")
            return False
        loaded, manifest, error = self._load_manifest(self.store)
        if not loaded or manifest is None:
            self._set_error(
                f"No se pudieron actualizar los datos locales: "
                f"{error or 'la base no contiene una sede válida.'}"
            )
            return False

        self.manifest = manifest
        student_ids = {student["id"] for student in manifest["students"]}
        enrollment_ids = {
            enrollment["id"] for enrollment in manifest["enrollments"]
        }
        course_ids = {course["id"] for course in manifest["courses"]}
        if self._selected_student_id not in student_ids:
            self._selected_student_id = ""
        if self._selected_enrollment_id not in enrollment_ids:
            self._selected_enrollment_id = ""
        if self._selected_course_id not in course_ids:
            courses = manifest["courses"]
            self._selected_course_id = courses[0]["id"] if courses else None
        self._invalidate_student_rows()
        self.dataChanged.emit()
        self.selectionChanged.emit()
        self._set_error("Datos actualizados desde la base local.")
        return True

    @Slot(result=bool)
    def closeCampus(self):
        if self.store is None or self.manifest is None:
            self._set_error("No hay una sede abierta para cerrar.")
            return False
        if self.catalog:
            try:
                self.catalog.deactivate()
            except CampusCatalogError as exc:
                self._set_error(f"No se pudo cerrar la sede: {exc}")
                return False
        previous_store = self.store
        self.store = None
        self.manifest = None
        self._invalidate_student_rows()
        self._selected_student_id = ""
        self._selected_enrollment_id = ""
        self._selected_course_id = None
        self._dispose_store(previous_store)
        self.dataChanged.emit()
        self.selectionChanged.emit()
        self._backup_items = []
        self.backupDirectoryChanged.emit()
        self.backupStateChanged.emit()
        self._set_error(
            "Sede cerrada. Su base de datos se conservó y puedes volver a abrirla."
        )
        return True

    def _finish_database_change(self, store, manifest, message, register=True):
        catalog_error = ""
        if self.catalog and register:
            try:
                self.catalog.register(
                    store.path,
                    manifest["campus_name"],
                    activate=True,
                )
            except CampusCatalogError as exc:
                catalog_error = str(exc)
        previous_store = self.store
        self.store = store
        self.manifest = manifest
        self._invalidate_student_rows()
        self._selected_student_id = ""
        self._selected_enrollment_id = ""
        courses = manifest.get("courses", [])
        self._selected_course_id = courses[0]["id"] if courses else None
        if previous_store is not None and previous_store is not store:
            self._dispose_store(previous_store)
        self.dataChanged.emit()
        self.selectionChanged.emit()
        if previous_store is None or previous_store.path != store.path:
            self._backup_items = []
            self.backupDirectoryChanged.emit()
            self.backupStateChanged.emit()
        self._set_error(f"{message} {catalog_error}" if catalog_error else message)
        return True

    @Slot(str)
    def exportPackage(self, path):
        if not self.manifest:
            self._set_error(
                "Primero abre una sede o crea una nueva en este dispositivo."
            )
            return
        try:
            output = dict(self.manifest)
            if not self.isNewCampus:
                output["bundle_id"] = str(uuid.uuid4())
            write_package(self._local_path(path), output)
            message = (
                "Paquete inicial de sede generado correctamente."
                if self.isNewCampus
                else "Archivo de sincronización generado correctamente."
            )
            history_event = self._sync_history_event(
                "export",
                str(output["bundle_id"]),
                "success",
                {
                    "students": len(output["students"]),
                    "enrollments": len(output["enrollments"]),
                    "courses": len(output["courses"]),
                    "promoters": len(output["promoters"]),
                },
                "Paquete de sincronización exportado.",
            )
            history_saved = self._record_sync_history_event(history_event)
            logger.info(
                "sync.package_exported",
                history_saved=history_saved,
                student_count=len(output["students"]),
                enrollment_count=len(output["enrollments"]),
                course_count=len(output["courses"]),
                promoter_count=len(output["promoters"]),
            )
            if not history_saved:
                message += " No se pudo guardar el historial local."
            self._set_error(message)
        except (PackageError, OSError, ValueError) as exc:
            logger.error(
                "sync.package_export_failed",
                error_type=exc.__class__.__name__,
            )
            self._set_error(str(exc))

    @Slot(str, result=bool)
    def exportRegister(self, path):
        if not self.manifest:
            self._set_error(
                "Primero abre una sede o crea una nueva en este dispositivo."
            )
            return False
        output_path = Path(self._local_path(path))
        try:
            export_register(self.manifest, output_path)
        except (OSError, TypeError, ValueError) as exc:
            logger.error(
                "workspace.register_export_failed",
                error_type=exc.__class__.__name__,
            )
            self._set_error(f"No se pudo exportar el registro: {exc}")
            return False
        self._set_error(
            f"Registro exportado correctamente: {output_path.name}"
        )
        return True

    @Slot(str, str, str, str, str, str, str, result=int)
    def createCourse(
        self,
        name,
        schedule,
        group_name,
        start_date,
        enrollment_fee,
        monthly_fee,
        capacity,
    ):
        if not self.manifest:
            self._set_error(
                "Primero abre una sede o crea una nueva en este dispositivo."
            )
            return 0
        try:
            mutation = self._record_service.create_course(
                self.manifest,
                name,
                schedule,
                group_name,
                start_date,
                enrollment_fee,
                monthly_fee,
                capacity,
            )
            course_id = int(mutation.record["id"])
        except ValueError as exc:
            self._log_validation_failure("course.create", exc)
            self._set_error(str(exc) or "Revisa los datos del curso.")
            return 0
        self._selected_course_id = course_id
        if not self._save({"courses": [mutation]}):
            return 0
        self.selectionChanged.emit()
        self._set_error("Curso guardado localmente.")
        return course_id

    @Slot(int, str, str, str, str, str, str, str, bool, result=bool)
    def saveCourse(
        self,
        source_id,
        name,
        schedule,
        group_name,
        start_date,
        enrollment_fee,
        monthly_fee,
        capacity,
        active,
    ):
        if self.store is None or not self.manifest:
            self._set_error("Primero abre una sede o crea una nueva en este dispositivo.")
            return False
        try:
            mutation = self._record_service.update_course(
                self.manifest,
                source_id,
                name,
                schedule,
                group_name,
                start_date,
                enrollment_fee,
                monthly_fee,
                capacity,
                active,
            )
        except ValueError as exc:
            self._log_validation_failure("course.update", exc)
            self._set_error(str(exc) or "Revisa los datos del curso.")
            return False
        self._selected_course_id = source_id
        if not self._save({"courses": [mutation]}):
            return False
        self.selectionChanged.emit()
        self._set_error("Curso actualizado correctamente en este dispositivo.")
        return True

    @Slot(int, str, str, str, str, str, str, str, bool, result=bool)
    def saveCourseAsync(
        self,
        source_id,
        name,
        schedule,
        group_name,
        start_date,
        enrollment_fee,
        monthly_fee,
        capacity,
        active,
    ):
        if self.isBusy:
            self._set_error("Ya hay un guardado en curso.")
            return False
        if self.store is None or not self.manifest:
            self._set_error("Primero abre una sede o crea una nueva en este dispositivo.")
            return False

        updated_manifest = deepcopy(self.manifest)
        try:
            mutation = self._record_service.update_course(
                updated_manifest,
                source_id,
                name,
                schedule,
                group_name,
                start_date,
                enrollment_fee,
                monthly_fee,
                capacity,
                active,
            )
        except ValueError as exc:
            self._log_validation_failure("course.update", exc)
            self._set_error(str(exc) or "Revisa los datos del curso.")
            return False

        self._pending_course_save_id = source_id
        self._course_save_in_progress = True
        self._save_in_progress = True
        self._activity_message = "Guardando cambios en la base de datos..."
        self.courseSaveStateChanged.emit()
        self.savingStateChanged.emit()
        self.activityStateChanged.emit()
        changes = {"courses": [mutation]}
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            worker = _WorkspaceSaveWorker(
                self.store, updated_manifest, record_changes=changes
            )
            worker.signals.finished.connect(self._finish_course_save)
            self._course_save_worker = worker
            self._save_pool.start(worker)
        else:
            self._course_save_task = loop.create_task(
                self._save_course_manifest(
                    self.store, updated_manifest, changes
                )
            )
        return True

    async def _save_course_manifest(
        self,
        store: WorkspaceStore,
        manifest: dict[str, Any],
        record_changes: dict[str, list[RecordMutation]],
    ):
        try:
            await store.save_records(manifest, record_changes)
        except (
            OSError,
            RuntimeError,
            SQLAlchemyError,
            ValueError,
            KeyError,
            TypeError,
        ) as exc:
            logger.error(
                "workspace.save_failed",
                error_type=exc.__class__.__name__,
            )
            self._finish_course_save(
                False, None, str(exc) or exc.__class__.__name__
            )
            return
        self._finish_course_save(True, manifest, "")

    @Slot(bool, object, str)
    def _finish_course_save(self, succeeded, manifest, message):
        self._course_save_worker = None
        self._course_save_task = None
        self._course_save_in_progress = False
        self._save_in_progress = False
        self._activity_message = ""
        self.courseSaveStateChanged.emit()
        self.savingStateChanged.emit()
        self.activityStateChanged.emit()
        course_id = self._pending_course_save_id
        self._pending_course_save_id = None
        if succeeded and manifest is not None and course_id is not None:
            self.manifest = manifest
            self._selected_course_id = course_id
            self._invalidate_student_rows()
            self.dataChanged.emit()
            self.selectionChanged.emit()
            self._backup_items = []
            self.backupDirectoryChanged.emit()
            self.backupStateChanged.emit()
            self._set_error("Curso actualizado correctamente en este dispositivo.")
        else:
            self._set_error(
                message or "No se pudieron guardar los cambios localmente."
            )
        self.courseSaveFinished.emit(
            succeeded and manifest is not None and course_id is not None
        )

    @Slot(str, result=int)
    def createPromoter(self, name):
        try:
            if not self.manifest:
                raise ValueError(
                    "Los promotores se crean desde Desktop al preparar una sede nueva."
                )
            mutation = self._record_service.create_promoter(
                self.manifest, name
            )
            promoter_id = int(mutation.record["id"])
        except ValueError as exc:
            self._log_validation_failure("promoter.create", exc)
            self._set_error(str(exc))
            return 0
        if not self._save({"promoters": [mutation]}):
            return 0
        self._set_error("Promotor guardado localmente.")
        return promoter_id

    @Slot(str)
    def selectStudent(self, source_id):
        self._selected_student_id = source_id
        self.selectionChanged.emit()

    @Slot()
    def newStudent(self):
        self._selected_student_id = ""
        self.selectionChanged.emit()

    @Slot(str)
    def selectEnrollment(self, source_id):
        self._selected_enrollment_id = source_id
        self.selectionChanged.emit()

    @Slot(int)
    def selectCourse(self, source_id):
        self._selected_course_id = source_id
        self.selectionChanged.emit()

    @Slot()
    def newEnrollment(self):
        self._selected_enrollment_id = ""
        self.selectionChanged.emit()

    @Slot(str)
    def attachEnrollmentImage(self, path):
        row = self.selectedEnrollment
        if not self.manifest or not row:
            self._set_error("Guarda primero la matrícula para adjuntar una imagen.")
            return
        if not row.get("record_code"):
            self._set_error(
                "Ingresa y guarda el código de ficha antes de adjuntar una imagen."
            )
            return
        try:
            image_path = Path(self._local_path(path))
            if image_path.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
                raise ValueError("Selecciona una imagen JPG, PNG o WEBP.")
            content = image_path.read_bytes()
            if not content or len(content) > 10 * 1024 * 1024:
                raise ValueError("La imagen está vacía o supera el máximo de 10 MB.")
        except (OSError, ValueError) as exc:
            if isinstance(exc, ValueError):
                self._log_validation_failure("enrollment.image_attach", exc)
            else:
                logger.error(
                    "enrollment.image_attach_failed",
                    error_type=exc.__class__.__name__,
                )
            self._set_error(str(exc))
            return
        image_hash = hashlib.sha256(content).hexdigest()
        package_path = f"attachments/{image_hash}.jpg"
        self.manifest.setdefault("_attachment_data", {})[package_path] = (
            base64.b64encode(content).decode("ascii")
        )
        row["record_image"] = package_path
        row["record_image_hash"] = image_hash
        mutation = self._mutation_for_record(
            self.manifest, "enrollments", row
        )
        if not self._save(
            {"enrollments": [mutation]}
        ):
            return
        self.selectionChanged.emit()
        self._set_error("Imagen de ficha guardada localmente.")

    @Slot()
    def clearEnrollmentImage(self):
        row = (
            next(
                (
                    item
                    for item in self.manifest["enrollments"]
                    if item["id"] == self._selected_enrollment_id
                ),
                None,
            )
            if self.manifest
            else None
        )
        if not self.manifest or not row or not row.get("record_image"):
            self._set_error("La matrícula seleccionada no tiene imagen de ficha.")
            return
        row["record_image"] = None
        row["record_image_hash"] = ""
        self._record_service.remove_unused_attachments(self.manifest)
        mutation = self._mutation_for_record(
            self.manifest, "enrollments", row
        )
        if not self._save(
            {"enrollments": [mutation]}
        ):
            return
        self.selectionChanged.emit()
        self._set_error("Se quitará la imagen al sincronizar con la web.")

    @Slot(str, str, str, str, str, result=bool)
    def saveStudent(
        self, source_id, last_name, first_name, document_number, phone_text
    ):
        if not self.manifest:
            self._set_error("Primero abre el archivo de una sede.")
            return False
        try:
            mutation = self._record_service.save_student(
                self.manifest,
                source_id,
                last_name,
                first_name,
                document_number,
                phone_text,
            )
            student_id = str(mutation.record["id"])
        except ValueError as exc:
            self._log_validation_failure("student.save", exc)
            self._set_error(str(exc))
            return False
        self._selected_student_id = student_id
        if not self._save({"students": [mutation]}):
            return False
        self.selectionChanged.emit()
        self._set_error("Estudiante guardado en este dispositivo.")
        return True

    @Slot(str, bool, result=bool)
    def setStudentActive(self, source_id, active):
        if not self.manifest:
            self._set_error("Primero abre el archivo de una sede.")
            return False
        try:
            mutation = self._record_service.set_student_active(
                self.manifest,
                source_id,
                active,
            )
        except ValueError as exc:
            self._log_validation_failure("student.set_active", exc)
            self._set_error(str(exc))
            return False
        if not self._save({"students": [mutation]}):
            return False
        state = "activado" if active else "desactivado"
        self._set_error(f"Estudiante {state} correctamente en este dispositivo.")
        return True

    @Slot("QVariantMap", "QVariantMap", result="QVariantMap")
    def createEnrollment(self, student_fields, enrollment_fields):
        failure = {"ok": False}
        if self.store is None or not self.manifest:
            self._set_error("Primero abre el archivo de una sede.")
            return failure
        try:
            result = self._create_enrollment_use_case.execute(
                self.manifest,
                student_fields,
                enrollment_fields,
            )
        except ValueError as exc:
            self._log_validation_failure("enrollment.create", exc)
            self._set_error(str(exc) or "Revisa los datos de la matrícula.")
            return failure
        succeeded, error = self._persist_manifest(
            self.store,
            result.manifest,
            {
                "students": (
                    [result.student_change]
                    if result.student_change is not None
                    else []
                ),
                "enrollments": [result.enrollment_change],
            },
        )
        if not succeeded:
            self._set_error(
                f"No se pudieron guardar los cambios localmente: {error}"
            )
            return failure
        self.manifest = result.manifest
        self._selected_student_id = result.student_id
        self._selected_enrollment_id = result.enrollment_id
        self._invalidate_student_rows()
        self.dataChanged.emit()
        self.selectionChanged.emit()
        self._set_error("Matrícula guardada en este dispositivo.")
        return {
            "ok": True,
            "student_id": result.student_id,
            "enrollment_id": result.enrollment_id,
            "student_created": result.student_created,
        }

    @Slot(str, "QVariantMap", result=bool)
    def saveEnrollment(self, source_id, fields):
        if not self.manifest:
            self._set_error("Primero abre el archivo de una sede.")
            return False
        if not isinstance(fields, dict):
            self._set_error("Los datos de la matrícula no tienen un formato válido.")
            return False
        try:
            mutation = self._record_service.save_enrollment(
                self.manifest,
                source_id,
                fields,
            )
            enrollment_id = str(mutation.record["id"])
        except ValueError as exc:
            self._log_validation_failure("enrollment.save", exc)
            self._set_error(str(exc) or "Revisa los datos de la matrícula.")
            return False
        self._selected_enrollment_id = enrollment_id
        if not self._save({"enrollments": [mutation]}):
            return False
        self.selectionChanged.emit()
        self._set_error("Matrícula guardada en este dispositivo.")
        return True

    @staticmethod
    def _local_path(value):
        url = QUrl(value)
        return url.toLocalFile() if url.isLocalFile() else value
