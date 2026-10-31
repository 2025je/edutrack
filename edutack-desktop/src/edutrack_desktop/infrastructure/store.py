import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, Table, URL, event, exists, func, inspect, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.sql.elements import ColumnElement
import structlog

from .models import (
    CourseRecord,
    EnrollmentRecord,
    PromoterRecord,
    SyncHistoryRecord,
    StudentRecord,
    Workspace,
)
from .backup import create_sqlite_backup
from .search import normalize_search_text

logger = structlog.get_logger(__name__)
audit_logger = structlog.get_logger("edutrack_desktop.database")


class LocalStore:
    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_async_engine(
            URL.create("sqlite+aiosqlite", database=str(self.path)),
            poolclass=NullPool,
        )
        event.listen(
            self.engine.sync_engine, "before_cursor_execute", self._log_statement
        )
        event.listen(self.engine.sync_engine, "connect", self._enable_foreign_keys)
        self.session_factory = async_sessionmaker(
            self.engine, expire_on_commit=False
        )
        self._initialized = False

    async def initialize(self):
        if self._initialized:
            return

        audit_logger.info("database.schema_upgrade_started")
        config_path = Path(__file__).resolve().parent / "alembic.ini"

        def upgrade_schema(connection):
            config = Config(str(config_path))
            config.set_main_option(
                "sqlalchemy.url",
                self.engine.url.render_as_string().replace("%", "%%"),
            )
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        async with self.engine.begin() as connection:
            await connection.run_sync(upgrade_schema)

        await self._migrate_legacy_workspace()
        self._initialized = True
        audit_logger.info("database.schema_upgrade_completed")

    def _log_statement(
        self, connection, cursor, statement, parameters, context, executemany
    ):
        logger.debug(
            "database.statement",
            database_path=str(self.path),
            sql=statement,
            executemany=executemany,
        )

    @staticmethod
    def _enable_foreign_keys(connection, _):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async def _migrate_legacy_workspace(self):
        def read_legacy_workspace(connection):
            if not inspect(connection).has_table("workspace"):
                return False, None

            metadata = MetaData()
            legacy = Table("workspace", metadata, autoload_with=connection)
            if "id" not in legacy.c or "data" not in legacy.c:
                raise RuntimeError(
                    "La tabla local antigua workspace no tiene el formato esperado."
                )
            row = connection.execute(
                select(legacy.c.data).where(legacy.c.id == 1)
            ).first()
            return True, row.data if row is not None else None

        async with self.engine.connect() as connection:
            table_exists, legacy_data = await connection.run_sync(
                read_legacy_workspace
            )
        if not table_exists:
            return

        if legacy_data is not None:
            manifest = json.loads(legacy_data)
            if await self._load() is None:
                await self._save(manifest)

        def drop_legacy_workspace(connection):
            legacy = Table("workspace", MetaData(), autoload_with=connection)
            legacy.drop(connection)

        async with self.engine.begin() as connection:
            await connection.run_sync(drop_legacy_workspace)

    async def load(self):
        await self.initialize()
        return await self._load()

    async def search_students(self, query: str, limit: int = 20):
        await self.initialize()
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            limit = 20
        limit = min(limit, 100)
        tokens = normalize_search_text(query).split()

        async with self.session_factory() as session:
            statement = select(StudentRecord)
            for index, token in enumerate(tokens):
                escaped = token.replace("\\", "\\\\").replace("%", "\\%").replace(
                    "_", "\\_"
                )
                pattern = f"{escaped}%"
                search_columns = (
                    StudentRecord.last_name_search,
                    StudentRecord.first_name_search,
                    StudentRecord.document_number_search,
                )
                token_conditions = [
                    column.like(pattern, escape="\\") for column in search_columns
                ]
                if index:
                    word_pattern = f"% {escaped}%"
                    token_conditions.extend(
                        column.like(word_pattern, escape="\\")
                        for column in search_columns
                    )
                statement = statement.where(
                    or_(*token_conditions)
                )
            students = (
                await session.scalars(
                    statement.order_by(StudentRecord.position.desc()).limit(limit)
                )
            ).all()
            if not students:
                return []

            student_ids = [student.id for student in students]
            enrollment_rows = (
                await session.execute(
                    select(
                        EnrollmentRecord.student_id,
                        CourseRecord.name,
                        CourseRecord.schedule,
                        CourseRecord.group_name,
                    )
                    .outerjoin(
                        CourseRecord,
                        EnrollmentRecord.course_id == CourseRecord.id,
                    )
                    .where(
                        EnrollmentRecord.active.is_(True),
                        EnrollmentRecord.student_id.in_(student_ids),
                    )
                    .order_by(EnrollmentRecord.position.desc())
                )
            ).all()
            active_courses: dict[str, list[str]] = {}
            for student_id, name, schedule, group_name in enrollment_rows:
                if student_id is None:
                    continue
                course_label = (
                    f"{name} · {schedule} · Grupo {group_name}"
                    if name is not None
                    else "Pendiente de curso"
                )
                active_courses.setdefault(student_id, []).append(course_label)

            return [
                {
                    "id": student.id,
                    "server_id": student.server_id,
                    "base_hash": student.base_hash,
                    "last_name": student.last_name,
                    "first_name": student.first_name,
                    "document_number": student.document_number,
                    "phone_numbers": student.phone_numbers,
                    "active": student.active,
                    "courses": active_courses.get(student.id, []),
                    "label": " ".join(
                        part
                        for part in (student.last_name, student.first_name)
                        if part
                    ),
                }
                for student in students
            ]

    async def student_page(
        self,
        query: str,
        status_filter_index: int,
        course_filter_id: int,
        page_index: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int, int]:
        await self.initialize()
        if status_filter_index not in (0, 1, 2):
            raise ValueError("El filtro de estado de estudiantes no es válido.")
        if course_filter_id < 0 or page_index < 0 or not 1 <= page_size <= 100:
            raise ValueError("La página de estudiantes solicitada no es válida.")

        conditions: list[ColumnElement[bool]] = []
        if status_filter_index == 1:
            conditions.append(StudentRecord.active.is_(True))
        elif status_filter_index == 2:
            conditions.append(StudentRecord.active.is_(False))

        if course_filter_id:
            conditions.append(
                exists(
                    select(EnrollmentRecord.id).where(
                        EnrollmentRecord.student_id == StudentRecord.id,
                        EnrollmentRecord.course_id == course_filter_id,
                        EnrollmentRecord.active.is_(True),
                    )
                )
            )

        query = query.strip()
        async with self.session_factory() as session:
            if query:
                normalized_query = normalize_search_text(query)
                escaped_query = (
                    normalized_query.replace("\\", "\\\\")
                    .replace("%", "\\%")
                    .replace("_", "\\_")
                )
                pattern = f"%{escaped_query}%"
                searchable_columns = (
                    StudentRecord.last_name_search,
                    StudentRecord.first_name_search,
                    StudentRecord.document_number_search,
                    StudentRecord.last_name_search
                    + " "
                    + StudentRecord.first_name_search,
                )
                search_conditions: list[ColumnElement[bool]] = [
                    column.like(pattern, escape="\\")
                    for column in searchable_columns
                ]
                folded_query = query.casefold()
                course_rows = (
                    await session.execute(
                        select(
                            CourseRecord.id,
                            CourseRecord.name,
                            CourseRecord.schedule,
                            CourseRecord.group_name,
                        )
                    )
                ).all()
                matching_course_ids = [
                    course_id
                    for course_id, name, schedule, group_name in course_rows
                    if folded_query
                    in f"{name} · {schedule} · Grupo {group_name}".casefold()
                ]

                if matching_course_ids:
                    search_conditions.append(
                        exists(
                            select(EnrollmentRecord.id)
                            .join(
                                CourseRecord,
                                EnrollmentRecord.course_id == CourseRecord.id,
                            )
                            .where(
                                EnrollmentRecord.student_id == StudentRecord.id,
                                EnrollmentRecord.active.is_(True),
                                EnrollmentRecord.course_id.in_(matching_course_ids),
                            )
                        )
                    )
                conditions.append(or_(*search_conditions))

            total_count = await session.scalar(
                select(func.count()).select_from(StudentRecord)
            )
            matching_count = await session.scalar(
                select(func.count())
                .select_from(StudentRecord)
                .where(*conditions)
            )
            students = (
                await session.scalars(
                    select(StudentRecord)
                    .where(*conditions)
                    .order_by(StudentRecord.position.desc())
                    .offset(page_index * page_size)
                    .limit(page_size)
                )
            ).all()
            return await self._student_page_rows(
                session, students, total_count, matching_count
            )

    @staticmethod
    async def _student_page_rows(
        session: AsyncSession,
        students: Sequence[StudentRecord],
        total_count: int | None,
        matching_count: int | None,
    ) -> tuple[list[dict[str, Any]], int, int]:
        if not students:
            return [], int(total_count or 0), int(matching_count or 0)

        student_ids = [student.id for student in students]
        enrollment_rows = (
            await session.execute(
                select(
                    EnrollmentRecord.student_id,
                    CourseRecord.name,
                    CourseRecord.schedule,
                    CourseRecord.group_name,
                )
                .outerjoin(
                    CourseRecord,
                    EnrollmentRecord.course_id == CourseRecord.id,
                )
                .where(
                    EnrollmentRecord.active.is_(True),
                    EnrollmentRecord.student_id.in_(student_ids),
                )
                .order_by(EnrollmentRecord.position.desc())
            )
        ).all()
        active_courses: dict[str, list[str]] = {}
        for student_id, name, schedule, group_name in enrollment_rows:
            if student_id is None:
                continue
            course_label = (
                f"{name} · {schedule} · Grupo {group_name}"
                if name is not None
                else "Pendiente de curso"
            )
            active_courses.setdefault(student_id, []).append(course_label)

        rows = [
            {
                "id": student.id,
                "server_id": student.server_id,
                "base_hash": student.base_hash,
                "last_name": student.last_name,
                "first_name": student.first_name,
                "document_number": student.document_number,
                "phone_numbers": student.phone_numbers,
                "active": student.active,
                "courses": active_courses.get(student.id, []),
                "label": " ".join(
                    part
                    for part in (student.last_name, student.first_name)
                    if part
                ),
            }
            for student in students
        ]
        return rows, int(total_count or 0), int(matching_count or 0)

    async def _load(self):
        async with self.session_factory() as session:
            workspace = await session.get(Workspace, 1)
            if workspace is None:
                return None

            students = (
                await session.scalars(
                    select(StudentRecord).order_by(StudentRecord.position)
                )
            ).all()
            enrollments = (
                await session.scalars(
                    select(EnrollmentRecord).order_by(EnrollmentRecord.position)
                )
            ).all()
            courses = (
                await session.scalars(
                    select(CourseRecord).order_by(CourseRecord.position)
                )
            ).all()
            promoters = (
                await session.scalars(
                    select(PromoterRecord).order_by(PromoterRecord.position)
                )
            ).all()
            manifest = {
                "format": workspace.format,
                "version": workspace.version,
                "bundle_id": workspace.bundle_id,
                "campus_id": workspace.campus_id,
                "campus_name": workspace.campus_name,
                "campus_address": workspace.campus_address,
                "students": [
                    {
                        "id": item.id,
                        "server_id": item.server_id,
                        "base_hash": item.base_hash,
                        "last_name": item.last_name,
                        "first_name": item.first_name,
                        "document_number": item.document_number,
                        "phone_numbers": item.phone_numbers,
                        "active": item.active,
                    }
                    for item in students
                ],
                "enrollments": [
                    {
                        "id": item.id,
                        "server_id": item.server_id,
                        "base_hash": item.base_hash,
                        "student_id": item.student_id,
                        "student_server_id": item.student_server_id,
                        "course_id": item.course_id,
                        "enrollment_date": item.enrollment_date,
                        "promoter_ids": item.promoter_ids,
                        "enrollment_fee": item.enrollment_fee,
                        "monthly_fee": item.monthly_fee,
                        "record_code": item.record_code,
                        "active": item.active,
                        "record_image": item.record_image,
                        "record_image_hash": item.record_image_hash,
                        "record_image_quality": item.record_image_quality,
                    }
                    for item in enrollments
                ],
                "courses": [
                    {
                        "id": item.id,
                        "server_id": item.server_id,
                        "name": item.name,
                        "schedule": item.schedule,
                        "group": item.group_name,
                        "start_date": item.start_date,
                        "enrollment_fee": item.enrollment_fee,
                        "monthly_fee": item.monthly_fee,
                        "capacity": item.capacity,
                        "active": item.active,
                    }
                    for item in courses
                ],
                "promoters": [
                    {
                        "id": item.id,
                        "server_id": (
                            item.server_id
                            if item.server_id is not None or workspace.version == 3
                            else item.id
                        ),
                        "name": item.name,
                        "active": item.active,
                    }
                    for item in promoters
                ],
            }
            if workspace.attachment_data is not None:
                manifest["_attachment_data"] = workspace.attachment_data
            if workspace.version == 3:
                manifest["campus_mode"] = "new"
            return manifest

    async def save(self, manifest):
        await self.initialize()
        await self._save(manifest)

    async def save_with_sync_history(self, manifest, history_event):
        await self.initialize()
        await self._save(manifest, sync_history_event=history_event)

    async def record_sync_history(self, history_event):
        await self.initialize()
        async with self.session_factory.begin() as session:
            session.add(SyncHistoryRecord(**history_event))

    async def list_sync_history(self, limit=50):
        await self.initialize()
        limit = max(1, min(int(limit), 200))
        async with self.session_factory() as session:
            records = (
                await session.scalars(
                    select(SyncHistoryRecord)
                    .order_by(SyncHistoryRecord.id.desc())
                    .limit(limit)
                )
            ).all()
            return [
                {
                    "operation": record.operation,
                    "bundle_id": record.bundle_id or "",
                    "created_at": record.created_at,
                    "status": record.status,
                    "affected_counts": record.affected_counts,
                    "message": record.message,
                }
                for record in records
            ]

    async def has_imported_bundle(self, bundle_id):
        await self.initialize()
        async with self.session_factory() as session:
            return (
                await session.scalar(
                    select(SyncHistoryRecord.id)
                    .where(
                        SyncHistoryRecord.operation == "import",
                        SyncHistoryRecord.bundle_id == bundle_id,
                        SyncHistoryRecord.status == "success",
                    )
                    .limit(1)
                )
            ) is not None

    def create_backup(self, destination):
        return create_sqlite_backup(self.path, Path(destination))

    async def save_records(self, manifest, changes):
        """Persist only named records and workspace metadata in one transaction."""
        await self.initialize()
        async with self.session_factory.begin() as session:
            workspace = await session.get(Workspace, 1)
            if workspace is None:
                raise RuntimeError("No hay un espacio de trabajo inicializado.")
            workspace_values = {
                "format": manifest["format"],
                "version": manifest["version"],
                "bundle_id": manifest["bundle_id"],
                "campus_id": manifest["campus_id"],
                "campus_name": manifest["campus_name"],
                "campus_address": manifest.get("campus_address", ""),
                "attachment_data": manifest.get("_attachment_data"),
            }
            for key, value in workspace_values.items():
                if getattr(workspace, key) != value:
                    setattr(workspace, key, value)

            def requested_rows(
                collection_name: str,
                requested_ids: list[Any],
                id_getter: Any,
            ) -> dict[Any, tuple[int, dict[str, Any]]]:
                requested_set = set(requested_ids)
                found: dict[Any, tuple[int, dict[str, Any]]] = {}
                if not requested_set:
                    return found
                for position, item in enumerate(manifest[collection_name]):
                    record_id = id_getter(item)
                    if record_id in requested_set:
                        found[record_id] = (position, item)
                if found.keys() != requested_set:
                    raise ValueError(
                        f"No se encontraron todos los registros de {collection_name}."
                    )
                return found

            async def upsert(model, record_id, values):
                record = await session.get(model, record_id)
                if record is None:
                    session.add(model(**values))
                    return
                for key, value in values.items():
                    if getattr(record, key) != value:
                        setattr(record, key, value)

            students = requested_rows(
                "students", changes.get("students", []), lambda item: item["id"]
            )
            for student_id, (position, item) in students.items():
                await upsert(
                    StudentRecord,
                    student_id,
                    {
                        "id": student_id,
                        "workspace_id": workspace.id,
                        "position": position,
                        "server_id": item["server_id"],
                        "base_hash": item["base_hash"],
                        "last_name": item["last_name"],
                        "first_name": item["first_name"],
                        "document_number": item["document_number"],
                        "last_name_search": normalize_search_text(
                            item["last_name"]
                        ),
                        "first_name_search": normalize_search_text(
                            item["first_name"]
                        ),
                        "document_number_search": normalize_search_text(
                            item["document_number"]
                        ),
                        "phone_numbers": item["phone_numbers"],
                        "active": item["active"],
                    },
                )

            courses = requested_rows(
                "courses",
                changes.get("courses", []),
                lambda item: int(item["id"]),
            )
            for course_id, (position, item) in courses.items():
                await upsert(
                    CourseRecord,
                    course_id,
                    {
                        "id": course_id,
                        "workspace_id": workspace.id,
                        "position": position,
                        "server_id": item.get("server_id", course_id),
                        "name": item["name"],
                        "schedule": item["schedule"],
                        "group_name": item["group"],
                        "start_date": item["start_date"],
                        "enrollment_fee": item["enrollment_fee"],
                        "monthly_fee": item["monthly_fee"],
                        "capacity": item["capacity"],
                        "active": item["active"],
                    },
                )

            promoters = requested_rows(
                "promoters",
                changes.get("promoters", []),
                lambda item: int(item["id"]),
            )
            for promoter_id, (position, item) in promoters.items():
                await upsert(
                    PromoterRecord,
                    promoter_id,
                    {
                        "id": promoter_id,
                        "workspace_id": workspace.id,
                        "position": position,
                        "server_id": (
                            item.get("server_id")
                            if item.get("server_id") is not None
                            or manifest["version"] == 3
                            else promoter_id
                        ),
                        "name": item["name"],
                        "active": item["active"],
                    },
                )

            enrollments = requested_rows(
                "enrollments",
                changes.get("enrollments", []),
                lambda item: item["id"],
            )
            for enrollment_id, (position, item) in enrollments.items():
                student_id = item.get("student_id")
                if student_id is not None and await session.get(
                    StudentRecord, student_id
                ) is None:
                    raise ValueError(
                        "Una matrícula hace referencia a un estudiante inexistente."
                    )
                course_id = item.get("course_id")
                if course_id is not None and await session.get(
                    CourseRecord, int(course_id)
                ) is None:
                    raise ValueError(
                        "Una matrícula hace referencia a un curso inexistente."
                    )
                promoter_ids = [int(value) for value in item["promoter_ids"]]
                for promoter_id in promoter_ids:
                    if await session.get(PromoterRecord, promoter_id) is None:
                        raise ValueError(
                            "Una matrícula hace referencia a un promotor inexistente."
                        )
                await upsert(
                    EnrollmentRecord,
                    enrollment_id,
                    {
                        "id": enrollment_id,
                        "workspace_id": workspace.id,
                        "position": position,
                        "server_id": item["server_id"],
                        "base_hash": item["base_hash"],
                        "student_id": student_id,
                        "student_server_id": item["student_server_id"],
                        "course_id": int(course_id) if course_id is not None else None,
                        "enrollment_date": item["enrollment_date"],
                        "promoter_ids": promoter_ids,
                        "enrollment_fee": item["enrollment_fee"],
                        "monthly_fee": item["monthly_fee"],
                        "record_code": item["record_code"],
                        "active": item["active"],
                        "record_image": item["record_image"],
                        "record_image_hash": item["record_image_hash"],
                        "record_image_quality": item["record_image_quality"],
                    },
                )

        audit_logger.info(
            "database.records_saved",
            student_count=len(changes.get("students", [])),
            enrollment_count=len(changes.get("enrollments", [])),
            course_count=len(changes.get("courses", [])),
            promoter_count=len(changes.get("promoters", [])),
        )

    async def _save(self, manifest, sync_history_event=None):
        async with self.session_factory.begin() as session:
            workspace = await session.get(Workspace, 1)
            workspace_values = {
                "format": manifest["format"],
                "version": manifest["version"],
                "bundle_id": manifest["bundle_id"],
                "campus_id": manifest["campus_id"],
                "campus_name": manifest["campus_name"],
                "campus_address": manifest.get("campus_address", ""),
                "attachment_data": manifest.get("_attachment_data"),
            }
            if workspace is None:
                workspace = Workspace(id=1, **workspace_values)
                session.add(workspace)
            else:
                for key, value in workspace_values.items():
                    if getattr(workspace, key) != value:
                        setattr(workspace, key, value)
            await session.flush()

            student_ids = {item["id"] for item in manifest["students"]}
            course_ids = {int(item["id"]) for item in manifest["courses"]}
            promoter_ids = {int(item["id"]) for item in manifest["promoters"]}
            for item in manifest["enrollments"]:
                student_id = item.get("student_id")
                course_id = item.get("course_id")
                if student_id is not None and student_id not in student_ids:
                    raise ValueError(
                        "Una matrícula hace referencia a un estudiante inexistente."
                    )
                if course_id is not None and int(course_id) not in course_ids:
                    raise ValueError(
                        "Una matrícula hace referencia a un curso inexistente."
                    )
                if any(int(value) not in promoter_ids for value in item["promoter_ids"]):
                    raise ValueError(
                        "Una matrícula hace referencia a un promotor inexistente."
                    )

            async def synchronize(model, records, get_id, get_values):
                existing: list[Any] = list(
                    (await session.scalars(select(model))).all()
                )
                existing_by_id = {record.id: record for record in existing}
                requested_ids = set()
                for position, item in enumerate(records):
                    record_id = get_id(item)
                    requested_ids.add(record_id)
                    values = get_values(item, position)
                    record = existing_by_id.get(record_id)
                    if record is None:
                        session.add(model(**values))
                        continue
                    for key, value in values.items():
                        if getattr(record, key) != value:
                            setattr(record, key, value)
                return existing, requested_ids

            stale_students, _ = await synchronize(
                StudentRecord,
                manifest["students"],
                lambda item: item["id"],
                lambda item, position: {
                    "id": item["id"],
                    "workspace_id": workspace.id,
                    "position": position,
                    "server_id": item["server_id"],
                    "base_hash": item["base_hash"],
                    "last_name": item["last_name"],
                    "first_name": item["first_name"],
                    "document_number": item["document_number"],
                    "last_name_search": normalize_search_text(item["last_name"]),
                    "first_name_search": normalize_search_text(item["first_name"]),
                    "document_number_search": normalize_search_text(
                        item["document_number"]
                    ),
                    "phone_numbers": item["phone_numbers"],
                    "active": item["active"],
                },
            )
            stale_courses, _ = await synchronize(
                CourseRecord,
                manifest["courses"],
                lambda item: int(item["id"]),
                lambda item, position: {
                    "id": int(item["id"]),
                    "workspace_id": workspace.id,
                    "position": position,
                    "server_id": item.get("server_id", int(item["id"])),
                    "name": item["name"],
                    "schedule": item["schedule"],
                    "group_name": item["group"],
                    "start_date": item["start_date"],
                    "enrollment_fee": item["enrollment_fee"],
                    "monthly_fee": item["monthly_fee"],
                    "capacity": item["capacity"],
                    "active": item["active"],
                },
            )
            stale_promoters, _ = await synchronize(
                PromoterRecord,
                manifest["promoters"],
                lambda item: int(item["id"]),
                lambda item, position: {
                    "id": int(item["id"]),
                    "workspace_id": workspace.id,
                    "position": position,
                    "server_id": (
                        item.get("server_id")
                        if item.get("server_id") is not None
                        or manifest["version"] == 3
                        else int(item["id"])
                    ),
                    "name": item["name"],
                    "active": item["active"],
                },
            )
            await session.flush()

            stale_enrollments, requested_enrollments = await synchronize(
                EnrollmentRecord,
                manifest["enrollments"],
                lambda item: item["id"],
                lambda item, position: {
                    "id": item["id"],
                    "workspace_id": workspace.id,
                    "position": position,
                    "server_id": item["server_id"],
                    "base_hash": item["base_hash"],
                    "student_id": item.get("student_id"),
                    "student_server_id": item["student_server_id"],
                    "course_id": item.get("course_id"),
                    "enrollment_date": item["enrollment_date"],
                    "promoter_ids": [int(value) for value in item["promoter_ids"]],
                    "enrollment_fee": item["enrollment_fee"],
                    "monthly_fee": item["monthly_fee"],
                    "record_code": item["record_code"],
                    "active": item["active"],
                    "record_image": item["record_image"],
                    "record_image_hash": item["record_image_hash"],
                    "record_image_quality": item["record_image_quality"],
                },
            )
            for record in stale_enrollments:
                if record.id not in requested_enrollments:
                    await session.delete(record)
            await session.flush()

            for record in stale_students:
                if record.id not in student_ids:
                    await session.delete(record)
            for record in stale_courses:
                if record.id not in course_ids:
                    await session.delete(record)
            for record in stale_promoters:
                if record.id not in promoter_ids:
                    await session.delete(record)
            if sync_history_event is not None:
                session.add(SyncHistoryRecord(**sync_history_event))

        audit_logger.info(
            "database.manifest_saved",
            student_count=len(manifest["students"]),
            enrollment_count=len(manifest["enrollments"]),
            course_count=len(manifest["courses"]),
            promoter_count=len(manifest["promoters"]),
            includes_sync_history=sync_history_event is not None,
        )

    async def dispose(self):
        await self.engine.dispose()
