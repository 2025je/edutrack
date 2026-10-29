from typing import Any


def student_rows(manifest: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not manifest:
        return []
    rows = [
        {
            **student,
            "label": " ".join(
                part
                for part in (student["last_name"], student["first_name"])
                if part
            ),
        }
        for student in manifest["students"]
    ]
    return sorted(rows, key=lambda row: row["label"].casefold())


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
