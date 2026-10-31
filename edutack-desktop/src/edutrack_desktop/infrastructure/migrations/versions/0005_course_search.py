from alembic import op
import sqlalchemy as sa

from edutrack_desktop.infrastructure.search import normalize_search_text


revision = "0005_course_search"
down_revision = "0004_sync_history"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "desktop_courses",
        sa.Column(
            "search_text",
            sa.String(length=500, collation="NOCASE"),
            nullable=False,
            server_default="",
        ),
    )

    connection = op.get_bind()
    courses = sa.table(
        "desktop_courses",
        sa.column("id", sa.Integer()),
        sa.column("name", sa.String()),
        sa.column("schedule", sa.String()),
        sa.column("group", sa.String()),
        sa.column("search_text", sa.String()),
    )
    update_search_text = (
        sa.update(courses)
        .where(courses.c.id == sa.bindparam("course_id_param"))
        .values(search_text=sa.bindparam("course_search_param"))
    )
    batch = []
    course_rows = connection.execute(
        sa.select(
            courses.c.id,
            courses.c.name,
            courses.c.schedule,
            courses.c.group,
        ).execution_options(stream_results=True)
    ).mappings()
    for course in course_rows:
        label = (
            f"{course['name']} · {course['schedule']} · Grupo {course['group']}"
        )
        batch.append(
            {
                "course_id_param": course["id"],
                "course_search_param": normalize_search_text(label),
            }
        )
        if len(batch) == 500:
            connection.execute(update_search_text, batch)
            batch.clear()
    if batch:
        connection.execute(update_search_text, batch)


def downgrade():
    op.drop_column("desktop_courses", "search_text")
