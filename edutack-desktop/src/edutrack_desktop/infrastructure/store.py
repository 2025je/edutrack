import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import (
    MetaData,
    Table,
    URL,
    and_,
    event,
    exists,
    func,
    inspect,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.sql.elements import ColumnElement
import structlog

from ..domain.record_service import RecordMutation
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


def _workspace_values(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "format": manifest["format"],
        "version": manifest["version"],
        "bundle_id": manifest["bundle_id"],
        "campus_id": manifest["campus_id"],
        "campus_name": manifest["campus_name"],
        "campus_address": manifest.get("campus_address", ""),
        "attachment_data": manifest.get("_attachment_data"),
    }


def _student_values(
    item: dict[str, Any], workspace_id: int, position: int
) -> dict[str, Any]:
    return {
        "id": item["id"],
        "workspace_id": workspace_id,
        "position": position,
        "server_id": item["server_id"],
        "base_hash": item["base_hash"],
        "last_name": item["last_name"],
        "first_name": item["first_name"],
        "document_number": item["document_number"],
        "last_name_search": normalize_search_text(item["last_name"]),
        "first_name_search": normalize_search_text(item["first_name"]),
        "document_number_search": normalize_search_text(item["document_number"]),
        "phone_numbers": item["phone_numbers"],
        "active": item["active"],
    }


def _course_values(
    item: dict[str, Any], workspace_id: int, position: int
) -> dict[str, Any]:
    course_id = int(item["id"])
    search_text = f"{item['name']} · {item['schedule']} · Grupo {item['group']}"
    return {
        "id": course_id,
        "workspace_id": workspace_id,
        "position": position,
        "server_id": item.get("server_id", course_id),
        "name": item["name"],
        "schedule": item["schedule"],
        "group_name": item["group"],
        "search_text": normalize_search_text(search_text),
        "start_date": item["start_date"],
        "enrollment_fee": item["enrollment_fee"],
        "monthly_fee": item["monthly_fee"],
        "capacity": item["capacity"],
        "active": item["active"],
    }


def _promoter_values(
    item: dict[str, Any],
    workspace_id: int,
    position: int,
    version: int,
) -> dict[str, Any]:
    promoter_id = int(item["id"])
    return {
        "id": promoter_id,
        "workspace_id": workspace_id,
        "position": position,
        "server_id": (
            item.get("server_id")
            if item.get("server_id") is not None or version == 3
            else promoter_id
        ),
        "name": item["name"],
        "active": item["active"],
    }


def _enrollment_values(
    item: dict[str, Any], workspace_id: int, position: int
) -> dict[str, Any]:
    course_id = item.get("course_id")
    return {
        "id": item["id"],
        "workspace_id": workspace_id,
        "position": position,
        "server_id": item["server_id"],
        "base_hash": item["base_hash"],
        "student_id": item.get("student_id"),
        "student_server_id": item["student_server_id"],
        "course_id": int(course_id) if course_id is not None else None,
        "enrollment_date": item["enrollment_date"],
        "promoter_ids": [int(value) for value in item["promoter_ids"]],
        "enrollment_fee": item["enrollment_fee"],
        "monthly_fee": item["monthly_fee"],
        "record_code": item["record_code"],
        "active": item["active"],
        "record_image": item["record_image"],
        "record_image_hash": item["record_image_hash"],
        "record_image_quality": item["record_image_quality"],
    }


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
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
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
            table_exists, legacy_data = await connection.run_sync(read_legacy_workspace)
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
                escaped = (
                    token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
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
                statement = statement.where(or_(*token_conditions))
            students = (
                await session.scalars(
                    statement.order_by(StudentRecord.position.desc()).limit(limit)
                )
            ).all()
            if not students:
                return []

            active_courses = await self._active_courses(
                session, [student.id for student in students]
            )
            return [self._student_row(student, active_courses) for student in students]

    @staticmethod
    async def _active_courses(
        session: AsyncSession, student_ids: Sequence[str]
    ) -> dict[str, list[str]]:
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
        return active_courses

    @staticmethod
    def _student_row(
        student: StudentRecord, active_courses: dict[str, list[str]]
    ) -> dict[str, Any]:
        return {
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
                part for part in (student.last_name, student.first_name) if part
            ),
        }

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
                    column.like(pattern, escape="\\") for column in searchable_columns
                ]
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
                            CourseRecord.search_text.like(pattern, escape="\\"),
                        )
                    )
                )
                conditions.append(or_(*search_conditions))

            total_count = await session.scalar(
                select(func.count()).select_from(StudentRecord)
            )
            matching_count = await session.scalar(
                select(func.count()).select_from(StudentRecord).where(*conditions)
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

    async def course_page(
        self,
        query: str,
        page_index: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int, int]:
        await self.initialize()
        if page_index < 0 or not 1 <= page_size <= 100:
            raise ValueError("La página de cursos solicitada no es válida.")

        tokens = normalize_search_text(query).split()
        conditions: list[ColumnElement[bool]] = []
        for token in tokens:
            escaped = (
                token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            pattern = f"%{escaped}%"
            conditions.append(
                or_(
                    CourseRecord.search_text.like(pattern, escape="\\"),
                    CourseRecord.start_date.like(pattern, escape="\\"),
                )
            )

        active_student_count = func.count(func.distinct(StudentRecord.id)).label(
            "student_count"
        )
        course_statement = (
            select(
                CourseRecord.id.label("id"),
                CourseRecord.server_id.label("server_id"),
                CourseRecord.name.label("name"),
                CourseRecord.schedule.label("schedule"),
                CourseRecord.group_name.label("group"),
                CourseRecord.start_date.label("start_date"),
                CourseRecord.enrollment_fee.label("enrollment_fee"),
                CourseRecord.monthly_fee.label("monthly_fee"),
                CourseRecord.capacity.label("capacity"),
                CourseRecord.active.label("active"),
                active_student_count,
            )
            .select_from(CourseRecord)
            .outerjoin(
                EnrollmentRecord,
                and_(
                    EnrollmentRecord.course_id == CourseRecord.id,
                    EnrollmentRecord.active.is_(True),
                ),
            )
            .outerjoin(
                StudentRecord,
                and_(
                    StudentRecord.id == EnrollmentRecord.student_id,
                    StudentRecord.active.is_(True),
                ),
            )
            .where(*conditions)
            .group_by(CourseRecord.id)
            .order_by(CourseRecord.start_date.desc(), CourseRecord.position.desc())
            .offset(page_index * page_size)
            .limit(page_size)
        )

        async with self.session_factory() as session:
            total_count = await session.scalar(
                select(func.count()).select_from(CourseRecord)
            )
            matching_count = await session.scalar(
                select(func.count()).select_from(CourseRecord).where(*conditions)
            )
            rows = (await session.execute(course_statement)).mappings().all()
            return (
                [
                    {
                        **dict(row),
                        "label": (
                            f"{row['name']} · {row['schedule']} · Grupo {row['group']}"
                        ),
                    }
                    for row in rows
                ],
                int(total_count or 0),
                int(matching_count or 0),
            )

    async def enrollment_page(
        self,
        query: str,
        status_filter_index: int,
        course_filter_id: int,
        page_index: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int, int]:
        await self.initialize()
        if status_filter_index not in (0, 1, 2, 3, 4):
            raise ValueError("El filtro de estado de matrículas no es válido.")
        if (
            not isinstance(query, str)
            or isinstance(course_filter_id, bool)
            or not isinstance(course_filter_id, int)
            or isinstance(page_index, bool)
            or not isinstance(page_index, int)
            or isinstance(page_size, bool)
            or not isinstance(page_size, int)
            or course_filter_id < 0
            or page_index < 0
            or not 1 <= page_size <= 100
        ):
            raise ValueError("La página de matrículas solicitada no es válida.")

        conditions: list[ColumnElement[bool]] = []
        if status_filter_index == 1:
            conditions.extend(
                (
                    EnrollmentRecord.active.is_(True),
                    StudentRecord.id.is_not(None),
                    CourseRecord.id.is_not(None),
                )
            )
        elif status_filter_index == 2:
            conditions.append(EnrollmentRecord.active.is_(False))
        elif status_filter_index == 3:
            conditions.append(StudentRecord.id.is_(None))
        elif status_filter_index == 4:
            conditions.append(CourseRecord.id.is_(None))
        if course_filter_id:
            conditions.append(EnrollmentRecord.course_id == course_filter_id)

        student_search_columns = (
            StudentRecord.last_name_search,
            StudentRecord.first_name_search,
            StudentRecord.document_number_search,
            StudentRecord.last_name_search + " " + StudentRecord.first_name_search,
        )
        for token in normalize_search_text(query).split():
            escaped = (
                token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            pattern = f"%{escaped}%"
            conditions.append(
                or_(
                    *(
                        column.like(pattern, escape="\\")
                        for column in student_search_columns
                    ),
                    CourseRecord.search_text.like(pattern, escape="\\"),
                    EnrollmentRecord.enrollment_date.like(pattern, escape="\\"),
                )
            )

        joined_enrollments = (
            select(
                EnrollmentRecord,
                StudentRecord.last_name,
                StudentRecord.first_name,
                StudentRecord.active.label("student_active"),
                CourseRecord.name.label("course_name"),
                CourseRecord.schedule.label("course_schedule"),
                CourseRecord.group_name.label("course_group"),
            )
            .select_from(EnrollmentRecord)
            .outerjoin(
                StudentRecord,
                EnrollmentRecord.student_id == StudentRecord.id,
            )
            .outerjoin(
                CourseRecord,
                EnrollmentRecord.course_id == CourseRecord.id,
            )
            .where(*conditions)
        )
        async with self.session_factory() as session:
            total_count = await session.scalar(
                select(func.count()).select_from(EnrollmentRecord)
            )
            matching_count = await session.scalar(
                select(func.count(EnrollmentRecord.id))
                .select_from(EnrollmentRecord)
                .outerjoin(
                    StudentRecord,
                    EnrollmentRecord.student_id == StudentRecord.id,
                )
                .outerjoin(
                    CourseRecord,
                    EnrollmentRecord.course_id == CourseRecord.id,
                )
                .where(*conditions)
            )
            result = await session.execute(
                joined_enrollments.order_by(
                    EnrollmentRecord.enrollment_date.desc(),
                    EnrollmentRecord.position.desc(),
                )
                .offset(page_index * page_size)
                .limit(page_size)
            )
            rows = []
            for (
                enrollment,
                last_name,
                first_name,
                student_active,
                course_name,
                course_schedule,
                course_group,
            ) in result:
                student_label = (
                    " ".join(part for part in (last_name, first_name) if part)
                    if last_name is not None
                    else "Pendiente de estudiante"
                )
                pending_course = course_name is None
                course_label = (
                    f"{course_name} · {course_schedule} · Grupo {course_group}"
                    if not pending_course
                    else "Pendiente de curso"
                )
                rows.append(
                    {
                        "id": enrollment.id,
                        "server_id": enrollment.server_id,
                        "base_hash": enrollment.base_hash,
                        "student_id": enrollment.student_id,
                        "student_server_id": enrollment.student_server_id,
                        "course_id": enrollment.course_id,
                        "enrollment_date": enrollment.enrollment_date,
                        "promoter_ids": enrollment.promoter_ids,
                        "enrollment_fee": enrollment.enrollment_fee,
                        "monthly_fee": enrollment.monthly_fee,
                        "record_code": enrollment.record_code,
                        "active": enrollment.active,
                        "record_image": enrollment.record_image,
                        "record_image_hash": enrollment.record_image_hash,
                        "record_image_quality": enrollment.record_image_quality,
                        "student_label": student_label,
                        "course_label": course_label,
                        "pending_student": last_name is None,
                        "pending_course": pending_course,
                        "student_active": bool(student_active),
                        "label": f"{student_label} — {course_label}",
                    }
                )
            return rows, int(total_count or 0), int(matching_count or 0)

    @staticmethod
    async def _student_page_rows(
        session: AsyncSession,
        students: Sequence[StudentRecord],
        total_count: int | None,
        matching_count: int | None,
    ) -> tuple[list[dict[str, Any]], int, int]:
        if not students:
            return [], int(total_count or 0), int(matching_count or 0)

        active_courses = await LocalStore._active_courses(
            session, [student.id for student in students]
        )
        rows = [
            LocalStore._student_row(student, active_courses) for student in students
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

    async def save_records(
        self, manifest: dict[str, Any], changes: dict[str, list[RecordMutation]]
    ) -> None:
        """Persist changed records and workspace metadata in one transaction."""
        await self.initialize()

        def requested_changes(collection_name: str) -> list[RecordMutation]:
            mutations = changes.get(collection_name, [])
            seen_ids = set()
            for mutation in mutations:
                if (
                    not isinstance(mutation, RecordMutation)
                    or isinstance(mutation.position, bool)
                    or mutation.position < 0
                    or not isinstance(mutation.record, dict)
                    or "id" not in mutation.record
                ):
                    raise ValueError(
                        f"Los cambios de {collection_name} no son válidos."
                    )
                record_id = mutation.record["id"]
                if record_id in seen_ids:
                    raise ValueError(
                        f"Hay IDs duplicados en los cambios de {collection_name}."
                    )
                seen_ids.add(record_id)
            return mutations

        async def existing_ids(model, record_ids: set[Any]) -> set[Any]:
            if not record_ids:
                return set()
            result: Any = await session.scalars(
                select(model.id).where(model.id.in_(record_ids))
            )
            return set(result.all())

        async def upsert_many(model, mutations, values_for):
            if not mutations:
                return
            mutation_ids = {mutation.record["id"] for mutation in mutations}
            result: Any = await session.scalars(
                select(model).where(model.id.in_(mutation_ids))
            )
            existing_records: list[Any] = list(result.all())
            records_by_id = {record.id: record for record in existing_records}
            for mutation in mutations:
                item = mutation.record
                values = values_for(item, mutation.position)
                record = records_by_id.get(item["id"])
                if record is None:
                    session.add(model(**values))
                    continue
                for key, value in values.items():
                    if getattr(record, key) != value:
                        setattr(record, key, value)

        students = requested_changes("students")
        courses = requested_changes("courses")
        promoters = requested_changes("promoters")
        enrollments = requested_changes("enrollments")

        async with self.session_factory.begin() as session:
            workspace = await session.get(Workspace, 1)
            if workspace is None:
                raise RuntimeError("No hay un espacio de trabajo inicializado.")
            for key, value in _workspace_values(manifest).items():
                if getattr(workspace, key) != value:
                    setattr(workspace, key, value)

            await upsert_many(
                StudentRecord,
                students,
                lambda item, position: _student_values(item, workspace.id, position),
            )
            await upsert_many(
                CourseRecord,
                courses,
                lambda item, position: _course_values(item, workspace.id, position),
            )
            await upsert_many(
                PromoterRecord,
                promoters,
                lambda item, position: _promoter_values(
                    item, workspace.id, position, manifest["version"]
                ),
            )
            await session.flush()

            student_ids = {mutation.record["id"] for mutation in students}
            required_student_ids = {
                mutation.record["student_id"]
                for mutation in enrollments
                if mutation.record.get("student_id") is not None
            }
            missing_student_ids = required_student_ids - student_ids
            available_student_ids = student_ids | await existing_ids(
                StudentRecord, missing_student_ids
            )

            course_ids = {int(mutation.record["id"]) for mutation in courses}
            required_course_ids = {
                int(mutation.record["course_id"])
                for mutation in enrollments
                if mutation.record.get("course_id") is not None
            }
            missing_course_ids = required_course_ids - course_ids
            available_course_ids = course_ids | await existing_ids(
                CourseRecord, missing_course_ids
            )

            promoter_ids = {int(mutation.record["id"]) for mutation in promoters}
            required_promoter_ids = {
                int(promoter_id)
                for mutation in enrollments
                for promoter_id in mutation.record["promoter_ids"]
            }
            missing_promoter_ids = required_promoter_ids - promoter_ids
            available_promoter_ids = promoter_ids | await existing_ids(
                PromoterRecord, missing_promoter_ids
            )

            for mutation in enrollments:
                item = mutation.record
                student_id = item.get("student_id")
                if student_id is not None and student_id not in available_student_ids:
                    raise ValueError(
                        "Una matrícula hace referencia a un estudiante inexistente."
                    )
                course_id = item.get("course_id")
                if course_id is not None and int(course_id) not in available_course_ids:
                    raise ValueError(
                        "Una matrícula hace referencia a un curso inexistente."
                    )
                if any(
                    int(promoter_id) not in available_promoter_ids
                    for promoter_id in item["promoter_ids"]
                ):
                    raise ValueError(
                        "Una matrícula hace referencia a un promotor inexistente."
                    )

            await upsert_many(
                EnrollmentRecord,
                enrollments,
                lambda item, position: _enrollment_values(item, workspace.id, position),
            )

        audit_logger.info(
            "database.records_saved",
            student_count=len(students),
            enrollment_count=len(enrollments),
            course_count=len(courses),
            promoter_count=len(promoters),
        )

    async def _save(self, manifest, sync_history_event=None):
        async with self.session_factory.begin() as session:
            workspace = await session.get(Workspace, 1)
            workspace_values = _workspace_values(manifest)
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
                if any(
                    int(value) not in promoter_ids for value in item["promoter_ids"]
                ):
                    raise ValueError(
                        "Una matrícula hace referencia a un promotor inexistente."
                    )

            async def synchronize(model, records, get_id, get_values):
                existing: list[Any] = list((await session.scalars(select(model))).all())
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
                lambda item, position: _student_values(item, workspace.id, position),
            )
            stale_courses, _ = await synchronize(
                CourseRecord,
                manifest["courses"],
                lambda item: int(item["id"]),
                lambda item, position: _course_values(item, workspace.id, position),
            )
            stale_promoters, _ = await synchronize(
                PromoterRecord,
                manifest["promoters"],
                lambda item: int(item["id"]),
                lambda item, position: _promoter_values(
                    item, workspace.id, position, manifest["version"]
                ),
            )
            await session.flush()

            stale_enrollments, requested_enrollments = await synchronize(
                EnrollmentRecord,
                manifest["enrollments"],
                lambda item: item["id"],
                lambda item, position: _enrollment_values(item, workspace.id, position),
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
