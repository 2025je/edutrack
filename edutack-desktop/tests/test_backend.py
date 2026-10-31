import asyncio
import time
import uuid
from copy import deepcopy

import pytest
from PySide6.QtCore import (
    QAbstractListModel,
    QCoreApplication,
    QEventLoop,
    QTimer,
    QUrl,
    Qt,
)
from PySide6.QtGui import QImage

from edutrack_desktop.infrastructure.app_settings import DesktopSettings
from edutrack_desktop.infrastructure.store import LocalStore
from edutrack_desktop.infrastructure.transfer import read_package
from edutrack_desktop.presentation.backend import DesktopBackend
from edutrack_desktop.presentation.list_models import (
    CourseListModel,
    EnrollmentListModel,
)


@pytest.fixture(scope="module", autouse=True)
def qcore_application():
    return QCoreApplication.instance() or QCoreApplication([])


def test_desktop_settings_configure_default_storage_paths(tmp_path):
    created_paths = []

    def store_factory(path):
        created_paths.append(path)
        return LocalStore(path)

    backend = DesktopBackend(
        settings=DesktopSettings(data_dir=tmp_path),
        store_factory=store_factory,
    )

    assert backend.store.path == (tmp_path / "edutrack-desktop.sqlite3").resolve()
    assert backend.catalog.path == (tmp_path / "campuses.json").resolve()
    assert created_paths == [backend.store.path]


def test_backend_can_defer_initialization(tmp_path):
    backend = DesktopBackend(
        tmp_path / "workspace.sqlite3",
        defer_initialize=True,
    )

    assert backend.store is None
    assert backend.manifest is None


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
    asyncio.run(LocalStore(path).save(manifest))
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
    assert asyncio.run(backend.store.load()) == backend.manifest

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


def test_database_saves_expose_global_saving_state(tmp_path):
    def store_factory(path):
        store = LocalStore(path)
        store_save = store.save

        async def slow_save(manifest):
            time.sleep(0.1)
            await store_save(manifest)

        store.save = slow_save
        return store

    backend = DesktopBackend(
        tmp_path / "workspace.sqlite3", store_factory=store_factory
    )
    saving_states = []
    backend.savingStateChanged.connect(
        lambda: saving_states.append(backend.isSaving)
    )
    assert backend.createWorkspace("Sede de prueba", "")
    assert saving_states == [True, False]

    assert backend.saveStudent("", "Pérez", "Ana", "12345678", "987654321")
    assert saving_states == [True, False, True, False]


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


def test_student_can_be_deactivated_and_activated(tmp_path):
    backend = DesktopBackend(tmp_path / "workspace.sqlite3")
    backend.createWorkspace("Sede de prueba", "")
    backend.saveStudent("", "Pérez", "Ana", "", "987654321")
    student_id = backend.selectedStudent["id"]

    assert backend.setStudentActive(student_id, False)
    assert backend.students[0]["active"] is False
    assert "desactivado correctamente" in backend.errorMessage

    assert backend.setStudentActive(student_id, True)
    assert backend.students[0]["active"] is True
    assert "activado correctamente" in backend.errorMessage

    assert not backend.setStudentActive("missing-student", True)
    assert "Selecciona un estudiante válido" in backend.errorMessage


def test_student_pages_filter_and_refresh_after_saving(tmp_path):
    backend = DesktopBackend(tmp_path / "workspace.sqlite3")
    backend.createWorkspace("Sede de prueba", "")
    backend.saveStudent("", "ROJAS", "LUIS", "11111111", "987654321")
    backend.saveStudent("", "PEREZ", "ANA", "22222222", "912345678")
    backend.saveStudent("", "GOMEZ", "MARIO", "33333333", "923456789")

    assert backend.matchingStudentCount("") == 3
    assert [row["label"] for row in backend.studentPage("", 0, 2)] == [
        "GOMEZ MARIO",
        "PEREZ ANA",
    ]
    assert [row["label"] for row in backend.studentPage("", 1, 2)] == [
        "ROJAS LUIS"
    ]
    assert backend.matchingStudentCount("2222") == 1
    assert backend.studentPage("2222", 0, 50)[0]["label"] == "PEREZ ANA"

    backend.saveStudent("", "ALVA", "SOFIA", "44444444", "934567890")
    assert backend.matchingStudentCount("") == 4
    assert not backend.studentPage("", 0, 101)


def test_student_list_model_filters_and_refreshes_after_saving(tmp_path):
    backend = DesktopBackend(tmp_path / "workspace.sqlite3")
    backend.createWorkspace("Sede de prueba", "")
    backend.saveStudent("", "ROJAS", "LUIS", "11111111", "987654321")
    backend.saveStudent("", "PEREZ", "ANA", "22222222", "912345678")
    backend.saveStudent("", "GOMEZ", "MARIO", "33333333", "923456789")

    model = backend.studentListModel
    assert isinstance(model, QAbstractListModel)
    model.activate()
    role_ids = {
        role_name.data().decode(): role_id
        for role_id, role_name in model.roleNames().items()
    }

    assert model.totalCount == 3
    assert model.matchingCount == 3
    assert model.rowCount() == 3
    assert model.data(model.index(0, 0), role_ids["label"]) == "GOMEZ MARIO"

    model.setQuery("2222")
    assert model.matchingCount == 1
    assert model.rowCount() == 1
    assert model.data(model.index(0, 0), role_ids["studentId"])
    assert model.rowAt(0)["label"] == "PEREZ ANA"

    backend.saveStudent("", "ALVA", "SOFIA", "44444444", "934567890")
    assert model.totalCount == 4
    assert model.matchingCount == 1


def test_course_list_model_searches_accent_insensitively_and_counts_active_students(
    tmp_path,
):
    backend = DesktopBackend(tmp_path / "workspace.sqlite3")
    backend.createWorkspace("Sede de prueba", "")
    course_id = backend.createCourse(
        "Matemáticas",
        "Mañana",
        "1",
        "2026-01-05",
        "100.00",
        "80.00",
        "20",
    )
    backend.createCourse(
        "Inglés",
        "Tarde",
        "2",
        "2026-02-02",
        "100.00",
        "80.00",
        "20",
    )
    assert backend.saveStudent(
        "",
        "PÉREZ",
        "ANA",
        "12345678",
        "987654321",
    )
    student_id = backend.selectedStudent["id"]
    assert backend.saveEnrollment(
        "",
        {
            "student_id": student_id,
            "course_id": course_id,
            "enrollment_date": "2026-01-05",
            "enrollment_fee": "100.00",
            "monthly_fee": "80.00",
        },
    )

    model = backend.courseListModel
    assert isinstance(model, QAbstractListModel)
    model.activate()
    assert model.totalCount == 2
    assert model.matchingCount == 2

    model.setQuery("matematicas manana")
    assert model.matchingCount == 1
    assert model.rowCount() == 1
    course_group = model.rowAt(0)
    assert course_group["courses"][0]["id"] == course_id
    assert course_group["courses"][0]["student_count"] == 1

    model.setQuery("2026-02")
    assert model.matchingCount == 1
    assert model.rowAt(0)["courses"][0]["name"].casefold() == "inglés".casefold()


def test_course_list_model_paginates_before_grouping():
    rows = [
        {
            "id": index,
            "name": f"Curso {index}",
            "schedule": "Mañana",
            "group": "1",
            "start_date": "2026-01-05",
            "student_count": 0,
            "capacity": 20,
            "active": True,
        }
        for index in range(1, 4)
    ]

    def page_provider(query, page_index, page_size):
        matching = [
            row for row in rows if query.lower() in row["name"].lower()
        ]
        start = page_index * page_size
        return matching[start : start + page_size], len(rows), len(matching)

    model = CourseListModel(page_provider, page_size=2)
    model.activate()

    assert model.totalCount == 3
    assert model.matchingCount == 3
    assert model.pageCount == 2
    assert [row["id"] for row in model.rowAt(0)["courses"]] == [1, 2]

    model.setPageIndex(1)
    assert [row["id"] for row in model.rowAt(0)["courses"]] == [3]
    model.setQuery("Curso 2")
    assert model.pageIndex == 0
    assert model.matchingCount == 1
    assert model.rowAt(0)["courses"][0]["id"] == 2


def test_enrollment_list_model_filters_status_and_pages_rows():
    rows = [
        {
            "id": "active",
            "student_label": "PEREZ ANA",
            "course_label": "English · Morning · Group 1",
            "enrollment_date": "2026-01-04",
            "active": True,
            "pending_student": False,
            "pending_course": False,
            "course_id": 10,
        },
        {
            "id": "inactive",
            "student_label": "PEREZ LUIS",
            "course_label": "English · Morning · Group 1",
            "enrollment_date": "2026-01-03",
            "active": False,
            "pending_student": False,
            "pending_course": False,
            "course_id": 10,
        },
        {
            "id": "pending-student",
            "student_label": "Pendiente de estudiante",
            "course_label": "English · Morning · Group 1",
            "enrollment_date": "2026-01-02",
            "active": True,
            "pending_student": True,
            "pending_course": False,
            "course_id": 10,
        },
        {
            "id": "pending-course",
            "student_label": "GOMEZ MARIO",
            "course_label": "Pendiente de curso",
            "enrollment_date": "2026-01-01",
            "active": True,
            "pending_student": False,
            "pending_course": True,
            "course_id": None,
        },
    ]
    model = EnrollmentListModel(lambda: rows, page_size=2)
    model.activate()

    assert isinstance(model, QAbstractListModel)
    assert model.totalCount == 4
    assert model.matchingCount == 4
    assert model.rowCount() == 2
    assert model.pageCount == 2
    model.setPageIndex(1)
    assert model.rowAt(0)["id"] == "pending-student"
    assert model.rowAt(1)["id"] == "pending-course"

    model.setFilters("perez", 1, 10)
    assert model.pageIndex == 0
    assert model.matchingCount == 1
    assert model.rowAt(0)["id"] == "active"

    model.setFilters("", 2, 10)
    assert model.rowAt(0)["id"] == "inactive"
    model.setFilters("", 3, 0)
    assert model.rowAt(0)["id"] == "pending-student"
    model.setFilters("", 4, 0)
    assert model.rowAt(0)["id"] == "pending-course"


def test_dashboard_summary_cache_updates_and_workspace_refresh_reloads(tmp_path):
    path = tmp_path / "workspace.sqlite3"
    backend = DesktopBackend(path)
    backend.createWorkspace("Sede de prueba", "")

    assert backend.dashboardSummary["student_count"] == 0
    backend.saveStudent("", "Pérez", "Ana", "", "987654321")
    assert backend.dashboardSummary["student_count"] == 1

    external_manifest = deepcopy(backend.manifest)
    external_manifest["campus_address"] = "Dirección actualizada"
    asyncio.run(backend.store.save(external_manifest))

    assert backend.manifest["campus_address"] == ""
    assert backend.refreshWorkspace()
    assert backend.manifest["campus_address"] == "Dirección actualizada"


def test_search_students_normalizes_limits_and_reports_enrollments(tmp_path):
    backend = DesktopBackend(tmp_path / "workspace.sqlite3")
    backend.createWorkspace("Sede de prueba", "")
    course_id = backend.createCourse(
        "Inglés", "Mañana", "1", "2026-01-01", "100.00", "80.00", "20"
    )
    backend.saveStudent("", "ROJAS", "LUIS", "11111111", "987654321")
    backend.saveStudent("", "PEREZ", "ANA", "22222222", "912345678")
    backend.saveStudent("", "PEREYRA", "JOSE", "33333333", "923456789")
    enrolled = backend.searchStudents("perez ana")[0]
    backend.saveEnrollment(
        "",
        {
            "student_id": enrolled["id"],
            "course_id": course_id,
            "enrollment_date": "2026-01-02",
            "enrollment_fee": "100.00",
            "monthly_fee": "80.00",
        },
    )

    # Sin consulta devuelve los más recientes primero.
    assert [row["label"] for row in backend.searchStudents("")] == [
        "PEREYRA JOSE",
        "PEREZ ANA",
        "ROJAS LUIS",
    ]
    # Insensible a mayúsculas y busca por apellido o documento.
    assert [row["label"] for row in backend.searchStudents("pere")] == [
        "PEREYRA JOSE",
        "PEREZ ANA",
    ]
    assert backend.searchStudents("2222")[0]["label"] == "PEREZ ANA"
    # Respeta el límite y rechaza límites inválidos sin fallar.
    assert len(backend.searchStudents("", 2)) == 2
    assert len(backend.searchStudents("", 0)) == 3
    assert len(backend.searchStudents("", 500)) == 3
    # Expone las matrículas activas para advertir en el asistente.
    match = backend.searchStudents("perez ana")[0]
    assert len(match["courses"]) == 1
    assert backend.searchStudents("pereyra")[0]["courses"] == []
    # Sin sede abierta no devuelve resultados.
    closed = DesktopBackend(tmp_path / "otra.sqlite3", defer_initialize=True)
    assert closed.searchStudents("pere") == []


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
    asyncio.run(backend.store.save(backend.manifest))
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


def test_save_course_async_persists_and_signals_completion(tmp_path):
    path = tmp_path / "workspace.sqlite3"
    backend = DesktopBackend(path)
    backend.createWorkspace("Sede de prueba", "")
    course_id = backend.createCourse(
        "Cocina", "Sábado", "1", "2026-01-01", "30.00", "50.00", "20"
    )
    loop = QEventLoop()
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit)
    completed = []

    def on_finished(saved):
        completed.append(saved)
        loop.quit()

    backend.courseSaveFinished.connect(on_finished)
    assert backend.saveCourseAsync(
        course_id,
        "Cocina avanzada",
        "Lunes 9:00",
        "1",
        "2026-02-02",
        "35.00",
        "55.50",
        "12",
        True,
    )
    assert backend.courseSaveInProgress
    timeout.start(5000)
    if not completed:
        loop.exec()
    timeout.stop()

    assert completed == [True]
    assert not backend.courseSaveInProgress
    assert backend.selectedCourse["name"] == "COCINA AVANZADA"
    reloaded_backend = DesktopBackend(path)
    persisted_course = next(
        item for item in reloaded_backend.courses if item["id"] == course_id
    )
    assert persisted_course["name"] == "COCINA AVANZADA"


def test_save_course_async_reports_persistence_errors(tmp_path, monkeypatch):
    backend = DesktopBackend(tmp_path / "workspace.sqlite3")
    backend.createWorkspace("Sede de prueba", "")
    course_id = backend.createCourse(
        "Cocina", "Sábado", "1", "2026-01-01", "30.00", "50.00", "20"
    )
    backend.selectCourse(course_id)

    async def fail_save_records(_manifest, _record_changes):
        raise OSError("disco lleno")

    monkeypatch.setattr(backend.store, "save_records", fail_save_records)
    loop = QEventLoop()
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit)
    completed = []

    def on_finished(saved):
        completed.append(saved)
        loop.quit()

    backend.courseSaveFinished.connect(on_finished)
    assert backend.saveCourseAsync(
        course_id,
        "Cocina avanzada",
        "Lunes 9:00",
        "1",
        "2026-02-02",
        "35.00",
        "55.50",
        "12",
        True,
    )
    timeout.start(5000)
    if not completed:
        loop.exec()
    timeout.stop()

    assert completed == [False]
    assert not backend.courseSaveInProgress
    assert "disco lleno" in backend.errorMessage
    assert backend.selectedCourse["name"] == "COCINA"


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
    assert backend.saveEnrollment(
        enrollment_id,
        {
            "student_id": student_id,
            "course_id": course_id,
            "enrollment_date": "2026-01-02",
            "enrollment_fee": "100.00",
            "monthly_fee": "80.00",
            "active": False,
        },
    )

    enrollment = backend.selectedEnrollment
    assert enrollment["record_code"] == 42
    assert enrollment["record_image_quality"] == 60
    assert enrollment["promoter_ids"] == [promoter_id]
    assert enrollment["active"] is False


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

    original_store_factory = backend._store_factory

    def slow_store_factory(path):
        store = original_store_factory(path)
        store_load = store.load

        async def slow_load():
            time.sleep(0.1)
            return await store_load()

        store.load = slow_load
        return store

    backend._store_factory = slow_store_factory
    activity_states = []
    backend.activityStateChanged.connect(
        lambda: activity_states.append((backend.isBusy, backend.activityMessage))
    )
    assert backend.switchCampus(str(first_path))
    assert activity_states == [
        (True, "Cargando los datos de la sede..."),
        (False, ""),
    ]
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


def test_removing_saved_campus_only_removes_catalog_entry(tmp_path):
    default_path = tmp_path / "default.sqlite3"
    catalog_path = tmp_path / "campuses.json"
    saved_path = tmp_path / "sites" / "saved.sqlite3"
    active_path = tmp_path / "sites" / "active.sqlite3"
    backend = DesktopBackend(default_path, catalog_path)

    assert backend.createWorkspace("Sede guardada", "", str(saved_path))
    assert backend.createWorkspace("Sede activa", "", str(active_path))
    assert not backend.removeCampusFromList(str(active_path))
    assert "Cierra la sede activa" in backend.errorMessage
    assert len(backend.campuses) == 2

    assert backend.removeCampusFromList(str(saved_path))
    assert saved_path.is_file()
    assert [campus["campus_name"] for campus in backend.campuses] == [
        "Sede activa"
    ]
    assert backend.catalog.active_path == str(active_path.resolve())
    assert "se conservaron" in backend.errorMessage

    assert backend.closeCampus()
    reopened_backend = DesktopBackend(default_path, catalog_path)
    assert [campus["campus_name"] for campus in reopened_backend.campuses] == [
        "Sede activa"
    ]
    assert saved_path.is_file()
    assert active_path.is_file()


def test_removing_last_default_campus_stays_removed_after_restart(tmp_path):
    database_path = tmp_path / "default.sqlite3"
    catalog_path = tmp_path / "campuses.json"
    backend = DesktopBackend(database_path, catalog_path)

    assert backend.createWorkspace("Sede guardada", "", str(database_path))
    assert backend.closeCampus()
    assert backend.removeCampusFromList(str(database_path))
    assert database_path.is_file()
    assert backend.campuses == []

    reopened_backend = DesktopBackend(database_path, catalog_path)
    assert not reopened_backend.hasWorkspace
    assert reopened_backend.campuses == []
    assert database_path.is_file()


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
    backups = list((tmp_path / "backups").glob("sede-*.sqlite3"))
    assert len(backups) == 1
    history = asyncio.run(backend.store.list_sync_history())
    imports = [event for event in history if event["operation"] == "import"]
    assert len(imports) == 1
    assert imports[0]["status"] == "success"
    assert "Respaldo:" in backend.errorMessage
    assert not backend.openPackage(str(package_path), str(database_path), True)
    assert "ya se importó" in backend.errorMessage


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
