from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Workspace(Base):
    __tablename__ = "desktop_workspaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    format: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    bundle_id: Mapped[str] = mapped_column(String(36), nullable=False)
    campus_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    campus_name: Mapped[str] = mapped_column(String(200), nullable=False)
    campus_address: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    attachment_data: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)


class StudentRecord(Base):
    __tablename__ = "desktop_students"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("desktop_workspaces.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    server_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    base_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_name: Mapped[str] = mapped_column(String(120), nullable=False)
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    document_number: Mapped[str] = mapped_column(String(20), nullable=False)
    last_name_search: Mapped[str] = mapped_column(
        String(120, collation="NOCASE"), nullable=False, default="", server_default=""
    )
    first_name_search: Mapped[str] = mapped_column(
        String(120, collation="NOCASE"), nullable=False, default="", server_default=""
    )
    document_number_search: Mapped[str] = mapped_column(
        String(20, collation="NOCASE"), nullable=False, default="", server_default=""
    )
    phone_numbers: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)


class CourseRecord(Base):
    __tablename__ = "desktop_courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("desktop_workspaces.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    server_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    schedule: Mapped[str] = mapped_column(String(100), nullable=False)
    group_name: Mapped[str] = mapped_column("group", String(100), nullable=False)
    start_date: Mapped[str] = mapped_column(String(10), nullable=False)
    enrollment_fee: Mapped[str] = mapped_column(String(20), nullable=False)
    monthly_fee: Mapped[str] = mapped_column(String(20), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)


class PromoterRecord(Base):
    __tablename__ = "desktop_promoters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("desktop_workspaces.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    server_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)


class EnrollmentRecord(Base):
    __tablename__ = "desktop_enrollments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("desktop_workspaces.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    server_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    base_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    student_id: Mapped[str | None] = mapped_column(
        ForeignKey("desktop_students.id"), nullable=True
    )
    student_server_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    course_id: Mapped[int | None] = mapped_column(
        ForeignKey("desktop_courses.id"), nullable=True
    )
    enrollment_date: Mapped[str] = mapped_column(String(10), nullable=False)
    promoter_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    enrollment_fee: Mapped[str] = mapped_column(String(20), nullable=False)
    monthly_fee: Mapped[str] = mapped_column(String(20), nullable=False)
    record_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    record_image: Mapped[str | None] = mapped_column(String(100), nullable=True)
    record_image_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    record_image_quality: Mapped[int] = mapped_column(Integer, nullable=False)


class SyncHistoryRecord(Base):
    __tablename__ = "desktop_sync_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation: Mapped[str] = mapped_column(String(20), nullable=False)
    bundle_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    affected_counts: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False, default="")
