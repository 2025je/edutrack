import asyncio
from copy import deepcopy
import json
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from hypothesis import given, settings, strategies as st
from alembic import command
from alembic.config import Config
from sqlalchemy import event, inspect, select

from edutrack_desktop.domain.record_service import RecordMutation
from edutrack_desktop.infrastructure.models import CourseRecord, StudentRecord
from edutrack_desktop.infrastructure.search import normalize_search_text
from edutrack_desktop.infrastructure.store import LocalStore
from edutrack_desktop.infrastructure.transfer import (
    PackageError,
    read_package,
    write_package,
)

COURSE_TEXT_ALPHABET = (
    "áéíóúüñÁÉÍÓÚÜÑabcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -_."
)


async def _table_names(store):
    async with store.engine.connect() as connection:
        return await connection.run_sync(
            lambda sync_connection: inspect(sync_connection).get_table_names()
        )


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


def test_corrupt_package_is_rejected(tmp_path):
    path = tmp_path / "corrupt.edutrack"
    path.write_bytes(b"not a zip archive")

    with pytest.raises(PackageError, match="No se pudo abrir"):
        read_package(path)


def test_local_store_persists_workspace(manifest, tmp_path):
    store = LocalStore(tmp_path / "José" / "data.sqlite3")

    async def verify_store():
        await store.save(manifest)
        assert await store.load() == manifest
        assert "desktop_students" in await _table_names(store)
        async with store.session_factory() as session:
            assert (
                await session.get(StudentRecord, manifest["students"][0]["id"])
                is not None
            )

    asyncio.run(verify_store())


def test_local_store_save_updates_rows_without_replacing_tables(manifest, tmp_path):
    store = LocalStore(tmp_path / "incremental.sqlite3")
    student_id = manifest["students"][0]["id"]

    async def verify_incremental_save():
        await store.save(manifest)
        async with store.engine.begin() as connection:
            await connection.exec_driver_sql(
                "CREATE TABLE student_delete_audit (student_id TEXT NOT NULL)"
            )
            await connection.exec_driver_sql(
                "CREATE TRIGGER audit_student_delete "
                "AFTER DELETE ON desktop_students BEGIN "
                "INSERT INTO student_delete_audit(student_id) VALUES (OLD.id); "
                "END"
            )

        updated = deepcopy(manifest)
        updated["students"][0]["first_name"] = "ANA MARÍA"
        updated["courses"][0]["name"] = "MATEMÁTICAS AVANZADAS"
        updated["promoters"][0]["name"] = "PROMOTOR ACTUALIZADO"
        updated["enrollments"][0]["monthly_fee"] = "90.00"
        await store.save(updated)

        async with store.session_factory() as session:
            student = await session.get(StudentRecord, student_id)
            assert student is not None
            assert student.first_name == "ANA MARÍA"
            assert student.server_id == 10
            assert student.base_hash == "a" * 64

        async with store.engine.connect() as connection:
            audit_rows = await connection.exec_driver_sql(
                "SELECT student_id FROM student_delete_audit"
            )
            assert audit_rows.fetchall() == []
        assert await store.load() == updated

        removal = deepcopy(updated)
        removed_id = removal["students"][0]["id"]
        removal["students"] = []
        removal["enrollments"] = []
        await store.save(removal)
        async with store.engine.connect() as connection:
            audit_rows = await connection.exec_driver_sql(
                "SELECT student_id FROM student_delete_audit"
            )
            assert audit_rows.fetchall() == [(removed_id,)]
        assert await store.load() == removal

    asyncio.run(verify_incremental_save())


def test_local_store_incremental_save_rolls_back_invalid_references(
    manifest, tmp_path
):
    store = LocalStore(tmp_path / "rollback.sqlite3")

    async def verify_rollback():
        await store.save(manifest)
        invalid = deepcopy(manifest)
        invalid["campus_name"] = "Cambio que debe revertirse"
        invalid["enrollments"][0]["student_id"] = str(uuid.uuid4())

        with pytest.raises(ValueError, match="estudiante inexistente"):
            await store.save(invalid)

        assert await store.load() == manifest

    asyncio.run(verify_rollback())


def test_local_store_record_save_touches_only_requested_rows(manifest, tmp_path):
    store = LocalStore(tmp_path / "specific-save.sqlite3")
    student_id = manifest["students"][0]["id"]

    async def verify_specific_save():
        await store.save(manifest)
        updated = deepcopy(manifest)
        updated["students"][0]["first_name"] = "ANA ACTUALIZADA"
        statements = []

        def capture_sql(_connection, _cursor, statement, _parameters, *_):
            statements.append(statement.lower())

        event.listen(store.engine.sync_engine, "before_cursor_execute", capture_sql)
        try:
            await store.save_records(
                updated,
                {
                    "students": [
                        RecordMutation(0, updated["students"][0])
                    ]
                },
            )
        finally:
            event.remove(
                store.engine.sync_engine, "before_cursor_execute", capture_sql
            )

        assert any(
            "select" in statement and "from desktop_students" in statement
            for statement in statements
        )
        assert not any(
            ("from desktop_courses" in statement)
            or ("from desktop_enrollments" in statement)
            or ("from desktop_promoters" in statement)
            for statement in statements
        )
        assert not any("delete from" in statement for statement in statements)
        result = await store.search_students("ana actualizada")
        assert result[0]["id"] == student_id

    asyncio.run(verify_specific_save())


def test_incremental_enrollment_save_batches_records_and_reference_checks(
    manifest, tmp_path
):
    data = deepcopy(manifest)
    for _ in range(4):
        enrollment = deepcopy(data["enrollments"][0])
        enrollment["id"] = str(uuid.uuid4())
        enrollment["record_code"] = None
        data["enrollments"].append(enrollment)

    store = LocalStore(tmp_path / "batched-save.sqlite3")

    async def verify_batched_save():
        await store.save(data)
        updated = deepcopy(data)
        changes = []
        for position, enrollment in enumerate(updated["enrollments"]):
            enrollment["monthly_fee"] = f"{81 + position}.00"
            changes.append(RecordMutation(position, enrollment))

        statements = []

        def capture_sql(_connection, _cursor, statement, _parameters, *_):
            if statement.lstrip().lower().startswith("select"):
                statements.append(statement.lower())

        event.listen(store.engine.sync_engine, "before_cursor_execute", capture_sql)
        try:
            await store.save_records(updated, {"enrollments": changes})
        finally:
            event.remove(
                store.engine.sync_engine, "before_cursor_execute", capture_sql
            )

        for table in (
            "desktop_enrollments",
            "desktop_students",
            "desktop_courses",
            "desktop_promoters",
        ):
            assert sum(f"from {table}" in statement for statement in statements) == 1
        assert await store.load() == updated

    try:
        asyncio.run(verify_batched_save())
    finally:
        asyncio.run(store.dispose())


def test_student_page_searches_filters_and_paginates_in_sqlite(
    manifest, tmp_path
):
    data = deepcopy(manifest)
    inactive_student_id = str(uuid.uuid4())
    data["students"].append(
        {
            "id": inactive_student_id,
            "server_id": None,
            "base_hash": None,
            "last_name": "Gómez",
            "first_name": "Luis",
            "document_number": "87654321",
            "phone_numbers": [],
            "active": False,
        }
    )
    data["courses"].append(
        {
            "id": 31,
            "server_id": 31,
            "name": "Historia",
            "schedule": "Tarde",
            "group": "2",
            "start_date": "2026-01-01",
            "enrollment_fee": "100.00",
            "monthly_fee": "80.00",
            "capacity": 20,
            "active": True,
        }
    )
    data["enrollments"].append(
        {
            "id": str(uuid.uuid4()),
            "server_id": None,
            "base_hash": None,
            "student_id": inactive_student_id,
            "student_server_id": None,
            "course_id": 31,
            "enrollment_date": "2026-01-03",
            "promoter_ids": [],
            "enrollment_fee": "100.00",
            "monthly_fee": "80.00",
            "record_code": None,
            "active": True,
            "record_image": None,
            "record_image_hash": "",
            "record_image_quality": 80,
        }
    )
    store = LocalStore(tmp_path / "student-page.sqlite3")

    async def verify_page():
        await store.save(data)

        first_page, total, matching = await store.student_page("", 0, 0, 0, 1)
        second_page, _, _ = await store.student_page("", 0, 0, 1, 1)
        assert total == matching == 2
        assert first_page[0]["label"] == "Gómez Luis"
        assert second_page[0]["label"] == "Pérez Ana"

        inactive_page, _, inactive_count = await store.student_page(
            "", 2, 0, 0, 50
        )
        assert inactive_count == 1
        assert inactive_page[0]["id"] == inactive_student_id

        course_page, _, course_count = await store.student_page(
            "", 0, 30, 0, 50
        )
        assert course_count == 1
        assert course_page[0]["label"] == "Pérez Ana"

        search_page, _, search_count = await store.student_page(
            "historia", 0, 0, 0, 50
        )
        assert search_count == 1
        assert search_page[0]["id"] == inactive_student_id
        assert search_page[0]["courses"] == ["Historia · Tarde · Grupo 2"]

        accented_course_page, _, accented_course_count = await store.student_page(
            "matematicas", 0, 0, 0, 50
        )
        assert accented_course_count == 1
        assert accented_course_page[0]["id"] == manifest["students"][0]["id"]

        accented_page, _, accented_count = await store.student_page(
            "gomez", 0, 0, 0, 50
        )
        assert accented_count == 1
        assert accented_page[0]["id"] == inactive_student_id

    try:
        asyncio.run(verify_page())
    finally:
        asyncio.run(store.dispose())


def test_search_indexes_backfill_and_return_normalized_limited_results(
    manifest, tmp_path
):
    store = LocalStore(tmp_path / "search.sqlite3")

    async def verify_search():
        await store.save(manifest)
        result = await store.search_students("péREZ aNa")
        assert [row["id"] for row in result] == [manifest["students"][0]["id"]]
        assert result[0]["label"] == "Pérez Ana"
        assert result[0]["courses"] == ["Matemáticas · Mañana · Grupo 1"]
        assert await store.search_students("12345678") == result
        assert await store.search_students("sin coincidencia") == []

        async with store.engine.connect() as connection:
            indexes = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_indexes(
                    "desktop_students"
                )
            )
            index_names = {index["name"] for index in indexes}
            assert "ix_desktop_students_last_name_search" in index_names
            assert "ix_desktop_students_first_name_search" in index_names
            assert "ix_desktop_students_document_number_search" in index_names
            enrollment_indexes = {
                index["name"]
                for index in await connection.run_sync(
                    lambda sync_connection: inspect(sync_connection).get_indexes(
                        "desktop_enrollments"
                    )
                )
            }
            assert "ix_desktop_enrollments_student_id" in enrollment_indexes
            assert "ix_desktop_enrollments_course_id" in enrollment_indexes
            assert "ix_desktop_enrollments_active" in enrollment_indexes
            course_indexes = {
                index["name"]
                for index in await connection.run_sync(
                    lambda sync_connection: inspect(sync_connection).get_indexes(
                        "desktop_courses"
                    )
                )
            }
            assert "ix_desktop_courses_name" in course_indexes
            assert "ix_desktop_courses_active" in course_indexes
            promoter_indexes = {
                index["name"]
                for index in await connection.run_sync(
                    lambda sync_connection: inspect(sync_connection).get_indexes(
                        "desktop_promoters"
                    )
                )
            }
            assert "ix_desktop_promoters_name" in promoter_indexes
            plan = await connection.exec_driver_sql(
                "EXPLAIN QUERY PLAN SELECT id FROM desktop_students "
                "WHERE last_name_search LIKE 'per%'"
            )
            assert any(
                "ix_desktop_students_last_name_search" in row[3]
                for row in plan.fetchall()
            )

    asyncio.run(verify_search())


def test_migration_from_revision_0002_backfills_search_columns(manifest, tmp_path):
    database_path = tmp_path / "existing-0002.sqlite3"
    store = LocalStore(database_path)

    async def verify_upgrade():
        await store.save(manifest)
        config_path = (
            Path(__file__).parents[1]
            / "src"
            / "edutrack_desktop"
            / "infrastructure"
            / "alembic.ini"
        )

        def downgrade_schema(connection):
            config = Config(str(config_path))
            config.set_main_option(
                "sqlalchemy.url",
                store.engine.url.render_as_string().replace("%", "%%"),
            )
            config.attributes["connection"] = connection
            command.downgrade(config, "0002_initial_campus")

        async with store.engine.begin() as connection:
            await connection.run_sync(downgrade_schema)
        await store.dispose()

        upgraded_store = LocalStore(database_path)
        assert await upgraded_store.search_students("perez ana")
        course_page, _, course_count = await upgraded_store.student_page(
            "matematicas", 0, 0, 0, 50
        )
        assert course_count == 1
        assert course_page[0]["id"] == manifest["students"][0]["id"]
        assert await upgraded_store.load() == manifest
        await upgraded_store.dispose()

    asyncio.run(verify_upgrade())


@given(st.text())
def test_search_text_normalization_is_idempotent(value):
    normalized = normalize_search_text(value)

    assert normalize_search_text(normalized) == normalized


@settings(max_examples=2, deadline=None)
@given(
    names=st.lists(
        st.text(
            alphabet=COURSE_TEXT_ALPHABET,
            min_size=1,
            max_size=30,
        ),
        min_size=501,
        max_size=501,
    ),
    schedules=st.lists(
        st.text(
            alphabet=COURSE_TEXT_ALPHABET,
            min_size=1,
            max_size=20,
        ),
        min_size=501,
        max_size=501,
    ),
)
def test_course_search_migration_backfills_multiple_batches(names, schedules):
    with TemporaryDirectory() as directory:
        database_path = Path(directory) / "course-search.sqlite3"
        manifest = {
            "format": "edutrack-offline",
            "version": 2,
            "bundle_id": "00000000-0000-0000-0000-000000000001",
            "campus_id": 1,
            "campus_name": "Sede de prueba",
            "campus_address": "",
            "students": [],
            "enrollments": [],
            "courses": [
                {
                    "id": index,
                    "server_id": None,
                    "name": f"{names[index - 1]} {index}",
                    "schedule": schedules[index - 1],
                    "group": "1",
                    "start_date": "2026-01-01",
                    "enrollment_fee": "100.00",
                    "monthly_fee": "80.00",
                    "capacity": 20,
                    "active": True,
                }
                for index in range(1, 502)
            ],
            "promoters": [],
        }

        async def verify_upgrade():
            store = LocalStore(database_path)
            try:
                await store.save(manifest)
                config_path = (
                    Path(__file__).parents[1]
                    / "src"
                    / "edutrack_desktop"
                    / "infrastructure"
                    / "alembic.ini"
                )

                def downgrade_schema(connection):
                    config = Config(str(config_path))
                    config.set_main_option(
                        "sqlalchemy.url",
                        store.engine.url.render_as_string().replace("%", "%%"),
                    )
                    config.attributes["connection"] = connection
                    command.downgrade(config, "0004_sync_history")

                async with store.engine.begin() as connection:
                    await connection.run_sync(downgrade_schema)
            finally:
                await store.dispose()

            upgraded_store = LocalStore(database_path)
            try:
                await upgraded_store.load()
                async with upgraded_store.session_factory() as session:
                    rows = (
                        await session.execute(
                            select(CourseRecord.id, CourseRecord.search_text)
                        )
                    ).all()
                expected = {
                    course["id"]: normalize_search_text(
                        f"{course['name']} · {course['schedule']} · "
                        f"Grupo {course['group']}"
                    )
                    for course in manifest["courses"]
                }
                assert dict(rows) == expected
            finally:
                await upgraded_store.dispose()

        asyncio.run(verify_upgrade())


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

    assert asyncio.run(store.load()) == manifest
    table_names = asyncio.run(_table_names(store))
    assert "workspace" not in table_names
    assert "desktop_students" in table_names
