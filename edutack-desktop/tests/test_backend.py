import uuid

import pytest
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QImage

from edutrack_desktop.backend import DesktopBackend
from edutrack_desktop.store import LocalStore
from edutrack_desktop.transfer import read_package


@pytest.fixture(scope="module", autouse=True)
def qcore_application():
    return QCoreApplication.instance() or QCoreApplication([])


def test_new_campus_workspace_exports_catalog_and_records(tmp_path):
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
    promoter_id = backend.createPromoter("Promotor local")
    backend.saveStudent("", "Pérez", "Ana", "12345678", "987654321")
    student = backend.selectedStudent
    assert backend.saveEnrollment(
        "",
        {
            "student_id": student["id"],
            "course_id": course_id,
            "enrollment_date": "2026-01-02",
            "enrollment_fee": "100.00",
            "monthly_fee": "80.00",
            "record_code": "",
            "record_image_quality": 80,
            "promoter_ids": [promoter_id],
        },
    )
    backend.selectCourse(course_id)
    assert backend.selectedCourse["id"] == course_id
    assert backend.courses[0]["student_count"] == 1
    assert [student["label"] for student in backend.courseStudents] == ["PÉREZ ANA"]

    output = tmp_path / "sede-inicial.edutrack"
    initial_bundle_id = backend.manifest["bundle_id"]
    backend.exportPackage(str(output))
    package = read_package(output)

    assert package["version"] == 3
    assert package["campus_mode"] == "new"
    assert package["campus_id"] is None
    assert package["campus_name"] == "Sede inicial"
    assert package["campus_address"] == "Av. Principal 123"
    assert package["bundle_id"] == initial_bundle_id
    assert package["courses"][0]["id"] == course_id
    assert package["courses"][0]["server_id"] is None
    assert package["promoters"][-1]["id"] == promoter_id
    assert package["students"][0]["server_id"] is None
    assert package["enrollments"][0]["course_id"] == course_id
    assert package["enrollments"][0]["promoter_ids"] == [promoter_id]


def test_edit_existing_and_add_student_and_enrollment(tmp_path):
    path = tmp_path / "workspace.sqlite3"
    student_id = str(uuid.uuid4())
    course_id = 12
    manifest = {
        "format": "edutrack-offline",
        "version": 2,
        "bundle_id": str(uuid.uuid4()),
        "campus_id": 4,
        "campus_name": "Sede de prueba",
        "students": [
            {
                "id": student_id,
                "server_id": 45,
                "base_hash": "b" * 64,
                "last_name": "PEREZ",
                "first_name": "ANA",
                "document_number": "12345678",
                "phone_numbers": ["987654321"],
                "active": True,
            }
        ],
        "enrollments": [],
        "courses": [
            {
                "id": course_id,
                "name": "Matemáticas",
                "schedule": "Mañana",
                "group": "1",
                "start_date": "2026-01-01",
                "enrollment_fee": "100.00",
                "monthly_fee": "80.00",
                "capacity": 20,
                "active": True,
            }
        ],
        "promoters": [],
    }
    LocalStore(path).save(manifest)
    backend = DesktopBackend(path)

    new_course_id = backend.createCourse(
        "Comunicación",
        "Tarde",
        "2",
        "2026-02-01",
        "50.00",
        "40.00",
        "15",
    )
    new_course = next(
        course for course in backend.manifest["courses"] if course["id"] == new_course_id
    )
    assert new_course["server_id"] is None
    reloaded_backend = DesktopBackend(path)
    persisted_course = next(
        course for course in reloaded_backend.manifest["courses"] if course["id"] == new_course_id
    )
    assert persisted_course["server_id"] is None

    backend.saveStudent(student_id, "Pérez", "Ana Actualizada", "12345678", "987654321")
    backend.saveStudent("", "García", "Luis", "87654321", "912345678")
    new_student = next(
        item for item in backend.manifest["students"] if item["document_number"] == "87654321"
    )
    backend.saveEnrollment(
        "",
        {
            "student_id": new_student["id"],
            "course_id": course_id,
            "enrollment_date": "2026-01-02",
            "enrollment_fee": "100.00",
            "monthly_fee": "80.00",
            "record_code": "5",
            "promoter_ids": [],
        },
    )
    image_path = tmp_path / "ficha.png"
    image = QImage(3, 3, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.blue)
    assert image.save(str(image_path), "PNG")
    backend.attachEnrollmentImage(str(image_path))
    assert backend.store.load() == backend.manifest

    output = tmp_path / "changes.edutrack"
    backend.exportPackage(str(output))
    updated = read_package(output)
    assert any(
        course["id"] == new_course_id and course["server_id"] is None
        for course in updated["courses"]
    )

    existing = next(item for item in updated["students"] if item["id"] == student_id)
    assert existing["server_id"] == 45
    assert existing["base_hash"] == "b" * 64
    assert existing["first_name"] == "ANA ACTUALIZADA"
    assert new_student["server_id"] is None
    assert len(updated["enrollments"]) == 1
    assert updated["enrollments"][0]["student_id"] == new_student["id"]
    image_name = updated["enrollments"][0]["record_image"]
    assert image_name in updated["_attachment_data"]
    assert "correctamente" in backend.errorMessage
