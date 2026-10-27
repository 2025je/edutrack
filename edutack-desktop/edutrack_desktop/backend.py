import base64
import hashlib
import re
import sqlite3
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from PySide6.QtCore import QObject, Property, QStandardPaths, QUrl, Signal, Slot
from sqlalchemy.exc import SQLAlchemyError

from .campus_catalog import CampusCatalog, CampusCatalogError
from .store import LocalStore
from .transfer import (
    INITIAL_CAMPUS_VERSION,
    PACKAGE_FORMAT,
    PackageError,
    read_package,
    write_package,
)

PHONE_PATTERN = re.compile(r"9\d{8}\Z")


class DesktopBackend(QObject):
    dataChanged = Signal()
    selectionChanged = Signal()
    errorChanged = Signal()

    def __init__(self, store_path=None, catalog_path=None):
        super().__init__()
        uses_default_path = store_path is None
        if store_path is None:
            data_dir = Path(
                QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
            )
            store_path = data_dir / "edutrack-desktop.sqlite3"
        default_store_path = Path(store_path).expanduser().resolve()
        if catalog_path is None and uses_default_path:
            catalog_path = default_store_path.parent / "campuses.json"
        self.catalog = CampusCatalog(catalog_path) if catalog_path is not None else None

        selected_path = default_store_path
        startup_error = ""
        closed_on_start = bool(
            self.catalog and self.catalog.records and not self.catalog.active_path
        )
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
                self.store = LocalStore(selected_path)
            except (OSError, RuntimeError, SQLAlchemyError, ValueError) as exc:
                if selected_path == default_store_path:
                    raise
                startup_error = f"No se pudo abrir la sede registrada: {exc}"
                self.store = LocalStore(default_store_path)
            self.manifest = self.store.load()
        self._error_message = startup_error
        if self.catalog and self.manifest:
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
        if not self.manifest:
            return []
        rows = []
        for student in self.manifest["students"]:
            rows.append(
                {
                    **student,
                    "label": " ".join(
                        part
                        for part in (student["last_name"], student["first_name"])
                        if part
                    ),
                }
            )
        return sorted(rows, key=lambda row: row["label"].casefold())

    @Property("QVariantList", notify=dataChanged)
    def enrollments(self):
        if not self.manifest:
            return []
        students = {item["id"]: item for item in self.manifest["students"]}
        courses = {item["id"]: item for item in self.manifest["courses"]}
        rows = []
        for enrollment in self.manifest["enrollments"]:
            student = students.get(enrollment.get("student_id"))
            course = courses.get(enrollment.get("course_id"))
            student_name = (
                " ".join(
                    part
                    for part in (student["last_name"], student["first_name"])
                    if part
                )
                if student
                else "Sin estudiante"
            )
            course_name = (
                f"{course['name']} · {course['schedule']} · Grupo {course['group']}"
                if course
                else "Pendiente de curso"
            )
            rows.append(
                {
                    **enrollment,
                    "label": f"{student_name} — {course_name}",
                }
            )
        return sorted(rows, key=lambda row: row["label"].casefold())

    @Property("QVariantList", notify=dataChanged)
    def courses(self):
        if not self.manifest:
            return []
        rows = []
        for course in self.manifest["courses"]:
            rows.append(
                {
                    **course,
                    "label": (
                        f"{course['name']} · {course['schedule']} · Grupo {course['group']}"
                    ),
                    "student_count": len(self._course_students(course["id"])),
                }
            )
        return sorted(
            rows,
            key=lambda row: (
                row["name"].casefold(),
                row["schedule"].casefold(),
                str(row["group"]).casefold(),
            ),
        )

    @Property("QVariantList", notify=selectionChanged)
    def courseStudents(self):
        if not self.manifest or self._selected_course_id is None:
            return []
        return self._course_students(self._selected_course_id)

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

    def _course_students(self, course_id):
        students = {student["id"]: student for student in self.manifest["students"]}
        roster = {}
        for enrollment in self.manifest["enrollments"]:
            if enrollment.get("course_id") != course_id or not enrollment.get(
                "active", True
            ):
                continue
            student = students.get(enrollment.get("student_id"))
            if not student or not student.get("active", True):
                continue
            roster[student["id"]] = {
                **student,
                "label": " ".join(
                    part
                    for part in (student["last_name"], student["first_name"])
                    if part
                ),
            }
        return sorted(roster.values(), key=lambda row: row["label"].casefold())

    def _save(self):
        if self.store is None:
            self._set_error("No hay una sede abierta para guardar los cambios.")
            return False
        try:
            self.store.save(self.manifest)
        except (SQLAlchemyError, ValueError, KeyError, TypeError) as exc:
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
                target_store = LocalStore(target_path)
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
                target_store = LocalStore(target_path)
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
            target_store = LocalStore(target_path)
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
            target_store = LocalStore(target_path)
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
        raw_name = name.strip()
        raw_schedule = schedule.strip()
        raw_group = group_name.strip()
        if (
            not raw_name
            or len(raw_name) > 120
            or not raw_schedule
            or len(raw_schedule) > 120
            or len(raw_group) > 50
        ):
            self._set_error("Ingresa un nombre de curso y un horario válidos.")
            return 0
        name = " ".join(raw_name.split()).upper()
        schedule = " ".join(raw_schedule.split()).upper()
        try:
            group_name = str(int(raw_group)) if raw_group.isdigit() else ""
        except ValueError:
            group_name = ""
        if not name or not schedule:
            self._set_error("Ingresa un nombre de curso y un horario válidos.")
            return 0
        if not group_name or int(group_name) < 1 or len(group_name) > 50:
            self._set_error("El grupo debe ser un número entero positivo.")
            return 0
        try:
            date_text = start_date.strip()
            course_date = date.fromisoformat(date_text)
            if course_date.isoformat() != date_text:
                raise ValueError("La fecha de inicio no es válida.")
            course_date = course_date.isoformat()
            enrollment_fee = self._amount(enrollment_fee, "costo de matrícula")
            monthly_fee = self._amount(monthly_fee, "mensualidad")
            capacity = int(capacity)
            if capacity < 1 or capacity > 2_147_483_647:
                raise ValueError("La capacidad debe ser un entero positivo.")
        except (ValueError, InvalidOperation) as exc:
            self._set_error(str(exc) or "Revisa los datos del curso.")
            return 0
        if any(
            item["name"].strip().casefold() == name.casefold()
            and item["schedule"].strip().casefold() == schedule.casefold()
            and str(item["group"]).strip() == group_name
            for item in self.manifest["courses"]
        ):
            self._set_error("Ya existe un curso con el mismo nombre, horario y grupo.")
            return 0
        course_id = (
            max((int(item["id"]) for item in self.manifest["courses"]), default=0) + 1
        )
        self.manifest["courses"].append(
            {
                "id": course_id,
                "server_id": None,
                "name": name,
                "schedule": schedule,
                "group": group_name,
                "start_date": course_date,
                "enrollment_fee": enrollment_fee,
                "monthly_fee": monthly_fee,
                "capacity": capacity,
                "active": True,
            }
        )
        self._selected_course_id = course_id
        if not self._save():
            return 0
        self.selectionChanged.emit()
        self._set_error("Curso guardado localmente.")
        return course_id

    @Slot(str, result=int)
    def createPromoter(self, name):
        if not self.isNewCampus:
            self._set_error(
                "Los promotores se crean desde Desktop al preparar una sede nueva."
            )
            return 0
        name = name.strip().upper()
        if not name or len(name) > 120:
            self._set_error("Ingresa un nombre de promotor válido.")
            return 0
        if any(
            item["name"].strip().casefold() == name.casefold()
            for item in self.manifest["promoters"]
        ):
            self._set_error("Ya existe un promotor con ese nombre.")
            return 0
        promoter_id = (
            max((int(item["id"]) for item in self.manifest["promoters"]), default=0) + 1
        )
        self.manifest["promoters"].append(
            {"id": promoter_id, "server_id": None, "name": name, "active": True}
        )
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
        if not row:
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
        if not row or not row.get("record_image"):
            self._set_error("La matrícula seleccionada no tiene imagen de ficha.")
            return
        row["record_image"] = None
        row["record_image_hash"] = ""
        self._remove_unused_attachments()
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
        last_name = last_name.strip().upper()
        first_name = first_name.strip().upper()
        document_number = document_number.strip()
        phones = [value.strip() for value in phone_text.split(",") if value.strip()]
        if not last_name or not first_name:
            self._set_error("Apellidos y nombres son obligatorios.")
            return
        if len(last_name) > 120 or len(first_name) > 120 or len(document_number) > 20:
            self._set_error("Revisa la longitud de apellidos, nombres o DNI.")
            return
        if not phones or any(not PHONE_PATTERN.fullmatch(phone) for phone in phones):
            self._set_error("Ingresa uno o más celulares peruanos de 9 dígitos.")
            return
        if len(set(phones)) != len(phones):
            self._set_error("No repitas un teléfono.")
            return
        row = next(
            (item for item in self.manifest["students"] if item["id"] == source_id),
            None,
        )
        full_name = f"{last_name} {first_name}".strip().casefold()
        duplicate = any(
            item is not row
            and " ".join(
                part
                for part in (
                    str(item.get("last_name", "")).strip(),
                    str(item.get("first_name", "")).strip(),
                )
                if part
            )
            .strip()
            .casefold()
            == full_name
            for item in self.manifest["students"]
        )
        if duplicate:
            self._set_error("Ya existe un estudiante con estos apellidos y nombres.")
            return
        if row is None:
            row = {
                "id": str(uuid.uuid4()),
                "server_id": None,
                "base_hash": None,
                "active": True,
            }
            self.manifest["students"].append(row)
        row.update(
            {
                "last_name": last_name,
                "first_name": first_name,
                "document_number": document_number,
                "phone_numbers": phones,
            }
        )
        self._selected_student_id = row["id"]
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
        row = next(
            (item for item in self.manifest["enrollments"] if item["id"] == source_id),
            None,
        )
        if source_id and row is None:
            self._set_error("La matrícula seleccionada ya no existe.")
            return False
        try:
            student_id = str(fields.get("student_id") or "").strip() or None
            course_id = self._optional_integer(fields.get("course_id"), "curso")
            student = next(
                (
                    item
                    for item in self.manifest["students"]
                    if item["id"] == student_id
                ),
                None,
            )
            course = next(
                (item for item in self.manifest["courses"] if item["id"] == course_id),
                None,
            )
            if student_id and student is None:
                raise ValueError("Selecciona un estudiante válido.")
            if course_id and course is None:
                raise ValueError("Selecciona un curso válido.")
            if not student_id and not course_id:
                raise ValueError("La matrícula requiere un estudiante o un curso.")
            if row and row.get("student_id") and not student_id:
                raise ValueError(
                    "Una matrícula que ya tiene estudiante no puede quedarse sin él."
                )
            date_text = str(fields.get("enrollment_date", "")).strip()
            enrollment_date = date.fromisoformat(date_text)
            if enrollment_date.isoformat() != date_text:
                raise ValueError("La fecha de matrícula no es válida.")
            if course_id:
                enrollment_fee = self._amount(
                    fields.get("enrollment_fee"), "costo de matrícula"
                )
                monthly_fee = self._amount(fields.get("monthly_fee"), "mensualidad")
            else:
                enrollment_fee = monthly_fee = "0.00"
            code_text = str(
                fields.get(
                    "record_code",
                    row.get("record_code", "") if row else "",
                )
                or ""
            ).strip()
            if code_text and (
                len(code_text) > 50
                or not code_text.isascii()
                or not code_text.isdigit()
            ):
                raise ValueError("Ingrese solo números en el código de ficha.")
            record_code = int(code_text) if code_text else None
            if record_code is not None and not 0 < record_code <= 2_147_483_647:
                raise ValueError("El código de ficha debe ser un entero positivo.")
            raw_promoter_ids = (
                fields.get(
                    "promoter_ids",
                    row.get("promoter_ids", []) if row else [],
                )
                or []
            )
            if not isinstance(raw_promoter_ids, (list, tuple)):
                raise ValueError("Selecciona promotores válidos.")
            if any(isinstance(value, bool) for value in raw_promoter_ids):
                raise ValueError("Selecciona promotores válidos.")
            promoter_ids = [int(value) for value in raw_promoter_ids]
            if len(set(promoter_ids)) != len(promoter_ids):
                raise ValueError("Una matrícula no puede repetir promotores.")
            promoters_by_id = {item["id"]: item for item in self.manifest["promoters"]}
            if any(value not in promoters_by_id for value in promoter_ids):
                raise ValueError("Selecciona promotores válidos.")
            quality_text = str(
                fields.get(
                    "record_image_quality",
                    row.get("record_image_quality", 80) if row else 80,
                )
            ).strip()
            if quality_text not in ("60", "80", "90"):
                raise ValueError("La calidad de imagen de ficha no es válida.")
            record_image_quality = int(quality_text)
        except (ValueError, InvalidOperation, TypeError) as exc:
            self._set_error(str(exc) or "Revisa los datos de la matrícula.")
            return False

        if (
            student
            and not student["active"]
            and (not row or row.get("student_id") != student_id)
        ):
            self._set_error("No se puede matricular a un estudiante inactivo.")
            return False
        if (
            course
            and not course["active"]
            and (not row or row.get("course_id") != course_id)
        ):
            self._set_error("No se pueden crear matrículas en un curso inactivo.")
            return False
        if (
            student_id
            and course_id
            and any(
                item is not row
                and item.get("student_id") == student_id
                and item.get("course_id") == course_id
                for item in self.manifest["enrollments"]
            )
        ):
            self._set_error("Este estudiante ya está matriculado en este curso.")
            return False
        if record_code is not None and any(
            item is not row
            and item.get("record_code") not in (None, "")
            and int(item["record_code"]) == record_code
            and item.get("enrollment_date") == enrollment_date.isoformat()
            for item in self.manifest["enrollments"]
        ):
            self._set_error(
                "Este código de ficha ya está registrado en la misma fecha de matrícula."
            )
            return False
        if any(
            not promoters_by_id[pk]["active"]
            and (not row or pk not in row.get("promoter_ids", []))
            for pk in promoter_ids
        ):
            self._set_error("No se pueden asignar promotores inactivos.")
            return False
        if len(promoter_ids) > 1 and any(
            promoters_by_id[pk]["name"].upper() in ("PARTICULAR", "NN")
            for pk in promoter_ids
        ):
            self._set_error(
                "PARTICULAR y NN no se pueden combinar con otros promotores."
            )
            return False

        if row is None:
            row = {
                "id": str(uuid.uuid4()),
                "server_id": None,
                "base_hash": None,
                "active": True,
                "record_image": None,
                "record_image_hash": "",
                "record_image_quality": 80,
            }
            self.manifest["enrollments"].append(row)
        if not record_code:
            row["record_image"] = None
            row["record_image_hash"] = ""
            self._remove_unused_attachments()
        row.update(
            {
                "student_id": student_id,
                "student_server_id": student["server_id"] if student else None,
                "course_id": course_id,
                "enrollment_date": enrollment_date.isoformat(),
                "promoter_ids": promoter_ids,
                "enrollment_fee": enrollment_fee,
                "monthly_fee": monthly_fee,
                "record_code": record_code,
                "record_image_quality": record_image_quality,
            }
        )
        self._selected_enrollment_id = row["id"]
        if not self._save():
            return False
        self.selectionChanged.emit()
        self._set_error("Matrícula guardada en este dispositivo.")
        return True

    def _remove_unused_attachments(self):
        if not self.manifest:
            return
        referenced = {
            row["record_image"]
            for row in self.manifest["enrollments"]
            if row.get("record_image")
        }
        attachments = self.manifest.get("_attachment_data", {})
        self.manifest["_attachment_data"] = {
            path: content for path, content in attachments.items() if path in referenced
        }

    @staticmethod
    def _optional_integer(value, label):
        if value in (None, ""):
            return None
        result = int(value)
        if result < 1:
            raise ValueError(f"El {label} seleccionado no es válido.")
        return result

    @staticmethod
    def _amount(value, label):
        try:
            amount = Decimal(str(value).strip())
        except InvalidOperation as exc:
            raise ValueError(f"El {label} no es válido.") from exc
        if (
            not amount.is_finite()
            or amount < Decimal("0.01")
            or amount >= Decimal("100000000")
            or amount.as_tuple().exponent < -2
            or len(amount.as_tuple().digits) > 10
        ):
            raise ValueError(
                f"El {label} debe ser mayor que cero y tener hasta 2 decimales."
            )
        return format(amount, ".2f")

    @staticmethod
    def _local_path(value):
        url = QUrl(value)
        return url.toLocalFile() if url.isLocalFile() else value
