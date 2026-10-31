from edutrack_desktop.application.presenters import (
    course_rows,
    course_students,
    course_week_groups,
    dashboard_summary,
    enrollment_rows,
    student_rows,
)


def test_student_rows_include_active_course_labels():
    manifest = {
        "students": [
            {
                "id": "student-1",
                "last_name": "PEREZ",
                "first_name": "ANA",
                "active": True,
            },
            {
                "id": "student-2",
                "last_name": "ROJAS",
                "first_name": "LUIS",
                "active": True,
            },
        ],
        "courses": [
            {
                "id": 1,
                "name": "Matemáticas",
                "schedule": "Mañana",
                "group": "1",
            }
        ],
        "enrollments": [
            {
                "id": "enrollment-1",
                "student_id": "student-1",
                "course_id": 1,
                "active": True,
            },
            {
                "id": "enrollment-2",
                "student_id": "student-1",
                "course_id": None,
                "active": True,
            },
            {
                "id": "enrollment-3",
                "student_id": "student-2",
                "course_id": 1,
                "active": False,
            },
        ],
    }

    rows = {row["id"]: row for row in student_rows(manifest)}

    assert [row["id"] for row in student_rows(manifest)] == [
        "student-2",
        "student-1",
    ]
    assert rows["student-1"]["courses"] == [
        "Matemáticas · Mañana · Grupo 1",
        "Pendiente de curso",
    ]
    assert rows["student-2"]["courses"] == []


def test_enrollment_rows_label_missing_students_and_courses():
    manifest = {
        "students": [
            {"id": "student-1", "last_name": "PEREZ", "first_name": "ANA"},
        ],
        "courses": [
            {
                "id": 1,
                "name": "Matemáticas",
                "schedule": "Mañana",
                "group": "1",
            }
        ],
        "enrollments": [
            {
                "id": "normal",
                "student_id": "student-1",
                "course_id": 1,
                "enrollment_date": "2026-10-01",
                "active": True,
            },
            {
                "id": "pending-student",
                "student_id": None,
                "course_id": 1,
                "enrollment_date": "2026-10-02",
                "active": True,
            },
            {
                "id": "pending-course",
                "student_id": "student-1",
                "course_id": None,
                "enrollment_date": "2026-10-03",
                "active": True,
            },
        ],
    }

    rows = {row["id"]: row for row in enrollment_rows(manifest)}

    assert [row["id"] for row in enrollment_rows(manifest)] == [
        "pending-course",
        "pending-student",
        "normal",
    ]
    assert rows["normal"]["student_label"] == "PEREZ ANA"
    assert rows["normal"]["course_label"] == "Matemáticas · Mañana · Grupo 1"
    assert rows["normal"]["pending_student"] is False
    assert rows["normal"]["pending_course"] is False
    assert rows["normal"]["student_active"] is True
    assert rows["pending-student"]["pending_student"] is True
    assert rows["pending-student"]["student_active"] is False
    assert rows["pending-course"]["pending_course"] is True


def test_course_rows_are_ordered_by_start_date_newest_first():
    manifest = {
        "students": [],
        "enrollments": [],
        "courses": [
            {
                "id": 1,
                "name": "Curso antiguo",
                "schedule": "Mañana",
                "group": "1",
                "start_date": "2026-01-01",
                "active": True,
            },
            {
                "id": 2,
                "name": "Curso reciente",
                "schedule": "Tarde",
                "group": "1",
                "start_date": "2026-03-01",
                "active": True,
            },
            {
                "id": 3,
                "name": "Curso agregado al final",
                "schedule": "Noche",
                "group": "1",
                "start_date": "2026-03-01",
                "active": True,
            },
        ],
    }

    assert [row["id"] for row in course_rows(manifest)] == [3, 2, 1]


def test_course_week_groups_sort_dates_and_keep_invalid_dates_at_the_end():
    courses = [
        {
            "id": 1,
            "name": "B",
            "schedule": "Mañana",
            "group": "1",
            "start_date": "2026-01-05",
        },
        {
            "id": 2,
            "name": "A",
            "schedule": "Tarde",
            "group": "2",
            "start_date": "2026-01-05",
        },
        {
            "id": 3,
            "name": "Anterior",
            "schedule": "Mañana",
            "group": "1",
            "start_date": "2026-01-04",
        },
        {
            "id": 4,
            "name": "Fecha inválida",
            "schedule": "Mañana",
            "group": "1",
            "start_date": "2026-02-30",
        },
    ]

    groups = course_week_groups(courses)

    assert [group["label"] for group in groups] == [
        "SEMANA: del 5 al 11 de enero de 2026",
        "SEMANA: del 29 de diciembre de 2025 al 4 de enero de 2026",
        "Semana no definida",
    ]
    assert [course["id"] for course in groups[0]["courses"]] == [2, 1]
    assert [course["id"] for course in groups[1]["courses"]] == [3]
    assert [course["id"] for course in groups[2]["courses"]] == [4]


def test_course_students_are_ordered_by_registration_recency():
    manifest = {
        "students": [
            {
                "id": "student-old",
                "last_name": "ANTIGUO",
                "first_name": "ALUMNO",
                "active": True,
            },
            {
                "id": "student-new",
                "last_name": "RECIENTE",
                "first_name": "ALUMNO",
                "active": True,
            },
        ],
        "enrollments": [
            {"student_id": "student-new", "course_id": 1, "active": True},
            {"student_id": "student-old", "course_id": 1, "active": True},
        ],
    }

    assert [
        row["id"] for row in course_students(manifest, 1)
    ] == ["student-new", "student-old"]


def test_dashboard_summary_reports_local_metrics_and_recent_records():
    manifest = {
        "students": [
            {
                "id": "student-active",
                "last_name": "PEREZ",
                "first_name": "ANA",
                "active": True,
            },
            {
                "id": "student-inactive",
                "last_name": "ROJAS",
                "first_name": "LUIS",
                "active": False,
            },
        ],
        "courses": [
            {
                "id": 1,
                "name": "Inglés",
                "schedule": "Mañana",
                "group": "1",
                "start_date": "2026-01-01",
                "capacity": 1,
                "active": True,
            },
            {
                "id": 2,
                "name": "Cocina",
                "schedule": "Tarde",
                "group": "2",
                "start_date": "2026-01-02",
                "capacity": 10,
                "active": False,
            },
        ],
        "enrollments": [
            {
                "id": "enrollment-today",
                "student_id": "student-active",
                "course_id": 1,
                "enrollment_date": "2026-02-03",
                "active": True,
            },
            {
                "id": "enrollment-inactive",
                "student_id": "student-inactive",
                "course_id": 2,
                "enrollment_date": "2026-02-03",
                "active": False,
            },
            {
                "id": "enrollment-pending",
                "student_id": "missing-student",
                "course_id": 1,
                "enrollment_date": "2026-02-02",
                "active": True,
            },
        ],
    }

    summary = dashboard_summary(manifest, today="2026-02-03")

    assert summary["summary_date"] == "2026-02-03"
    assert summary["student_count"] == 2
    assert summary["active_students"] == 1
    assert summary["course_count"] == 2
    assert summary["active_courses"] == 1
    assert summary["full_courses"] == 1
    assert summary["enrollment_count"] == 3
    assert summary["active_enrollments"] == 1
    assert summary["today_enrollments"] == 2
    assert summary["pending_enrollments"] == 1
    assert summary["course_occupancy_rows"][0]["id"] == 1
    assert summary["course_occupancy_rows"][0]["student_count"] == 1
    assert summary["recent_enrollments"][0]["id"] == "enrollment-inactive"
    assert summary["recent_enrollments"][-1]["pending_student"] is True


def test_dashboard_summary_handles_an_empty_workspace():
    summary = dashboard_summary(None, today="2026-02-03")

    assert summary["summary_date"] == "2026-02-03"
    assert summary["student_count"] == 0
    assert summary["course_occupancy_rows"] == []
    assert summary["recent_enrollments"] == []
