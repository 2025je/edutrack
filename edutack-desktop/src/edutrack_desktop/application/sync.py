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
        student_server_id = identity_overrides.get("student", {}).get(
            student_id
        )
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
        else tuple(field for field in _ENROLLMENT_FIELDS if field != "record_image_hash")
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
            }
        )

    local_students = {
        student["id"]: student for student in local_manifest["students"]
    }
    incoming_students = {
        student["id"]: student for student in incoming_manifest["students"]
    }
    local_courses = {course["id"]: course for course in local_manifest["courses"]}
    incoming_courses = {
        course["id"]: course for course in incoming_manifest["courses"]
    }
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
    ) -> None:
        by_server_id, by_local_id = _identity_maps(local_records)
        matched_ids = matched_local_ids[kind]
        for incoming in incoming_records:
            current = _match_record(incoming, by_server_id, by_local_id)
            if current is None:
                add_item(kind, "new", label(incoming), "Se agregará desde Web.")
                continue

            matched_ids.add(current["id"])
            if fingerprint is not None:
                current_hash = fingerprint(current, False)
                incoming_hash = fingerprint(incoming, True)
                if current_hash == incoming_hash:
                    add_item(
                        kind,
                        "unchanged",
                        label(incoming),
                        "No requiere cambios.",
                    )
                elif (
                    non_image_fingerprint is not None
                    and non_image_fingerprint(current, False)
                    == non_image_fingerprint(incoming, True)
                ):
                    add_item(
                        kind,
                        "updated",
                        label(incoming),
                        "Cambió la imagen de ficha; revísala antes de confirmar.",
                        attention=True,
                    )
                elif (
                    current.get("base_hash")
                    and current_hash == current["base_hash"]
                ):
                    add_item(
                        kind,
                        "updated",
                        label(incoming),
                        "El cambio remoto se puede aplicar sobre la base local.",
                    )
                else:
                    add_item(
                        kind,
                        "conflict",
                        label(incoming),
                        "Hay cambios locales y remotos; resuélvelos en EduTrack Web antes de importar.",
                        attention=True,
                    )
                continue

            changed = any(current.get(field) != incoming.get(field) for field in fields or ())
            if changed:
                add_item(
                    kind,
                    "updated",
                    label(incoming),
                    "Cambió en el paquete. Revisa este registro antes de confirmar.",
                    attention=True,
                )
            else:
                add_item(
                    kind,
                    "unchanged",
                    label(incoming),
                    "No requiere cambios.",
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
    )

    def enrollment_label(
        enrollment: dict[str, Any], students: dict[str, dict[str, Any]], courses: dict[Any, dict[str, Any]]
    ) -> str:
        student_id = enrollment.get("student_id")
        student = students.get(student_id) if student_id is not None else None
        course = courses.get(enrollment.get("course_id"))
        student_name = (
            " ".join(
                part
                for part in (student.get("last_name", ""), student.get("first_name", ""))
                if part
            )
            if student
            else "Estudiante pendiente"
        )
        course_name = course.get("name", "Curso pendiente") if course else "Curso pendiente"
        return f"{student_name} · {course_name} · {enrollment.get('enrollment_date', '')}"

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
