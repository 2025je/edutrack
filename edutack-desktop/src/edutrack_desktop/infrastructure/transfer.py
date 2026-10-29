import base64
import hashlib
import io
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path
from pathlib import PurePosixPath

from pydantic import ValidationError

from .schemas import (
    EnrollmentManifestRecord,
    ManifestEnvelope,
    StudentManifestRecord,
)

PACKAGE_FORMAT = "edutrack-offline"
SCHEMA_VERSION = 2
INITIAL_CAMPUS_VERSION = 3
MAX_PACKAGE_BYTES = 25 * 1024 * 1024
MAX_MANIFEST_BYTES = 50 * 1024 * 1024
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_ARCHIVE_FILES = 4002
ATTACHMENT_PATTERN = re.compile(r"attachments/[0-9a-f]{64}\.jpg\Z")


class PackageError(ValueError):
    pass


def read_package(path):
    try:
        payload = Path(path).read_bytes()
    except OSError as exc:
        raise PackageError(f"No se pudo leer el archivo: {exc}") from exc
    if not payload or len(payload) > MAX_PACKAGE_BYTES:
        raise PackageError("El archivo está vacío o supera el máximo de 25 MB.")
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = archive.infolist()
            if not members or len(members) > MAX_ARCHIVE_FILES:
                raise PackageError("El paquete contiene una cantidad de archivos no permitida.")
            if len({member.filename for member in members}) != len(members):
                raise PackageError("El paquete contiene nombres repetidos.")
            if sum(member.file_size for member in members) > MAX_MANIFEST_BYTES:
                raise PackageError("El contenido descomprimido supera el máximo permitido.")
            manifest_member = next(
                (member for member in members if member.filename == "manifest.json"),
                None,
            )
            if manifest_member is None or manifest_member.file_size > MAX_MANIFEST_BYTES:
                raise PackageError("El archivo no contiene un manifiesto EduTrack válido.")
            manifest_data = archive.read(manifest_member)
            attachments = {}
            for member in members:
                name = member.filename
                path_object = PurePosixPath(name)
                if path_object.is_absolute() or "\\" in name or ".." in path_object.parts:
                    raise PackageError("El paquete contiene una ruta no permitida.")
                if name == "manifest.json":
                    continue
                if not ATTACHMENT_PATTERN.fullmatch(name) or member.file_size > MAX_ATTACHMENT_BYTES:
                    raise PackageError(f"El archivo {name} no está permitido.")
                attachments[name] = archive.read(member)
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise PackageError("No se pudo abrir el paquete EduTrack.") from exc
    try:
        manifest = json.loads(manifest_data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackageError("El manifiesto no contiene JSON UTF-8 válido.") from exc
    validate_manifest(manifest)
    if attachments:
        manifest["_attachment_data"] = {
            name: base64.b64encode(content).decode("ascii")
            for name, content in attachments.items()
        }
    validate_manifest(manifest)
    referenced = {
        row["record_image"]
        for row in manifest["enrollments"]
        if row.get("record_image")
    }
    if referenced != set(attachments):
        raise PackageError("El paquete contiene imágenes no asociadas a matrículas.")
    for row in manifest["enrollments"]:
        image_path = row.get("record_image")
        image_hash = row.get("record_image_hash", "")
        if image_path and (
            not isinstance(image_hash, str)
            or hashlib.sha256(attachments[image_path]).hexdigest() != image_hash
        ):
            raise PackageError(f"La imagen {image_path} no coincide con su huella.")
    return manifest


def validate_manifest(manifest):
    if not isinstance(manifest, dict):
        raise PackageError("El manifiesto debe ser un objeto JSON.")
    version = manifest.get("version")
    if manifest.get("format") != PACKAGE_FORMAT or version not in (
        SCHEMA_VERSION,
        INITIAL_CAMPUS_VERSION,
    ):
        raise PackageError("El archivo fue generado por una versión incompatible.")
    is_new_campus = version == INITIAL_CAMPUS_VERSION
    if is_new_campus:
        if manifest.get("campus_mode") != "new" or manifest.get("campus_id") is not None:
            raise PackageError("El paquete inicial no contiene una sede nueva válida.")
    elif type(manifest.get("campus_id")) is not int or manifest["campus_id"] < 1:
        raise PackageError("El paquete no contiene una sede válida.")
    campus_name = manifest.get("campus_name")
    campus_address = manifest.get("campus_address", "")
    if not isinstance(campus_name, str) or not campus_name.strip() or len(campus_name) > 120:
        raise PackageError("El nombre de la sede no es válido.")
    if not isinstance(campus_address, str) or len(campus_address) > 200:
        raise PackageError("La dirección de la sede no es válida.")
    for key in ("students", "enrollments", "courses", "promoters"):
        if not isinstance(manifest.get(key), list):
            raise PackageError(f"El manifiesto no contiene una lista {key} válida.")
    if len(manifest["students"]) > 2000 or len(manifest["enrollments"]) > 2000:
        raise PackageError("El paquete supera el límite de registros admitidos.")
    try:
        ManifestEnvelope.model_validate(manifest)
    except ValidationError as exc:
        raise PackageError("El manifiesto tiene un formato no válido.") from exc

    student_ids = set()
    for student in manifest["students"]:
        if not isinstance(student, dict) or not isinstance(student.get("id"), str):
            raise PackageError("El archivo contiene un estudiante inválido.")
        if student["id"] in student_ids:
            raise PackageError("El archivo repite identificadores de estudiantes.")
        if not isinstance(student.get("phone_numbers"), list):
            raise PackageError("El archivo contiene teléfonos inválidos.")
        try:
            StudentManifestRecord.model_validate(student)
        except ValidationError:
            raise PackageError("El archivo contiene un estudiante inválido.")
        student_ids.add(student["id"])
        if is_new_campus and (
            student.get("server_id") is not None or student.get("base_hash") is not None
        ):
            raise PackageError("Un estudiante de una sede nueva no puede tener ID web.")

    enrollment_ids = set()
    for enrollment in manifest["enrollments"]:
        if not isinstance(enrollment, dict) or not isinstance(
            enrollment.get("id"), str
        ):
            raise PackageError("El archivo contiene una matrícula inválida.")
        if enrollment["id"] in enrollment_ids:
            raise PackageError("El archivo repite identificadores de matrículas.")
        try:
            EnrollmentManifestRecord.model_validate(enrollment)
        except ValidationError:
            raise PackageError("El archivo contiene una matrícula inválida.")
        enrollment_ids.add(enrollment["id"])
        if enrollment.get("student_id") and enrollment["student_id"] not in student_ids:
            raise PackageError("Una matrícula apunta a un estudiante inexistente.")
        if not enrollment.get("student_id") and enrollment.get("course_id") in (None, ""):
            raise PackageError("Una matrícula necesita un estudiante o un curso.")
        image_path = enrollment.get("record_image")
        if image_path and (
            not isinstance(image_path, str) or not ATTACHMENT_PATTERN.fullmatch(image_path)
        ):
            raise PackageError("Una matrícula contiene una ruta de imagen inválida.")
        if is_new_campus and (
            enrollment.get("server_id") is not None
            or enrollment.get("base_hash") is not None
            or enrollment.get("student_server_id") is not None
        ):
            raise PackageError("Una matrícula de una sede nueva no puede tener IDs web.")

    if is_new_campus:
        course_ids = set()
        for course in manifest["courses"]:
            if (
                not isinstance(course, dict)
                or type(course.get("id")) is not int
                or course["id"] < 1
                or course["id"] in course_ids
                or course.get("server_id") is not None
            ):
                raise PackageError("El paquete contiene un curso local inválido.")
            course_ids.add(course["id"])
        promoter_ids = set()
        for promoter in manifest["promoters"]:
            if (
                not isinstance(promoter, dict)
                or type(promoter.get("id")) is not int
                or promoter["id"] < 1
                or promoter["id"] in promoter_ids
                or promoter.get("server_id") is not None
            ):
                raise PackageError("El paquete contiene un promotor local inválido.")
            promoter_ids.add(promoter["id"])
        for enrollment in manifest["enrollments"]:
            if enrollment.get("course_id") not in (None, "") and enrollment["course_id"] not in course_ids:
                raise PackageError("Una matrícula apunta a un curso inexistente.")
            if any(promoter_id not in promoter_ids for promoter_id in enrollment["promoter_ids"]):
                raise PackageError("Una matrícula apunta a un promotor inexistente.")


def write_package(path, manifest):
    validate_manifest(manifest)
    if not isinstance(manifest.get("_attachment_data", {}), dict):
        raise PackageError("Los adjuntos del espacio de trabajo no tienen un formato válido.")
    attachments = {}
    for name, encoded in manifest.get("_attachment_data", {}).items():
        if not ATTACHMENT_PATTERN.fullmatch(name):
            raise PackageError("El paquete contiene una ruta de imagen no permitida.")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as exc:
            raise PackageError(f"La imagen {name} no tiene contenido válido.") from exc
        if len(content) > MAX_ATTACHMENT_BYTES:
            raise PackageError(f"La imagen {name} supera el máximo de 10 MB.")
        attachments[name] = content
    referenced = {
        row["record_image"]
        for row in manifest["enrollments"]
        if row.get("record_image")
    }
    if referenced != set(attachments):
        raise PackageError("Falta una imagen de ficha o hay imágenes no asociadas.")
    for row in manifest["enrollments"]:
        image_path = row.get("record_image")
        if image_path and hashlib.sha256(attachments[image_path]).hexdigest() != row.get(
            "record_image_hash"
        ):
            raise PackageError(f"La imagen {image_path} no coincide con su huella.")
    if len(attachments) + 1 > MAX_ARCHIVE_FILES:
        raise PackageError("El paquete contiene demasiadas imágenes.")
    if sum(map(len, attachments.values())) > MAX_MANIFEST_BYTES:
        raise PackageError("Las imágenes superan el máximo descomprimido permitido.")
    serialized = {key: value for key, value in manifest.items() if key != "_attachment_data"}
    encoded = json.dumps(
        serialized, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    if len(encoded) + sum(map(len, attachments.values())) > MAX_MANIFEST_BYTES:
        raise PackageError("Los datos descomprimidos superan el máximo permitido.")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
        with zipfile.ZipFile(temporary_name, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "manifest.json",
                encoded,
            )
            for name, content in attachments.items():
                archive.writestr(name, content)
        if Path(temporary_name).stat().st_size > MAX_PACKAGE_BYTES:
            raise PackageError("El paquete supera el máximo permitido de 25 MB.")
        os.replace(temporary_name, destination)
    except OSError as exc:
        raise PackageError(f"No se pudo guardar el archivo: {exc}") from exc
    finally:
        if temporary_name and Path(temporary_name).exists():
            Path(temporary_name).unlink()
