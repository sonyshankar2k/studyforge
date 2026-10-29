"""API contracts (Pydantic v2).

Think of these as TypeScript interfaces that also validate at runtime.
`*Create` = POST body, `*Update` = PATCH body (all optional except `version`),
`*Out` = what the API returns.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import ArmType, ObjectiveLevel, StudyPhase, StudyStatus


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Arms ----------
class ArmBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    arm_type: ArmType
    description: str | None = None
    planned_size: int | None = Field(default=None, ge=1)
    dose: str | None = Field(default=None, max_length=100)


class ArmCreate(ArmBase):
    @model_validator(mode="after")
    def dose_required_for_experimental(self) -> "ArmCreate":
        # Conditional validation: the same rule the Angular form enforces.
        if self.arm_type == ArmType.EXPERIMENTAL and not self.dose:
            raise ValueError("dose is required for experimental arms")
        return self


class ArmUpdate(BaseModel):
    version: int
    name: str | None = Field(default=None, min_length=1, max_length=200)
    arm_type: ArmType | None = None
    description: str | None = None
    planned_size: int | None = Field(default=None, ge=1)
    dose: str | None = Field(default=None, max_length=100)


class ArmOut(ArmBase, ORMModel):
    id: int
    study_id: int
    version: int


# ---------- Objectives ----------
class ObjectiveBase(BaseModel):
    level: ObjectiveLevel
    description: str = Field(min_length=1)
    endpoint: str = Field(min_length=1)


class ObjectiveCreate(ObjectiveBase):
    pass


class ObjectiveUpdate(BaseModel):
    version: int
    level: ObjectiveLevel | None = None
    description: str | None = Field(default=None, min_length=1)
    endpoint: str | None = Field(default=None, min_length=1)


class ObjectiveOut(ObjectiveBase, ORMModel):
    id: int
    study_id: int
    version: int


# ---------- Studies ----------
class StudyBase(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    acronym: str | None = Field(default=None, max_length=50)
    phase: StudyPhase = StudyPhase.PHASE_1
    therapeutic_area: str | None = Field(default=None, max_length=100)


class StudyCreate(StudyBase):
    pass


class StudyUpdate(BaseModel):
    version: int
    title: str | None = Field(default=None, min_length=3, max_length=300)
    acronym: str | None = Field(default=None, max_length=50)
    phase: StudyPhase | None = None
    therapeutic_area: str | None = Field(default=None, max_length=100)
    status: StudyStatus | None = None


class StudySummary(StudyBase, ORMModel):
    id: int
    status: StudyStatus
    version: int
    updated_at: datetime


class StudyDetail(StudySummary):
    arms: list[ArmOut]
    objectives: list[ObjectiveOut]


# ---------- Audit + errors ----------
class AuditEntryOut(ORMModel):
    id: int
    entity_type: str
    entity_id: int
    action: str
    changes: dict[str, Any]
    changed_by: str
    changed_at: datetime


class ConflictDetail(BaseModel):
    """Body of a 409: the client shows 'theirs' vs 'yours' from this."""

    message: str
    current: dict[str, Any]
