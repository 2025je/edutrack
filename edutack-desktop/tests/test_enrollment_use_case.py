import asyncio
import sqlite3
import uuid

import pytest
from PySide6.QtCore import QCoreApplication

from edutrack_desktop.presentation.backend import DesktopBackend


@pytest.fixture(scope="module", autouse=True)
def qcore_application():
    return QCoreApplication.instance() or QCoreApplication([])


def _enrollment_fields(**overrides):
    fields = {
        "course_id": 12,
        "enrollment_date": "2026-01-02",
        "enrollment_fee": "100.00",
        "monthly_fee": "80.00",
    }
    fields.update(overrides)
    return fields


@pytest.mark.parametrize(
    ("inactive_record", "expected_error"),
    [
        ("student", "estudiante inactivo"),
        ("course", "curso inactivo"),
    ],
)
def test_backend_create_enrollment_rejects_inactive_sqlite_references(
    inactive_record, expected_error, tmp_path
):
    backend = DesktopBackend(tmp_path / "workspace.sqlite3")
    backend.createWorkspace("Sede inicial", "")
    course_id = backend.createCourse(
        "Matemáticas",
        "Mañana",
        "1",
        "2026-01-01",
        "100.00",
        "80.00",
        "20",
    )
    backend.saveStudent("", "Pérez", "Ana", "12345678", "987654321")
    student_id = backend.selectedStudent["id"]
    table, record_id = {
        "student": ("desktop_students", student_id),
        "course": ("desktop_courses", course_id),
    }[inactive_record]

    with sqlite3.connect(backend.store.path) as connection:
        connection.execute(
            f"UPDATE {table} SET active = 0 WHERE id = ?",
            (record_id,),
        )

    result = backend.createEnrollment(
        {"id": student_id},
        _enrollment_fields(course_id=course_id),
    )

    assert result["ok"] is False
    assert expected_error in backend.errorMessage
    persisted = asyncio.run(backend.store.load())
    assert len(persisted["students"]) == 1
    assert persisted["enrollments"] == []


def test_backend_create_enrollment_rejects_unknown_student_from_sqlite(tmp_path):
    backend = DesktopBackend(tmp_path / "workspace.sqlite3")
    backend.createWorkspace("Sede inicial", "")
    course_id = backend.createCourse(
        "Matemáticas",
        "Mañana",
        "1",
        "2026-01-01",
        "100.00",
        "80.00",
        "20",
    )

    result = backend.createEnrollment(
        {"id": str(uuid.uuid4())},
        _enrollment_fields(course_id=course_id),
    )

    assert result["ok"] is False
    assert "estudiante válido" in backend.errorMessage
    persisted = asyncio.run(backend.store.load())
    assert persisted["students"] == []
    assert persisted["enrollments"] == []


def test_backend_create_enrollment_invalid_student_leaves_no_records(tmp_path):
    backend = DesktopBackend(tmp_path / "workspace.sqlite3")
    backend.createWorkspace("Sede inicial", "")
    course_id = backend.createCourse(
        "Matemáticas",
        "Mañana",
        "1",
        "2026-01-01",
        "100.00",
        "80.00",
        "20",
    )

    result = backend.createEnrollment(
        {
            "last_name": "Pérez",
            "first_name": "Ana",
            "document_number": "12345678",
            "phone_text": "teléfono-malo",
        },
        _enrollment_fields(course_id=course_id),
    )

    assert result["ok"] is False
    workspace_info = asyncio.run(backend.store.workspace_info())
    assert workspace_info["students"] == 0
    assert workspace_info["enrollments"] == 0


def test_backend_create_enrollment_persists_atomically(tmp_path):
    backend = DesktopBackend(tmp_path / "workspace.sqlite3")
    backend.createWorkspace("Sede inicial", "Av. Principal 123")
    course_id = backend.createCourse(
        "Matemáticas",
        "Mañana",
        "1",
        "2026-01-01",
        "100.00",
        "80.00",
        "20",
    )
    assert backend.manifest is None

    result = backend.createEnrollment(
        {
            "last_name": "Pérez",
            "first_name": "Ana",
            "document_number": "12345678",
            "phone_text": "987654321",
        },
        {
            "course_id": course_id,
            "enrollment_date": "2026-01-02",
            "enrollment_fee": "100.00",
            "monthly_fee": "80.00",
        },
    )

    assert result["ok"] is True
    assert result["student_created"] is True
    assert backend.manifest is None
    assert backend.errorMessage == "Matrícula guardada en este dispositivo."

    # Los datos operativos se recuperan desde SQLite.
    reopened = DesktopBackend(
        backend.store.path,
        catalog_path=tmp_path / "campuses.json",
    )
    persisted = asyncio.run(reopened.store.load())
    assert len(persisted["students"]) == 1
    assert len(persisted["enrollments"]) == 1
    assert persisted["students"][0]["id"] == result["student_id"]
    assert persisted["enrollments"][0]["record_code"] is None
    assert persisted["enrollments"][0]["promoter_ids"] == []
    assert persisted["enrollments"][0]["id"] == result["enrollment_id"]


def test_backend_create_enrollment_failure_leaves_no_partial_student(tmp_path):
    backend = DesktopBackend(tmp_path / "workspace.sqlite3")
    backend.createWorkspace("Sede inicial", "Av. Principal 123")
    course_id = backend.createCourse(
        "Matemáticas",
        "Mañana",
        "1",
        "2026-01-01",
        "100.00",
        "80.00",
        "20",
    )

    result = backend.createEnrollment(
        {
            "last_name": "Pérez",
            "first_name": "Ana",
            "document_number": "12345678",
            "phone_text": "987654321",
        },
        {
            "course_id": course_id,
            "enrollment_date": "fecha-invalida",
            "enrollment_fee": "100.00",
            "monthly_fee": "80.00",
        },
    )

    assert result["ok"] is False
    workspace_info = asyncio.run(backend.store.workspace_info())
    assert workspace_info["students"] == 0
    assert workspace_info["enrollments"] == 0
    assert backend.errorMessage


def test_backend_create_enrollment_uses_sqlite_without_a_manifest(tmp_path):
    backend = DesktopBackend(tmp_path / "workspace.sqlite3")
    backend.createWorkspace("Sede inicial", "")
    course_id = backend.createCourse(
        "Matemáticas",
        "Mañana",
        "1",
        "2026-01-01",
        "100.00",
        "80.00",
        "20",
    )
    backend.manifest = None

    result = backend.createEnrollment(
        {
            "last_name": "Pérez",
            "first_name": "Ana",
            "document_number": "12345678",
            "phone_text": "987654321",
        },
        _enrollment_fields(course_id=course_id),
    )

    assert result["ok"] is True
    assert result["student_created"] is True
    assert backend.manifest is None
    persisted = asyncio.run(backend.store.load())
    assert len(persisted["students"]) == 1
    assert len(persisted["enrollments"]) == 1
    assert persisted["enrollments"][0]["student_id"] == result["student_id"]


def test_backend_create_enrollment_rejects_duplicate_student_from_sqlite(tmp_path):
    backend = DesktopBackend(tmp_path / "workspace.sqlite3")
    backend.createWorkspace("Sede inicial", "")
    course_id = backend.createCourse(
        "Matemáticas",
        "Mañana",
        "1",
        "2026-01-01",
        "100.00",
        "80.00",
        "20",
    )
    backend.saveStudent("", "Pérez", "Ana", "12345678", "987654321")

    result = backend.createEnrollment(
        {
            "last_name": "pÉrez",
            "first_name": "ana",
            "document_number": "87654321",
            "phone_text": "987111222",
        },
        _enrollment_fields(course_id=course_id),
    )

    assert result["ok"] is False
    assert "Ya existe un estudiante" in backend.errorMessage
    persisted = asyncio.run(backend.store.load())
    assert len(persisted["students"]) == 1
    assert persisted["enrollments"] == []


def test_backend_create_enrollment_uses_existing_student_from_sqlite(tmp_path):
    backend = DesktopBackend(tmp_path / "workspace.sqlite3")
    backend.createWorkspace("Sede inicial", "")
    course_id = backend.createCourse(
        "Matemáticas",
        "Mañana",
        "1",
        "2026-01-01",
        "100.00",
        "80.00",
        "20",
    )
    backend.saveStudent("", "Pérez", "Ana", "12345678", "987654321")
    student_id = backend.selectedStudent["id"]
    backend.manifest = None

    result = backend.createEnrollment(
        {"id": student_id},
        _enrollment_fields(course_id=course_id),
    )

    assert result["ok"] is True
    assert result["student_created"] is False
    persisted = asyncio.run(backend.store.load())
    assert len(persisted["students"]) == 1
    assert len(persisted["enrollments"]) == 1
    assert persisted["enrollments"][0]["student_id"] == student_id


def test_backend_create_enrollment_rolls_back_student_on_sql_failure(tmp_path):
    backend = DesktopBackend(tmp_path / "workspace.sqlite3")
    backend.createWorkspace("Sede inicial", "")
    course_id = backend.createCourse(
        "Matemáticas",
        "Mañana",
        "1",
        "2026-01-01",
        "100.00",
        "80.00",
        "20",
    )
    with sqlite3.connect(backend.store.path) as connection:
        connection.execute(
            "CREATE TRIGGER reject_enrollment_insert "
            "BEFORE INSERT ON desktop_enrollments "
            "BEGIN SELECT RAISE(ABORT, 'test enrollment failure'); END"
        )

    result = backend.createEnrollment(
        {
            "last_name": "Pérez",
            "first_name": "Ana",
            "document_number": "12345678",
            "phone_text": "987654321",
        },
        _enrollment_fields(course_id=course_id),
    )

    assert result["ok"] is False
    persisted = asyncio.run(backend.store.load())
    assert persisted["students"] == []
    assert persisted["enrollments"] == []


def test_backend_create_enrollment_requires_open_workspace(tmp_path):
    backend = DesktopBackend(
        tmp_path / "workspace.sqlite3",
        defer_initialize=True,
    )

    result = backend.createEnrollment({}, {})

    assert result["ok"] is False
    assert backend.errorMessage == "Primero abre el archivo de una sede."
