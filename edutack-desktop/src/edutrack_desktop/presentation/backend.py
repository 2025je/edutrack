import base64
import hashlib
import re
import sqlite3
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from PySide6.QtCore import QObject, QStandardPaths, QUrl, Signal, Slot
from sqlalchemy.exc import SQLAlchemyError
import structlog

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
    enrollment_rows,
    student_rows,
)
from ..domain.record_service import RecordService
from ..infrastructure.app_settings import DesktopSettings
from ..infrastructure.campus_catalog import CampusCatalog, CampusCatalogError
from ..infrastructure.store import LocalStore
from ..infrastructure.transfer import (
    INITIAL_CAMPUS_VERSION,
    PACKAGE_FORMAT,
    PackageError,
    read_package,
    write_package,
)

logger = structlog.get_logger(__name__)


def _create_local_store(path: Path) -> WorkspaceStore:
    return LocalStore(path)


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

    def __init__(
        self,
        store_path=None,
        catalog_path=None,
        settings=None,
        *,
        store_factory: StoreFactory | None = None,
        catalog_factory: CampusCatalogFactory | None = None,
        record_service: RecordServicePort | None = None,
    ):
        super().__init__()
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
        closed_on_start = bool(
            self.catalog and self.catalog.records and not self.catalog.active_path
        )
        self.store: WorkspaceStore | None = None
        self.manifest: dict[str, Any] | None = None
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

        if closed_on_start:
            self.store = None
            self.manifest = None
        else:
            try:
                self.store = self._store_factory(selected_path)
            except (OSError, RuntimeError, SQLAlchemyError, ValueError) as exc:
                if selected_path == default_store_path:
                    raise
                startup_error = f"No se pudo abrir la sede registrada: {exc}"
                self.store = self._store_factory(default_store_path)
            self.manifest = self.store.load()
        self._error_message = startup_error
        if self.catalog and self.manifest and self.store:
            try:
                self.catalog.register(
                    self.store.path,
                    self.manifest["campus_name"],
                    activate=True,
                )
            except CampusCatalogError as exc:
                self._error_message = str(exc)
        self._selected_student_id = ""
        self._selected_enrollment_id = ""
        courses = self.manifest.get("courses", []) if self.manifest else []
        self._selected_course_id = courses[0]["id"] if courses else None

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
        return student_rows(self.manifest)

    @Property("QVariantList", notify=dataChanged)
    def enrollments(self):
        return enrollment_rows(self.manifest)

    @Property("QVariantList", notify=dataChanged)
    def courses(self):
        return course_rows(self.manifest)

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
            for course in self.manifest["courses"]
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

    def _set_error(self, message):
        self._error_message = message
        self.errorChanged.emit()

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

    def _save(self):
        if self.store is None or self.manifest is None:
            self._set_error("No hay una sede abierta para guardar los cambios.")
            return False
        try:
            self.store.save(self.manifest)
        except (SQLAlchemyError, ValueError, KeyError, TypeError) as exc:
            logger.exception(
                "workspace.save_failed",
                database_path=str(self.store.path),
                error=str(exc),
            )
            self._set_error(f"No se pudieron guardar los cambios localmente: {exc}")
            return False
        self.dataChanged.emit()
        return True

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
            target_store.save(manifest)
        except (OSError, RuntimeError, SQLAlchemyError, ValueError) as exc:
            if target_store is not None and target_store is not self.store:
                target_store.engine.dispose()
            self._set_error(str(exc))
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
            existing_manifest = target_store.load() if target_exists else None
            if (
                target_exists
                and not empty_current_store
                and (
                    existing_manifest is None
                    or not self._same_campus(existing_manifest, manifest)
                )
            ):
                if target_store is not self.store:
                    target_store.engine.dispose()
                self._set_error(
                    "El paquete no pertenece a la sede guardada en la base seleccionada."
                )
                return False
            target_store.save(manifest)
        except (OSError, RuntimeError, SQLAlchemyError, ValueError) as exc:
            if target_store is not None and target_store is not self.store:
                target_store.engine.dispose()
            self._set_error(f"No se pudo guardar la sede importada: {exc}")
            return False
        return self._finish_database_change(
            target_store,
            manifest,
            (
                "Datos sincronizados actualizados en la base de esta sede."
                if target_exists
                else "Sede importada correctamente en una base de datos independiente."
            ),
        )

    @staticmethod
    def _same_campus(existing, incoming):
        existing_id = existing.get("campus_id")
        incoming_id = incoming.get("campus_id")
        if existing_id is not None and incoming_id is not None:
            return existing_id == incoming_id
        existing_bundle = existing.get("bundle_id")
        incoming_bundle = incoming.get("bundle_id")
        return bool(existing_bundle and existing_bundle == incoming_bundle)

    @Slot(str, result=bool)
    def isRegisteredDatabase(self, path):
        return bool(
            self.catalog
            and self.catalog.contains(
                Path(self._local_path(path)).expanduser().resolve()
            )
        )

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
            manifest = target_store.load()
            if manifest is None:
                target_store.engine.dispose()
                self._set_error(
                    "La base seleccionada no contiene una sede de EduTrack."
                )
                return False
            self.catalog.activate(target_path)
        except (
            CampusCatalogError,
            OSError,
            RuntimeError,
            SQLAlchemyError,
            ValueError,
        ) as exc:
            if target_store is not None and target_store is not self.store:
                target_store.engine.dispose()
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
            manifest = target_store.load()
            if manifest is None:
                target_store.engine.dispose()
                self._set_error(
                    "La base seleccionada no contiene una sede de EduTrack."
                )
                return False
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
            if target_store is not None and target_store is not self.store:
                target_store.engine.dispose()
            self._set_error(f"No se pudo abrir la base seleccionada: {exc}")
            return False
        return self._finish_database_change(
            target_store,
            manifest,
            f"Sede {manifest['campus_name']} abierta.",
            register=False,
        )

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
        self._selected_student_id = ""
        self._selected_enrollment_id = ""
        self._selected_course_id = None
        previous_store.engine.dispose()
        self.dataChanged.emit()
        self.selectionChanged.emit()
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
        self._selected_student_id = ""
        self._selected_enrollment_id = ""
        courses = manifest.get("courses", [])
        self._selected_course_id = courses[0]["id"] if courses else None
        if previous_store is not None and previous_store is not store:
            previous_store.engine.dispose()
        self.dataChanged.emit()
        self.selectionChanged.emit()
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
            self._set_error(message)
        except (PackageError, OSError, ValueError) as exc:
            self._set_error(str(exc))

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
            course_id = self._record_service.create_course(
                self.manifest,
                name,
                schedule,
                group_name,
                start_date,
                enrollment_fee,
                monthly_fee,
                capacity,
            )
        except ValueError as exc:
            self._set_error(str(exc) or "Revisa los datos del curso.")
            return 0
        self._selected_course_id = course_id
        if not self._save():
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
        if not self.manifest:
            self._set_error("Primero abre una sede o crea una nueva en este dispositivo.")
            return False
        try:
            self._record_service.update_course(
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
            self._set_error(str(exc) or "Revisa los datos del curso.")
            return False
        self._selected_course_id = source_id
        if not self._save():
            return False
        self.selectionChanged.emit()
        self._set_error("Curso actualizado correctamente en este dispositivo.")
        return True

    @Slot(str, result=int)
    def createPromoter(self, name):
        try:
            if not self.manifest:
                raise ValueError(
                    "Los promotores se crean desde Desktop al preparar una sede nueva."
                )
            promoter_id = self._record_service.create_promoter(self.manifest, name)
        except ValueError as exc:
            self._set_error(str(exc))
            return 0
        if not self._save():
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
            self._set_error(str(exc))
            return
        image_hash = hashlib.sha256(content).hexdigest()
        package_path = f"attachments/{image_hash}.jpg"
        self.manifest.setdefault("_attachment_data", {})[package_path] = (
            base64.b64encode(content).decode("ascii")
        )
        row["record_image"] = package_path
        row["record_image_hash"] = image_hash
        if not self._save():
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
        if not self._save():
            return
        self.selectionChanged.emit()
        self._set_error("Se quitará la imagen al sincronizar con la web.")

    @Slot(str, str, str, str, str)
    def saveStudent(
        self, source_id, last_name, first_name, document_number, phone_text
    ):
        if not self.manifest:
            self._set_error("Primero abre el archivo de una sede.")
            return
        try:
            student_id = self._record_service.save_student(
                self.manifest,
                source_id,
                last_name,
                first_name,
                document_number,
                phone_text,
            )
        except ValueError as exc:
            self._set_error(str(exc))
            return
        self._selected_student_id = student_id
        if not self._save():
            return
        self.selectionChanged.emit()
        self._set_error("Estudiante guardado en este dispositivo.")

    @Slot(str, "QVariantMap", result=bool)
    def saveEnrollment(self, source_id, fields):
        if not self.manifest:
            self._set_error("Primero abre el archivo de una sede.")
            return False
        if not isinstance(fields, dict):
            self._set_error("Los datos de la matrícula no tienen un formato válido.")
            return False
        try:
            enrollment_id = self._record_service.save_enrollment(
                self.manifest,
                source_id,
                fields,
            )
        except ValueError as exc:
            self._set_error(str(exc) or "Revisa los datos de la matrícula.")
            return False
        self._selected_enrollment_id = enrollment_id
        if not self._save():
            return False
        self.selectionChanged.emit()
        self._set_error("Matrícula guardada en este dispositivo.")
        return True

    @staticmethod
    def _local_path(value):
        url = QUrl(value)
        return url.toLocalFile() if url.isLocalFile() else value
