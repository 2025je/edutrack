from datetime import date, timedelta
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
    return list(reversed(rows))


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
                "student_label": (
                    " ".join(
                        part
                        for part in (student["last_name"], student["first_name"])
                        if part
                    )
                    if student
                    else "Pendiente de estudiante"
                ),
                "course_label": course_name,
                "pending_student": student is None,
                "pending_course": course is None,
                "student_active": bool(
                    student and student.get("active", True)
                ),
                "label": f"{student_name} — {course_name}",
            }
        )
    return sorted(
        reversed(rows),
        key=lambda row: str(row.get("enrollment_date", "")),
        reverse=True,
    )


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
    student_order = {
        student["id"]: index
        for index, student in enumerate(manifest["students"])
    }
    return sorted(
        roster.values(),
        key=lambda row: student_order.get(row["id"], -1),
        reverse=True,
    )


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
        reversed(rows),
        key=lambda row: str(row.get("start_date", "")),
        reverse=True,
    )


def course_week_groups(courses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups_by_start: dict[date, dict[str, Any]] = {}
    ungrouped_courses: list[dict[str, Any]] = []

    for course in courses:
        start_date = str(course.get("start_date") or "")
        try:
            parsed_date = date.fromisoformat(start_date)
        except ValueError:
            ungrouped_courses.append(course)
            continue
        if parsed_date.isoformat() != start_date:
            ungrouped_courses.append(course)
            continue

        week_start = parsed_date - timedelta(days=parsed_date.weekday())
        group = groups_by_start.setdefault(
            week_start,
            {
                "start_date": week_start.isoformat(),
                "label": "",
                "courses": [],
            },
        )
        group["courses"].append(course)

    def sort_courses(rows: list[dict[str, Any]]) -> None:
        rows.sort(key=lambda course: str(course.get("group") or ""))
        rows.sort(key=lambda course: str(course.get("schedule") or ""))
        rows.sort(key=lambda course: str(course.get("name") or ""))
        rows.sort(
            key=lambda course: str(course.get("start_date") or ""),
            reverse=True,
        )

    def week_range_label(start: date, end: date) -> str:
        months = (
            "enero",
            "febrero",
            "marzo",
            "abril",
            "mayo",
            "junio",
            "julio",
            "agosto",
            "septiembre",
            "octubre",
            "noviembre",
            "diciembre",
        )
        if start.year == end.year and start.month == end.month:
            return f"{start.day} al {end.day} de {months[end.month - 1]} de {end.year}"
        if start.year == end.year:
            return (
                f"{start.day} de {months[start.month - 1]} al {end.day} de "
                f"{months[end.month - 1]} de {end.year}"
            )
        return (
            f"{start.day} de {months[start.month - 1]} de {start.year} al "
            f"{end.day} de {months[end.month - 1]} de {end.year}"
        )

    groups = []
    for week_start in sorted(groups_by_start, reverse=True):
        group = groups_by_start[week_start]
        week_end = week_start + timedelta(days=6)
        group["label"] = (
            "SEMANA: del " + week_range_label(week_start, week_end)
        )
        sort_courses(group["courses"])
        groups.append(group)

    if ungrouped_courses:
        sort_courses(ungrouped_courses)
        groups.append(
            {
                "label": "Semana no definida",
                "courses": ungrouped_courses,
            }
        )
    return groups


def dashboard_summary(
    manifest: dict[str, Any] | None,
    today: str | None = None,
) -> dict[str, Any]:
    if not manifest:
        return {
            "summary_date": today or date.today().isoformat(),
            "student_count": 0,
            "active_students": 0,
            "course_count": 0,
            "active_courses": 0,
            "full_courses": 0,
            "enrollment_count": 0,
            "active_enrollments": 0,
            "today_enrollments": 0,
            "pending_enrollments": 0,
            "course_occupancy_rows": [],
            "recent_enrollments": [],
        }

    summary_date = today or date.today().isoformat()
    students = {item["id"]: item for item in manifest["students"]}
    courses = {item["id"]: item for item in manifest["courses"]}
    course_student_ids: dict[int, set[str]] = {}
    recent_enrollments: list[dict[str, Any]] = []
    active_enrollments = 0
    today_enrollments = 0
    pending_enrollments = 0

    for enrollment in reversed(manifest["enrollments"]):
        student = students.get(enrollment.get("student_id"))
        course = courses.get(enrollment.get("course_id"))
        pending_student = student is None
        pending_course = course is None
        active = enrollment.get("active", True)

        if active and not pending_student and not pending_course:
            active_enrollments += 1
        if pending_student or pending_course:
            pending_enrollments += 1
        enrollment_date = str(enrollment.get("enrollment_date", ""))
        if enrollment_date == summary_date:
            today_enrollments += 1

        if (
            active
            and student
            and student.get("active", True)
            and course
        ):
            course_student_ids.setdefault(course["id"], set()).add(student["id"])

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
        recent_enrollments.append(
            {
                **enrollment,
                "student_label": (
                    student_name if student else "Pendiente de estudiante"
                ),
                "course_label": course_name,
                "pending_student": pending_student,
                "pending_course": pending_course,
                "label": f"{student_name} — {course_name}",
            }
        )

    course_rows_for_summary = [
        {
            **course,
            "label": f"{course['name']} · {course['schedule']} · Grupo {course['group']}",
            "student_count": len(course_student_ids.get(course["id"], set())),
        }
        for course in reversed(manifest["courses"])
    ]
    course_rows_for_summary.sort(
        key=lambda row: str(row.get("start_date", "")),
        reverse=True,
    )
    occupancy_rows = sorted(
        course_rows_for_summary,
        key=lambda row: row["student_count"],
        reverse=True,
    )[:6]
    recent_enrollments.sort(
        key=lambda row: str(row.get("enrollment_date", "")),
        reverse=True,
    )
    full_courses = sum(
        course.get("capacity", 0) > 0
        and course["student_count"] >= course["capacity"]
        for course in course_rows_for_summary
    )

    return {
        "summary_date": summary_date,
        "student_count": len(manifest["students"]),
        "active_students": sum(
            student.get("active", True) for student in manifest["students"]
        ),
        "course_count": len(course_rows_for_summary),
        "active_courses": sum(
            course.get("active", True) for course in course_rows_for_summary
        ),
        "full_courses": full_courses,
        "enrollment_count": len(manifest["enrollments"]),
        "active_enrollments": active_enrollments,
        "today_enrollments": today_enrollments,
        "pending_enrollments": pending_enrollments,
        "course_occupancy_rows": occupancy_rows,
        "recent_enrollments": recent_enrollments[:6],
    }
