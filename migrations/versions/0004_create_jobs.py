"""create jobs

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

job_type = sa.Enum("extract_sketch", "generate_design", "try_on", name="job_type")
job_status = sa.Enum("pending", "running", "done", "failed", "cancelled", name="job_status")


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", job_type, nullable=False),
        sa.Column("status", job_status, nullable=False, server_default="pending"),
        sa.Column("progress", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("input_ref", sa.Text(), nullable=False),
        sa.Column("output_ref", sa.Text()),
        sa.Column("error_code", sa.String(50)),
        sa.Column("error_message", sa.Text()),
        sa.Column("retry_count", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("progress BETWEEN 0 AND 100", name="ck_jobs_progress_range"),
    )
    op.create_index("ix_jobs_user_created", "jobs", ["user_id", sa.text("created_at DESC")])
    op.create_index("ix_jobs_active_status", "jobs", ["status"],
                    postgresql_where=sa.text("status IN ('pending', 'running')"))
    op.create_index("ix_jobs_type_status", "jobs", ["type", "status"])


def downgrade() -> None:
    op.drop_index("ix_jobs_type_status", table_name="jobs")
    op.drop_index("ix_jobs_active_status", table_name="jobs")
    op.drop_index("ix_jobs_user_created", table_name="jobs")
    op.drop_table("jobs")
    job_status.drop(op.get_bind(), checkfirst=True)
    job_type.drop(op.get_bind(), checkfirst=True)
