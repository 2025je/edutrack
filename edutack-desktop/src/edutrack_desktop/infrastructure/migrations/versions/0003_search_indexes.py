from alembic import op
import sqlalchemy as sa

from edutrack_desktop.infrastructure.search import normalize_search_text


revision = "0003_search_indexes"
down_revision = "0002_initial_campus"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "desktop_students",
        sa.Column(
            "last_name_search",
            sa.String(length=120, collation="NOCASE"),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "desktop_students",
        sa.Column(
            "first_name_search",
            sa.String(length=120, collation="NOCASE"),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "desktop_students",
        sa.Column(
            "document_number_search",
            sa.String(length=20, collation="NOCASE"),
            nullable=False,
            server_default="",
        ),
    )

    connection = op.get_bind()
    students = sa.table(
        "desktop_students",
        sa.column("id", sa.String()),
        sa.column("last_name", sa.String()),
        sa.column("first_name", sa.String()),
        sa.column("document_number", sa.String()),
        sa.column("last_name_search", sa.String()),
        sa.column("first_name_search", sa.String()),
        sa.column("document_number_search", sa.String()),
    )
    for student in connection.execute(
        sa.select(
            students.c.id,
            students.c.last_name,
            students.c.first_name,
            students.c.document_number,
        )
    ).mappings():
        connection.execute(
            students.update()
            .where(students.c.id == student["id"])
            .values(
                last_name_search=normalize_search_text(student["last_name"]),
                first_name_search=normalize_search_text(student["first_name"]),
                document_number_search=normalize_search_text(
                    student["document_number"]
                ),
            )
        )

    op.create_index(
        "ix_desktop_students_last_name_search",
        "desktop_students",
        ["last_name_search"],
    )
    op.create_index(
        "ix_desktop_students_first_name_search",
        "desktop_students",
        ["first_name_search"],
    )
    op.create_index(
        "ix_desktop_students_document_number_search",
        "desktop_students",
        ["document_number_search"],
    )
    op.create_index(
        "ix_desktop_enrollments_student_id",
        "desktop_enrollments",
        ["student_id"],
    )
    op.create_index(
        "ix_desktop_enrollments_course_id",
        "desktop_enrollments",
        ["course_id"],
    )
    op.create_index(
        "ix_desktop_enrollments_active",
        "desktop_enrollments",
        ["active"],
    )
    op.create_index("ix_desktop_courses_name", "desktop_courses", ["name"])
    op.create_index("ix_desktop_courses_active", "desktop_courses", ["active"])
    op.create_index("ix_desktop_promoters_name", "desktop_promoters", ["name"])


def downgrade():
    op.drop_index("ix_desktop_promoters_name", table_name="desktop_promoters")
    op.drop_index("ix_desktop_courses_active", table_name="desktop_courses")
    op.drop_index("ix_desktop_courses_name", table_name="desktop_courses")
    op.drop_index("ix_desktop_enrollments_active", table_name="desktop_enrollments")
    op.drop_index("ix_desktop_enrollments_course_id", table_name="desktop_enrollments")
    op.drop_index("ix_desktop_enrollments_student_id", table_name="desktop_enrollments")
    op.drop_index(
        "ix_desktop_students_document_number_search",
        table_name="desktop_students",
    )
    op.drop_index(
        "ix_desktop_students_first_name_search",
        table_name="desktop_students",
    )
    op.drop_index(
        "ix_desktop_students_last_name_search",
        table_name="desktop_students",
    )
    op.drop_column("desktop_students", "document_number_search")
    op.drop_column("desktop_students", "first_name_search")
    op.drop_column("desktop_students", "last_name_search")
