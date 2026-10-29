from typing import Any


def student_rows(manifest: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not manifest:
        return []
    courses = {course["id"]: course for course in manifest["courses"]}
    enrolled_courses: dict[str, list[str]] = {}
    for enrollment in manifest["enrollments"]:
        if not enrollment.get("active", True):
            continue
        student_id = enrollment.get("student_id")
        if not student_id:
            continue
        course = courses.get(enrollment.get("course_id"))
        course_label = (
            f"{course['name']} · {course['schedule']} · Grupo {course['group']}"
            if course
            else "Pendiente de curso"
        )
        enrolled_courses.setdefault(student_id, []).append(course_label)
    rows = [
        {
            **student,
            "courses": enrolled_courses.get(student["id"], []),
            "label": " ".join(
                part
                for part in (student["last_name"], student["first_name"])
                if part
            ),
        }
        for student in manifest["students"]
    ]
    return sorted(rows, key=lambda row: row["label"].casefold())


def filter_student_rows(
    rows: list[dict[str, Any]], query: str
) -> list[dict[str, Any]]:
    normalized_query = query.strip().casefold()
    if not normalized_query:
        return rows
    return [
        row
        for row in rows
        if normalized_query
        in " ".join(
            (
                str(row.get("label", "")),
                str(row.get("document_number", "")),
                " ".join(row.get("courses", [])),
                "activo" if row.get("active", True) else "inactivo",
            )
        ).casefold()
    ]


def enrollment_rows(manifest: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not manifest:
        return []
    students = {item["id"]: item for item in manifest["students"]}
    courses = {item["id"]: item for item in manifest["courses"]}
    rows = []
    for enrollment in manifest["enrollments"]:
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


def course_students(
    manifest: dict[str, Any], course_id: int
) -> list[dict[str, Any]]:
    students = {student["id"]: student for student in manifest["students"]}
    roster = {}
    for enrollment in manifest["enrollments"]:
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


def course_rows(manifest: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not manifest:
        return []
    rows = [
        {
            **course,
            "label": (
                f"{course['name']} · {course['schedule']} · Grupo {course['group']}"
            ),
            "student_count": len(course_students(manifest, course["id"])),
        }
        for course in manifest["courses"]
    ]
    return sorted(
        rows,
        key=lambda row: (
            row["name"].casefold(),
            row["schedule"].casefold(),
            str(row["group"]).casefold(),
        ),
    )
