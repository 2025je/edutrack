import hashlib
import io
import json
import re
import uuid
import zipfile
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db.models import Q
from PIL import Image, UnidentifiedImageError

from .duplicates import name_key
from .installments import fee_conflicts, sync_initial_installments
from .models import Course, Enrollment, Ficha, Promoter, Student, StudentPhone

PACKAGE_FORMAT = "edutrack-offline"
SCHEMA_VERSION = 2
INITIAL_CAMPUS_VERSION = 3
MAX_PACKAGE_BYTES = 25 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_RECORDS = 2000
MAX_ARCHIVE_FILES = 4002
PHONE_PATTERN = re.compile(r"9\d{8}\Z")
HASH_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
ATTACHMENT_PATTERN = re.compile(r"attachments/[0-9a-f]{64}\.jpg\Z")

STUDENT_FIELDS = (
    "last_name",
    "first_name",
    "document_number",
    "phone_numbers",
    "active",
)
ENROLLMENT_FIELDS = (
    "student_server_id",
    "course_id",
    "enrollment_date",
    "promoter_ids",
    "enrollment_fee",
    "monthly_fee",
    "record_code",
    "record_image_hash",
    "active",
)


class OfflinePackageError(ValueError):
    pass


def _object(value, label):
    if not isinstance(value, dict):
        raise OfflinePackageError(f"{label} debe ser un objeto JSON.")
    return value


def _string(value, label, maximum, required=True):
    if not isinstance(value, str):
        raise OfflinePackageError(f"{label} debe ser texto.")
    result = value.strip()
    if required and not result:
        raise OfflinePackageError(f"{label} es obligatorio.")
    if len(result) > maximum:
        raise OfflinePackageError(f"{label} supera {maximum} caracteres.")
    return result


def _uuid_text(value, label):
    try:
        return str(uuid.UUID(_string(value, label, 36)))
    except (ValueError, AttributeError) as exc:
        raise OfflinePackageError(f"{label} no es un UUID válido.") from exc


def _positive_id(value, label, optional=False):
    if optional and value is None:
        return None
    if type(value) is not int or value < 1:
        raise OfflinePackageError(f"{label} debe ser un entero positivo.")
    return value


def _boolean(value, label):
    if type(value) is not bool:
        raise OfflinePackageError(f"{label} debe ser verdadero o falso.")
    return value


def _amount(value, label, allow_zero=False):
    if not isinstance(value, str):
        raise OfflinePackageError(f"{label} debe ser texto decimal.")
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise OfflinePackageError(f"{label} no es un importe válido.") from exc
    if (
        not amount.is_finite()
        or amount < (Decimal("0.00") if allow_zero else Decimal("0.01"))
        or amount.as_tuple().exponent < -2
        or len(amount.as_tuple().digits) > 10
    ):
        raise OfflinePackageError(f"{label} debe ser mayor que cero y tener hasta 2 decimales.")
    return format(amount, ".2f")


def _optional_hash(value, label, server_id):
    if server_id is None and value is None:
        return None
    if not isinstance(value, str) or not HASH_PATTERN.fullmatch(value):
        raise OfflinePackageError(f"{label} no es una huella válida.")
    return value


def _fingerprint(fields, row):
    values = {field: row[field] for field in fields}
    encoded = json.dumps(values, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def student_fingerprint(row):
    values = {
        "last_name": row["last_name"].strip().upper(),
        "first_name": row["first_name"].strip().upper(),
        "document_number": row["document_number"].strip(),
        "phone_numbers": list(row["phone_numbers"]),
        "active": row["active"],
    }
    return _fingerprint(STUDENT_FIELDS, values)


def enrollment_fingerprint(row):
    values = {
        "student_server_id": row["student_server_id"],
        "course_id": row["course_id"],
        "enrollment_date": row["enrollment_date"],
        "promoter_ids": sorted(row["promoter_ids"]),
        "enrollment_fee": format(Decimal(row["enrollment_fee"]), ".2f"),
        "monthly_fee": format(Decimal(row["monthly_fee"]), ".2f"),
        "record_code": row["record_code"],
        "record_image_hash": row["record_image_hash"],
        "active": row["active"],
    }
    return _fingerprint(ENROLLMENT_FIELDS, values)


def _student_values(student):
    phones = list(
        StudentPhone.objects.filter(student=student, invalid=False)
        .order_by("id")
        .values_list("number", flat=True)
    )
    if not phones:
        phones = [value.strip() for value in (student.phone or "").split(",") if value.strip()]
    return {
        "last_name": student.last_name,
        "first_name": student.first_name,
        "document_number": student.document_number,
        "phone_numbers": phones,
        "active": student.active,
    }


def _read_ficha_image(ficha):
    if not ficha or not ficha.image:
        return None, None, ""
    try:
        with ficha.image.open("rb") as image_file:
            data = image_file.read(MAX_ATTACHMENT_BYTES + 1)
    except OSError as exc:
        raise OfflinePackageError("No se pudo leer una imagen de ficha de la sede.") from exc
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise OfflinePackageError("Una imagen de ficha supera el máximo de 10 MB.")
    path = f"attachments/{hashlib.sha256(ficha.image.name.encode('utf-8')).hexdigest()}.jpg"
    return path, data, hashlib.sha256(data).hexdigest()


def _enrollment_values(enrollment, attachments=None):
    ficha = enrollment.ficha if hasattr(enrollment, "ficha") else None
    image_path, image_data, image_hash = _read_ficha_image(ficha)
    if image_path and attachments is not None:
        attachments[image_path] = image_data
    return {
        "student_server_id": enrollment.student_id,
        "course_id": enrollment.course_id,
        "enrollment_date": enrollment.enrollment_date.isoformat(),
        "promoter_ids": sorted(enrollment.promoter.values_list("pk", flat=True)),
        "enrollment_fee": format(enrollment.enrollment_fee, ".2f"),
        "monthly_fee": format(enrollment.monthly_fee, ".2f"),
        "record_code": ficha.code if ficha else None,
        "record_image": image_path,
        "record_image_hash": image_hash,
        "record_image_quality": 80,
        "active": enrollment.active,
    }


def export_campus(campus):
    students = list(Student.objects.filter(campus=campus).prefetch_related("phones").order_by("pk"))
    student_ids = {student.pk: str(uuid.uuid4()) for student in students}
    student_rows = []
    for student in students:
        values = _student_values(student)
        student_rows.append(
            {
                "id": student_ids[student.pk],
                "server_id": student.pk,
                "base_hash": student_fingerprint(values),
                **values,
            }
        )

    enrollment_rows = []
    attachments = {}
    enrollments = (
        Enrollment.objects.filter(campus=campus)
        .select_related("student", "course", "ficha")
        .prefetch_related("promoter")
        .order_by("pk")
    )
    for enrollment in enrollments:
        values = _enrollment_values(enrollment, attachments)
        enrollment_rows.append(
            {
                "id": str(uuid.uuid4()),
                "server_id": enrollment.pk,
                "base_hash": enrollment_fingerprint(values),
                "student_id": student_ids.get(enrollment.student_id),
                **values,
            }
        )

    courses = Course.objects.filter(campus=campus).order_by("name", "schedule", "group")
    promoters = (
        Promoter.objects.filter(Q(campuses=campus) | Q(campuses__isnull=True))
        .distinct()
        .order_by("name")
    )
    manifest = {
        "format": PACKAGE_FORMAT,
        "version": SCHEMA_VERSION,
        "bundle_id": str(uuid.uuid4()),
        "campus_id": campus.pk,
        "campus_name": campus.name,
        "campus_address": campus.address,
        "students": student_rows,
        "enrollments": enrollment_rows,
        "courses": [
            {
                "id": course.pk,
                "server_id": course.pk,
                "name": course.name,
                "schedule": course.schedule,
                "group": course.group,
                "start_date": course.start_date.isoformat() if course.start_date else None,
                "enrollment_fee": str(course.enrollment_fee or Decimal("0.00")),
                "monthly_fee": str(course.monthly_fee or Decimal("0.00")),
                "capacity": course.capacity,
                "active": course.active,
            }
            for course in courses
        ],
        "promoters": [
            {"id": promoter.pk, "name": promoter.name, "active": promoter.active}
            for promoter in promoters
        ],
    }
    return manifest, attachments


def package_bytes(manifest, attachments=None):
    attachments = attachments or {}
    if (
        len(manifest.get("students", [])) > MAX_RECORDS
        or len(manifest.get("enrollments", [])) > MAX_RECORDS
    ):
        raise OfflinePackageError(f"La sede supera el máximo de {MAX_RECORDS} registros por tipo.")
    if (
        len(attachments) + 1 > MAX_ARCHIVE_FILES
        or sum(len(data) for data in attachments.values()) > MAX_UNCOMPRESSED_BYTES
    ):
        raise OfflinePackageError("Las imágenes superan el límite descomprimido permitido.")
    encoded_manifest = json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    if (
        len(encoded_manifest) + sum(len(data) for data in attachments.values())
        > MAX_UNCOMPRESSED_BYTES
    ):
        raise OfflinePackageError("Los datos descomprimidos superan el límite permitido.")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", encoded_manifest)
        for name, content in attachments.items():
            if not ATTACHMENT_PATTERN.fullmatch(name) or len(content) > MAX_ATTACHMENT_BYTES:
                raise OfflinePackageError("La exportación contiene una imagen no permitida.")
            archive.writestr(name, content)
            if output.tell() > MAX_PACKAGE_BYTES:
                raise OfflinePackageError("La exportación supera el tamaño máximo de 25 MB.")
    payload = output.getvalue()
    if len(payload) > MAX_PACKAGE_BYTES:
        raise OfflinePackageError("La exportación supera el tamaño máximo de 25 MB.")
    return payload


def parse_package(data):
    if not data or len(data) > MAX_PACKAGE_BYTES:
        raise OfflinePackageError("El paquete está vacío o supera el tamaño máximo de 25 MB.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if not infos or len(infos) > MAX_ARCHIVE_FILES:
                raise OfflinePackageError(
                    "El paquete contiene una cantidad de archivos no permitida."
                )
            if len({item.filename for item in infos}) != len(infos):
                raise OfflinePackageError("El paquete contiene nombres de archivo repetidos.")
            if sum(item.file_size for item in infos) > MAX_UNCOMPRESSED_BYTES:
                raise OfflinePackageError("El contenido descomprimido supera el tamaño permitido.")
            members = {}
            for info in infos:
                name = info.filename
                path = PurePosixPath(name)
                if path.is_absolute() or "\\" in name or ".." in path.parts:
                    raise OfflinePackageError("El paquete contiene una ruta no permitida.")
                if name == "manifest.json" and not info.is_dir():
                    members[name] = info
                elif ATTACHMENT_PATTERN.fullmatch(name) and not info.is_dir():
                    if info.file_size > MAX_ATTACHMENT_BYTES:
                        raise OfflinePackageError(f"La imagen {name} supera el máximo de 10 MB.")
                    members[name] = info
                else:
                    raise OfflinePackageError(f"El archivo {name} no está permitido en el paquete.")
            if "manifest.json" not in members:
                raise OfflinePackageError("Falta manifest.json en el paquete.")
            raw = archive.read(members["manifest.json"])
            attachments = {}
            for name, info in members.items():
                if name == "manifest.json":
                    continue
                content = archive.read(info)
                try:
                    with Image.open(io.BytesIO(content)) as image:
                        if image.width * image.height > Image.MAX_IMAGE_PIXELS:
                            raise OfflinePackageError(
                                f"La imagen {name} supera la resolución permitida."
                            )
                        image.verify()
                except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
                    raise OfflinePackageError(f"La imagen {name} no es válida.") from exc
                attachments[name] = content
    except (zipfile.BadZipFile, RuntimeError) as exc:
        raise OfflinePackageError("El archivo no es un paquete EduTrack Desktop válido.") from exc
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OfflinePackageError("manifest.json no contiene JSON UTF-8 válido.") from exc
    return _parse_manifest(manifest, attachments)


def _parse_manifest(value, attachments):
    manifest = _object(value, "El manifiesto")
    version = manifest.get("version")
    if manifest.get("format") != PACKAGE_FORMAT or version not in (
        SCHEMA_VERSION,
        INITIAL_CAMPUS_VERSION,
    ):
        raise OfflinePackageError("La versión del paquete no es compatible.")
    is_new_campus = version == INITIAL_CAMPUS_VERSION
    if is_new_campus:
        if manifest.get("campus_mode") != "new" or manifest.get("campus_id") is not None:
            raise OfflinePackageError("El paquete inicial no contiene una sede nueva válida.")
        if not isinstance(manifest.get("bundle_id"), str):
            raise OfflinePackageError("El paquete inicial no contiene un identificador válido.")
    try:
        bundle_id = _uuid_text(manifest.get("bundle_id"), "bundle_id")
    except OfflinePackageError:
        raise
    campus_id = None if is_new_campus else _positive_id(manifest.get("campus_id"), "campus_id")
    campus_name = _string(manifest.get("campus_name"), "campus_name", 120)
    campus_address = _string(
        manifest.get("campus_address", ""),
        "campus_address",
        200,
        required=False,
    )
    raw_students = manifest.get("students")
    raw_enrollments = manifest.get("enrollments")
    raw_courses = manifest.get("courses")
    raw_promoters = manifest.get("promoters")
    if not all(
        isinstance(rows, list)
        for rows in (raw_students, raw_enrollments, raw_courses, raw_promoters)
    ):
        raise OfflinePackageError("students, enrollments, courses y promoters deben ser listas.")
    if any(
        len(rows) > MAX_RECORDS
        for rows in (raw_students, raw_enrollments, raw_courses, raw_promoters)
    ):
        raise OfflinePackageError(
            f"El paquete supera el máximo de {MAX_RECORDS} registros por tipo."
        )

    students = []
    student_ids = set()
    student_server_ids = set()
    for index, raw in enumerate(raw_students, start=1):
        row = _object(raw, f"students[{index}]")
        source_id = _uuid_text(row.get("id"), f"students[{index}].id")
        if source_id in student_ids:
            raise OfflinePackageError("El paquete repite un identificador de estudiante.")
        student_ids.add(source_id)
        server_id = _positive_id(row.get("server_id"), "server_id", optional=True)
        if server_id is not None and server_id in student_server_ids:
            raise OfflinePackageError("El paquete repite un identificador web de estudiante.")
        if server_id is not None:
            student_server_ids.add(server_id)
        last_name = _string(row.get("last_name"), "Apellidos", 120)
        first_name = _string(row.get("first_name"), "Nombres", 120)
        document_number = _string(row.get("document_number", ""), "DNI", 20, required=False)
        phones = row.get("phone_numbers")
        if not isinstance(phones, list) or not 1 <= len(phones) <= 20:
            raise OfflinePackageError(f"students[{index}] debe tener entre 1 y 20 teléfonos.")
        phones = [_string(phone, "Teléfono", 20) for phone in phones]
        if any(not PHONE_PATTERN.fullmatch(phone) for phone in phones) or len(set(phones)) != len(
            phones
        ):
            raise OfflinePackageError(
                f"students[{index}] contiene teléfonos inválidos o repetidos."
            )
        student = {
            "id": source_id,
            "server_id": server_id,
            "base_hash": _optional_hash(row.get("base_hash"), "base_hash", server_id),
            "last_name": last_name,
            "first_name": first_name,
            "document_number": document_number,
            "phone_numbers": phones,
            "active": _boolean(row.get("active"), "active"),
        }
        if is_new_campus and server_id is not None:
            raise OfflinePackageError("Un estudiante de una sede nueva no puede tener ID web.")
        if server_id is None and row.get("base_hash") is not None:
            raise OfflinePackageError("Un estudiante nuevo no puede tener base_hash.")
        students.append(student)

    enrollments = []
    enrollment_ids = set()
    enrollment_server_ids = set()
    referenced_attachments = set()
    for index, raw in enumerate(raw_enrollments, start=1):
        row = _object(raw, f"enrollments[{index}]")
        source_id = _uuid_text(row.get("id"), f"enrollments[{index}].id")
        if source_id in enrollment_ids:
            raise OfflinePackageError("El paquete repite un identificador de matrícula.")
        enrollment_ids.add(source_id)
        server_id = _positive_id(row.get("server_id"), "server_id", optional=True)
        if server_id is not None and server_id in enrollment_server_ids:
            raise OfflinePackageError("El paquete repite un identificador web de matrícula.")
        if server_id is not None:
            enrollment_server_ids.add(server_id)
        student_source_id = row.get("student_id")
        if student_source_id is not None:
            student_source_id = _uuid_text(student_source_id, "student_id")
            if student_source_id not in student_ids:
                raise OfflinePackageError(
                    f"enrollments[{index}] apunta a un estudiante inexistente."
                )
        student_server_id = _positive_id(
            row.get("student_server_id"), "student_server_id", optional=True
        )
        raw_date = _string(row.get("enrollment_date"), "Fecha de matrícula", 10)
        try:
            enrollment_date = date.fromisoformat(raw_date).isoformat()
        except ValueError as exc:
            raise OfflinePackageError(f"enrollments[{index}] tiene una fecha inválida.") from exc
        promoter_ids = row.get("promoter_ids", [])
        if not isinstance(promoter_ids, list):
            raise OfflinePackageError("promoter_ids debe ser una lista.")
        promoter_ids = [_positive_id(pk, "promoter_id") for pk in promoter_ids]
        if len(set(promoter_ids)) != len(promoter_ids):
            raise OfflinePackageError("Una matrícula repite promotores.")
        raw_code = row.get("record_code")
        if raw_code in (None, ""):
            record_code = None
        elif type(raw_code) is int and raw_code > 0:
            record_code = raw_code
        elif (
            isinstance(raw_code, str)
            and raw_code.isascii()
            and raw_code.isdigit()
            and int(raw_code) > 0
        ):
            record_code = int(raw_code)
        else:
            raise OfflinePackageError("El código de ficha debe ser un entero positivo.")
        if record_code and record_code > 2_147_483_647:
            raise OfflinePackageError("El código de ficha supera el máximo permitido.")
        image_path = row.get("record_image")
        image_hash = row.get("record_image_hash", "")
        if image_path in (None, ""):
            image_path = None
            if image_hash not in ("", None):
                raise OfflinePackageError("La huella de imagen requiere un archivo asociado.")
            image_hash = ""
        elif not isinstance(image_path, str) or not ATTACHMENT_PATTERN.fullmatch(image_path):
            raise OfflinePackageError("La ruta de imagen de ficha no es válida.")
        else:
            if not record_code:
                raise OfflinePackageError("La imagen de ficha requiere un código de ficha.")
            if image_path not in attachments:
                raise OfflinePackageError(f"Falta la imagen {image_path}.")
            if not isinstance(image_hash, str) or not HASH_PATTERN.fullmatch(image_hash):
                raise OfflinePackageError("La huella de imagen de ficha no es válida.")
            if hashlib.sha256(attachments[image_path]).hexdigest() != image_hash:
                raise OfflinePackageError(f"La imagen {image_path} no coincide con su huella.")
            referenced_attachments.add(image_path)
        quality = row.get("record_image_quality", 80)
        if type(quality) is not int or quality not in (60, 80, 90):
            raise OfflinePackageError("La calidad de imagen de ficha no es válida.")
        enrollment = {
            "id": source_id,
            "server_id": server_id,
            "base_hash": _optional_hash(row.get("base_hash"), "base_hash", server_id),
            "student_id": student_source_id,
            "student_server_id": student_server_id,
            "course_id": _positive_id(row.get("course_id"), "course_id", optional=True),
            "enrollment_date": enrollment_date,
            "promoter_ids": promoter_ids,
            "enrollment_fee": _amount(row.get("enrollment_fee"), "Costo de matrícula"),
            "monthly_fee": _amount(row.get("monthly_fee"), "Mensualidad"),
            "record_code": record_code,
            "record_image": image_path,
            "record_image_hash": image_hash,
            "record_image_quality": quality,
            "active": _boolean(row.get("active"), "active"),
        }
        if is_new_campus and (
            server_id is not None
            or student_server_id is not None
            or row.get("base_hash") is not None
        ):
            raise OfflinePackageError("Una matrícula de una sede nueva no puede tener IDs web.")
        if server_id is None and row.get("base_hash") is not None:
            raise OfflinePackageError("Una matrícula nueva no puede tener base_hash.")
        if student_source_id:
            linked = next(student for student in students if student["id"] == student_source_id)
            if linked["server_id"] != student_server_id:
                raise OfflinePackageError(
                    f"enrollments[{index}] no coincide con el identificador web del estudiante."
                )
        elif student_server_id is not None:
            raise OfflinePackageError(
                "Una matrícula sin estudiante no puede tener student_server_id."
            )
        enrollments.append(enrollment)

    if referenced_attachments != set(attachments):
        raise OfflinePackageError("El paquete contiene imágenes no asociadas a una matrícula.")

    courses = []
    course_ids = set()
    course_server_ids = set()
    for raw in raw_courses:
        row = _object(raw, "course")
        course_id = _positive_id(row.get("id"), "course.id")
        if course_id in course_ids:
            raise OfflinePackageError("El paquete repite un identificador de curso.")
        course_ids.add(course_id)
        if is_new_campus and row.get("server_id") is not None:
            raise OfflinePackageError("Un curso de una sede nueva no puede tener ID web.")
        server_id = (
            None
            if is_new_campus
            else _positive_id(row.get("server_id", course_id), "course.server_id", optional=True)
        )
        if server_id is not None and server_id in course_server_ids:
            raise OfflinePackageError("El paquete repite un identificador web de curso.")
        if server_id is not None:
            course_server_ids.add(server_id)
        start_date = row.get("start_date")
        if is_new_campus or server_id is None:
            if not isinstance(start_date, str):
                raise OfflinePackageError("La fecha de inicio del curso es obligatoria.")
            try:
                start_date = date.fromisoformat(start_date).isoformat()
            except ValueError as exc:
                raise OfflinePackageError("La fecha de inicio del curso no es válida.") from exc
        group = _string(row.get("group"), "course.group", 50)
        if (is_new_campus or server_id is None) and not (
            group.isascii() and group.isdigit() and int(group) > 0
        ):
            raise OfflinePackageError("El grupo del curso debe ser un entero positivo.")
        courses.append(
            {
                "id": course_id,
                "server_id": server_id,
                "name": _string(row.get("name"), "course.name", 120),
                "schedule": _string(row.get("schedule"), "course.schedule", 120),
                "group": group,
                "start_date": start_date,
                "enrollment_fee": _amount(
                    row.get("enrollment_fee", "0.00"),
                    "Costo del curso",
                    allow_zero=not is_new_campus,
                ),
                "monthly_fee": _amount(
                    row.get("monthly_fee", "0.00"),
                    "Mensualidad del curso",
                    allow_zero=not is_new_campus,
                ),
                "capacity": (
                    _positive_id(row.get("capacity"), "course.capacity")
                    if is_new_campus or server_id is None
                    else row.get("capacity")
                ),
                "active": _boolean(row.get("active"), "course.active"),
            }
        )
    promoters = []
    promoter_ids = set()
    for raw in raw_promoters:
        row = _object(raw, "promoter")
        promoter_id = _positive_id(row.get("id"), "promoter.id")
        if promoter_id in promoter_ids:
            raise OfflinePackageError("El paquete repite un identificador de promotor.")
        promoter_ids.add(promoter_id)
        if is_new_campus and row.get("server_id") is not None:
            raise OfflinePackageError("Un promotor de una sede nueva no puede tener ID web.")
        promoters.append(
            {
                "id": promoter_id,
                "name": _string(row.get("name"), "promoter.name", 120),
                "active": _boolean(row.get("active"), "promoter.active"),
            }
        )
    if is_new_campus:
        for enrollment in enrollments:
            if enrollment["course_id"] not in course_ids:
                raise OfflinePackageError("Una matrícula apunta a un curso inexistente.")
            if any(pk not in promoter_ids for pk in enrollment["promoter_ids"]):
                raise OfflinePackageError("Una matrícula apunta a un promotor inexistente.")
    return {
        "bundle_id": bundle_id,
        "version": version,
        "campus_mode": "new" if is_new_campus else "existing",
        "campus_id": campus_id,
        "campus_name": campus_name,
        "campus_address": campus_address,
        "students": students,
        "enrollments": enrollments,
        "courses": courses,
        "promoters": promoters,
        "attachments": attachments,
    }


def _row(kind, record, state, message=""):
    return {
        "kind": kind,
        "source_id": record["id"],
        "server_id": record["server_id"],
        "label": (
            f"{record['last_name']} {record['first_name']}".strip() if kind == "student" else ""
        ),
        "state": state,
        "message": message,
        "resolvable": message.startswith("El registro cambió en la web después de exportarlo."),
    }


def _sync_state(record, current, fingerprint):
    if record["server_id"] is None:
        return "new", ""
    if current is None:
        return "error", "El registro ya no existe en la web; no se puede actualizar."
    current_hash = fingerprint(current)
    incoming_hash = fingerprint(record)
    if incoming_hash == current_hash or incoming_hash == record["base_hash"]:
        return "unchanged", ""
    if current_hash != record["base_hash"]:
        return "conflict", "El registro cambió en la web después de exportarlo."
    return "update", ""


def _course_key(course):
    if isinstance(course, Course):
        name, schedule, group = course.name, course.schedule, course.group
    else:
        name, schedule, group = course["name"], course["schedule"], course["group"]
    return (
        str(name).strip().casefold(),
        str(schedule).strip().casefold(),
        str(group).strip().casefold(),
    )


def _course_from_package(item, campus):
    start_date = date.fromisoformat(item["start_date"]) if item["start_date"] else None
    return Course(
        campus=campus,
        name=item["name"].upper(),
        schedule=item["schedule"].upper(),
        group=item["group"],
        capacity=item["capacity"],
        start_date=start_date,
        enrollment_fee=Decimal(item["enrollment_fee"]),
        monthly_fee=Decimal(item["monthly_fee"]),
        active=item["active"],
    )


def _course_matches(current, incoming):
    return (
        current.name.strip().casefold() == incoming.name.strip().casefold()
        and current.schedule.strip().casefold() == incoming.schedule.strip().casefold()
        and current.group.strip().casefold() == incoming.group.strip().casefold()
        and current.capacity == incoming.capacity
        and current.start_date == incoming.start_date
        and Decimal(current.enrollment_fee or 0) == incoming.enrollment_fee
        and Decimal(current.monthly_fee or 0) == incoming.monthly_fee
        and current.active == incoming.active
    )


def review_courses(package, campus):
    existing = {course.pk: course for course in Course.objects.filter(campus=campus)}
    existing_by_key = {_course_key(course): course for course in existing.values()}
    course_map = {}
    pending_keys = set()
    rows = []
    for item in package["courses"]:
        server_id = item["server_id"]
        row = {
            "kind": "course",
            "source_id": item["id"],
            "server_id": server_id,
            "label": f"{item['name']} · {item['schedule']} · Grupo {item['group']}",
            "state": "unchanged",
            "message": "",
            "resolvable": False,
        }
        if server_id is not None:
            current = existing.get(server_id)
            if current is None:
                row["state"] = "error"
                row["message"] = "El curso ya no existe en la sede."
            else:
                course_map[item["id"]] = current
            rows.append(row)
            continue

        try:
            incoming = _course_from_package(item, campus)
        except (ValueError, InvalidOperation) as exc:
            row["state"] = "error"
            row["message"] = str(exc) or "La fecha del curso no es válida."
            rows.append(row)
            continue

        key = _course_key(item)
        current = existing_by_key.get(key)
        if current:
            course_map[item["id"]] = current
            if not _course_matches(current, incoming):
                row["message"] = (
                    "Ya existe un curso con el mismo nombre, horario y grupo; "
                    "se conservarán sus datos web."
                )
        elif key in pending_keys:
            row["state"] = "error"
            row["message"] = "El paquete repite un curso nuevo con los mismos datos."
        else:
            try:
                incoming.full_clean()
            except ValidationError as exc:
                row["state"] = "error"
                row["message"] = (
                    "; ".join(text for messages in exc.message_dict.values() for text in messages)
                    if hasattr(exc, "message_dict")
                    else "; ".join(exc.messages)
                )
            else:
                row["state"] = "new"
                row["message"] = "Se creará en la sede."
                course_map[item["id"]] = incoming
                pending_keys.add(key)
        rows.append(row)
    return rows, course_map


def review_package(package, campus, resolutions=None):
    if package["campus_id"] != campus.pk:
        raise OfflinePackageError("El archivo pertenece a otra sede.")
    resolutions = resolutions or {}
    existing_students = {
        item.pk: item for item in Student.objects.filter(campus=campus).prefetch_related("phones")
    }
    student_rows = []
    student_states = {}
    for student in package["students"]:
        current = existing_students.get(student["server_id"])
        state, message = _sync_state(
            student,
            _student_values(current) if current else None,
            student_fingerprint,
        )
        resolution = resolutions.get(f"student:{student['id']}")
        if state == "conflict" and resolution in ("web", "desktop"):
            if resolution == "web":
                state, message = "unchanged", "Se conservará la versión web."
            elif current:
                state, message = "update", "Se aplicará la versión Desktop elegida."
            else:
                state, message = (
                    "error",
                    "No se puede restaurar automáticamente un registro eliminado.",
                )
        student_states[student["id"]] = state
        student_rows.append(_row("student", student, state, message))

    existing_name_keys = {name_key(item.full_name): item.pk for item in existing_students.values()}
    existing_documents = {
        item.document_number.strip().casefold(): item.pk
        for item in existing_students.values()
        if item.document_number.strip()
    }
    pending_names = {}
    pending_documents = {}
    for student in package["students"]:
        if student_states[student["id"]] not in ("new", "update"):
            continue
        current_id = student["server_id"]
        full_name = " ".join((student["last_name"], student["first_name"])).strip()
        key = name_key(full_name)
        document = student["document_number"].strip().casefold()
        duplicate = (
            existing_name_keys.get(key) not in (None, current_id)
            or (document and existing_documents.get(document) not in (None, current_id))
            or (key in pending_names and pending_names[key] != student["id"])
            or (
                document
                and document in pending_documents
                and pending_documents[document] != student["id"]
            )
        )
        model = Student(
            campus=campus,
            full_name=full_name,
            last_name=student["last_name"],
            first_name=student["first_name"],
            document_number=student["document_number"],
            phone=", ".join(student["phone_numbers"]),
            active=student["active"],
        )
        try:
            if duplicate:
                raise ValidationError("Ya existe otro estudiante con el mismo nombre o DNI.")
            model.full_clean(validate_unique=False, validate_constraints=False)
            for number in student["phone_numbers"]:
                StudentPhone(number=number).full_clean(
                    exclude=["student"],
                    validate_unique=False,
                    validate_constraints=False,
                )
        except ValidationError as exc:
            student_states[student["id"]] = "error"
            row = next(item for item in student_rows if item["source_id"] == student["id"])
            row["state"] = "error"
            row["message"] = (
                "; ".join(text for messages in exc.message_dict.values() for text in messages)
                if hasattr(exc, "message_dict")
                else "; ".join(exc.messages)
            )
        else:
            pending_names[key] = student["id"]
            if document:
                pending_documents[document] = student["id"]

    _, courses = review_courses(package, campus)
    promoters = {
        item.pk: item
        for item in Promoter.objects.filter(
            Q(campuses=campus) | Q(campuses__isnull=True)
        ).distinct()
    }
    enrollments = {
        item.pk: item
        for item in Enrollment.objects.filter(campus=campus)
        .select_related("student", "course", "ficha")
        .prefetch_related("promoter")
    }
    existing_codes = {
        (item.enrollment_date, item.ficha.code): item.pk
        for item in enrollments.values()
        if hasattr(item, "ficha")
    }
    enrollment_rows = []
    enrollment_states = {}
    seen_pairs = {}
    seen_codes = {}
    for enrollment in package["enrollments"]:
        current = enrollments.get(enrollment["server_id"])
        course = courses.get(enrollment["course_id"])
        state, message = _sync_state(
            enrollment,
            _enrollment_values(current) if current else None,
            enrollment_fingerprint,
        )
        resolution = resolutions.get(f"enrollment:{enrollment['id']}")
        if state == "conflict" and resolution in ("web", "desktop"):
            if resolution == "web":
                state, message = "unchanged", "Se conservará la versión web."
            elif current:
                state, message = "update", "Se aplicará la versión Desktop elegida."
            else:
                state, message = (
                    "error",
                    "No se puede restaurar automáticamente una matrícula eliminada.",
                )
        enrollment_states[enrollment["id"]] = state

        if state in ("new", "update"):
            linked_student = (
                next(
                    (
                        item
                        for item in package["students"]
                        if item["id"] == enrollment["student_id"]
                    ),
                    None,
                )
                if enrollment["student_id"]
                else None
            )
            target_student_id = (
                linked_student["server_id"]
                if linked_student and linked_student["server_id"]
                else None
            )
            if linked_student and student_states[linked_student["id"]] == "error":
                state, message = "error", "El estudiante vinculado tiene datos inválidos."
            elif (
                linked_student
                and not linked_student["active"]
                and (not current or current.student_id != linked_student["server_id"])
            ):
                state, message = "error", "No se puede matricular a un estudiante inactivo."
            elif linked_student and student_states[linked_student["id"]] == "conflict":
                state, message = "omitted", "Resuelve primero el conflicto del estudiante."
            elif not linked_student and not enrollment["course_id"]:
                state, message = "error", "La matrícula necesita un estudiante o un curso."
            elif not linked_student and enrollment["server_id"] is None:
                state, message = "error", "Una matrícula nueva debe tener un estudiante."
            elif enrollment["course_id"] and course is None:
                state, message = "error", "El curso ya no existe o pertenece a otra sede."
            elif enrollment["course_id"] and not course.active:
                if not current or current.course_id != enrollment["course_id"]:
                    state, message = (
                        "error",
                        "No se pueden asignar matrículas nuevas a un curso inactivo.",
                    )
            elif any(pk not in promoters for pk in enrollment["promoter_ids"]):
                state, message = "error", "Uno o más promotores ya no pertenecen a esta sede."
            elif any(
                not promoters[pk].active
                and (not current or pk not in current.promoter.values_list("pk", flat=True))
                for pk in enrollment["promoter_ids"]
            ):
                state, message = "error", "No se pueden asignar promotores inactivos."
            elif len(enrollment["promoter_ids"]) > 1 and any(
                promoters[pk].name in ("PARTICULAR", "NN") for pk in enrollment["promoter_ids"]
            ):
                state, message = "error", "PARTICULAR y NN no se combinan con otros promotores."
            elif enrollment["record_image"] and not enrollment["record_code"]:
                state, message = "error", "La imagen de ficha requiere un código de ficha."
            else:
                linked_id = target_student_id or (
                    current.student_id if current and not linked_student else None
                )
                duplicate_pair = (
                    Enrollment.objects.filter(
                        student_id=linked_id, course_id=enrollment["course_id"]
                    )
                    .exclude(pk=current.pk if current else None)
                    .exists()
                    if linked_id and enrollment["course_id"]
                    else False
                )
                pair_key = (
                    linked_student["id"] if linked_student else None,
                    enrollment["course_id"],
                )
                code_key = (
                    date.fromisoformat(enrollment["enrollment_date"]),
                    enrollment["record_code"],
                )
                if duplicate_pair or (
                    enrollment["course_id"]
                    and pair_key in seen_pairs
                    and seen_pairs[pair_key] != enrollment["id"]
                ):
                    state, message = "error", "El estudiante ya está matriculado en ese curso."
                elif enrollment["record_code"] and (
                    existing_codes.get(code_key) not in (None, current.pk if current else None)
                    or (code_key in seen_codes and seen_codes[code_key] != enrollment["id"])
                ):
                    state, message = "error", "El código de ficha ya existe para esa fecha y sede."
                elif current:
                    fee_errors = fee_conflicts(
                        list(current.installments.select_related()),
                        {
                            "enrollment_fee": Decimal(enrollment["enrollment_fee"]),
                            "monthly_fee": Decimal(enrollment["monthly_fee"]),
                        },
                    )
                    if fee_errors:
                        state, message = "error", "; ".join(error for _, error in fee_errors)
                if state in ("new", "update"):
                    if enrollment["course_id"]:
                        seen_pairs[pair_key] = enrollment["id"]
                    if enrollment["record_code"]:
                        seen_codes[code_key] = enrollment["id"]

        enrollment_states[enrollment["id"]] = state
        label = "Matrícula"
        if enrollment["student_id"]:
            linked = next(
                item for item in package["students"] if item["id"] == enrollment["student_id"]
            )
            label = f"{linked['last_name']} {linked['first_name']}".strip()
        row = _row("enrollment", enrollment, state, message)
        row["label"] = label
        enrollment_rows.append(row)

    return student_rows, enrollment_rows


def import_initial_package(package, request):
    from django.core.exceptions import ValidationError
    from django.db import IntegrityError, transaction

    from core.models import Campus

    from .models import Schedule

    if package.get("campus_mode") != "new":
        raise OfflinePackageError("El paquete no contiene una sede inicial.")
    if not request.user.has_perm("core.add_campus"):
        raise OfflinePackageError("No tienes permiso para crear una sede nueva.")
    if Campus.objects.filter(desktop_bundle_id=package["bundle_id"]).exists():
        raise OfflinePackageError("Este paquete inicial ya fue importado.")
    if Campus.objects.filter(name__iexact=package["campus_name"]).exists():
        raise OfflinePackageError("Ya existe una sede con ese nombre.")

    previous_campus_id = request.session.get("selected_campus_id")
    imported = False
    try:
        with transaction.atomic():
            campus = Campus(
                name=package["campus_name"],
                address=package["campus_address"],
                desktop_bundle_id=package["bundle_id"],
            )
            campus.full_clean()
            campus.save()
            campus.users.add(request.user)

            promoter_map = {}
            for item in package["promoters"]:
                promoter = Promoter.objects.filter(name__iexact=item["name"]).first()
                if promoter is None:
                    promoter = Promoter.objects.create(
                        name=item["name"],
                        active=item["active"],
                    )
                elif promoter.active != item["active"]:
                    raise OfflinePackageError(
                        f'El promotor "{item["name"]}" ya existe con otro estado.'
                    )
                promoter.campuses.add(campus)
                promoter_map[item["id"]] = promoter.pk

            course_map = {}
            for item in package["courses"]:
                Schedule.objects.get_or_create(campus=campus, name=item["schedule"])
                course = Course(
                    campus=campus,
                    name=item["name"],
                    schedule=item["schedule"],
                    group=item["group"],
                    capacity=item["capacity"],
                    start_date=date.fromisoformat(item["start_date"]),
                    enrollment_fee=Decimal(item["enrollment_fee"]),
                    monthly_fee=Decimal(item["monthly_fee"]),
                    active=item["active"],
                )
                course.full_clean()
                course.save()
                course_map[item["id"]] = course.pk

            imported_package = {
                **package,
                "version": SCHEMA_VERSION,
                "campus_mode": "existing",
                "campus_id": campus.pk,
                "courses": [
                    {**item, "server_id": course_map[item["id"]]} for item in package["courses"]
                ],
                "enrollments": [
                    {
                        **item,
                        "promoter_ids": [promoter_map[pk] for pk in item["promoter_ids"]],
                    }
                    for item in package["enrollments"]
                ],
            }
            request.session["selected_campus_id"] = campus.pk
            counts = import_package(imported_package, campus, request)
        imported = True
    except OfflinePackageError:
        raise
    except (IntegrityError, ValidationError, Course.DoesNotExist) as exc:
        raise OfflinePackageError(
            "No se creó la sede porque los datos del paquete dejaron de ser válidos."
        ) from exc
    finally:
        if not imported:
            if previous_campus_id is None:
                request.session.pop("selected_campus_id", None)
            else:
                request.session["selected_campus_id"] = previous_campus_id
    return campus, counts[1:]


def import_package(package, campus, request, resolutions=None, allowed_changes=None):
    from django.db import IntegrityError, transaction

    from core.activity import record
    from core.models import ActivityLog
    from payments.models import Installment
    from .images import to_jpeg
    from .models import Schedule

    resolutions = resolutions or {}
    allowed_changes = allowed_changes or {
        "course": True,
        "student": True,
        "enrollment": True,
    }
    created_courses = 0
    created_students = updated_students = created_enrollments = updated_enrollments = 0
    try:
        with transaction.atomic():
            list(Student.objects.select_for_update().filter(campus=campus))
            list(
                Enrollment.objects.select_for_update(of=("self",)).filter(campus=campus).order_by()
            )
            list(Course.objects.select_for_update().filter(campus=campus))
            student_rows, enrollment_rows = review_package(package, campus, resolutions)
            course_rows, course_map = review_courses(package, campus)
            for rows, kind in (
                (student_rows, "student"),
                (enrollment_rows, "enrollment"),
            ):
                if not allowed_changes.get(kind, False):
                    for row in rows:
                        if row["state"] == "update":
                            row["state"] = "error"
                            row["message"] = "No tienes permiso para modificar este registro."
            if not allowed_changes.get("course", False):
                for row in course_rows:
                    if row["state"] == "new":
                        row["state"] = "error"
                        row["message"] = "No tienes permiso para crear cursos."
            blocked_course_ids = {
                row["source_id"] for row in course_rows if row["state"] == "error"
            }
            for enrollment in package["enrollments"]:
                if enrollment["course_id"] not in blocked_course_ids:
                    continue
                row = next(
                    item for item in enrollment_rows if item["source_id"] == enrollment["id"]
                )
                if row["state"] in ("new", "update"):
                    row["state"] = "error"
                    row["message"] = "El curso vinculado no se pudo crear o validar."
            if any(
                row["state"] == "conflict" for row in student_rows + enrollment_rows + course_rows
            ):
                raise OfflinePackageError(
                    "Los datos cambiaron durante la revisión. Actualiza la vista previa y resuelve los conflictos."
                )
            student_states = {row["source_id"]: row["state"] for row in student_rows}
            enrollment_states = {row["source_id"]: row["state"] for row in enrollment_rows}
            course_states = {row["source_id"]: row["state"] for row in course_rows}
            for course in package["courses"]:
                if course_states[course["id"]] != "new":
                    continue
                model = _course_from_package(course, campus)
                Schedule.objects.get_or_create(campus=campus, name=model.schedule)
                model.full_clean()
                model.save()
                course_map[course["id"]] = model
                created_courses += 1
            student_map = {
                student["id"]: Student.objects.get(pk=student["server_id"], campus=campus)
                for student in package["students"]
                if student["server_id"] and student_states[student["id"]] in ("unchanged", "update")
            }
            for student in package["students"]:
                state = student_states[student["id"]]
                if state not in ("new", "update"):
                    continue
                model = student_map.get(student["id"])
                created = model is None
                if created:
                    model = Student(campus=campus)
                model.full_name = f"{student['last_name']} {student['first_name']}".strip()
                model.last_name = student["last_name"]
                model.first_name = student["first_name"]
                model.document_number = student["document_number"]
                model.phone = ", ".join(student["phone_numbers"])
                model.active = student["active"]
                model.full_clean()
                model.save()
                StudentPhone.objects.filter(student=model, invalid=False).delete()
                StudentPhone.objects.bulk_create(
                    [
                        StudentPhone(student=model, number=number)
                        for number in student["phone_numbers"]
                    ]
                )
                student_map[student["id"]] = model
                if created:
                    created_students += 1
                else:
                    updated_students += 1

            for enrollment in package["enrollments"]:
                state = enrollment_states[enrollment["id"]]
                if state not in ("new", "update"):
                    continue
                current = (
                    Enrollment.objects.select_for_update(of=("self",))
                    .filter(pk=enrollment["server_id"], campus=campus)
                    .first()
                    if enrollment["server_id"]
                    else None
                )
                created = current is None
                model = current or Enrollment(campus=campus)
                linked = (
                    student_map.get(enrollment["student_id"]) if enrollment["student_id"] else None
                )
                model.student = linked
                model.course = course_map.get(enrollment["course_id"])
                model.enrollment_date = date.fromisoformat(enrollment["enrollment_date"])
                model.enrollment_fee = Decimal(enrollment["enrollment_fee"])
                model.monthly_fee = Decimal(enrollment["monthly_fee"])
                model.active = enrollment["active"]
                model.full_clean()
                model.save()
                model.promoter.set(enrollment["promoter_ids"])
                if enrollment["record_code"]:
                    ficha = Ficha.objects.filter(enrollment=model).first()
                    old_image_name = ficha.image.name if ficha and ficha.image else ""
                    old_image_storage = ficha.image.storage if old_image_name else None
                    if ficha:
                        ficha.code = enrollment["record_code"]
                        ficha.date = model.enrollment_date
                        ficha.campus = campus
                    else:
                        ficha = Ficha(
                            enrollment=model,
                            campus=campus,
                            date=model.enrollment_date,
                            code=enrollment["record_code"],
                        )
                    if enrollment["record_image"]:
                        uploaded = ContentFile(
                            package["attachments"][enrollment["record_image"]],
                            name=PurePosixPath(enrollment["record_image"]).name,
                        )
                        ficha.image = to_jpeg(uploaded, str(enrollment["record_image_quality"]))
                    elif ficha.image:
                        ficha.image = ""
                    ficha.full_clean()
                    ficha.save()
                    if old_image_name and old_image_storage and old_image_name != ficha.image.name:
                        transaction.on_commit(
                            lambda storage=old_image_storage, name=old_image_name: storage.delete(
                                name
                            )
                        )
                elif current:
                    ficha = Ficha.objects.filter(enrollment=model).first()
                    if ficha:
                        image_name = ficha.image.name if ficha.image else ""
                        image_storage = ficha.image.storage if image_name else None
                        ficha.delete()
                        if image_storage:
                            transaction.on_commit(
                                lambda storage=image_storage, name=image_name: storage.delete(name)
                            )
                else:
                    ficha = Ficha.objects.filter(enrollment=model).first()
                    if ficha and ficha.image:
                        image_name = ficha.image.name
                        image_storage = ficha.image.storage
                        ficha.image = ""
                        ficha.save(update_fields=["image"])
                        transaction.on_commit(
                            lambda storage=image_storage, name=image_name: storage.delete(name)
                        )
                installments = list(
                    Installment.objects.select_for_update().filter(enrollment=model)
                )
                if current:
                    conflicts = fee_conflicts(
                        installments,
                        {
                            "enrollment_fee": model.enrollment_fee,
                            "monthly_fee": model.monthly_fee,
                        },
                    )
                    if conflicts:
                        raise OfflinePackageError(
                            "No se puede actualizar una matrícula por pagos ya registrados."
                        )
                sync_initial_installments(model, installments)
                if created:
                    created_enrollments += 1
                else:
                    updated_enrollments += 1
    except (IntegrityError, ValidationError, Course.DoesNotExist) as exc:
        raise OfflinePackageError(
            "No se guardaron cambios porque los datos dejaron de ser válidos. "
            "Vuelve a generar la vista previa."
        ) from exc

    if created_courses or created_students or created_enrollments:
        record(
            request,
            ActivityLog.Action.CREATE,
            f"Sincronizó desde desktop: {created_courses} curso(s), "
            f"{created_students} estudiante(s) y "
            f"{created_enrollments} matrícula(s) nuevos",
        )
    if updated_students or updated_enrollments:
        record(
            request,
            ActivityLog.Action.UPDATE,
            f"Sincronizó desde desktop: {updated_students} estudiante(s) y "
            f"{updated_enrollments} matrícula(s) actualizados",
        )
    return (
        created_courses,
        created_students,
        updated_students,
        created_enrollments,
        updated_enrollments,
    )
