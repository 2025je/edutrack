import base64
import hashlib
import re
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from PySide6.QtCore import QObject, Property, QStandardPaths, Signal, Slot
from sqlalchemy.exc import SQLAlchemyError

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

    def __init__(self, store_path=None):
        super().__init__()
        if store_path is None:
            data_dir = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
            store_path = data_dir / "edutrack-desktop.sqlite3"
        self.store = LocalStore(store_path)
        self.manifest = self.store.load()
        self._selected_student_id = ""
        self._selected_enrollment_id = ""
        courses = self.manifest.get("courses", []) if self.manifest else []
        self._selected_course_id = courses[0]["id"] if courses else None
        self._error_message = ""

    @Property(str, notify=dataChanged)
    def campusName(self):
        return self.manifest.get("campus_name", "Sin archivo de sede") if self.manifest else "Sin archivo de sede"

    @Property(bool, notify=dataChanged)
    def hasWorkspace(self):
        return self.manifest is not None

    @Property(bool, notify=dataChanged)
    def isNewCampus(self):
        return bool(self.manifest and self.manifest.get("campus_mode") == "new")

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
                        part for part in (student["last_name"], student["first_name"]) if part
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
                    part for part in (student["last_name"], student["first_name"]) if part
                )
                if student
                else "Sin estudiante"
            )
            course_name = (
                f'{course["name"]} · {course["schedule"]} · Grupo {course["group"]}'
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
                        f'{course["name"]} · {course["schedule"]} · Grupo {course["group"]}'
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
                    f'{course["name"]} · {course["schedule"]} · Grupo {course["group"]}'
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
            (item for item in self.manifest["students"] if item["id"] == self._selected_student_id),
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

    def _course_students(self, course_id):
        students = {
            student["id"]: student for student in self.manifest["students"]
        }
        roster = {}
        for enrollment in self.manifest["enrollments"]:
            if (
                enrollment.get("course_id") != course_id
                or not enrollment.get("active", True)
            ):
                continue
            student = students.get(enrollment.get("student_id"))
            if not student or not student.get("active", True):
                continue
            roster[student["id"]] = {
                **student,
                "label": " ".join(
                    part for part in (student["last_name"], student["first_name"]) if part
                ),
            }
        return sorted(roster.values(), key=lambda row: row["label"].casefold())

    def _save(self):
        try:
            self.store.save(self.manifest)
        except (SQLAlchemyError, ValueError, KeyError, TypeError) as exc:
            self._set_error(f"No se pudieron guardar los cambios localmente: {exc}")
            return False
        self.dataChanged.emit()
        return True

    @Slot(str, str)
    def createWorkspace(self, campus_name, campus_address):
        if self.manifest:
            self._set_error("Ya hay una sede abierta en este dispositivo.")
            return
        campus_name = campus_name.strip()
        campus_address = campus_address.strip()
        if not campus_name or len(campus_name) > 120 or len(campus_address) > 200:
            self._set_error("Ingresa un nombre de sede válido y una dirección de hasta 200 caracteres.")
            return
        self.manifest = {
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
        self._selected_student_id = ""
        self._selected_enrollment_id = ""
        self._selected_course_id = None
        if not self._save():
            self.manifest = None
            self.dataChanged.emit()
            return
        self.selectionChanged.emit()
        self._set_error("Sede creada correctamente en este dispositivo.")

    @Slot(str)
    def openPackage(self, path):
        try:
            manifest = read_package(self._local_path(path))
            self.store.save(manifest)
            self.manifest = manifest
            self._selected_student_id = ""
            self._selected_enrollment_id = ""
            self._selected_course_id = next(
                (course["id"] for course in manifest["courses"]), None
            )
            self.dataChanged.emit()
            self.selectionChanged.emit()
            self._set_error("")
        except (PackageError, OSError, ValueError, SQLAlchemyError) as exc:
            self._set_error(str(exc))

    @Slot(str)
    def exportPackage(self, path):
        if not self.manifest:
            self._set_error("Primero abre una sede o crea una nueva en este dispositivo.")
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
            self._set_error("Primero abre una sede o crea una nueva en este dispositivo.")
            return 0
        name = name.strip().upper()
        schedule = schedule.strip().upper()
        group_name = group_name.strip()
        if not name or len(name) > 120 or not schedule or len(schedule) > 120:
            self._set_error("Ingresa un nombre de curso y un horario válidos.")
            return 0
        if (
            not group_name.isascii()
            or not group_name.isdigit()
            or int(group_name) < 1
            or len(group_name) > 50
        ):
            self._set_error("El grupo debe ser un número entero positivo.")
            return 0
        try:
            course_date = date.fromisoformat(start_date.strip()).isoformat()
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
        course_id = max((int(item["id"]) for item in self.manifest["courses"]), default=0) + 1
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
            self._set_error("Los promotores se crean desde Desktop al preparar una sede nueva.")
            return 0
        name = name.strip().upper()
        if not name or len(name) > 120:
            self._set_error("Ingresa un nombre de promotor válido.")
            return 0
        if any(item["name"].strip().casefold() == name.casefold() for item in self.manifest["promoters"]):
            self._set_error("Ya existe un promotor con ese nombre.")
            return 0
        promoter_id = max((int(item["id"]) for item in self.manifest["promoters"]), default=0) + 1
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
            self._set_error("Ingresa y guarda el código de ficha antes de adjuntar una imagen.")
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
        self.manifest.setdefault("_attachment_data", {})[package_path] = base64.b64encode(
            content
        ).decode("ascii")
        row["record_image"] = package_path
        row["record_image_hash"] = image_hash
        if not self._save():
            return
        self.selectionChanged.emit()
        self._set_error("Imagen de ficha guardada localmente.")

    @Slot()
    def clearEnrollmentImage(self):
        row = next(
            (
                item
                for item in self.manifest["enrollments"]
                if item["id"] == self._selected_enrollment_id
            ),
            None,
        ) if self.manifest else None
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
    def saveStudent(self, source_id, last_name, first_name, document_number, phone_text):
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
        if not phones or len(phones) > 20 or any(not PHONE_PATTERN.fullmatch(phone) for phone in phones):
            self._set_error("Ingresa entre 1 y 20 celulares peruanos de 9 dígitos.")
            return
        if len(set(phones)) != len(phones):
            self._set_error("No repitas un teléfono.")
            return
        row = next(
            (item for item in self.manifest["students"] if item["id"] == source_id),
            None,
        )
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
        try:
            student_id = fields.get("student_id") or None
            course_id = self._optional_integer(fields.get("course_id"), "curso")
            if student_id and not any(
                item["id"] == student_id for item in self.manifest["students"]
            ):
                raise ValueError("Selecciona un estudiante válido.")
            if course_id and not any(
                item["id"] == course_id for item in self.manifest["courses"]
            ):
                raise ValueError("Selecciona un curso válido.")
            if not student_id and not course_id:
                raise ValueError("La matrícula requiere un estudiante o un curso.")
            if not source_id and (not student_id or not course_id):
                raise ValueError("Una matrícula nueva requiere estudiante y curso.")
            enrollment_date = date.fromisoformat(str(fields.get("enrollment_date", "")).strip())
            enrollment_fee = self._amount(fields.get("enrollment_fee"), "costo de matrícula")
            monthly_fee = self._amount(fields.get("monthly_fee"), "mensualidad")
            code_text = str(fields.get("record_code", "")).strip()
            record_code = int(code_text) if code_text else None
            if record_code is not None and record_code < 1:
                raise ValueError("El código de ficha debe ser positivo.")
            promoter_ids = [int(value) for value in fields.get("promoter_ids", [])]
            valid_promoters = {item["id"] for item in self.manifest["promoters"]}
            if any(value not in valid_promoters for value in promoter_ids):
                raise ValueError("Selecciona promotores válidos.")
        except (ValueError, InvalidOperation) as exc:
            self._set_error(str(exc) or "Revisa los datos de la matrícula.")
            return False

        student = next(
            (item for item in self.manifest["students"] if item["id"] == student_id),
            None,
        )
        row = next(
            (item for item in self.manifest["enrollments"] if item["id"] == source_id),
            None,
        )
        if row is None:
            if not student["active"]:
                self._set_error("No se puede matricular a un estudiante inactivo.")
                return False
            selected_course = next(
                item for item in self.manifest["courses"] if item["id"] == course_id
            )
            if not selected_course["active"]:
                self._set_error("No se pueden crear matrículas en un curso inactivo.")
                return False
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
                "record_image_quality": int(fields.get("record_image_quality", 80)),
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
        if not amount.is_finite() or amount < Decimal("0.01") or amount.as_tuple().exponent < -2:
            raise ValueError(f"El {label} debe ser mayor que cero y tener hasta 2 decimales.")
        return format(amount, ".2f")

    @staticmethod
    def _local_path(value):
        return value.removeprefix("file:///").replace("/", "\\") if value.startswith("file:///") else value
