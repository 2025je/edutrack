from alembic import op
import sqlalchemy as sa

revision = "0001_local_workspace"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "desktop_workspaces",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("format", sa.String(length=40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("bundle_id", sa.String(length=36), nullable=False),
        sa.Column("campus_id", sa.Integer(), nullable=False),
        sa.Column("campus_name", sa.String(length=200), nullable=False),
        sa.Column("attachment_data", sa.JSON(), nullable=True),
    )
    op.create_table(
        "desktop_students",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("server_id", sa.Integer(), nullable=True),
        sa.Column("base_hash", sa.String(length=64), nullable=True),
        sa.Column("last_name", sa.String(length=120), nullable=False),
        sa.Column("first_name", sa.String(length=120), nullable=False),
        sa.Column("document_number", sa.String(length=20), nullable=False),
        sa.Column("phone_numbers", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["desktop_workspaces.id"], ondelete="CASCADE"
        ),
    )
    op.create_table(
        "desktop_courses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("schedule", sa.String(length=100), nullable=False),
        sa.Column("group", sa.String(length=100), nullable=False),
        sa.Column("start_date", sa.String(length=10), nullable=False),
        sa.Column("enrollment_fee", sa.String(length=20), nullable=False),
        sa.Column("monthly_fee", sa.String(length=20), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["desktop_workspaces.id"], ondelete="CASCADE"
        ),
    )
    op.create_table(
        "desktop_promoters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["desktop_workspaces.id"], ondelete="CASCADE"
        ),
    )
    op.create_table(
        "desktop_enrollments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("server_id", sa.Integer(), nullable=True),
        sa.Column("base_hash", sa.String(length=64), nullable=True),
        sa.Column("student_id", sa.String(length=36), nullable=True),
        sa.Column("student_server_id", sa.Integer(), nullable=True),
        sa.Column("course_id", sa.Integer(), nullable=True),
        sa.Column("enrollment_date", sa.String(length=10), nullable=False),
        sa.Column("promoter_ids", sa.JSON(), nullable=False),
        sa.Column("enrollment_fee", sa.String(length=20), nullable=False),
        sa.Column("monthly_fee", sa.String(length=20), nullable=False),
        sa.Column("record_code", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("record_image", sa.String(length=100), nullable=True),
        sa.Column("record_image_hash", sa.String(length=64), nullable=False),
        sa.Column("record_image_quality", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["desktop_workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["student_id"], ["desktop_students.id"]),
        sa.ForeignKeyConstraint(["course_id"], ["desktop_courses.id"]),
    )


def downgrade():
    op.drop_table("desktop_enrollments")
    op.drop_table("desktop_promoters")
    op.drop_table("desktop_courses")
    op.drop_table("desktop_students")
    op.drop_table("desktop_workspaces")
