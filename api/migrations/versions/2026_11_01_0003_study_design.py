"""Study design: eligibility criteria and the Schedule of Activities.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _study_fk() -> sa.Column:
    return sa.Column(
        "study_id", sa.Integer(), sa.ForeignKey("study.id", ondelete="CASCADE"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "eligibility_criterion",
        sa.Column("id", sa.Integer(), primary_key=True),
        _study_fk(),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
    )
    op.create_index("ix_eligibility_criterion_study_id", "eligibility_criterion", ["study_id"])

    op.create_table(
        "encounter",
        sa.Column("id", sa.Integer(), primary_key=True),
        _study_fk(),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("window_before", sa.Integer(), nullable=False),
        sa.Column("window_after", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("study_id", "name", name="uq_encounter_name"),
    )
    op.create_index("ix_encounter_study_id", "encounter", ["study_id"])

    op.create_table(
        "activity",
        sa.Column("id", sa.Integer(), primary_key=True),
        _study_fk(),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("study_id", "name", name="uq_activity_name"),
    )
    op.create_index("ix_activity_study_id", "activity", ["study_id"])

    op.create_table(
        "scheduled_activity",
        sa.Column("id", sa.Integer(), primary_key=True),
        _study_fk(),
        sa.Column(
            "encounter_id",
            sa.Integer(),
            sa.ForeignKey("encounter.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "activity_id",
            sa.Integer(),
            sa.ForeignKey("activity.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint("encounter_id", "activity_id", name="uq_schedule_cell"),
    )
    op.create_index("ix_scheduled_activity_study_id", "scheduled_activity", ["study_id"])


def downgrade() -> None:
    op.drop_table("scheduled_activity")
    op.drop_table("activity")
    op.drop_table("encounter")
    op.drop_table("eligibility_criterion")
