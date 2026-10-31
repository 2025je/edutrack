import asyncio
from copy import deepcopy
import sqlite3
import uuid
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from edutrack_desktop.application.sync import (
    _enrollment_fingerprint,
    _student_fingerprint,
    build_import_preview,
)
from edutrack_desktop.infrastructure.backup import (
    create_sqlite_backup,
    restore_sqlite_backup,
    verify_sqlite_backup,
)
from edutrack_desktop.infrastructure.store import LocalStore
from edutrack_desktop.infrastructure.transfer import write_package
from edutrack_desktop.presentation.backend import DesktopBackend


@pytest.fixture(scope="module", autouse=True)
def qcore_application():
    return QCoreApplication.instance() or QCoreApplication([])


@pytest.fixture
def manifest():
    student_id = str(uuid.uuid4())
    return {
        "format": "edutrack-offline",
        "version": 2,
        "bundle_id": str(uuid.uuid4()),
        "campus_id": 7,
        "campus_name": "Sede de prueba",
        "campus_address": "",
        "students": [
            {
                "id": student_id,
                "server_id": 10,
                "base_hash": None,
                "last_name": "PÉREZ",
                "first_name": "ANA",
                "document_number": "12345678",
                "phone_numbers": ["987654321"],
                "active": True,
            }
        ],
        "enrollments": [
            {
                "id": str(uuid.uuid4()),
                "server_id": 20,
                "base_hash": None,
                "student_id": student_id,
                "student_server_id": 10,
                "course_id": 30,
                "enrollment_date": "2026-01-02",
                "promoter_ids": [40],
                "enrollment_fee": "100.00",
                "monthly_fee": "80.00",
                "record_code": 5,
                "active": True,
                "record_image": None,
                "record_image_hash": "",
                "record_image_quality": 80,
            }
        ],
        "courses": [
            {
                "id": 30,
                "server_id": 30,
                "name": "MATEMÁTICAS",
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
            {
                "id": 40,
                "server_id": 40,
                "name": "PROMOTOR",
                "active": True,
            }
        ],
    }


def _set_base_hashes(value):
    students = {item["id"]: item for item in value["students"]}
    courses = {item["id"]: item for item in value["courses"]}
    promoters = {item["id"]: item for item in value["promoters"]}
    for student in value["students"]:
        student["base_hash"] = _student_fingerprint(student)
    for enrollment in value["enrollments"]:
        enrollment["base_hash"] = _enrollment_fingerprint(
            enrollment,
            students,
            courses,
            promoters,
        )


def test_preview_classifies_unchanged_and_remote_only_updates(manifest):
    local = deepcopy(manifest)
    _set_base_hashes(local)

    unchanged = build_import_preview(local, deepcopy(local))
    assert unchanged["unchanged"] == 4
    assert unchanged["conflicts"] == 0
    assert unchanged["can_import"] is True

    incoming = deepcopy(local)
    incoming["students"][0]["first_name"] = "ANA MARÍA"
    preview = build_import_preview(local, incoming)
    assert preview["updated"] == 1
    assert preview["conflicts"] == 0
    assert preview["can_import"] is True


def test_preview_blocks_concurrent_and_unmatched_local_changes(manifest):
    local = deepcopy(manifest)
    _set_base_hashes(local)
    local["students"][0]["first_name"] = "CAMBIO LOCAL"
    incoming = deepcopy(manifest)
    incoming["students"][0]["first_name"] = "CAMBIO WEB"

    preview = build_import_preview(local, incoming)
    assert preview["conflicts"] == 1
    assert preview["can_import"] is False

    initial_local = deepcopy(manifest)
    initial_local["students"][0]["server_id"] = None
    initial_local["enrollments"][0]["student_server_id"] = None
    initial_local["courses"][0]["server_id"] = None
    initial_local["promoters"][0]["server_id"] = None
    _set_base_hashes(initial_local)
    returned_from_web = deepcopy(initial_local)
    returned_from_web["students"][0]["server_id"] = 99
    returned_from_web["enrollments"][0]["student_server_id"] = 99
    returned_from_web["courses"][0]["server_id"] = 31
    returned_from_web["promoters"][0]["server_id"] = 41
    preview = build_import_preview(initial_local, returned_from_web)
    assert preview["conflicts"] == 0
    assert preview["unchanged"] == 4


def test_preview_counts_new_and_changed_images(manifest):
    local = deepcopy(manifest)
    incoming = deepcopy(manifest)
    incoming["enrollments"][0]["record_image"] = "attachments/" + "a" * 64 + ".jpg"
    incoming["enrollments"][0]["record_image_hash"] = "a" * 64

    preview = build_import_preview(local, incoming)
    assert preview["images_new"] == 1
    assert preview["images_changed"] == 0

    local["enrollments"][0]["record_image"] = "attachments/" + "b" * 64 + ".jpg"
    local["enrollments"][0]["record_image_hash"] = "b" * 64
    preview = build_import_preview(local, incoming)
    assert preview["images_new"] == 0
    assert preview["images_changed"] == 1


def test_preview_requires_confirmation_for_web_image_normalization(manifest):
    local = deepcopy(manifest)
    incoming = deepcopy(manifest)
    local["enrollments"][0]["record_image"] = "attachments/" + "b" * 64 + ".jpg"
    local["enrollments"][0]["record_image_hash"] = "b" * 64
    incoming["enrollments"][0]["record_image"] = "attachments/" + "a" * 64 + ".jpg"
    incoming["enrollments"][0]["record_image_hash"] = "a" * 64

    preview = build_import_preview(local, incoming)
    enrollment = next(item for item in preview["items"] if item["kind"] == "enrollment")
    assert enrollment["state"] == "updated"
    assert enrollment["attention"] is True
    assert preview["conflicts"] == 0
    assert preview["can_import"] is True
    assert preview["images_changed"] == 1


def test_initial_desktop_bundle_matches_first_web_round_trip(manifest):
    incoming = deepcopy(manifest)
    incoming["desktop_bundle_id"] = manifest["bundle_id"]
    incoming["bundle_id"] = str(uuid.uuid4())
    incoming["campus_id"] = 70

    assert DesktopBackend._same_campus(manifest, incoming) is True
    incoming["desktop_bundle_id"] = str(uuid.uuid4())
    assert DesktopBackend._same_campus(manifest, incoming) is False


def test_sync_history_is_atomic_with_manifest_save(manifest, tmp_path):
    store = LocalStore(tmp_path / "history.sqlite3")
    event = {
        "operation": "import",
        "bundle_id": manifest["bundle_id"],
        "created_at": "2026-01-02T03:04:05+00:00",
        "status": "success",
        "affected_counts": {"new": 1, "updated": 0, "unchanged": 3},
        "message": "Paquete validado e importado.",
    }

    async def verify():
        await store.save(manifest)
        invalid = deepcopy(manifest)
        invalid["campus_name"] = "Este cambio debe revertirse"
        invalid["enrollments"][0]["course_id"] = 999
        with pytest.raises(ValueError, match="curso inexistente"):
            await store.save_with_sync_history(invalid, event)
        assert await store.load() == manifest
        assert await store.list_sync_history() == []

        updated = deepcopy(manifest)
        updated["campus_name"] = "Sede actualizada"
        await store.save_with_sync_history(updated, event)
        assert await store.load() == updated
        history = await store.list_sync_history()
        assert len(history) == 1
        assert history[0]["affected_counts"] == event["affected_counts"]
        assert await store.has_imported_bundle(manifest["bundle_id"])

    asyncio.run(verify())


def test_sqlite_backup_is_verified_and_never_overwritten(manifest, tmp_path):
    source = tmp_path / "source.sqlite3"
    asyncio.run(LocalStore(source).save(manifest))
    backup_path = tmp_path / "backups" / "manual.sqlite3"

    assert create_sqlite_backup(source, backup_path) == backup_path.resolve()
    with sqlite3.connect(backup_path) as connection:
        assert connection.execute("PRAGMA quick_check").fetchone() == ("ok",)
    with pytest.raises(FileExistsError):
        create_sqlite_backup(source, backup_path)


def test_backup_verification_checks_workspace_and_integrity(manifest, tmp_path):
    source = tmp_path / "source.sqlite3"
    asyncio.run(LocalStore(source).save(manifest))

    details = verify_sqlite_backup(source)
    assert details["bundle_id"] == manifest["bundle_id"]
    assert details["campus_id"] == manifest["campus_id"]
    assert details["campus_name"] == manifest["campus_name"]

    corrupt = tmp_path / "corrupt.sqlite3"
    corrupt.write_bytes(b"not a sqlite database")
    with pytest.raises(sqlite3.DatabaseError):
        verify_sqlite_backup(corrupt)

    incomplete = tmp_path / "incomplete.sqlite3"
    with sqlite3.connect(incomplete) as connection:
        connection.execute(
            "CREATE TABLE desktop_workspaces ("
            "id INTEGER PRIMARY KEY, format TEXT, version INTEGER, "
            "bundle_id TEXT, campus_id INTEGER, campus_name TEXT)"
        )
        connection.execute(
            "INSERT INTO desktop_workspaces VALUES "
            "(1, 'edutrack-offline', 2, 'bundle', 7, 'Sede')"
        )
    with pytest.raises(sqlite3.DatabaseError, match="todas las tablas"):
        verify_sqlite_backup(incomplete)


def test_restore_sqlite_backup_replaces_database_from_verified_copy(
    manifest, tmp_path
):
    source = tmp_path / "source.sqlite3"
    destination = tmp_path / "destination.sqlite3"
    asyncio.run(LocalStore(source).save(manifest))

    changed = deepcopy(manifest)
    changed["campus_name"] = "Sede que será reemplazada"
    asyncio.run(LocalStore(destination).save(changed))

    assert restore_sqlite_backup(source, destination) == destination.resolve()
    assert asyncio.run(LocalStore(destination).load()) == manifest

    before_invalid_restore = asyncio.run(LocalStore(destination).load())
    invalid_source = tmp_path / "corrupt.sqlite3"
    invalid_source.write_bytes(b"not a sqlite database")
    with pytest.raises(sqlite3.DatabaseError):
        restore_sqlite_backup(invalid_source, destination)
    assert asyncio.run(LocalStore(destination).load()) == before_invalid_restore


def _await_signal(signal, start_operation):
    loop = QEventLoop()
    result = []

    def finished(*args):
        result.append(args)
        if loop.isRunning():
            loop.quit()

    signal.connect(finished)
    assert start_operation()
    QTimer.singleShot(0, lambda: loop.quit() if result else None)
    QTimer.singleShot(10000, loop.quit)
    if not result:
        loop.exec()
    signal.disconnect(finished)
    assert result, "The background operation did not emit its completion signal."
    return result[0]


def test_backend_previews_then_atomically_imports_with_backup_and_history(
    manifest, tmp_path
):
    database_path = tmp_path / "workspace.sqlite3"
    asyncio.run(LocalStore(database_path).save(manifest))
    backend = DesktopBackend(
        database_path,
        catalog_path=tmp_path / "campuses.json",
    )
    incoming = deepcopy(manifest)
    incoming["bundle_id"] = str(uuid.uuid4())
    package_path = tmp_path / "updated.edutrack"
    write_package(package_path, incoming)

    succeeded, preview, error = _await_signal(
        backend.syncPreviewFinished,
        lambda: backend.preparePackageImport(str(package_path)),
    )
    assert succeeded is True
    assert error == ""
    assert preview["can_import"] is True
    assert backend.syncInProgress is False

    succeeded, result, error = _await_signal(
        backend.syncImportFinished,
        backend.confirmPackageImport,
    )
    assert succeeded is True
    assert error == ""
    assert Path(result["backup_path"]).is_file()
    assert asyncio.run(backend.store.load()) == incoming
    history = asyncio.run(backend.store.list_sync_history())
    assert len(history) == 1
    assert history[0]["operation"] == "import"
    assert history[0]["bundle_id"] == incoming["bundle_id"]


def test_backend_manages_and_restores_only_compatible_backups(manifest, tmp_path):
    database_path = tmp_path / "workspace.sqlite3"
    asyncio.run(LocalStore(database_path).save(manifest))
    backend = DesktopBackend(
        database_path,
        catalog_path=tmp_path / "campuses.json",
    )

    _, succeeded, created, error = _await_signal(
        backend.backupOperationFinished,
        backend.createBackup,
    )
    assert succeeded is True
    assert error == ""
    backup_path = Path(created["path"])
    assert backup_path.is_file()
    assert backup_path.parent == tmp_path / "backups"

    assert backend.saveStudent("", "OTRO", "ESTUDIANTE", "", "912345678")
    incompatible_manifest = deepcopy(manifest)
    incompatible_manifest["campus_id"] = 999
    incompatible_manifest["bundle_id"] = str(uuid.uuid4())
    incompatible_path = backup_path.parent / "other-campus.sqlite3"
    asyncio.run(LocalStore(incompatible_path).save(incompatible_manifest))

    _, succeeded, items, error = _await_signal(
        backend.backupOperationFinished,
        backend.refreshBackups,
    )
    assert succeeded is True
    assert error == ""
    incompatible_item = next(
        item for item in items if item["path"] == str(incompatible_path)
    )
    assert incompatible_item["valid"] is True
    assert incompatible_item["compatible"] is False

    _, succeeded, _, error = _await_signal(
        backend.backupOperationFinished,
        lambda: backend.restoreBackup(str(incompatible_path)),
    )
    assert succeeded is False
    assert "otra sede" in error
    assert len(backend.students) == 2

    _, succeeded, restored, error = _await_signal(
        backend.backupOperationFinished,
        lambda: backend.restoreBackup(str(backup_path)),
    )
    assert succeeded is True
    assert error == ""
    assert Path(restored["recovery_backup"]).is_file()
    assert asyncio.run(backend.store.load()) == manifest
    assert len(backend.students) == 1
