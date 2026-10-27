import json
import sqlite3
import uuid
from contextlib import closing

import pytest
from sqlalchemy import inspect

from edutrack_desktop.models import StudentRecord
from edutrack_desktop.store import LocalStore
from edutrack_desktop.transfer import PackageError, read_package, write_package


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
                "base_hash": "a" * 64,
                "last_name": "Pérez",
                "first_name": "Ana",
                "document_number": "12345678",
                "phone_numbers": ["987654321"],
                "active": True,
            }
        ],
        "enrollments": [
            {
                "id": str(uuid.uuid4()),
                "server_id": 20,
                "base_hash": "b" * 64,
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
        "promoters": [
            {"id": 40, "server_id": 40, "name": "Promotor", "active": True}
        ],
    }


def test_package_round_trips(manifest, tmp_path):
    path = tmp_path / "sede.edutrack"
    write_package(path, manifest)

    assert read_package(path) == manifest


def test_invalid_manifest_is_rejected(manifest, tmp_path):
    path = tmp_path / "sede.edutrack"
    invalid = {**manifest, "version": 1}

    with pytest.raises(PackageError):
        write_package(path, invalid)


def test_local_store_persists_workspace(manifest, tmp_path):
    store = LocalStore(tmp_path / "José" / "data.sqlite3")
    store.save(manifest)

    assert store.load() == manifest
    assert "desktop_students" in inspect(store.engine).get_table_names()
    with store.session_factory() as session:
        assert session.get(StudentRecord, manifest["students"][0]["id"]) is not None


def test_legacy_json_workspace_is_migrated_without_data_loss(manifest, tmp_path):
    path = tmp_path / "legacy.sqlite3"
    legacy_manifest = {
        **manifest,
        "courses": [
            {key: value for key, value in course.items() if key != "server_id"}
            for course in manifest["courses"]
        ],
        "promoters": [
            {key: value for key, value in promoter.items() if key != "server_id"}
            for promoter in manifest["promoters"]
        ],
    }
    legacy_manifest.pop("campus_address")
    with closing(sqlite3.connect(path)) as database:
        with database:
            database.execute(
                "CREATE TABLE workspace (id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL)"
            )
            database.execute(
                "INSERT INTO workspace (id, data) VALUES (1, ?)",
                (json.dumps(legacy_manifest),),
            )

    store = LocalStore(path)

    assert store.load() == manifest
    assert "workspace" not in inspect(store.engine).get_table_names()
    assert "desktop_students" in inspect(store.engine).get_table_names()
