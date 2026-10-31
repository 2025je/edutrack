from alembic import op
import sqlalchemy as sa


revision = "0004_sync_history"
down_revision = "0003_search_indexes"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "desktop_sync_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("operation", sa.String(length=20), nullable=False),
        sa.Column("bundle_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("affected_counts", sa.JSON(), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_desktop_sync_history_operation_bundle_status",
        "desktop_sync_history",
        ["operation", "bundle_id", "status"],
    )


def downgrade():
    op.drop_index(
        "ix_desktop_sync_history_operation_bundle_status",
        table_name="desktop_sync_history",
    )
    op.drop_table("desktop_sync_history")
