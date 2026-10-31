import uuid

import pytest
from PySide6.QtCore import QCoreApplication

from edutrack_desktop.application.enrollment import CreateEnrollmentUseCase
from edutrack_desktop.domain.record_service import RecordService
from edutrack_desktop.presentation.backend import DesktopBackend


@pytest.fixture(scope="module", autouse=True)
def qcore_application():
    return QCoreApplication.instance() or QCoreApplication([])


def _manifest():
    student_id = str(uuid.uuid4())
    return {
        "format": "edutrack-offline",
        "version": 2,
        "bundle_id": str(uuid.uuid4()),
        "campus_id": 4,
        "campus_name": "Sede de prueba",
        "campus_address": "",
        "students": [
            {
                "id": student_id,
                "server_id": 45,
                "base_hash": "b" * 64,
                "last_name": "QUISPE",
                "first_name": "MARÍA",
                "document_number": "87654321",
                "phone_numbers": ["987654321"],
                "active": True,
            }
        ],
        "enrollments": [],
        "courses": [
            {
                "id": 12,
                "server_id": 12,
                "name": "INGLÉS",
                "schedule": "MAÑANA",
                "group": "1",
                "start_date": "2026-01-01",
                "enrollment_fee": "100.00",
                "monthly_fee": "80.00",
                "capacity": 20,
                "active": True,
            }
        ],
        "promoters": [
            {"id": 1, "server_id": 1, "name": "PARTICULAR", "active": True},
        ],
    }


def _enrollment_fields(**overrides):
    fields = {
        "course_id": 12,
        "enrollment_date": "2026-01-02",
        "enrollment_fee": "100.00",
        "monthly_fee": "80.00",
        "record_code": "",
        "record_image_quality": 80,
        "promoter_ids": [1],
    }
    fields.update(overrides)
    return fields


def test_use_case_enrolls_existing_student_without_touching_input_manifest():
    manifest = _manifest()
    use_case = CreateEnrollmentUseCase(RecordService())

    result = use_case.execute(
        manifest,
        {"id": manifest["students"][0]["id"]},
        _enrollment_fields(),
    )

    assert manifest["enrollments"] == []
    assert result.student_created is False
    assert result.student_id == manifest["students"][0]["id"]
    assert len(result.manifest["enrollments"]) == 1
    saved = result.manifest["enrollments"][0]
    assert saved["id"] == result.enrollment_id
    assert saved["student_id"] == result.student_id
    assert saved["course_id"] == 12
    assert saved["student_server_id"] == 45


def test_use_case_creates_student_and_enrollment_together():
    manifest = _manifest()
    use_case = CreateEnrollmentUseCase(RecordService())

    result = use_case.execute(
        manifest,
        {
            "last_name": "Pérez",
            "first_name": "Ana",
            "document_number": "12345678",
            "phone_text": "987111222",
        },
        _enrollment_fields(),
    )

    assert result.student_created is True
    assert len(result.manifest["students"]) == 2
    created = result.manifest["students"][-1]
    assert created["id"] == result.student_id
    assert created["last_name"] == "PÉREZ"
    assert result.manifest["enrollments"][0]["student_id"] == result.student_id
    # El manifiesto original no se modifica.
    assert len(manifest["students"]) == 1
    assert manifest["enrollments"] == []


def test_use_case_failure_in_enrollment_does_not_create_student():
    manifest = _manifest()
    use_case = CreateEnrollmentUseCase(RecordService())

    with pytest.raises(ValueError):
        use_case.execute(
            manifest,
            {
                "last_name": "Pérez",
                "first_name": "Ana",
                "document_number": "12345678",
                "phone_text": "987111222",
            },
            _enrollment_fields(enrollment_date="fecha-invalida"),
        )

    assert len(manifest["students"]) == 1
    assert manifest["enrollments"] == []


def test_use_case_failure_in_student_does_not_enroll():
    manifest = _manifest()
    use_case = CreateEnrollmentUseCase(RecordService())

    with pytest.raises(ValueError):
        use_case.execute(
            manifest,
            {
                "last_name": "Pérez",
                "first_name": "Ana",
                "document_number": "12345678",
                "phone_text": "teléfono-malo",
            },
            _enrollment_fields(),
        )

    assert len(manifest["students"]) == 1
    assert manifest["enrollments"] == []


def test_use_case_rejects_unknown_student_id():
    manifest = _manifest()
    use_case = CreateEnrollmentUseCase(RecordService())

    with pytest.raises(ValueError):
        use_case.execute(
            manifest,
            {"id": str(uuid.uuid4())},
            _enrollment_fields(),
        )

    assert manifest["enrollments"] == []


@pytest.mark.parametrize(
    ("inactive_record", "expected_error"),
    [
        ("student", "estudiante inactivo"),
        ("course", "curso inactivo"),
        ("promoter", "promotores inactivos"),
    ],
)
def test_use_case_rejects_inactive_enrollment_references(
    inactive_record, expected_error
):
    manifest = _manifest()
    if inactive_record == "student":
        manifest["students"][0]["active"] = False
    elif inactive_record == "course":
        manifest["courses"][0]["active"] = False
    else:
        manifest["promoters"][0]["active"] = False

    with pytest.raises(ValueError, match=expected_error):
        CreateEnrollmentUseCase(RecordService()).execute(
            manifest,
            {"id": manifest["students"][0]["id"]},
            _enrollment_fields(),
        )

    assert manifest["enrollments"] == []


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
            "record_code": "55",
            "record_image_quality": 80,
            "promoter_ids": [1],
        },
    )

    assert result["ok"] is True
    assert result["student_created"] is True
    assert backend.selectedStudent["id"] == result["student_id"]
    assert backend.selectedEnrollment["id"] == result["enrollment_id"]
    assert backend.errorMessage == "Matrícula guardada en este dispositivo."

    # Los datos quedaron persistidos: reabrir la base los recupera.
    reopened = DesktopBackend(
        backend.store.path,
        catalog_path=tmp_path / "campuses.json",
    )
    assert len(reopened.manifest["students"]) == 1
    assert len(reopened.manifest["enrollments"]) == 1
    assert reopened.manifest["enrollments"][0]["record_code"] == 55


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
    assert backend.manifest["students"] == []
    assert backend.manifest["enrollments"] == []
    assert backend.errorMessage


def test_backend_create_enrollment_requires_open_workspace(tmp_path):
    backend = DesktopBackend(
        tmp_path / "workspace.sqlite3",
        defer_initialize=True,
    )

    result = backend.createEnrollment({}, {})

    assert result["ok"] is False
    assert backend.errorMessage == "Primero abre el archivo de una sede."
