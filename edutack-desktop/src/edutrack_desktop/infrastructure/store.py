import json
from collections.abc import Sequence
from datetime import date
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
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.sql.elements import ColumnElement
import structlog

from ..application.ports import RecordServicePort
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

_WEB_MANAGED_ENROLLMENT_FIELDS = frozenset(
    {
        "promoter_ids",
        "record_code",
        "record_image",
        "record_image_hash",
        "record_image_quality",
    }
)


def _editable_enrollment_fields(fields: dict[str, Any]) -> dict[str, Any]:
    promoter_ids = fields.get("promoter_ids")
    record_code = str(fields.get("record_code") or "").strip()
    image_quality = fields.get("record_image_quality")
    if (
        promoter_ids not in (None, [], ())
        or record_code
        or fields.get("record_image")
        or fields.get("record_image_hash")
        or image_quality not in (None, "", 80, "80")
    ):
        raise ValueError(
            "Los promotores y las fichas se gestionan desde EduTrack Web."
        )
    return {
        key: value
        for key, value in fields.items()
        if key not in _WEB_MANAGED_ENROLLMENT_FIELDS
    }


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


def _student_context_item(student: StudentRecord) -> dict[str, Any]:
    return {
        "id": student.id,
        "server_id": student.server_id,
        "base_hash": student.base_hash,
        "last_name": student.last_name,
        "first_name": student.first_name,
        "document_number": student.document_number,
        "phone_numbers": student.phone_numbers,
        "active": student.active,
    }


def _course_values(
    item: dict[str, Any], workspace_id: int, position: int
) -> dict[str, Any]:
    course_id = int(item["id"])
    return {
        "id": course_id,
        "workspace_id": workspace_id,
        "position": position,
        "server_id": item.get("server_id", course_id),
        "name": item["name"],
        "schedule": item["schedule"],
        "group_name": item["group"],
        "search_text": _course_search_text(item),
        "start_date": item["start_date"],
        "enrollment_fee": item["enrollment_fee"],
        "monthly_fee": item["monthly_fee"],
        "capacity": item["capacity"],
        "active": item["active"],
    }


def _course_search_text(item: dict[str, Any]) -> str:
    value = f"{item['name']} · {item['schedule']} · Grupo {item['group']}"
    return normalize_search_text(value)


def _course_context(records: Sequence[CourseRecord]) -> dict[str, Any]:
    return {
        "courses": [
            {
                "id": course.id,
                "server_id": course.server_id,
                "name": course.name,
                "schedule": course.schedule,
                "group": course.group_name,
                "start_date": course.start_date,
                "enrollment_fee": course.enrollment_fee,
                "monthly_fee": course.monthly_fee,
                "capacity": course.capacity,
                "active": course.active,
            }
            for course in records
        ]
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


def _enrollment_context_item(enrollment: EnrollmentRecord) -> dict[str, Any]:
    return {
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

    async def workspace_info(self) -> dict[str, Any] | None:
        await self.initialize()
        statement = select(
            Workspace.format.label("format"),
            Workspace.version.label("version"),
            Workspace.bundle_id.label("bundle_id"),
            Workspace.campus_id.label("campus_id"),
            Workspace.campus_name.label("campus_name"),
            Workspace.campus_address.label("campus_address"),
            (
                select(func.count())
                .select_from(StudentRecord)
                .scalar_subquery()
                .label("students")
            ),
            (
                select(func.count())
                .select_from(EnrollmentRecord)
                .scalar_subquery()
                .label("enrollments")
            ),
            (
                select(func.count())
                .select_from(CourseRecord)
                .scalar_subquery()
                .label("courses")
            ),
            (
                select(func.count())
                .select_from(PromoterRecord)
                .scalar_subquery()
                .label("promoters")
            ),
            (
                select(CourseRecord.id)
                .order_by(CourseRecord.position)
                .limit(1)
                .scalar_subquery()
                .label("first_course_id")
            ),
        ).where(Workspace.id == 1)
        async with self.session_factory() as session:
            row = (await session.execute(statement)).mappings().one_or_none()
            if row is None:
                return None
            info = dict(row)
            info["campus_mode"] = "new" if info["version"] == 3 else "existing"
            return info

    async def register_export_data(self) -> dict[str, Any] | None:
        await self.initialize()
        async with self.session_factory() as session:
            if await session.get(Workspace, 1) is None:
                return None

            courses = (
                await session.scalars(
                    select(CourseRecord).order_by(CourseRecord.position)
                )
            ).all()
            course_ids = [course.id for course in courses]
            enrollments = (
                await session.scalars(
                    select(EnrollmentRecord)
                    .where(EnrollmentRecord.course_id.in_(course_ids))
                    .order_by(EnrollmentRecord.position)
                )
            ).all() if course_ids else []
            student_ids = {
                enrollment.student_id
                for enrollment in enrollments
                if enrollment.student_id is not None
            }
            students = (
                await session.scalars(
                    select(StudentRecord).where(StudentRecord.id.in_(student_ids))
                )
            ).all() if student_ids else []
            promoter_ids = {
                promoter_id
                for enrollment in enrollments
                for promoter_id in enrollment.promoter_ids
            }
            promoters = (
                await session.scalars(
                    select(PromoterRecord).where(PromoterRecord.id.in_(promoter_ids))
                )
            ).all() if promoter_ids else []

            return {
                "courses": [
                    {
                        "id": course.id,
                        "name": course.name,
                        "schedule": course.schedule,
                        "group": course.group_name,
                        "start_date": course.start_date,
                        "enrollment_fee": course.enrollment_fee,
                        "monthly_fee": course.monthly_fee,
                        "capacity": course.capacity,
                        "active": course.active,
                    }
                    for course in courses
                ],
                "enrollments": [
                    {
                        "id": enrollment.id,
                        "student_id": enrollment.student_id,
                        "course_id": enrollment.course_id,
                        "enrollment_date": enrollment.enrollment_date,
                        "promoter_ids": enrollment.promoter_ids,
                        "enrollment_fee": enrollment.enrollment_fee,
                        "monthly_fee": enrollment.monthly_fee,
                        "record_code": enrollment.record_code,
                        "active": enrollment.active,
                    }
                    for enrollment in enrollments
                ],
                "students": [
                    {
                        "id": student.id,
                        "last_name": student.last_name,
                        "first_name": student.first_name,
                        "document_number": student.document_number,
                        "phone_numbers": student.phone_numbers,
                        "active": student.active,
                    }
                    for student in students
                ],
                "promoters": [
                    {"id": promoter.id, "name": promoter.name}
                    for promoter in promoters
                ],
            }

    async def update_course(
        self,
        course_id: int,
        name: str,
        schedule: str,
        group_name: str,
        start_date: str,
        enrollment_fee: str,
        monthly_fee: str,
        capacity: str,
        active: bool,
        record_service: RecordServicePort,
    ) -> dict[str, Any]:
        await self.initialize()
        async with self.session_factory.begin() as session:
            workspace = await session.get(Workspace, 1)
            if workspace is None:
                raise RuntimeError("No hay un espacio de trabajo inicializado.")

            target = await session.get(CourseRecord, course_id)
            if target is None:
                raise ValueError("Selecciona un curso válido para editar.")
            fields = record_service.normalize_course_fields(
                {"courses": []},
                course_id,
                name,
                schedule,
                group_name,
                start_date,
                enrollment_fee,
                monthly_fee,
                capacity,
            )
            matching_courses = (
                await session.scalars(
                    select(CourseRecord).where(
                        CourseRecord.id != course_id,
                        CourseRecord.search_text == _course_search_text(fields),
                    )
                )
            ).all()
            course_context = _course_context([target, *matching_courses])
            mutation = record_service.update_course(
                course_context,
                course_id,
                name,
                schedule,
                group_name,
                start_date,
                enrollment_fee,
                monthly_fee,
                capacity,
                active,
            )
            for key, value in _course_values(
                mutation.record, workspace.id, target.position
            ).items():
                setattr(target, key, value)
            return dict(mutation.record)

    async def create_course(
        self,
        name: str,
        schedule: str,
        group_name: str,
        start_date: str,
        enrollment_fee: str,
        monthly_fee: str,
        capacity: str,
        record_service: RecordServicePort,
    ) -> dict[str, Any]:
        await self.initialize()
        async with self.session_factory.begin() as session:
            workspace = await session.get(Workspace, 1)
            if workspace is None:
                raise RuntimeError("No hay un espacio de trabajo inicializado.")
            fields = record_service.normalize_course_fields(
                {"courses": []},
                None,
                name,
                schedule,
                group_name,
                start_date,
                enrollment_fee,
                monthly_fee,
                capacity,
            )
            matching_courses = (
                await session.scalars(
                    select(CourseRecord).where(
                        CourseRecord.search_text == _course_search_text(fields)
                    )
                )
            ).all()
            next_course_id = int(
                await session.scalar(
                    select(func.coalesce(func.max(CourseRecord.id), 0))
                )
            ) + 1
            next_position = int(
                await session.scalar(select(func.count(CourseRecord.id)))
            )
            mutation = record_service.create_course(
                _course_context(matching_courses),
                name,
                schedule,
                group_name,
                start_date,
                enrollment_fee,
                monthly_fee,
                capacity,
                course_id=next_course_id,
                position=next_position,
            )
            session.add(
                CourseRecord(
                    **_course_values(
                        mutation.record, workspace.id, mutation.position
                    )
                )
            )
            return dict(mutation.record)

    async def save_student(
        self,
        source_id: str,
        last_name: str,
        first_name: str,
        document_number: str,
        phone_text: str,
        record_service: RecordServicePort,
    ) -> dict[str, Any]:
        await self.initialize()
        async with self.session_factory.begin() as session:
            workspace = await session.get(Workspace, 1)
            if workspace is None:
                raise RuntimeError("No hay un espacio de trabajo inicializado.")

            target = (
                await session.get(StudentRecord, source_id) if source_id else None
            )
            if source_id and target is None:
                raise ValueError("El estudiante seleccionado ya no existe.")
            normalized_last_name = normalize_search_text(last_name.strip().upper())
            normalized_first_name = normalize_search_text(first_name.strip().upper())
            candidates_statement = select(StudentRecord).where(
                StudentRecord.last_name_search == normalized_last_name,
                StudentRecord.first_name_search == normalized_first_name,
            )
            if source_id:
                candidates_statement = candidates_statement.where(
                    StudentRecord.id != source_id
                )
            candidates = (
                await session.scalars(candidates_statement)
            ).all()
            context_students = [_student_context_item(item) for item in candidates]
            if target is not None:
                context_students.append(_student_context_item(target))

            mutation = record_service.save_student(
                {"students": context_students},
                source_id,
                last_name,
                first_name,
                document_number,
                phone_text,
            )
            if target is None:
                last_position = await session.scalar(
                    select(func.max(StudentRecord.position))
                )
                position = int(last_position if last_position is not None else -1) + 1
                session.add(
                    StudentRecord(
                        **_student_values(mutation.record, workspace.id, position)
                    )
                )
            else:
                for key, value in _student_values(
                    mutation.record, workspace.id, target.position
                ).items():
                    setattr(target, key, value)
            return dict(mutation.record)

    async def set_student_active(
        self,
        student_id: str,
        active: bool,
        record_service: RecordServicePort,
    ) -> dict[str, Any]:
        await self.initialize()
        async with self.session_factory.begin() as session:
            student = await session.get(StudentRecord, student_id)
            context = {
                "students": (
                    [_student_context_item(student)] if student is not None else []
                )
            }
            mutation = record_service.set_student_active(
                context,
                student_id,
                active,
            )
            if student is None:
                raise RuntimeError("El estudiante seleccionado ya no está disponible.")
            student.active = mutation.record["active"]
            return dict(mutation.record)

    async def save_enrollment(
        self,
        source_id: str,
        fields: dict[str, Any],
        record_service: RecordServicePort,
    ) -> dict[str, Any]:
        await self.initialize()
        if not isinstance(fields, dict):
            raise TypeError("Los datos de la matrícula no tienen un formato válido.")
        fields = _editable_enrollment_fields(fields)

        student_id = str(fields.get("student_id") or "").strip() or None
        raw_course_id = fields.get("course_id")
        try:
            course_id = (
                int(raw_course_id)
                if raw_course_id is not None and raw_course_id != ""
                else None
            )
        except (TypeError, ValueError):
            course_id = None

        async with self.session_factory.begin() as session:
            workspace = await session.get(Workspace, 1)
            if workspace is None:
                raise RuntimeError("No hay un espacio de trabajo inicializado.")
            target = (
                await session.get(EnrollmentRecord, source_id) if source_id else None
            )
            student = (
                await session.get(StudentRecord, student_id) if student_id else None
            )
            course = (
                await session.get(CourseRecord, course_id)
                if course_id is not None
                else None
            )

            raw_promoter_ids = fields.get(
                "promoter_ids",
                target.promoter_ids if target is not None else [],
            )
            promoter_ids: set[int] = set()
            if isinstance(raw_promoter_ids, (list, tuple)):
                for value in raw_promoter_ids:
                    try:
                        promoter_ids.add(int(value))
                    except (TypeError, ValueError):
                        continue
            promoters = (
                list(
                    (
                        await session.scalars(
                            select(PromoterRecord).where(
                                PromoterRecord.id.in_(promoter_ids)
                            )
                        )
                    ).all()
                )
                if promoter_ids
                else []
            )

            conditions = []
            if student_id and course_id is not None:
                conditions.append(
                    and_(
                        EnrollmentRecord.student_id == student_id,
                        EnrollmentRecord.course_id == course_id,
                    )
                )

            code_text = str(
                fields.get(
                    "record_code",
                    target.record_code if target is not None else "",
                )
                or ""
            ).strip()
            date_text = str(fields.get("enrollment_date", "")).strip()
            candidate_code = None
            if len(code_text) <= 50 and code_text.isascii() and code_text.isdigit():
                candidate_code = int(code_text)
            if candidate_code is not None:
                try:
                    candidate_date = date.fromisoformat(date_text)
                except ValueError:
                    candidate_date = None
                if (
                    candidate_date is not None
                    and candidate_date.isoformat() == date_text
                    and 0 < candidate_code <= 2_147_483_647
                ):
                    conditions.append(
                        and_(
                            EnrollmentRecord.record_code == candidate_code,
                            EnrollmentRecord.enrollment_date == date_text,
                        )
                    )

            conflicting_enrollments = (
                list(
                    (
                        await session.scalars(
                            select(EnrollmentRecord).where(or_(*conditions))
                        )
                    ).all()
                )
                if conditions
                else []
            )
            enrollment_context = {
                item.id: _enrollment_context_item(item)
                for item in conflicting_enrollments
            }
            if target is not None:
                enrollment_context.setdefault(
                    target.id, _enrollment_context_item(target)
                )

            attachments_to_clean = not code_text
            if attachments_to_clean:
                image_references = (
                    await session.execute(
                        select(EnrollmentRecord.id, EnrollmentRecord.record_image)
                        .where(EnrollmentRecord.record_image.is_not(None))
                    )
                ).all()
                for enrollment_id, image_path in image_references:
                    if enrollment_id not in enrollment_context:
                        enrollment_context[enrollment_id] = {
                            "id": enrollment_id,
                            "record_image": image_path,
                        }

            manifest_context = {
                "students": (
                    [_student_context_item(student)] if student is not None else []
                ),
                "courses": _course_context([course])["courses"]
                if course is not None
                else [],
                "promoters": [
                    {
                        "id": promoter.id,
                        "name": promoter.name,
                        "active": promoter.active,
                    }
                    for promoter in promoters
                ],
                "enrollments": list(enrollment_context.values()),
                "_attachment_data": workspace.attachment_data or {},
            }
            mutation = record_service.save_enrollment(
                manifest_context,
                source_id,
                fields,
            )
            position = (
                target.position
                if target is not None
                else int(
                    await session.scalar(
                        select(func.coalesce(func.max(EnrollmentRecord.position), -1))
                    )
                    or -1
                )
                + 1
            )
            values = _enrollment_values(mutation.record, workspace.id, position)
            if target is None:
                session.add(EnrollmentRecord(**values))
            else:
                for key, value in values.items():
                    setattr(target, key, value)

            if attachments_to_clean:
                attachment_data = manifest_context["_attachment_data"]
                if attachment_data != workspace.attachment_data:
                    workspace.attachment_data = attachment_data

            return {"record": dict(mutation.record)}

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

    async def search_course_options(
        self,
        query: str,
        include_inactive: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        await self.initialize()
        if not isinstance(include_inactive, bool):
            raise ValueError("El filtro de cursos inactivos no es válido.")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            limit = 50
        limit = min(limit, 100)
        conditions: list[ColumnElement[bool]] = []
        if not include_inactive:
            conditions.append(CourseRecord.active.is_(True))
        for token in normalize_search_text(query).split():
            escaped = token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            conditions.append(
                or_(
                    CourseRecord.search_text.like(pattern, escape="\\"),
                    CourseRecord.start_date.like(pattern, escape="\\"),
                )
            )
        statement = (
            select(
                CourseRecord.id.label("id"),
                CourseRecord.name.label("name"),
                CourseRecord.schedule.label("schedule"),
                CourseRecord.group_name.label("group"),
                CourseRecord.start_date.label("start_date"),
                CourseRecord.enrollment_fee.label("enrollment_fee"),
                CourseRecord.monthly_fee.label("monthly_fee"),
                CourseRecord.capacity.label("capacity"),
                CourseRecord.active.label("active"),
            )
            .where(*conditions)
            .order_by(CourseRecord.start_date.desc(), CourseRecord.position.desc())
            .limit(limit)
        )
        async with self.session_factory() as session:
            rows = (await session.execute(statement)).mappings().all()
            return [
                {
                    **dict(row),
                    "label": (
                        f"{row['name']} · {row['schedule']} · Grupo {row['group']}"
                    ),
                }
                for row in rows
            ]

    async def dashboard_summary(
        self, today: str | None = None
    ) -> dict[str, Any]:
        await self.initialize()
        summary_date = today or date.today().isoformat()
        student_course_counts = (
            select(
                EnrollmentRecord.course_id.label("course_id"),
                func.count(func.distinct(EnrollmentRecord.student_id)).label(
                    "student_count"
                ),
            )
            .join(StudentRecord, StudentRecord.id == EnrollmentRecord.student_id)
            .where(
                EnrollmentRecord.active.is_(True),
                StudentRecord.active.is_(True),
                EnrollmentRecord.course_id.is_not(None),
            )
            .group_by(EnrollmentRecord.course_id)
            .subquery()
        )

        student_count = (
            select(func.count()).select_from(StudentRecord).scalar_subquery()
        )
        active_student_count = (
            select(func.count())
            .select_from(StudentRecord)
            .where(StudentRecord.active.is_(True))
            .scalar_subquery()
        )
        course_count = select(func.count()).select_from(CourseRecord).scalar_subquery()
        active_course_count = (
            select(func.count())
            .select_from(CourseRecord)
            .where(CourseRecord.active.is_(True))
            .scalar_subquery()
        )
        enrollment_count = (
            select(func.count()).select_from(EnrollmentRecord).scalar_subquery()
        )
        active_enrollment_count = (
            select(func.count())
            .select_from(EnrollmentRecord)
            .where(
                EnrollmentRecord.active.is_(True),
                EnrollmentRecord.student_id.is_not(None),
                EnrollmentRecord.course_id.is_not(None),
            )
            .scalar_subquery()
        )
        today_enrollment_count = (
            select(func.count())
            .select_from(EnrollmentRecord)
            .where(EnrollmentRecord.enrollment_date == summary_date)
            .scalar_subquery()
        )
        pending_enrollment_count = (
            select(func.count())
            .select_from(EnrollmentRecord)
            .where(
                or_(
                    EnrollmentRecord.student_id.is_(None),
                    EnrollmentRecord.course_id.is_(None),
                )
            )
            .scalar_subquery()
        )
        full_course_count = (
            select(func.count(CourseRecord.id))
            .outerjoin(
                student_course_counts,
                student_course_counts.c.course_id == CourseRecord.id,
            )
            .where(
                CourseRecord.capacity > 0,
                func.coalesce(student_course_counts.c.student_count, 0)
                >= CourseRecord.capacity,
            )
            .scalar_subquery()
        )

        async with self.session_factory() as session:
            stats = (
                await session.execute(
                    select(
                        student_count.label("student_count"),
                        active_student_count.label("active_students"),
                        course_count.label("course_count"),
                        active_course_count.label("active_courses"),
                        enrollment_count.label("enrollment_count"),
                        active_enrollment_count.label("active_enrollments"),
                        today_enrollment_count.label("today_enrollments"),
                        pending_enrollment_count.label("pending_enrollments"),
                        full_course_count.label("full_courses"),
                    )
                )
            ).mappings().one()
            course_rows = (
                await session.execute(
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
                        func.coalesce(
                            student_course_counts.c.student_count, 0
                        ).label("student_count"),
                    )
                    .outerjoin(
                        student_course_counts,
                        student_course_counts.c.course_id == CourseRecord.id,
                    )
                    .order_by(
                        func.coalesce(
                            student_course_counts.c.student_count, 0
                        ).desc(),
                        CourseRecord.start_date.desc(),
                        CourseRecord.position.desc(),
                    )
                    .limit(6)
                )
            ).mappings().all()
            recent_rows = (
                await session.execute(
                    select(
                        EnrollmentRecord,
                        StudentRecord.last_name,
                        StudentRecord.first_name,
                        CourseRecord.name.label("course_name"),
                        CourseRecord.schedule.label("course_schedule"),
                        CourseRecord.group_name.label("course_group"),
                    )
                    .outerjoin(
                        StudentRecord,
                        StudentRecord.id == EnrollmentRecord.student_id,
                    )
                    .outerjoin(
                        CourseRecord,
                        CourseRecord.id == EnrollmentRecord.course_id,
                    )
                    .order_by(
                        EnrollmentRecord.enrollment_date.desc(),
                        EnrollmentRecord.position.desc(),
                    )
                    .limit(6)
                )
            ).all()

        occupancy_rows = [
            {
                **dict(row),
                "label": (
                    f"{row['name']} · {row['schedule']} · Grupo {row['group']}"
                ),
            }
            for row in course_rows
        ]
        recent_enrollments = []
        for (
            enrollment,
            last_name,
            first_name,
            course_name,
            course_schedule,
            course_group,
        ) in recent_rows:
            pending_student = last_name is None
            pending_course = course_name is None
            student_label = (
                " ".join(part for part in (last_name, first_name) if part)
                if not pending_student
                else "Sin estudiante"
            )
            course_label = (
                f"{course_name} · {course_schedule} · Grupo {course_group}"
                if not pending_course
                else "Pendiente de curso"
            )
            recent_enrollments.append(
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
                    "student_label": (
                        student_label
                        if not pending_student
                        else "Pendiente de estudiante"
                    ),
                    "course_label": course_label,
                    "pending_student": pending_student,
                    "pending_course": pending_course,
                    "label": f"{student_label} — {course_label}",
                }
            )

        return {
            "summary_date": summary_date,
            "student_count": int(stats["student_count"] or 0),
            "active_students": int(stats["active_students"] or 0),
            "course_count": int(stats["course_count"] or 0),
            "active_courses": int(stats["active_courses"] or 0),
            "full_courses": int(stats["full_courses"] or 0),
            "enrollment_count": int(stats["enrollment_count"] or 0),
            "active_enrollments": int(stats["active_enrollments"] or 0),
            "today_enrollments": int(stats["today_enrollments"] or 0),
            "pending_enrollments": int(stats["pending_enrollments"] or 0),
            "course_occupancy_rows": occupancy_rows,
            "recent_enrollments": recent_enrollments,
        }

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

    async def course_students(self, course_id: int) -> list[dict[str, Any]]:
        await self.initialize()
        if isinstance(course_id, bool) or not isinstance(course_id, int) or course_id < 1:
            raise ValueError("Selecciona un curso válido.")
        statement = (
            select(StudentRecord)
            .join(
                EnrollmentRecord,
                EnrollmentRecord.student_id == StudentRecord.id,
            )
            .where(
                EnrollmentRecord.course_id == course_id,
                EnrollmentRecord.active.is_(True),
                StudentRecord.active.is_(True),
            )
            .distinct()
            .order_by(StudentRecord.position.desc())
        )
        async with self.session_factory() as session:
            students = (await session.scalars(statement)).all()
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
                    "label": " ".join(
                        part
                        for part in (student.last_name, student.first_name)
                        if part
                    ),
                }
                for student in students
            ]

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
                CourseRecord.active.label("course_active"),
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
                course_active,
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
                        "course_active": bool(course_active),
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
            return await self._load_from_session(session)

    async def _load_from_session(self, session: AsyncSession):
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

    async def save_with_sync_history(
        self, manifest, history_event, *, expected_snapshot=None
    ):
        await self.initialize()
        await self._save(
            manifest,
            sync_history_event=history_event,
            expected_snapshot=expected_snapshot,
        )

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

    async def create_enrollment(
        self,
        student_fields: dict[str, Any],
        enrollment_fields: dict[str, Any],
        record_service: RecordServicePort,
    ) -> dict[str, Any]:
        await self.initialize()
        if not isinstance(student_fields, dict) or not isinstance(
            enrollment_fields, dict
        ):
            raise ValueError("Los datos de la matrícula no tienen un formato válido.")
        enrollment_fields = _editable_enrollment_fields(enrollment_fields)

        def student_values(record: StudentRecord) -> dict[str, Any]:
            return {
                "id": record.id,
                "server_id": record.server_id,
                "base_hash": record.base_hash,
                "last_name": record.last_name,
                "first_name": record.first_name,
                "document_number": record.document_number,
                "phone_numbers": record.phone_numbers,
                "active": record.active,
            }

        def course_values(record: CourseRecord) -> dict[str, Any]:
            return {
                "id": record.id,
                "server_id": record.server_id,
                "name": record.name,
                "schedule": record.schedule,
                "group": record.group_name,
                "start_date": record.start_date,
                "enrollment_fee": record.enrollment_fee,
                "monthly_fee": record.monthly_fee,
                "capacity": record.capacity,
                "active": record.active,
            }

        def promoter_values(record: PromoterRecord, version: int) -> dict[str, Any]:
            return {
                "id": record.id,
                "server_id": (
                    record.server_id
                    if record.server_id is not None or version == 3
                    else record.id
                ),
                "name": record.name,
                "active": record.active,
            }

        def enrollment_values(record: EnrollmentRecord) -> dict[str, Any]:
            return {
                "id": record.id,
                "student_id": record.student_id,
                "course_id": record.course_id,
                "enrollment_date": record.enrollment_date,
                "record_code": record.record_code,
            }

        student_id = str(student_fields.get("id") or "").strip()
        raw_course_id = enrollment_fields.get("course_id")
        course_id: int | None = None
        if raw_course_id is not None and raw_course_id != "":
            try:
                course_id = int(raw_course_id)
            except (TypeError, ValueError):
                course_id = None

        raw_promoter_ids = enrollment_fields.get("promoter_ids", [])
        promoter_ids: set[int] = set()
        if isinstance(raw_promoter_ids, (list, tuple)):
            for value in raw_promoter_ids:
                try:
                    promoter_ids.add(int(value))
                except (TypeError, ValueError):
                    continue

        conditions = []
        if student_id and course_id is not None:
            conditions.append(
                and_(
                    EnrollmentRecord.student_id == student_id,
                    EnrollmentRecord.course_id == course_id,
                )
            )
        code_text = str(enrollment_fields.get("record_code") or "").strip()
        candidate_code = None
        if code_text.isascii() and code_text.isdigit():
            try:
                candidate_code = int(code_text)
            except ValueError:
                candidate_code = None
        date_text = str(enrollment_fields.get("enrollment_date") or "").strip()
        if candidate_code is not None:
            try:
                candidate_date = date.fromisoformat(date_text)
            except ValueError:
                candidate_date = None
            if (
                candidate_date is not None
                and candidate_date.isoformat() == date_text
                and 0 < candidate_code <= 2_147_483_647
            ):
                conditions.append(
                    and_(
                        EnrollmentRecord.record_code == candidate_code,
                        EnrollmentRecord.enrollment_date == date_text,
                    )
                )

        async with self.session_factory.begin() as session:
            workspace = await session.get(Workspace, 1)
            if workspace is None:
                raise RuntimeError("No hay un espacio de trabajo inicializado.")

            if student_id:
                student_records = list(
                    (
                        await session.scalars(
                            select(StudentRecord).where(StudentRecord.id == student_id)
                        )
                    ).all()
                )
            else:
                last_name = str(student_fields.get("last_name") or "").strip()
                first_name = str(student_fields.get("first_name") or "").strip()
                if last_name and first_name:
                    student_records = list(
                        (
                            await session.scalars(
                                select(StudentRecord).where(
                                    StudentRecord.last_name_search
                                    == normalize_search_text(last_name),
                                    StudentRecord.first_name_search
                                    == normalize_search_text(first_name),
                                )
                            )
                        ).all()
                    )
                else:
                    student_records = []

            course_record = None
            if course_id is not None:
                course_record = await session.get(CourseRecord, course_id)

            if promoter_ids:
                promoter_records = list(
                    (
                        await session.scalars(
                            select(PromoterRecord).where(
                                PromoterRecord.id.in_(promoter_ids)
                            )
                        )
                    ).all()
                )
            else:
                promoter_records = []

            if conditions:
                conflicting_enrollments = list(
                    (
                        await session.scalars(
                            select(EnrollmentRecord).where(or_(*conditions))
                        )
                    ).all()
                )
            else:
                conflicting_enrollments = []

            manifest_context = {
                "students": [student_values(record) for record in student_records],
                "courses": [course_values(course_record)]
                if course_record is not None
                else [],
                "promoters": [
                    promoter_values(record, workspace.version)
                    for record in promoter_records
                ],
                "enrollments": [
                    enrollment_values(record)
                    for record in conflicting_enrollments
                ],
                "_attachment_data": {},
            }

            student_created = not student_id
            student_change = None
            if student_created:
                student_change = record_service.save_student(
                    manifest_context,
                    "",
                    str(student_fields.get("last_name") or ""),
                    str(student_fields.get("first_name") or ""),
                    str(student_fields.get("document_number") or ""),
                    str(student_fields.get("phone_text") or ""),
                )
                student_id = str(student_change.record["id"])

            fields = dict(enrollment_fields)
            fields["student_id"] = student_id
            enrollment_change = record_service.save_enrollment(
                manifest_context,
                "",
                fields,
            )

            if student_change is not None:
                position = await session.scalar(
                    select(func.coalesce(func.max(StudentRecord.position), -1))
                )
                session.add(
                    StudentRecord(
                        **_student_values(
                            student_change.record,
                            workspace.id,
                            int(position if position is not None else -1) + 1,
                        )
                    )
                )
                await session.flush()

            position = await session.scalar(
                select(func.coalesce(func.max(EnrollmentRecord.position), -1))
            )
            session.add(
                EnrollmentRecord(
                    **_enrollment_values(
                        enrollment_change.record,
                        workspace.id,
                        int(position if position is not None else -1) + 1,
                    )
                )
            )
            await session.flush()

        audit_logger.info(
            "database.enrollment_created",
            student_created=student_created,
        )
        return {
            "student_id": student_id,
            "enrollment_id": str(enrollment_change.record["id"]),
            "student_created": student_created,
        }

    async def _save(
        self, manifest, sync_history_event=None, expected_snapshot=None
    ):
        async with self.session_factory.begin() as session:
            if expected_snapshot is not None:
                await session.execute(text("BEGIN IMMEDIATE"))
                current = await self._load_from_session(session)
                if current != expected_snapshot:
                    raise ValueError(
                        "La sede cambió después de la vista previa. "
                        "Valida el paquete otra vez."
                    )

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
