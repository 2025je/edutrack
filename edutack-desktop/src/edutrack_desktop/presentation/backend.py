import asyncio
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
    QTimer,
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
from ..application.presenters import dashboard_summary
from ..application.sync import build_import_preview
from ..domain.record_service import RecordService
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
from .async_query import AsyncQueryWorker, run_async_operation
from .list_models import CourseListModel, EnrollmentListModel, StudentListModel

logger = structlog.get_logger(__name__)


def _create_local_store(path: Path) -> WorkspaceStore:
    return LocalStore(path)


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
            if self._operation_name.startswith("backup_"):
                event = "backup.operation_failed"
            elif self._operation_name == "register_export":
                event = "workspace.register_export_failed"
            else:
                event = "sync.operation_failed"
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
    workspaceInfoChanged = Signal()
    dashboardSummaryChanged = Signal()
    selectionChanged = Signal()
    errorChanged = Signal()
    syncStateChanged = Signal()
    syncPreviewFinished = Signal(bool, object, str)
    syncImportFinished = Signal(bool, object, str)
    syncExportFinished = Signal(bool, str)
    registerExportFinished = Signal(bool, str)
    studentSearchFinished = Signal(int, list, str)
    courseSearchFinished = Signal(int, list, str)
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
        self._query_pool = QThreadPool(self)
        self._query_pool.setMaxThreadCount(3)
        self._student_search_request_id = 0
        self._student_search_workers: dict[int, AsyncQueryWorker] = {}
        self._course_search_request_id = 0
        self._course_search_workers: dict[int, AsyncQueryWorker] = {}
        self._save_in_progress = False
        self._course_save_worker: AsyncQueryWorker | None = None
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
        self._create_enrollment_use_case = CreateEnrollmentUseCase(self._record_service)
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
        self._workspace_info: dict[str, Any] | None = None
        self._course_students_cache: list[dict[str, Any]] = []
        self._course_students_request_id = 0
        self._course_students_workers: dict[int, AsyncQueryWorker] = {}
        self._dashboard_summary_cache = dashboard_summary(None)
        self._dashboard_summary_requested = False
        self._dashboard_summary_dirty = False
        self._dashboard_summary_request_id = 0
        self._dashboard_summary_workers: dict[int, AsyncQueryWorker] = {}
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
        self._selected_student_record: dict[str, Any] | None = None
        self._selected_enrollment_id = ""
        self._selected_enrollment_record: dict[str, Any] | None = None
        self._selected_course_id: int | None = None
        self._student_list_model = StudentListModel(
            self._student_page_rows,
            parent=self,
            query_pool=self._query_pool,
        )
        self._course_list_model = CourseListModel(
            self._course_page_rows,
            parent=self,
            query_pool=self._query_pool,
        )
        self._enrollment_list_model = EnrollmentListModel(
            self._enrollment_page_rows,
            parent=self,
            query_pool=self._query_pool,
        )
        self._student_list_model.queryFailed.connect(self._on_student_page_failed)
        self._course_list_model.queryFailed.connect(self._on_course_page_failed)
        self._enrollment_list_model.queryFailed.connect(self._on_enrollment_page_failed)
        self._workspace_info_request_id = 0
        self._workspace_info_workers: dict[int, AsyncQueryWorker] = {}
        self.dataChanged.connect(self._on_data_changed)
        if not defer_initialize:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                run_async_operation(self.initialize())

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

        self._workspace_info = await self.store.workspace_info()
        logger.info(
            "database.opened",
            workspace_loaded=self._workspace_info is not None,
            student_count=(self._workspace_info or {}).get("students", 0),
            enrollment_count=(self._workspace_info or {}).get("enrollments", 0),
            course_count=(self._workspace_info or {}).get("courses", 0),
            promoter_count=(self._workspace_info or {}).get("promoters", 0),
        )
        self._error_message = self._startup_error
        if self.catalog and self._workspace_info and self.store:
            try:
                self.catalog.register(
                    self.store.path,
                    self._workspace_info["campus_name"],
                    activate=True,
                )
            except CampusCatalogError as exc:
                self._error_message = str(exc)
        self._selected_course_id = (
            self._workspace_info["first_course_id"]
            if self._workspace_info
            else None
        )
        self._initialized = True
        self._refresh_list_models()
        self.workspaceInfoChanged.emit()

    @Property(str, notify=workspaceInfoChanged)
    def campusName(self):
        return (
            self._workspace_info.get("campus_name", "Sin archivo de sede")
            if self._workspace_info
            else "Sin archivo de sede"
        )

    @Property(bool, notify=workspaceInfoChanged)
    def hasWorkspace(self):
        return self._workspace_info is not None

    @Property(bool, notify=workspaceInfoChanged)
    def isNewCampus(self):
        return bool(
            self._workspace_info
            and self._workspace_info.get("campus_mode") == "new"
        )

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

    @Property(str, notify=workspaceInfoChanged)
    def activeDatabasePath(self):
        return str(self.store.path) if self.store and self._workspace_info else ""

    @Property(int, notify=workspaceInfoChanged)
    def activeCampusIndex(self):
        if not self.catalog or not self.store or not self._workspace_info:
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

    def _on_data_changed(self) -> None:
        self._refresh_list_models()
        if self.store is not None:
            self._request_workspace_info()
        else:
            self._workspace_info_request_id += 1
            self._workspace_info = None
            self.workspaceInfoChanged.emit()
        if self._selected_course_id is not None:
            self._request_course_students()
        if self.store is None:
            self._dashboard_summary_request_id += 1
            self._dashboard_summary_requested = False
            self._dashboard_summary_dirty = False
            self._dashboard_summary_cache = dashboard_summary(None)
            self.dashboardSummaryChanged.emit()
            return
        if self._dashboard_summary_requested:
            self._dashboard_summary_dirty = True
            self._request_dashboard_summary()

    def _request_workspace_info(self) -> bool:
        store = self.store
        if store is None:
            return False
        self._workspace_info_request_id += 1
        request_id = self._workspace_info_request_id
        try:
            operation = store.workspace_info()
        except (
            OSError,
            RuntimeError,
            SQLAlchemyError,
            ValueError,
            TypeError,
            KeyError,
        ) as exc:
            self._finish_workspace_info(
                request_id,
                None,
                type(exc).__name__,
                str(exc),
            )
            return False
        worker = AsyncQueryWorker(request_id, operation)
        worker.signals.finished.connect(self._finish_workspace_info)
        self._workspace_info_workers[request_id] = worker
        self._query_pool.start(worker)
        return True

    @Slot(int, object, str, str)
    def _finish_workspace_info(
        self,
        request_id: int,
        info: object,
        error_type: str,
        error_message: str,
    ) -> None:
        self._workspace_info_workers.pop(request_id, None)
        if request_id != self._workspace_info_request_id:
            return
        if error_type:
            logger.error(
                "workspace.metadata_load_failed",
                error_type=error_type,
                error=error_message,
            )
            self._set_error("No se pudieron actualizar los datos de la sede.")
            return
        if info is not None and (
            not isinstance(info, dict)
            or not isinstance(info.get("campus_name"), str)
            or not isinstance(info.get("bundle_id"), str)
            or not isinstance(info.get("campus_mode"), str)
            or not all(
                isinstance(info.get(key), int)
                and not isinstance(info.get(key), bool)
                for key in ("students", "enrollments", "courses", "promoters")
            )
            or (
                info.get("first_course_id") is not None
                and (
                    not isinstance(info.get("first_course_id"), int)
                    or isinstance(info.get("first_course_id"), bool)
                )
            )
        ):
            self._set_error("La consulta de datos de sede devolvió datos no válidos.")
            return
        self._workspace_info = info
        self.workspaceInfoChanged.emit()

    def _student_page_rows(
        self,
        query: str,
        status_filter_index: int,
        course_filter_id: int,
        page_index: int,
        page_size: int,
    ) -> (
        Coroutine[Any, Any, tuple[list[dict[str, Any]], int, int]]
        | tuple[list[dict[str, Any]], int, int]
    ):
        if self.store is None:
            return [], 0, 0
        return self.store.student_page(
            query,
            status_filter_index,
            course_filter_id,
            page_index,
            page_size,
        )

    def _course_page_rows(
        self,
        query: str,
        page_index: int,
        page_size: int,
    ) -> (
        Coroutine[Any, Any, tuple[list[dict[str, Any]], int, int]]
        | tuple[list[dict[str, Any]], int, int]
    ):
        if self.store is None:
            return [], 0, 0
        return self.store.course_page(query, page_index, page_size)

    def _enrollment_page_rows(
        self,
        query: str,
        status_filter_index: int,
        course_filter_id: int,
        page_index: int,
        page_size: int,
    ) -> (
        Coroutine[Any, Any, tuple[list[dict[str, Any]], int, int]]
        | tuple[list[dict[str, Any]], int, int]
    ):
        if self.store is None:
            return [], 0, 0
        return self.store.enrollment_page(
            query,
            status_filter_index,
            course_filter_id,
            page_index,
            page_size,
        )

    def _on_student_page_failed(self, error_type: str, message: str) -> None:
        logger.error(
            "workspace.student_page_failed",
            error_type=error_type,
            error=message,
        )
        self._set_error(
            "No se pudo cargar la lista de estudiantes desde la base local."
        )

    def _on_course_page_failed(self, error_type: str, message: str) -> None:
        logger.error(
            "workspace.course_page_failed",
            error_type=error_type,
            error=message,
        )
        self._set_error("No se pudo cargar la lista de cursos desde la base local.")

    def _on_enrollment_page_failed(self, error_type: str, message: str) -> None:
        logger.error(
            "workspace.enrollment_page_failed",
            error_type=error_type,
            error=message,
        )
        self._set_error("No se pudo cargar la lista de matrículas desde la base local.")

    @Slot(str, result="QVariantList")
    @Slot(str, int, result="QVariantList")
    def searchStudents(self, query, limit=20):
        if self.store is None:
            return []
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or limit < 1
            or limit > 100
        ):
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

    @Slot(str, result=int)
    @Slot(str, int, result=int)
    def searchStudentsAsync(self, query: str, limit: int = 20) -> int:
        self._student_search_request_id += 1
        request_id = self._student_search_request_id
        if self.store is None:
            QTimer.singleShot(
                0,
                lambda: self.studentSearchFinished.emit(request_id, [], ""),
            )
            return request_id
        if isinstance(limit, bool) or limit < 1 or limit > 100:
            limit = 20
        try:
            operation = self.store.search_students(query, limit)
        except (OSError, RuntimeError, SQLAlchemyError, ValueError, TypeError) as exc:
            self._finish_student_search(
                request_id,
                None,
                type(exc).__name__,
                str(exc),
            )
            return request_id
        worker = AsyncQueryWorker(request_id, operation)
        worker.signals.finished.connect(self._finish_student_search)
        self._student_search_workers[request_id] = worker
        self._query_pool.start(worker)
        return request_id

    @Slot(int, object, str, str)
    def _finish_student_search(
        self,
        request_id: int,
        rows: object,
        error_type: str,
        error_message: str,
    ) -> None:
        self._student_search_workers.pop(request_id, None)
        if error_type:
            logger.error(
                "workspace.student_search_failed",
                error_type=error_type,
                error=error_message,
            )
            message = "No se pudo buscar estudiantes en la base local."
            self._set_error(message)
            self.studentSearchFinished.emit(request_id, [], message)
            return
        if not isinstance(rows, list):
            message = "La búsqueda de estudiantes devolvió datos no válidos."
            self._set_error(message)
            self.studentSearchFinished.emit(request_id, [], message)
            return
        self.studentSearchFinished.emit(request_id, rows, "")

    @Slot(str, bool, result=int)
    @Slot(str, bool, int, result=int)
    def searchCourseOptionsAsync(
        self,
        query: str,
        include_inactive: bool = False,
        limit: int = 50,
    ) -> int:
        self._course_search_request_id += 1
        request_id = self._course_search_request_id
        if self.store is None:
            message = (
                "No se pudieron buscar cursos porque no hay una base local disponible."
            )
            self._set_error(message)
            QTimer.singleShot(
                0,
                lambda: self.courseSearchFinished.emit(request_id, [], message),
            )
            return request_id
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or limit < 1
            or limit > 100
        ):
            limit = 50
        try:
            operation = self.store.search_course_options(
                query,
                include_inactive,
                limit,
            )
        except (
            OSError,
            RuntimeError,
            SQLAlchemyError,
            ValueError,
            TypeError,
            KeyError,
        ) as exc:
            self._finish_course_search(
                request_id,
                None,
                type(exc).__name__,
                str(exc),
            )
            return request_id
        worker = AsyncQueryWorker(request_id, operation)
        worker.signals.finished.connect(self._finish_course_search)
        self._course_search_workers[request_id] = worker
        self._query_pool.start(worker)
        return request_id

    @Slot(int, object, str, str)
    def _finish_course_search(
        self,
        request_id: int,
        courses: object,
        error_type: str,
        error_message: str,
    ) -> None:
        self._course_search_workers.pop(request_id, None)
        if error_type:
            logger.error(
                "workspace.course_search_failed",
                error_type=error_type,
                error=error_message,
            )
            message = "No se pudieron buscar cursos en la base local."
            self._set_error(message)
            self.courseSearchFinished.emit(request_id, [], message)
            return
        if not isinstance(courses, list) or not all(
            isinstance(course, dict)
            and isinstance(course.get("id"), int)
            and isinstance(course.get("label"), str)
            and isinstance(course.get("active"), bool)
            for course in courses
        ):
            message = "La búsqueda de cursos devolvió datos no válidos."
            self._set_error(message)
            self.courseSearchFinished.emit(request_id, [], message)
            return
        self.courseSearchFinished.emit(request_id, courses, "")

    @Property("QVariantMap", notify=dashboardSummaryChanged)
    def dashboardSummary(self):
        if self.store is not None and not self._dashboard_summary_requested:
            self._request_dashboard_summary()
        return self._dashboard_summary_cache

    @Slot(result=bool)
    def refreshDashboardSummary(self):
        if self.store is None:
            return False
        if self._dashboard_summary_cache["summary_date"] == date.today().isoformat():
            return False
        return self._request_dashboard_summary()

    def _request_dashboard_summary(self) -> bool:
        if self.store is None:
            return False
        if self._dashboard_summary_workers:
            self._dashboard_summary_dirty = True
            return True
        self._dashboard_summary_requested = True
        self._dashboard_summary_dirty = False
        self._dashboard_summary_request_id += 1
        request_id = self._dashboard_summary_request_id
        try:
            operation = self.store.dashboard_summary()
        except (
            OSError,
            RuntimeError,
            SQLAlchemyError,
            ValueError,
            TypeError,
            KeyError,
        ) as exc:
            self._finish_dashboard_summary(
                request_id,
                None,
                type(exc).__name__,
                str(exc),
            )
            return False
        worker = AsyncQueryWorker(request_id, operation)
        worker.signals.finished.connect(self._finish_dashboard_summary)
        self._dashboard_summary_workers[request_id] = worker
        self._query_pool.start(worker)
        return True

    @Slot(int, object, str, str)
    def _finish_dashboard_summary(
        self,
        request_id: int,
        summary: object,
        error_type: str,
        error_message: str,
    ) -> None:
        self._dashboard_summary_workers.pop(request_id, None)
        if request_id != self._dashboard_summary_request_id:
            return
        if error_type:
            logger.error(
                "workspace.dashboard_summary_failed",
                error_type=error_type,
                error=error_message,
            )
            self._set_error("No se pudo actualizar el resumen desde la base local.")
            if self._dashboard_summary_dirty:
                self._request_dashboard_summary()
            return
        if not isinstance(summary, dict):
            self._set_error("El resumen de la base local devolvió datos no válidos.")
            return
        self._dashboard_summary_cache = summary
        if self._dashboard_summary_dirty:
            self._request_dashboard_summary()
            return
        self.dashboardSummaryChanged.emit()

    @Property("QVariantList", notify=selectionChanged)
    def courseStudents(self):
        return self._course_students_cache

    def _request_course_students(self) -> bool:
        store = self.store
        course_id = self._selected_course_id
        self._course_students_request_id += 1
        request_id = self._course_students_request_id
        if store is None or course_id is None:
            self._course_students_cache = []
            self.selectionChanged.emit()
            return False
        try:
            operation = store.course_students(course_id)
        except (
            OSError,
            RuntimeError,
            SQLAlchemyError,
            ValueError,
            TypeError,
            KeyError,
        ) as exc:
            self._finish_course_students(
                request_id,
                None,
                type(exc).__name__,
                str(exc),
            )
            return False
        worker = AsyncQueryWorker(request_id, operation)
        worker.signals.finished.connect(self._finish_course_students)
        self._course_students_workers[request_id] = worker
        self._query_pool.start(worker)
        return True

    @Slot(int, object, str, str)
    def _finish_course_students(
        self,
        request_id: int,
        students: object,
        error_type: str,
        error_message: str,
    ) -> None:
        self._course_students_workers.pop(request_id, None)
        if request_id != self._course_students_request_id:
            return
        if error_type:
            logger.error(
                "workspace.course_students_failed",
                error_type=error_type,
                error=error_message,
            )
            self._course_students_cache = []
            self.selectionChanged.emit()
            self._set_error("No se pudo cargar la lista de alumnos del curso.")
            return
        if not isinstance(students, list) or not all(
            isinstance(student, dict) for student in students
        ):
            self._course_students_cache = []
            self.selectionChanged.emit()
            self._set_error(
                "La consulta de alumnos del curso devolvió datos no válidos."
            )
            return
        self._course_students_cache = students
        self.selectionChanged.emit()

    @Property("QVariantMap", notify=selectionChanged)
    def selectedStudent(self):
        student = self._selected_student_record
        if student is None or student.get("id") != self._selected_student_id:
            return {}
        return student

    @Property("QVariantMap", notify=selectionChanged)
    def selectedEnrollment(self):
        enrollment = self._selected_enrollment_record
        if enrollment is None or enrollment.get("id") != self._selected_enrollment_id:
            return {}
        return enrollment

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
            self._save_in_progress or self._load_in_progress or self._sync_in_progress
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

    @Property("QVariantMap", notify=workspaceInfoChanged)
    def syncWorkspaceInfo(self):
        info = self._workspace_info
        return {
            "campus_name": info.get("campus_name", "") if info else "",
            "workspace_id": (
                str(info.get("campus_id") or info.get("bundle_id", ""))
                if info
                else ""
            ),
            "students": info.get("students", 0) if info else 0,
            "enrollments": info.get("enrollments", 0) if info else 0,
            "courses": info.get("courses", 0) if info else 0,
            "promoters": info.get("promoters", 0) if info else 0,
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
            self._sync_history_cache = self._run_async(self.store.list_sync_history())
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
        if self.store is None or self._workspace_info is None:
            self._set_error("Primero abre una sede local.")
            return False
        if self.isBusy:
            self._set_error("Espera a que termine la operación en curso.")
            return False

        store = self.store
        workspace_info = deepcopy(self._workspace_info)
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
                    compatible = self._same_campus(workspace_info, backup_info)
                    message = "" if compatible else "El respaldo pertenece a otra sede."
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
        if self.store is None or self._workspace_info is None:
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
        if self.store is None or self._workspace_info is None:
            self._set_error("Primero abre una sede local.")
            return False
        if self.isBusy:
            self._set_error("Espera a que termine la operación en curso.")
            return False

        store = self.store
        local_path = store.path
        local_info = deepcopy(self._workspace_info)
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
            if not self._same_campus(local_info, backup_info):
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
                candidate_info = run_async_operation(candidate_store.workspace_info())
                if candidate_info is None:
                    raise ValueError("El respaldo no contiene una sede recuperable.")
                if not self._same_campus(local_info, candidate_info):
                    raise ValueError("El respaldo pertenece a otra sede.")
                run_async_operation(candidate_store.dispose())
                candidate_store = None

                recovery_path = self._new_backup_path(store, "pre-restore")
                store.create_backup(recovery_path)
                run_async_operation(store.dispose())
                restore_sqlite_backup(staging_path, local_path)
                destination_replaced = True

                restored_store = self._store_factory(local_path)
                restored_info = run_async_operation(restored_store.workspace_info())
                if restored_info is None or not self._same_campus(
                    local_info, restored_info
                ):
                    raise RuntimeError(
                        "La base restaurada no corresponde a la sede activa."
                    )
                return {
                    "store": restored_store,
                    "workspace_info": restored_info,
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
                        run_async_operation(restored_store.dispose())
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
                    run_async_operation(candidate_store.dispose())
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
                self.backupOperationFinished.emit(operation_name, False, {}, message)
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
                self.backupOperationFinished.emit(operation_name, True, result, "")
                return

            if operation_name == "backup_create":
                if not isinstance(result, dict):
                    message = "El resultado de creación del respaldo no es válido."
                    self._set_error(message)
                    self.backupOperationFinished.emit(
                        operation_name, False, {}, message
                    )
                    return
                self.backupOperationFinished.emit(operation_name, True, result, "")
                return

            if (
                not isinstance(result, dict)
                or not isinstance(result.get("workspace_info"), dict)
                or result.get("store") is None
            ):
                message = "El resultado de restauración no es válido."
                self._set_error(message)
                self.backupOperationFinished.emit(operation_name, False, {}, message)
                return
            recovery_backup = result["recovery_backup"]
            self._finish_database_restore(
                result["store"],
                result["workspace_info"],
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
            if operation_name == "register_export":
                message = f"No se pudo exportar el registro: {error}"
                self._set_error(message)
                self.registerExportFinished.emit(False, message)
                return

            operation = (
                "import" if operation_name in ("preview", "import") else "export"
            )
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

        if operation_name == "register_export":
            if not isinstance(result, str):
                message = "No se pudo exportar el registro: resultado no válido."
                self._set_error(message)
                self.registerExportFinished.emit(False, message)
                return
            message = f"Registro exportado correctamente: {result}"
            self._set_error(message)
            self.registerExportFinished.emit(True, message)
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
            run_async_operation(store.dispose())
            return

        task = loop.create_task(store.dispose())
        task.add_done_callback(
            lambda finished: self._finish_store_dispose(finished, store)
        )

    def _run_async(self, operation: Coroutine[Any, Any, Any]) -> Any:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return run_async_operation(operation)

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

    def _persist_manifest(self, store, manifest, history_event=None):
        if self.isBusy:
            return False, "Ya hay un guardado en curso."

        self._save_in_progress = True
        self._activity_message = "Guardando cambios en la base de datos..."
        self.savingStateChanged.emit()
        self.activityStateChanged.emit()
        try:
            operation = (
                store.save_with_sync_history(deepcopy(manifest), history_event)
                if history_event is not None
                else store.save(deepcopy(manifest))
            )
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

    def _run_store_write(self, operation: Coroutine[Any, Any, Any]) -> Any:
        self._save_in_progress = True
        self._activity_message = "Guardando cambios en la base de datos..."
        self.savingStateChanged.emit()
        self.activityStateChanged.emit()
        try:
            return self._run_async(operation)
        finally:
            self._save_in_progress = False
            self._activity_message = ""
            self.savingStateChanged.emit()
            self.activityStateChanged.emit()

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

    def _load_workspace_info(self, store):
        if self.isBusy:
            return False, None, "Ya hay otra operación en curso."

        self._load_in_progress = True
        self._activity_message = "Cargando los datos de la sede..."
        self.activityStateChanged.emit()
        try:
            return True, self._run_async(store.workspace_info()), ""
        except (
            OSError,
            RuntimeError,
            SQLAlchemyError,
            ValueError,
            KeyError,
            TypeError,
        ) as exc:
            logger.error(
                "workspace.metadata_load_failed",
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
        if self.store and target_path == self.store.path and self._workspace_info:
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
            "promoters": [],
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
            self.store
            and target_path == self.store.path
            and self._workspace_info is None
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
                backup_token = hashlib.sha256(bundle_id.encode("utf-8")).hexdigest()[
                    :12
                ]
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
                self._set_error(
                    f"No se pudo respaldar la sede antes de importar: {exc}"
                )
                return False

        preview = (
            build_import_preview(existing_manifest, manifest)
            if existing_manifest is not None and not empty_current_store
            else {
                "new": sum(
                    len(manifest[collection])
                    for collection in (
                        "students",
                        "enrollments",
                        "courses",
                        "promoters",
                    )
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
            {key: preview[key] for key in ("new", "updated", "unchanged", "conflicts")},
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
            (f"Datos sincronizados actualizados. Respaldo: {backup_path}")
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
        if self.store is None:
            self._set_error("Primero abre una sede local.")
            return False
        if self.isBusy:
            self._set_error("Espera a que termine la operación en curso.")
            return False

        store = self.store
        local_path = self._local_path(package_path)
        self._pending_import_manifest = None
        self._pending_import_snapshot = None
        self._pending_import_preview = {}

        def prepare():
            local_snapshot = run_async_operation(store.load())
            if local_snapshot is None:
                raise PackageError("La sede local no tiene un espacio de trabajo.")
            incoming = read_package(local_path)
            if not self._same_campus(local_snapshot, incoming):
                raise PackageError(
                    "El paquete no pertenece a la sede local actualmente abierta."
                )
            bundle_id = str(incoming["bundle_id"])
            if run_async_operation(store.has_imported_bundle(bundle_id)):
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
            current = run_async_operation(store.load())
            if current is None or current != snapshot:
                raise ValueError(
                    "La sede cambió después de la vista previa. Valida el paquete otra vez."
                )
            if not self._same_campus(current, incoming):
                raise PackageError(
                    "El paquete ya no corresponde a la sede local abierta."
                )
            if run_async_operation(store.has_imported_bundle(bundle_id)):
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
            run_async_operation(
                store.save_with_sync_history(
                    incoming,
                    event,
                    expected_snapshot=snapshot,
                )
            )
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
        if self.store is None:
            self._set_error(
                "Primero abre una sede o crea una nueva en este dispositivo."
            )
            return False
        if self.isBusy:
            self._set_error("Espera a que termine la operación en curso.")
            return False

        local_path = self._local_path(path)
        store = self.store
        metadata: dict[str, Any] = {"history_event": None}

        def export_package():
            output = run_async_operation(store.load())
            if output is None:
                raise ValueError("La sede local no tiene un espacio de trabajo.")
            if output.get("campus_mode") != "new":
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
            metadata["history_event"] = event
            write_package(local_path, output)
            try:
                run_async_operation(store.record_sync_history(event))
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
            metadata,
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
                and self._workspace_info is not None
                and target_path == self.store.path
            ):
                self._set_error("Cierra la sede activa antes de quitarla de la lista.")
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
        loaded, workspace_info, error = self._load_workspace_info(target_store)
        if not loaded:
            self._dispose_store(target_store)
            self._set_error(f"No se pudo abrir la sede seleccionada: {error}")
            return False
        if workspace_info is None:
            self._dispose_store(target_store)
            self._set_error("La base seleccionada no contiene una sede de EduTrack.")
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
            None,
            f"Sede {workspace_info['campus_name']} abierta.",
            register=False,
            workspace_info=workspace_info,
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
        except (
            CampusCatalogError,
            OSError,
            RuntimeError,
            SQLAlchemyError,
            ValueError,
        ) as exc:
            self._set_error(f"No se pudo abrir la base seleccionada: {exc}")
            return False
        loaded, workspace_info, error = self._load_workspace_info(target_store)
        if not loaded:
            self._dispose_store(target_store)
            self._set_error(f"No se pudo abrir la base seleccionada: {error}")
            return False
        if workspace_info is None:
            self._dispose_store(target_store)
            self._set_error("La base seleccionada no contiene una sede de EduTrack.")
            return False
        try:
            if self.catalog:
                self.catalog.register(
                    target_path,
                    workspace_info["campus_name"],
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
            None,
            f"Sede {workspace_info['campus_name']} abierta.",
            register=False,
            workspace_info=workspace_info,
        )

    @Slot(result=bool)
    def refreshWorkspace(self):
        if self.store is None or self._workspace_info is None:
            self._set_error("No hay una sede abierta para actualizar.")
            return False
        self._request_workspace_info()
        self._request_dashboard_summary()
        self._refresh_list_models()
        self.workspaceInfoChanged.emit()
        self.selectionChanged.emit()
        self._set_error("Datos actualizados desde la base local.")
        return True

    @Slot(result=bool)
    def closeCampus(self):
        if self.store is None or self._workspace_info is None:
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
        self._workspace_info = None
        self._workspace_info_request_id += 1
        self._selected_student_id = ""
        self._selected_student_record = None
        self._selected_enrollment_id = ""
        self._selected_enrollment_record = None
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

    def _finish_database_change(
        self,
        store,
        manifest,
        message,
        register=True,
        workspace_info=None,
    ):
        if workspace_info is None:
            if manifest is None:
                raise ValueError("Se requiere información de la sede.")
            workspace_info = self._workspace_info_from_manifest(manifest)
        catalog_error = ""
        if self.catalog and register:
            try:
                self.catalog.register(
                    store.path,
                    workspace_info["campus_name"],
                    activate=True,
                )
            except CampusCatalogError as exc:
                catalog_error = str(exc)
        previous_store = self.store
        self.store = store
        self.manifest = None
        self._workspace_info = workspace_info
        self._selected_student_id = ""
        self._selected_student_record = None
        self._selected_enrollment_id = ""
        self._selected_enrollment_record = None
        self._selected_course_id = workspace_info.get("first_course_id")
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

    def _finish_database_restore(
        self,
        store: WorkspaceStore,
        workspace_info: dict[str, Any],
        message: str,
    ) -> None:
        previous_store = self.store
        self.store = store
        self.manifest = None
        self._workspace_info = workspace_info
        self._selected_student_id = ""
        self._selected_student_record = None
        self._selected_enrollment_id = ""
        self._selected_enrollment_record = None
        self._selected_course_id = workspace_info.get("first_course_id")
        if previous_store is not None and previous_store is not store:
            self._dispose_store(previous_store)
        self.dataChanged.emit()
        self.selectionChanged.emit()
        if previous_store is None or previous_store.path != store.path:
            self._backup_items = []
            self.backupDirectoryChanged.emit()
            self.backupStateChanged.emit()
        self.workspaceInfoChanged.emit()
        self._set_error(message)

    @staticmethod
    def _workspace_info_from_manifest(
        manifest: dict[str, Any],
    ) -> dict[str, Any]:
        courses = manifest.get("courses", [])
        return {
            "format": manifest["format"],
            "version": manifest["version"],
            "bundle_id": manifest["bundle_id"],
            "campus_id": manifest["campus_id"],
            "campus_name": manifest["campus_name"],
            "campus_address": manifest.get("campus_address", ""),
            "campus_mode": manifest.get("campus_mode", "existing"),
            "students": len(manifest.get("students", [])),
            "enrollments": len(manifest.get("enrollments", [])),
            "courses": len(courses),
            "promoters": len(manifest.get("promoters", [])),
            "first_course_id": courses[0]["id"] if courses else None,
        }

    @Slot(str)
    def exportPackage(self, path):
        if self.store is None:
            self._set_error(
                "Primero abre una sede o crea una nueva en este dispositivo."
            )
            return
        try:
            output = self._run_async(self.store.load())
            if output is None:
                raise ValueError("La sede local no tiene un espacio de trabajo.")
            if output.get("campus_mode") != "new":
                output["bundle_id"] = str(uuid.uuid4())
            write_package(self._local_path(path), output)
            message = (
                "Paquete inicial de sede generado correctamente."
                if output.get("campus_mode") == "new"
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
        except (
            PackageError,
            OSError,
            RuntimeError,
            SQLAlchemyError,
            sqlite3.Error,
            ValueError,
        ) as exc:
            logger.error(
                "sync.package_export_failed",
                error_type=exc.__class__.__name__,
            )
            self._set_error(str(exc))

    @Slot(str, result=bool)
    def exportRegister(self, path):
        store = self.store
        if store is None:
            self._set_error(
                "Primero abre una sede o crea una nueva en este dispositivo."
            )
            return False
        output_path = Path(self._local_path(path))

        def export_from_sqlite():
            export_data = run_async_operation(store.register_export_data())
            if not isinstance(export_data, dict):
                raise RuntimeError("No hay una sede disponible para exportar.")
            export_register(export_data, output_path)
            return output_path.name

        return self._start_sync_operation(
            "register_export",
            export_from_sqlite,
            "Exportando registro de cursos...",
        )

    def _finish_course_write(self, course: dict[str, Any]) -> None:
        course_id = int(course["id"])
        self._selected_course_id = course_id
        self.dataChanged.emit()
        self.selectionChanged.emit()

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
        if self.isBusy:
            self._set_error("Ya hay un guardado en curso.")
            return 0
        store = self.store
        if store is None:
            self._set_error(
                "Primero abre una sede o crea una nueva en este dispositivo."
            )
            return 0
        try:
            course = self._run_store_write(
                store.create_course(
                name,
                schedule,
                group_name,
                start_date,
                enrollment_fee,
                monthly_fee,
                capacity,
                self._record_service,
                )
            )
        except ValueError as exc:
            self._log_validation_failure("course.create", exc)
            self._set_error(str(exc) or "Revisa los datos del curso.")
            return 0
        except (
            OSError,
            RuntimeError,
            SQLAlchemyError,
            sqlite3.Error,
            TypeError,
            KeyError,
        ) as exc:
            logger.error(
                "workspace.course_create_failed",
                error_type=exc.__class__.__name__,
            )
            self._set_error(f"No se pudo guardar el curso localmente: {exc}")
            return 0
        self._finish_course_write(course)
        self._set_error("Curso guardado localmente.")
        return int(course["id"])

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
        if self.isBusy:
            self._set_error("Ya hay un guardado en curso.")
            return False
        store = self.store
        if store is None:
            self._set_error(
                "Primero abre una sede o crea una nueva en este dispositivo."
            )
            return False
        try:
            course = self._run_store_write(
                store.update_course(
                source_id,
                name,
                schedule,
                group_name,
                start_date,
                enrollment_fee,
                monthly_fee,
                capacity,
                active,
                self._record_service,
                )
            )
        except ValueError as exc:
            self._log_validation_failure("course.update", exc)
            self._set_error(str(exc) or "Revisa los datos del curso.")
            return False
        except (
            OSError,
            RuntimeError,
            SQLAlchemyError,
            sqlite3.Error,
            TypeError,
            KeyError,
        ) as exc:
            logger.error(
                "workspace.course_update_failed",
                error_type=exc.__class__.__name__,
            )
            self._set_error(f"No se pudieron guardar los cambios localmente: {exc}")
            return False
        self._finish_course_write(course)
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
        store = self.store
        if store is None:
            self._set_error(
                "Primero abre una sede o crea una nueva en este dispositivo."
            )
            return False

        self._pending_course_save_id = source_id
        self._course_save_in_progress = True
        self._save_in_progress = True
        self._activity_message = "Guardando cambios en la base de datos..."
        self.courseSaveStateChanged.emit()
        self.savingStateChanged.emit()
        self.activityStateChanged.emit()
        operation = store.update_course(
            source_id,
            name,
            schedule,
            group_name,
            start_date,
            enrollment_fee,
            monthly_fee,
            capacity,
            active,
            self._record_service,
        )
        worker = AsyncQueryWorker(source_id, operation)
        worker.signals.finished.connect(self._finish_course_update)
        self._course_save_worker = worker
        self._save_pool.start(worker)
        return True

    @Slot(int, object, str, str)
    def _finish_course_update(
        self,
        _request_id: int,
        course: object,
        error_type: str,
        error_message: str,
    ) -> None:
        if error_type:
            logger.error(
                "workspace.course_update_failed",
                error_type=error_type,
                error=error_message,
            )
            self._finish_course_save(False, None, error_message)
            return
        if not isinstance(course, dict):
            self._finish_course_save(
                False, None, "La actualización del curso devolvió datos no válidos."
            )
            return
        self._finish_course_save(True, course, "")

    @Slot(bool, object, str)
    def _finish_course_save(self, succeeded, course, message):
        self._course_save_worker = None
        self._course_save_in_progress = False
        self._save_in_progress = False
        self._activity_message = ""
        self.courseSaveStateChanged.emit()
        self.savingStateChanged.emit()
        self.activityStateChanged.emit()
        course_id = self._pending_course_save_id
        self._pending_course_save_id = None
        if succeeded and isinstance(course, dict) and course_id is not None:
            self._finish_course_write(course)
            self._backup_items = []
            self.backupDirectoryChanged.emit()
            self.backupStateChanged.emit()
            self._set_error("Curso actualizado correctamente en este dispositivo.")
        else:
            self._set_error(message or "No se pudieron guardar los cambios localmente.")
        self.courseSaveFinished.emit(
            succeeded and isinstance(course, dict) and course_id is not None
        )

    @Slot(str)
    def selectStudent(self, source_id):
        if self._selected_student_id != source_id:
            self._selected_student_record = None
        self._selected_student_id = source_id
        self.selectionChanged.emit()

    @Slot()
    def newStudent(self):
        self._selected_student_id = ""
        self._selected_student_record = None
        self.selectionChanged.emit()

    @Slot(str)
    def selectEnrollment(self, source_id):
        if self._selected_enrollment_id != source_id:
            self._selected_enrollment_record = None
        self._selected_enrollment_id = source_id
        self.selectionChanged.emit()

    @Slot(int)
    def selectCourse(self, source_id):
        self._selected_course_id = source_id
        self._course_students_cache = []
        self._request_course_students()
        self.selectionChanged.emit()

    @Slot()
    def newEnrollment(self):
        self._selected_enrollment_id = ""
        self._selected_enrollment_record = None
        self.selectionChanged.emit()

    def _finish_student_write(
        self, student: dict[str, Any], *, select_student: bool = False
    ) -> None:
        student_id = str(student["id"])
        if select_student:
            self._selected_student_id = student_id
        if self._selected_student_id == student_id:
            self._selected_student_record = student
        self.dataChanged.emit()
        self.selectionChanged.emit()

    def _finish_enrollment_write(self, enrollment: dict[str, Any]) -> None:
        enrollment_id = str(enrollment["id"])
        self._selected_enrollment_id = enrollment_id
        self._selected_enrollment_record = enrollment
        self.dataChanged.emit()
        self.selectionChanged.emit()

    @Slot(str, str, str, str, str, result=bool)
    def saveStudent(
        self, source_id, last_name, first_name, document_number, phone_text
    ):
        if self.isBusy:
            self._set_error("Ya hay un guardado en curso.")
            return False
        store = self.store
        if store is None:
            self._set_error("Primero abre el archivo de una sede.")
            return False
        try:
            student = self._run_store_write(
                store.save_student(
                source_id,
                last_name,
                first_name,
                document_number,
                phone_text,
                self._record_service,
                )
            )
        except ValueError as exc:
            self._log_validation_failure("student.save", exc)
            self._set_error(str(exc))
            return False
        except (
            OSError,
            RuntimeError,
            SQLAlchemyError,
            sqlite3.Error,
            TypeError,
            KeyError,
        ) as exc:
            logger.error(
                "workspace.student_save_failed",
                error_type=exc.__class__.__name__,
            )
            self._set_error(f"No se pudo guardar el estudiante localmente: {exc}")
            return False
        self._finish_student_write(student, select_student=True)
        self._set_error("Estudiante guardado en este dispositivo.")
        return True

    @Slot(str, bool, result=bool)
    def setStudentActive(self, source_id, active):
        if self.isBusy:
            self._set_error("Ya hay un guardado en curso.")
            return False
        store = self.store
        if store is None:
            self._set_error("Primero abre el archivo de una sede.")
            return False
        try:
            student = self._run_store_write(
                store.set_student_active(
                    source_id,
                    active,
                    self._record_service,
                )
            )
        except ValueError as exc:
            self._log_validation_failure("student.set_active", exc)
            self._set_error(str(exc))
            return False
        except (
            OSError,
            RuntimeError,
            SQLAlchemyError,
            sqlite3.Error,
            TypeError,
            KeyError,
        ) as exc:
            logger.error(
                "workspace.student_activation_failed",
                error_type=exc.__class__.__name__,
            )
            self._set_error(f"No se pudo actualizar el estado del estudiante: {exc}")
            return False
        self._finish_student_write(student)
        state = "activado" if active else "desactivado"
        self._set_error(f"Estudiante {state} correctamente en este dispositivo.")
        return True

    @Slot("QVariantMap", "QVariantMap", result="QVariantMap")
    def createEnrollment(self, student_fields, enrollment_fields):
        failure = {"ok": False}
        if self.store is None:
            self._set_error("Primero abre el archivo de una sede.")
            return failure
        try:
            result = self._run_async(
                self._create_enrollment_use_case.execute_and_persist(
                    self.store,
                    student_fields,
                    enrollment_fields,
                )
            )
        except ValueError as exc:
            self._log_validation_failure("enrollment.create", exc)
            self._set_error(str(exc) or "Revisa los datos de la matrícula.")
            return failure
        except (
            OSError,
            RuntimeError,
            SQLAlchemyError,
            KeyError,
            TypeError,
        ) as exc:
            logger.error(
                "workspace.enrollment_create_failed",
                error_type=exc.__class__.__name__,
            )
            self._set_error(
                f"No se pudieron guardar localmente los cambios: "
                f"{str(exc) or exc.__class__.__name__}"
            )
            return failure

        if self._selected_student_id != result.student_id:
            self._selected_student_record = None
        self._selected_student_id = result.student_id
        self._selected_enrollment_id = result.enrollment_id
        self._selected_enrollment_record = None
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
        if self.isBusy:
            self._set_error("Ya hay un guardado en curso.")
            return False
        store = self.store
        if store is None:
            self._set_error("Primero abre el archivo de una sede.")
            return False
        if not isinstance(fields, dict):
            self._set_error("Los datos de la matrícula no tienen un formato válido.")
            return False
        try:
            result = self._run_store_write(
                store.save_enrollment(
                    source_id,
                    fields,
                    self._record_service,
                )
            )
        except ValueError as exc:
            self._log_validation_failure("enrollment.save", exc)
            self._set_error(str(exc) or "Revisa los datos de la matrícula.")
            return False
        except (
            OSError,
            RuntimeError,
            SQLAlchemyError,
            sqlite3.Error,
            TypeError,
            KeyError,
        ) as exc:
            logger.error(
                "workspace.enrollment_save_failed",
                error_type=exc.__class__.__name__,
            )
            self._set_error(f"No se pudo guardar la matrícula localmente: {exc}")
            return False

        if (
            not isinstance(result, dict)
            or not isinstance(result.get("record"), dict)
        ):
            self._set_error(
                "La actualización de la matrícula devolvió datos no válidos."
            )
            return False
        self._finish_enrollment_write(result["record"])
        self._set_error("Matrícula guardada en este dispositivo.")
        return True

    @staticmethod
    def _local_path(value):
        url = QUrl(value)
        return url.toLocalFile() if url.isLocalFile() else value
