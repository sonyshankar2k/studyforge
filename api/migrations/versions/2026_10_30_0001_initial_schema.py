"""Initial schema: users, studies, arms, objectives, audit log.

Revision ID: 0001
Revises:
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_app_user_email", "app_user", ["email"], unique=True)

    op.create_table(
        "study",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("acronym", sa.String(length=50), nullable=True),
        sa.Column("phase", sa.String(length=20), nullable=False),
        sa.Column("therapeutic_area", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "arm",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "study_id",
            sa.Integer(),
            sa.ForeignKey("study.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("arm_type", sa.String(length=30), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("planned_size", sa.Integer(), nullable=True),
        sa.Column("dose", sa.String(length=100), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
    )
    op.create_index("ix_arm_study_id", "arm", ["study_id"])

    op.create_table(
        "objective",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "study_id",
            sa.Integer(),
            sa.ForeignKey("study.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
    )
    op.create_index("ix_objective_study_id", "objective", ["study_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("study_id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(length=30), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=10), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.Column("changed_by", sa.String(length=100), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_log_study_id", "audit_log", ["study_id"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("objective")
    op.drop_table("arm")
    op.drop_table("study")
    op.drop_table("app_user")
