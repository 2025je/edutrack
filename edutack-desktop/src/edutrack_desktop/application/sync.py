import hashlib
import json
from decimal import Decimal
from typing import Any, Callable


_STUDENT_FIELDS = (
    "last_name",
    "first_name",
    "document_number",
    "phone_numbers",
    "active",
)
_ENROLLMENT_FIELDS = (
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
_COURSE_FIELDS = (
    "name",
    "schedule",
    "group",
    "start_date",
    "enrollment_fee",
    "monthly_fee",
    "capacity",
    "active",
)
_PROMOTER_FIELDS = ("name", "active")
_MAX_PREVIEW_ITEMS = 100
_FIELD_LABELS = {
    "last_name": "Apellidos",
    "first_name": "Nombres",
    "document_number": "Documento",
    "phone_numbers": "Teléfonos",
    "active": "Estado",
    "name": "Nombre",
    "schedule": "Horario",
    "group": "Grupo",
    "start_date": "Fecha de inicio",
    "enrollment_fee": "Costo de matrícula",
    "monthly_fee": "Mensualidad",
    "capacity": "Capacidad",
    "student": "Estudiante",
    "course": "Curso",
    "enrollment_date": "Fecha de matrícula",
    "promoter_ids": "Promotores",
    "record_code": "Código de ficha",
    "record_image_hash": "Imagen de ficha",
    "record": "Registro",
}


def _fingerprint(values: dict[str, Any], fields: tuple[str, ...]) -> str:
    payload = json.dumps(
        {field: values[field] for field in fields},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _student_fingerprint(student: dict[str, Any]) -> str:
    values = {
        "last_name": student["last_name"].strip().upper(),
        "first_name": student["first_name"].strip().upper(),
        "document_number": student["document_number"].strip(),
        "phone_numbers": list(student["phone_numbers"]),
        "active": student["active"],
    }
    return _fingerprint(values, _STUDENT_FIELDS)


def _enrollment_fingerprint(
    enrollment: dict[str, Any],
    students: dict[str, dict[str, Any]],
    courses: dict[Any, dict[str, Any]],
    promoters: dict[Any, dict[str, Any]],
    identity_overrides: dict[str, dict[Any, Any]] | None = None,
    include_image: bool = True,
) -> str:
    identity_overrides = identity_overrides or {}
    student_id = enrollment.get("student_id")
    student = students.get(student_id) if student_id is not None else None
    student_server_id = enrollment.get("student_server_id")
    if student_server_id is None and student is not None:
        student_server_id = student.get("server_id")
    if student_server_id is None and student_id is not None:
        student_server_id = identity_overrides.get("student", {}).get(student_id)
    course = courses.get(enrollment.get("course_id"))
    course_server_id = enrollment.get("course_id")
    if course is not None and course.get("server_id") is not None:
        course_server_id = course["server_id"]
    elif course_server_id is not None:
        course_server_id = identity_overrides.get("course", {}).get(
            course_server_id, course_server_id
        )
    promoter_server_ids = sorted(
        promoters.get(promoter_id, {}).get("server_id")
        or identity_overrides.get("promoter", {}).get(promoter_id, promoter_id)
        for promoter_id in enrollment["promoter_ids"]
    )
    values = {
        "student_server_id": student_server_id,
        "course_id": course_server_id,
        "enrollment_date": enrollment["enrollment_date"],
        "promoter_ids": promoter_server_ids,
        "enrollment_fee": format(Decimal(enrollment["enrollment_fee"]), ".2f"),
        "monthly_fee": format(Decimal(enrollment["monthly_fee"]), ".2f"),
        "record_code": enrollment.get("record_code"),
        "record_image_hash": enrollment.get("record_image_hash", ""),
        "active": enrollment["active"],
    }
    fields = (
        _ENROLLMENT_FIELDS
        if include_image
        else tuple(
            field for field in _ENROLLMENT_FIELDS if field != "record_image_hash"
        )
    )
    return _fingerprint(values, fields)


def _identity_maps(
    records: list[dict[str, Any]],
) -> tuple[dict[Any, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_server_id = {
        record["server_id"]: record
        for record in records
        if record.get("server_id") is not None
    }
    by_local_id = {record["id"]: record for record in records}
    return by_server_id, by_local_id


def _match_record(
    record: dict[str, Any],
    by_server_id: dict[Any, dict[str, Any]],
    by_local_id: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    server_id = record.get("server_id")
    if server_id is not None and server_id in by_server_id:
        return by_server_id[server_id]
    local_match = by_local_id.get(record["id"])
    if local_match is None:
        return None
    local_server_id = local_match.get("server_id")
    if server_id is not None and local_server_id not in (None, server_id):
        return None
    return local_match


def _preview_value(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Sí" if value else "No"
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value) or "—"
    return str(value)


def _field_changes(
    local: dict[str, Any],
    incoming: dict[str, Any],
    fields: tuple[str, ...],
) -> list[dict[str, str]]:
    changes = []
    for field in fields:
        local_value = local.get(field)
        incoming_value = incoming.get(field)
        if local_value == incoming_value:
            continue
        changes.append(
            {
                "field": _FIELD_LABELS.get(field, field),
                "local": _preview_value(local_value),
                "incoming": _preview_value(incoming_value),
            }
        )
    return changes


def _enrollment_field_changes(
    local: dict[str, Any],
    incoming: dict[str, Any],
    local_students: dict[str, dict[str, Any]],
    incoming_students: dict[str, dict[str, Any]],
    local_courses: dict[Any, dict[str, Any]],
    incoming_courses: dict[Any, dict[str, Any]],
    local_promoters: dict[Any, dict[str, Any]],
    incoming_promoters: dict[Any, dict[str, Any]],
    identity_overrides: dict[str, dict[Any, Any]],
) -> list[dict[str, str]]:
    def student_value(
        enrollment: dict[str, Any],
        students: dict[str, dict[str, Any]],
        use_overrides: bool,
    ) -> tuple[Any, str]:
        student_id = enrollment.get("student_id")
        student = students.get(student_id) if student_id is not None else None
        server_id = enrollment.get("student_server_id")
        if server_id is None and student is not None:
            server_id = student.get("server_id")
        if server_id is None and student_id is not None and use_overrides:
            server_id = identity_overrides.get("student", {}).get(student_id)
        key = ("server", server_id) if server_id is not None else ("local", student_id)
        label = (
            " ".join(
                part
                for part in (
                    student.get("last_name", ""),
                    student.get("first_name", ""),
                )
                if part
            )
            if student
            else "Pendiente de estudiante"
        )
        return key, label

    def course_value(
        course_id: Any,
        courses: dict[Any, dict[str, Any]],
        use_overrides: bool,
    ) -> tuple[Any, str]:
        course = courses.get(course_id)
        server_id = course.get("server_id") if course else None
        if server_id is None and use_overrides:
            server_id = identity_overrides.get("course", {}).get(course_id)
        if server_id is None:
            server_id = course_id
        key = ("server", server_id) if server_id is not None else ("local", None)
        label = (
            f"{course['name']} · {course['schedule']} · Grupo {course['group']}"
            if course
            else "Pendiente de curso"
        )
        return key, label

    def promoter_value(
        enrollment: dict[str, Any],
        promoters: dict[Any, dict[str, Any]],
        use_overrides: bool,
    ) -> tuple[list[Any], str]:
        identities = []
        names = []
        for promoter_id in enrollment.get("promoter_ids", []):
            promoter = promoters.get(promoter_id)
            server_id = promoter.get("server_id") if promoter else None
            if server_id is None and use_overrides:
                server_id = identity_overrides.get("promoter", {}).get(promoter_id)
            identity = server_id if server_id is not None else promoter_id
            identities.append(identity)
            names.append(
                promoter.get("name", f"ID {identity}") if promoter else f"ID {identity}"
            )
        return sorted(identities), ", ".join(sorted(names)) or "—"

    local_student = student_value(local, local_students, True)
    incoming_student = student_value(incoming, incoming_students, False)
    local_course = course_value(local.get("course_id"), local_courses, True)
    incoming_course = course_value(
        incoming.get("course_id"),
        incoming_courses,
        False,
    )
    local_promoter_value = promoter_value(local, local_promoters, True)
    incoming_promoter_value = promoter_value(incoming, incoming_promoters, False)

    def values(
        enrollment: dict[str, Any],
        student: tuple[Any, str],
        course: tuple[Any, str],
        promoters: tuple[list[Any], str],
    ) -> dict[str, tuple[Any, Any]]:
        image_hash = enrollment.get("record_image_hash", "")
        image_label = f"Imagen {image_hash[:12]}" if image_hash else "Sin imagen"
        enrollment_fee = format(Decimal(enrollment["enrollment_fee"]), ".2f")
        monthly_fee = format(Decimal(enrollment["monthly_fee"]), ".2f")
        return {
            "student": student,
            "course": course,
            "enrollment_date": (
                enrollment.get("enrollment_date"),
                enrollment.get("enrollment_date"),
            ),
            "promoter_ids": promoters,
            "enrollment_fee": (enrollment_fee, enrollment_fee),
            "monthly_fee": (monthly_fee, monthly_fee),
            "record_code": (
                enrollment.get("record_code"),
                enrollment.get("record_code"),
            ),
            "record_image_hash": (image_hash, image_label),
            "active": (
                enrollment.get("active"),
                enrollment.get("active"),
            ),
        }

    local_values = values(local, local_student, local_course, local_promoter_value)
    incoming_values = values(
        incoming,
        incoming_student,
        incoming_course,
        incoming_promoter_value,
    )
    changes = []
    for field in (
        "student",
        "course",
        "enrollment_date",
        "promoter_ids",
        "enrollment_fee",
        "monthly_fee",
        "record_code",
        "record_image_hash",
        "active",
    ):
        local_key, local_label = local_values[field]
        incoming_key, incoming_label = incoming_values[field]
        if local_key == incoming_key:
            continue
        changes.append(
            {
                "field": _FIELD_LABELS[field],
                "local": _preview_value(local_label),
                "incoming": _preview_value(incoming_label),
            }
        )
    return changes


def build_import_preview(
    local_manifest: dict[str, Any],
    incoming_manifest: dict[str, Any],
) -> dict[str, Any]:
    """Classify a validated package without changing either manifest."""
    counts = {
        "new": 0,
        "updated": 0,
        "unchanged": 0,
        "conflicts": 0,
        "attention": 0,
    }
    items: list[dict[str, Any]] = []
    matched_local_ids: dict[str, set[str]] = {
        "student": set(),
        "enrollment": set(),
        "course": set(),
        "promoter": set(),
    }

    def add_item(
        kind: str,
        state: str,
        label: str,
        message: str,
        *,
        attention: bool = False,
        changes: list[dict[str, str]] | tuple[()] = (),
    ) -> None:
        if state == "conflict":
            counts["conflicts"] += 1
        else:
            counts[state] += 1
        if attention:
            counts["attention"] += 1
        items.append(
            {
                "kind": kind,
                "state": state,
                "label": label,
                "message": message,
                "attention": attention,
                "changes": list(changes),
            }
        )

    local_students = {student["id"]: student for student in local_manifest["students"]}
    incoming_students = {
        student["id"]: student for student in incoming_manifest["students"]
    }
    local_courses = {course["id"]: course for course in local_manifest["courses"]}
    incoming_courses = {course["id"]: course for course in incoming_manifest["courses"]}
    local_promoters = {
        promoter["id"]: promoter for promoter in local_manifest["promoters"]
    }
    incoming_promoters = {
        promoter["id"]: promoter for promoter in incoming_manifest["promoters"]
    }
    incoming_identity_overrides = {
        "student": {
            record["id"]: record.get("server_id")
            for record in incoming_manifest["students"]
            if record.get("server_id") is not None
        },
        "course": {
            record["id"]: record.get("server_id")
            for record in incoming_manifest["courses"]
            if record.get("server_id") is not None
        },
        "promoter": {
            record["id"]: record.get("server_id")
            for record in incoming_manifest["promoters"]
            if record.get("server_id") is not None
        },
    }

    def compare_records(
        kind: str,
        local_records: list[dict[str, Any]],
        incoming_records: list[dict[str, Any]],
        label: Callable[[dict[str, Any]], str],
        fingerprint: Callable[[dict[str, Any], bool], str] | None,
        fields: tuple[str, ...] | None = None,
        non_image_fingerprint: Callable[[dict[str, Any], bool], str] | None = None,
        changes_for: Callable[[dict[str, Any], dict[str, Any]], list[dict[str, str]]]
        | None = None,
    ) -> None:
        by_server_id, by_local_id = _identity_maps(local_records)
        matched_ids = matched_local_ids[kind]
        for incoming in incoming_records:
            current = _match_record(incoming, by_server_id, by_local_id)
            if current is None:
                add_item(kind, "new", label(incoming), "Se agregará desde Web.")
                continue

            matched_ids.add(current["id"])
            changes = (
                changes_for(current, incoming)
                if changes_for is not None
                else _field_changes(current, incoming, fields or ())
            )
            if fingerprint is not None:
                current_hash = fingerprint(current, False)
                incoming_hash = fingerprint(incoming, True)
                if current_hash == incoming_hash:
                    add_item(
                        kind,
                        "unchanged",
                        label(incoming),
                        "No requiere cambios.",
                        changes=(),
                    )
                elif non_image_fingerprint is not None and non_image_fingerprint(
                    current, False
                ) == non_image_fingerprint(incoming, True):
                    add_item(
                        kind,
                        "updated",
                        label(incoming),
                        "Cambió la imagen de ficha; revísala antes de confirmar.",
                        attention=True,
                        changes=changes,
                    )
                elif current.get("base_hash") and current_hash == current["base_hash"]:
                    add_item(
                        kind,
                        "updated",
                        label(incoming),
                        "El cambio remoto se puede aplicar sobre la base local.",
                        changes=changes,
                    )
                else:
                    add_item(
                        kind,
                        "conflict",
                        label(incoming),
                        "Hay cambios locales y remotos; resuélvelos en EduTrack Web antes de importar.",
                        attention=True,
                        changes=changes,
                    )
                continue

            if changes:
                add_item(
                    kind,
                    "updated",
                    label(incoming),
                    "Cambió en el paquete. Revisa este registro antes de confirmar.",
                    attention=True,
                    changes=changes,
                )
            else:
                add_item(
                    kind,
                    "unchanged",
                    label(incoming),
                    "No requiere cambios.",
                    changes=(),
                )

        for current in local_records:
            if current["id"] in matched_ids:
                continue
            add_item(
                kind,
                "conflict",
                label(current),
                "No aparece en el paquete; importar lo eliminaría de la sede local.",
                attention=True,
                changes=[
                    {
                        "field": _FIELD_LABELS["record"],
                        "local": "Existe en Desktop",
                        "incoming": "No viene en el paquete",
                    }
                ],
            )

    compare_records(
        "student",
        local_manifest["students"],
        incoming_manifest["students"],
        lambda student: " ".join(
            part
            for part in (student.get("last_name", ""), student.get("first_name", ""))
            if part
        ),
        lambda student, _: _student_fingerprint(student),
        fields=_STUDENT_FIELDS,
    )

    def enrollment_label(
        enrollment: dict[str, Any],
        students: dict[str, dict[str, Any]],
        courses: dict[Any, dict[str, Any]],
    ) -> str:
        student_id = enrollment.get("student_id")
        student = students.get(student_id) if student_id is not None else None
        course = courses.get(enrollment.get("course_id"))
        student_name = (
            " ".join(
                part
                for part in (
                    student.get("last_name", ""),
                    student.get("first_name", ""),
                )
                if part
            )
            if student
            else "Estudiante pendiente"
        )
        course_name = (
            course.get("name", "Curso pendiente") if course else "Curso pendiente"
        )
        return (
            f"{student_name} · {course_name} · {enrollment.get('enrollment_date', '')}"
        )

    compare_records(
        "enrollment",
        local_manifest["enrollments"],
        incoming_manifest["enrollments"],
        lambda row: enrollment_label(row, incoming_students, incoming_courses),
        lambda row, is_incoming: _enrollment_fingerprint(
            row,
            incoming_students if is_incoming else local_students,
            incoming_courses if is_incoming else local_courses,
            incoming_promoters if is_incoming else local_promoters,
            None if is_incoming else incoming_identity_overrides,
        ),
        non_image_fingerprint=lambda row, is_incoming: _enrollment_fingerprint(
            row,
            incoming_students if is_incoming else local_students,
            incoming_courses if is_incoming else local_courses,
            incoming_promoters if is_incoming else local_promoters,
            None if is_incoming else incoming_identity_overrides,
            include_image=False,
        ),
        changes_for=lambda local, incoming: _enrollment_field_changes(
            local,
            incoming,
            local_students,
            incoming_students,
            local_courses,
            incoming_courses,
            local_promoters,
            incoming_promoters,
            incoming_identity_overrides,
        ),
    )
    compare_records(
        "course",
        local_manifest["courses"],
        incoming_manifest["courses"],
        lambda course: course.get("name", "Curso sin nombre"),
        None,
        _COURSE_FIELDS,
    )
    compare_records(
        "promoter",
        local_manifest["promoters"],
        incoming_manifest["promoters"],
        lambda promoter: promoter.get("name", "Promotor sin nombre"),
        None,
        _PROMOTER_FIELDS,
    )

    local_enrollments_by_server_id, local_enrollments_by_id = _identity_maps(
        local_manifest["enrollments"]
    )
    images_new = 0
    images_changed = 0
    for enrollment in incoming_manifest["enrollments"]:
        if not enrollment.get("record_image"):
            continue
        current = _match_record(
            enrollment,
            local_enrollments_by_server_id,
            local_enrollments_by_id,
        )
        if current is None or not current.get("record_image"):
            images_new += 1
        elif current.get("record_image_hash") != enrollment.get("record_image_hash"):
            images_changed += 1

    return {
        "new": counts["new"],
        "updated": counts["updated"],
        "unchanged": counts["unchanged"],
        "conflicts": counts["conflicts"],
        "attention": counts["attention"],
        "images_new": images_new,
        "images_changed": images_changed,
        "can_import": counts["conflicts"] == 0,
        "items": items[:_MAX_PREVIEW_ITEMS],
        "omitted_items": max(0, len(items) - _MAX_PREVIEW_ITEMS),
    }
