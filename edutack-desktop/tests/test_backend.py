import uuid

import pytest
from PySide6.QtCore import QCoreApplication, QUrl, Qt
from PySide6.QtGui import QImage

from edutrack_desktop.backend import DesktopBackend
from edutrack_desktop.store import LocalStore
from edutrack_desktop.transfer import read_package


@pytest.fixture(scope="module", autouse=True)
def qcore_application():
    return QCoreApplication.instance() or QCoreApplication([])


def test_new_campus_workspace_exports_catalog_and_records(tmp_path):
    backend = DesktopBackend(tmp_path / "workspace.sqlite3")
    assert backend.suggestedDatabaseFileName("Sede Norte") == (
        "edutrack-Sede-Norte.sqlite3"
    )
    assert backend.suggestedDatabaseFileName("Sede/Norte: Central") == (
        "edutrack-Sede-Norte-Central.sqlite3"
    )
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
        course
        for course in backend.manifest["courses"]
        if course["id"] == new_course_id
    )
    assert new_course["server_id"] is None
    reloaded_backend = DesktopBackend(path)
    persisted_course = next(
        course
        for course in reloaded_backend.manifest["courses"]
        if course["id"] == new_course_id
    )
    assert persisted_course["server_id"] is None

    backend.saveStudent(student_id, "Pérez", "Ana Actualizada", "12345678", "987654321")
    backend.saveStudent("", "García", "Luis", "87654321", "912345678")
    new_student = next(
        item
        for item in backend.manifest["students"]
        if item["document_number"] == "87654321"
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


def test_student_validation_matches_web_name_and_phone_rules(tmp_path):
    backend = DesktopBackend(tmp_path / "workspace.sqlite3")
    backend.createWorkspace("Sede de prueba", "")
    phones = [f"9{index:08d}" for index in range(1, 22)]

    backend.saveStudent("", "Pérez", "Ana", "", ", ".join(phones))

    student = backend.selectedStudent
    assert len(student["phone_numbers"]) == 21
    backend.saveStudent("", "PÉREZ", "ANA", "", ", ".join(phones))
    assert len(backend.students) == 1
    assert "Ya existe un estudiante" in backend.errorMessage

    backend.saveStudent(student["id"], "Pérez", "Ana", "", "987654321, 987654321")
    assert backend.selectedStudent["phone_numbers"] == phones
    assert "No repitas un teléfono" in backend.errorMessage


def test_course_validation_normalizes_identity_and_enforces_web_amount_limit(tmp_path):
    backend = DesktopBackend(tmp_path / "workspace.sqlite3")
    backend.createWorkspace("Sede de prueba", "")

    course_id = backend.createCourse(
        "  inglés   básico ",
        " lunes   8:00 ",
        "٠١",
        "2026-01-01",
        "100.00",
        "80.00",
        "20",
    )

    course = next(item for item in backend.courses if item["id"] == course_id)
    assert (course["name"], course["schedule"], course["group"]) == (
        "INGLÉS BÁSICO",
        "LUNES 8:00",
        "1",
    )
    assert (
        backend.createCourse(
            "INGLÉS BÁSICO",
            "LUNES 8:00",
            "1",
            "2026-01-01",
            "100.00",
            "80.00",
            "20",
        )
        == 0
    )
    assert "Ya existe un curso" in backend.errorMessage
    assert (
        backend.createCourse(
            "Curso fuera de rango",
            "Tarde",
            "2",
            "2026-01-01",
            "100000000.00",
            "80.00",
            "20",
        )
        == 0
    )


def test_save_course_updates_validates_and_persists(tmp_path):
    path = tmp_path / "workspace.sqlite3"
    backend = DesktopBackend(path)
    backend.createWorkspace("Sede de prueba", "")
    course_id = backend.createCourse(
        "Cocina", "Sábado", "1", "2026-01-01", "30.00", "50.00", "20"
    )
    existing_course_id = backend.createCourse(
        "Pastelería", "Tarde", "2", "2026-01-02", "40.00", "60.00", "15"
    )
    course = next(item for item in backend.manifest["courses"] if item["id"] == course_id)
    course["server_id"] = 25
    backend.store.save(backend.manifest)
    backend.selectCourse(course_id)

    assert backend.saveCourse(
        course_id,
        "  cocina   avanzada ",
        " lunes 9:00 ",
        "1",
        "2026-02-02",
        "35",
        "55.50",
        "12",
        False,
    )
    assert backend.selectedCourse == {
        "id": course_id,
        "server_id": 25,
        "name": "COCINA AVANZADA",
        "schedule": "LUNES 9:00",
        "group": "1",
        "start_date": "2026-02-02",
        "enrollment_fee": "35.00",
        "monthly_fee": "55.50",
        "capacity": 12,
        "active": False,
    }

    assert not backend.saveCourse(
        course_id,
        "Pastelería",
        "Tarde",
        "2",
        "2026-02-02",
        "35",
        "55.50",
        "12",
        True,
    )
    assert "Ya existe un curso" in backend.errorMessage
    assert backend.selectedCourse["name"] == "COCINA AVANZADA"
    assert existing_course_id != course_id

    reloaded_backend = DesktopBackend(path)
    persisted_course = next(
        item for item in reloaded_backend.courses if item["id"] == course_id
    )
    assert persisted_course["name"] == "COCINA AVANZADA"
    assert persisted_course["server_id"] == 25
    assert persisted_course["active"] is False


def test_enrollment_validation_supports_pending_and_reserved_records(tmp_path):
    backend = DesktopBackend(tmp_path / "workspace.sqlite3")
    backend.createWorkspace("Sede de prueba", "")
    course_id = backend.createCourse(
        "Matemáticas", "Mañana", "1", "2026-01-01", "100.00", "80.00", "20"
    )
    backend.saveStudent("", "Pérez", "Ana", "", "987654321")
    student_id = backend.selectedStudent["id"]

    assert not backend.saveEnrollment(
        "",
        {
            "student_id": "",
            "course_id": "",
            "enrollment_date": "2026-01-02",
            "enrollment_fee": "0.00",
            "monthly_fee": "0.00",
            "record_code": "",
            "record_image_quality": 80,
            "promoter_ids": [],
        },
    )
    assert "requiere un estudiante o un curso" in backend.errorMessage

    assert backend.saveEnrollment(
        "",
        {
            "student_id": student_id,
            "course_id": "",
            "enrollment_date": "2026-01-02",
            "enrollment_fee": "not-a-number",
            "monthly_fee": "",
            "record_code": "",
            "record_image_quality": 80,
            "promoter_ids": [],
        },
    )
    pending = backend.selectedEnrollment
    assert pending["course_id"] is None
    assert pending["enrollment_fee"] == pending["monthly_fee"] == "0.00"

    assert backend.saveEnrollment(
        "",
        {
            "student_id": "",
            "course_id": course_id,
            "enrollment_date": "2026-01-03",
            "enrollment_fee": "100.00",
            "monthly_fee": "80.00",
            "record_code": "",
            "record_image_quality": 80,
            "promoter_ids": [],
        },
    )
    reserved = backend.selectedEnrollment
    assert reserved["student_id"] is None
    assert reserved["course_id"] == course_id


def test_enrollment_validation_rejects_duplicate_pair_code_and_incompatible_promoters(
    tmp_path,
):
    backend = DesktopBackend(tmp_path / "workspace.sqlite3")
    backend.createWorkspace("Sede de prueba", "")
    course_id = backend.createCourse(
        "Matemáticas", "Mañana", "1", "2026-01-01", "100.00", "80.00", "20"
    )
    promoter_id = backend.createPromoter("Promotor local")
    backend.saveStudent("", "Pérez", "Ana", "", "987654321")
    first_student_id = backend.selectedStudent["id"]
    backend.saveStudent("", "García", "Luis", "", "912345678")
    second_student_id = backend.selectedStudent["id"]
    fields = {
        "student_id": first_student_id,
        "course_id": course_id,
        "enrollment_date": "2026-01-02",
        "enrollment_fee": "100.00",
        "monthly_fee": "80.00",
        "record_code": "42",
        "record_image_quality": 80,
        "promoter_ids": [],
    }

    assert backend.saveEnrollment("", fields)
    assert not backend.saveEnrollment("", fields)
    assert "ya está matriculado" in backend.errorMessage

    assert not backend.saveEnrollment(
        "",
        {
            **fields,
            "student_id": second_student_id,
            "record_code": "43",
            "promoter_ids": [1, promoter_id],
        },
    )
    assert "no se pueden combinar" in backend.errorMessage

    assert not backend.saveEnrollment(
        "",
        {
            **fields,
            "student_id": second_student_id,
            "record_code": "42",
        },
    )
    assert "código de ficha ya está registrado" in backend.errorMessage

    assert not backend.saveEnrollment(
        "",
        {
            **fields,
            "record_code": "+43",
        },
    )
    assert "solo números" in backend.errorMessage


def test_saving_enrollment_without_ficha_or_promoter_fields_preserves_existing_values(
    tmp_path,
):
    backend = DesktopBackend(tmp_path / "workspace.sqlite3")
    backend.createWorkspace("Sede de prueba", "")
    course_id = backend.createCourse(
        "Matemáticas", "Mañana", "1", "2026-01-01", "100.00", "80.00", "20"
    )
    promoter_id = backend.createPromoter("Promotor local")
    backend.saveStudent("", "Pérez", "Ana", "", "987654321")
    student_id = backend.selectedStudent["id"]
    fields = {
        "student_id": student_id,
        "course_id": course_id,
        "enrollment_date": "2026-01-02",
        "enrollment_fee": "100.00",
        "monthly_fee": "80.00",
        "record_code": "42",
        "record_image_quality": 60,
        "promoter_ids": [promoter_id],
    }

    assert backend.saveEnrollment("", fields)
    enrollment_id = backend.selectedEnrollment["id"]
    assert backend.saveEnrollment(
        enrollment_id,
        {
            "student_id": student_id,
            "course_id": course_id,
            "enrollment_date": "2026-01-02",
            "enrollment_fee": "100.00",
            "monthly_fee": "80.00",
        },
    )

    enrollment = backend.selectedEnrollment
    assert enrollment["record_code"] == 42
    assert enrollment["record_image_quality"] == 60
    assert enrollment["promoter_ids"] == [promoter_id]


def test_campus_catalog_keeps_separate_database_for_each_site(tmp_path):
    default_path = tmp_path / "default.sqlite3"
    catalog_path = tmp_path / "campuses.json"
    first_path = tmp_path / "sites" / "north.sqlite3"
    second_path = tmp_path / "sites" / "south.sqlite3"
    backend = DesktopBackend(default_path, catalog_path)

    first_path.parent.mkdir()
    first_path.touch()
    assert backend.createWorkspace(
        "Sede Norte",
        "",
        QUrl.fromLocalFile(str(first_path)).toString(),
    )
    backend.createCourse(
        "Matemáticas", "Mañana", "1", "2026-01-01", "100.00", "80.00", "20"
    )
    assert backend.createWorkspace("Sede Sur", "", str(second_path))
    assert [campus["campus_name"] for campus in backend.campuses] == [
        "Sede Norte",
        "Sede Sur",
    ]
    assert backend.courses == []
    assert backend.activeCampusIndex == 1

    assert backend.switchCampus(str(first_path))
    assert backend.campusName == "Sede Norte"
    assert len(backend.courses) == 1
    assert backend.activeCampusIndex == 0

    reopened_backend = DesktopBackend(default_path, catalog_path)
    assert reopened_backend.campusName == "Sede Norte"
    assert len(reopened_backend.courses) == 1

    external_path = tmp_path / "José" / "external.sqlite3"
    external_backend = DesktopBackend(external_path)
    assert external_backend.createWorkspace("Sede Externa", "")
    assert reopened_backend.openLocalDatabase(
        QUrl.fromLocalFile(str(external_path)).toString()
    )
    assert reopened_backend.campusName == "Sede Externa"
    assert reopened_backend.campuses[-1]["campus_name"] == "Sede Externa"


def test_imported_campus_uses_its_own_database(tmp_path):
    backend = DesktopBackend(
        tmp_path / "default.sqlite3",
        tmp_path / "campuses.json",
    )
    source_path = tmp_path / "source.sqlite3"
    imported_path = tmp_path / "imported.sqlite3"
    package_path = tmp_path / "campus.edutrack"

    assert backend.createWorkspace("Sede original", "", str(source_path))
    backend.exportPackage(str(package_path))
    imported_path.touch()
    assert backend.openPackage(
        QUrl.fromLocalFile(str(package_path)).toString(),
        QUrl.fromLocalFile(str(imported_path)).toString(),
    )
    assert backend.campusName == "Sede original"
    assert len(backend.campuses) == 2
    assert backend.activeDatabasePath == str(imported_path.resolve())

    assert backend.switchCampus(str(source_path))
    assert backend.campusName == "Sede original"


def test_importing_updated_package_replaces_only_the_confirmed_matching_site(tmp_path):
    database_path = tmp_path / "sede.sqlite3"
    package_path = tmp_path / "sede.edutrack"
    backend = DesktopBackend(
        tmp_path / "default.sqlite3",
        tmp_path / "campuses.json",
    )
    assert backend.createWorkspace("Sede Norte", "", str(database_path))
    backend.exportPackage(str(package_path))
    backend.saveStudent("", "Pérez", "Ana", "", "987654321")
    assert len(backend.students) == 1

    assert not backend.openPackage(str(package_path), str(database_path))
    assert len(backend.students) == 1
    assert backend.openPackage(str(package_path), str(database_path), True)
    assert backend.campusName == "Sede Norte"
    assert backend.students == []


def test_closing_campus_keeps_database_registered_and_reopenable(tmp_path):
    default_path = tmp_path / "default.sqlite3"
    catalog_path = tmp_path / "campuses.json"
    database_path = tmp_path / "sede.sqlite3"
    backend = DesktopBackend(default_path, catalog_path)
    assert backend.createWorkspace("Sede Guardada", "", str(database_path))
    backend.saveStudent("", "Pérez", "Ana", "", "987654321")

    assert backend.closeCampus()
    assert not backend.hasWorkspace
    assert backend.activeDatabasePath == ""
    assert len(backend.campuses) == 1

    reopened_backend = DesktopBackend(default_path, catalog_path)
    assert not reopened_backend.hasWorkspace
    assert reopened_backend.switchCampus(str(database_path))
    assert reopened_backend.campusName == "Sede Guardada"
    assert len(reopened_backend.students) == 1
