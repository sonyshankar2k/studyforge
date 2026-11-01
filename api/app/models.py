"""Database tables.

Every editable table has a `version` column for optimistic concurrency:
a client sends the version it last read, and the API rejects the update with
409 Conflict if someone else saved in between.

`AuditLog` records every change (who, what, when, old -> new values),
which is the core of an ALCOA+-style audit trail.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class StudyPhase(StrEnum):
    PHASE_1 = "Phase 1"
    PHASE_2 = "Phase 2"
    PHASE_3 = "Phase 3"
    PHASE_4 = "Phase 4"


class StudyStatus(StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"


class ArmType(StrEnum):
    EXPERIMENTAL = "experimental"
    ACTIVE_COMPARATOR = "active_comparator"
    PLACEBO = "placebo"


class ObjectiveLevel(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    EXPLORATORY = "exploratory"


class User(Base):
    __tablename__ = "app_user"  # "user" is a reserved word in PostgreSQL

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Study(Base):
    __tablename__ = "study"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    acronym: Mapped[str | None] = mapped_column(String(50))
    phase: Mapped[str] = mapped_column(String(20), default=StudyPhase.PHASE_1)
    therapeutic_area: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default=StudyStatus.DRAFT)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    arms: Mapped[list["Arm"]] = relationship(
        back_populates="study", cascade="all, delete-orphan", order_by="Arm.id"
    )
    objectives: Mapped[list["Objective"]] = relationship(
        back_populates="study", cascade="all, delete-orphan", order_by="Objective.id"
    )


class Arm(Base):
    __tablename__ = "arm"

    id: Mapped[int] = mapped_column(primary_key=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("study.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    arm_type: Mapped[str] = mapped_column(String(30))
    description: Mapped[str | None] = mapped_column(Text)
    planned_size: Mapped[int | None] = mapped_column(Integer)
    dose: Mapped[str | None] = mapped_column(String(100))
    version: Mapped[int] = mapped_column(Integer, default=1)

    study: Mapped[Study] = relationship(back_populates="arms")


class Objective(Base):
    __tablename__ = "objective"

    id: Mapped[int] = mapped_column(primary_key=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("study.id", ondelete="CASCADE"), index=True)
    level: Mapped[str] = mapped_column(String(20))
    description: Mapped[str] = mapped_column(Text)
    endpoint: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)

    study: Mapped[Study] = relationship(back_populates="objectives")


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}


class DigitizationJob(Base):
    """One "read this protocol with AI" request, processed by the background worker.

    Lifecycle: queued -> running -> succeeded | failed | cancelled.
    The extracted result is only a *proposal*: nothing reaches the study until a
    person reviews it and applies it (human in the loop, required for GxP work).
    """

    __tablename__ = "digitization_job"
    __table_args__ = (
        # Same user + same Idempotency-Key = same job. Makes upload retries safe.
        UniqueConstraint("created_by_id", "idempotency_key", name="uq_job_idempotency"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("study.id", ondelete="CASCADE"), index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"))
    created_by: Mapped[str] = mapped_column(String(254))  # email, for display and audit
    idempotency_key: Mapped[str] = mapped_column(String(100))

    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(255))

    status: Mapped[str] = mapped_column(String(20), default=JobStatus.QUEUED, index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    stage: Mapped[str] = mapped_column(String(200), default="Waiting for a worker")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    runs: Mapped[int] = mapped_column(Integer, default=1)  # bumps on manual retry
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    extractor: Mapped[str | None] = mapped_column(String(50))
    error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    study_id: Mapped[int] = mapped_column(Integer, index=True)
    entity_type: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(10))  # create | update | delete
    changes: Mapped[dict[str, Any]] = mapped_column(JSON)  # {"field": {"old": x, "new": y}}
    changed_by: Mapped[str] = mapped_column(String(100))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
