import json
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, Table, URL, create_engine, delete, event, inspect, select
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import sessionmaker

from .models import (
    CourseRecord,
    EnrollmentRecord,
    PromoterRecord,
    StudentRecord,
    Workspace,
)


class LocalStore:
    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            URL.create("sqlite", database=str(self.path)),
            poolclass=NullPool,
        )
        event.listen(self.engine, "connect", self._enable_foreign_keys)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)

        config_path = Path(__file__).resolve().parents[1] / "alembic.ini"
        config = Config(str(config_path))
        config.set_main_option("sqlalchemy.url", self.engine.url.render_as_string().replace("%", "%%"))
        with self.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        self._migrate_legacy_workspace()

    @staticmethod
    def _enable_foreign_keys(connection, _):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    def _migrate_legacy_workspace(self):
        if not inspect(self.engine).has_table("workspace"):
            return

        metadata = MetaData()
        legacy = Table("workspace", metadata, autoload_with=self.engine)
        if "id" not in legacy.c or "data" not in legacy.c:
            raise RuntimeError("La tabla local antigua workspace no tiene el formato esperado.")

        with self.engine.connect() as connection:
            row = connection.execute(
                select(legacy.c.data).where(legacy.c.id == 1)
            ).first()

        if row is not None:
            manifest = json.loads(row.data)
            if self.load() is None:
                self.save(manifest)

        with self.engine.begin() as connection:
            legacy.drop(connection)

    def load(self):
        with self.session_factory() as session:
            workspace = session.get(Workspace, 1)
            if workspace is None:
                return None

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
                    for item in session.scalars(
                        select(StudentRecord).order_by(StudentRecord.position)
                    )
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
                    for item in session.scalars(
                        select(EnrollmentRecord).order_by(EnrollmentRecord.position)
                    )
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
                    for item in session.scalars(select(CourseRecord).order_by(CourseRecord.position))
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
                    for item in session.scalars(
                        select(PromoterRecord).order_by(PromoterRecord.position)
                    )
                ],
            }
            if workspace.attachment_data is not None:
                manifest["_attachment_data"] = workspace.attachment_data
            if workspace.version == 3:
                manifest["campus_mode"] = "new"
            return manifest

    def save(self, manifest):
        with self.session_factory.begin() as session:
            session.execute(delete(EnrollmentRecord))
            session.execute(delete(StudentRecord))
            session.execute(delete(CourseRecord))
            session.execute(delete(PromoterRecord))
            session.execute(delete(Workspace))

            workspace = Workspace(
                id=1,
                format=manifest["format"],
                version=manifest["version"],
                bundle_id=manifest["bundle_id"],
                campus_id=manifest["campus_id"],
                campus_name=manifest["campus_name"],
                campus_address=manifest.get("campus_address", ""),
                attachment_data=manifest.get("_attachment_data"),
            )
            session.add(workspace)
            session.flush()

            student_ids = set()
            for position, item in enumerate(manifest["students"]):
                student_ids.add(item["id"])
                session.add(
                    StudentRecord(
                        id=item["id"],
                        workspace_id=workspace.id,
                        position=position,
                        server_id=item["server_id"],
                        base_hash=item["base_hash"],
                        last_name=item["last_name"],
                        first_name=item["first_name"],
                        document_number=item["document_number"],
                        phone_numbers=item["phone_numbers"],
                        active=item["active"],
                    )
                )

            course_ids = set()
            for position, item in enumerate(manifest["courses"]):
                course_id = int(item["id"])
                course_ids.add(course_id)
                session.add(
                    CourseRecord(
                        id=course_id,
                        workspace_id=workspace.id,
                        position=position,
                        server_id=item.get("server_id", course_id),
                        name=item["name"],
                        schedule=item["schedule"],
                        group_name=item["group"],
                        start_date=item["start_date"],
                        enrollment_fee=item["enrollment_fee"],
                        monthly_fee=item["monthly_fee"],
                        capacity=item["capacity"],
                        active=item["active"],
                    )
                )

            promoter_ids = set()
            for position, item in enumerate(manifest["promoters"]):
                promoter_id = int(item["id"])
                promoter_ids.add(promoter_id)
                session.add(
                    PromoterRecord(
                        id=promoter_id,
                        workspace_id=workspace.id,
                        position=position,
                        server_id=(
                            item.get("server_id")
                            if item.get("server_id") is not None
                            or manifest["version"] == 3
                            else promoter_id
                        ),
                        name=item["name"],
                        active=item["active"],
                    )
                )
            session.flush()

            for position, item in enumerate(manifest["enrollments"]):
                student_id = item.get("student_id")
                course_id = item.get("course_id")
                linked_promoters = [int(value) for value in item["promoter_ids"]]
                if student_id is not None and student_id not in student_ids:
                    raise ValueError("Una matrícula hace referencia a un estudiante inexistente.")
                if course_id is not None and course_id not in course_ids:
                    raise ValueError("Una matrícula hace referencia a un curso inexistente.")
                if any(value not in promoter_ids for value in linked_promoters):
                    raise ValueError("Una matrícula hace referencia a un promotor inexistente.")
                session.add(
                    EnrollmentRecord(
                        id=item["id"],
                        workspace_id=workspace.id,
                        position=position,
                        server_id=item["server_id"],
                        base_hash=item["base_hash"],
                        student_id=student_id,
                        student_server_id=item["student_server_id"],
                        course_id=course_id,
                        enrollment_date=item["enrollment_date"],
                        promoter_ids=linked_promoters,
                        enrollment_fee=item["enrollment_fee"],
                        monthly_fee=item["monthly_fee"],
                        record_code=item["record_code"],
                        active=item["active"],
                        record_image=item["record_image"],
                        record_image_hash=item["record_image_hash"],
                        record_image_quality=item["record_image_quality"],
                    )
                )
