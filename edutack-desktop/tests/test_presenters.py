from edutrack_desktop.application.presenters import student_rows


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

    assert rows["student-1"]["courses"] == [
        "Matemáticas · Mañana · Grupo 1",
        "Pendiente de curso",
    ]
    assert rows["student-2"]["courses"] == []
