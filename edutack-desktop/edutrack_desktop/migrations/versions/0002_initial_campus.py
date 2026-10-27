from alembic import op
import sqlalchemy as sa

revision = "0002_initial_campus"
down_revision = "0001_local_workspace"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("desktop_workspaces", recreate="always") as batch:
        batch.alter_column(
            "campus_id",
            existing_type=sa.Integer(),
            nullable=True,
        )
        batch.add_column(
            sa.Column(
                "campus_address",
                sa.String(length=200),
                nullable=False,
                server_default="",
            )
        )
    with op.batch_alter_table("desktop_courses") as batch:
        batch.add_column(sa.Column("server_id", sa.Integer(), nullable=True))
    with op.batch_alter_table("desktop_promoters") as batch:
        batch.add_column(sa.Column("server_id", sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table("desktop_promoters") as batch:
        batch.drop_column("server_id")
    with op.batch_alter_table("desktop_courses") as batch:
        batch.drop_column("server_id")
    with op.batch_alter_table("desktop_workspaces", recreate="always") as batch:
        batch.drop_column("campus_address")
        batch.alter_column(
            "campus_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
