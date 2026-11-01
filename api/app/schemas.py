"""API contracts (Pydantic v2).

Think of these as TypeScript interfaces that also validate at runtime.
`*Create` = POST body, `*Update` = PATCH body (all optional except `version`),
`*Out` = what the API returns.
"""

from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models import (
    ArmType,
    CriterionCategory,
    JobStatus,
    ObjectiveLevel,
    StudyPhase,
    StudyStatus,
)


def _as_utc(value: datetime) -> datetime:
    """Always send timestamps with a timezone. Some databases (SQLite) drop it;
    our timestamps are stored in UTC, so a missing zone means UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


# Database integer columns are 32-bit; reject anything larger with a 422.
DbInt = Annotated[int, Field(ge=1, le=2_147_483_647)]

# Use for every timestamp in a response, so the API always returns valid RFC 3339.
UTCDateTime = Annotated[datetime, AfterValidator(_as_utc)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Arms ----------
class ArmBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    arm_type: ArmType
    description: str | None = None
    planned_size: int | None = Field(default=None, ge=1, le=1_000_000)
    dose: str | None = Field(default=None, max_length=100)


class ArmCreate(ArmBase):
    @model_validator(mode="after")
    def dose_required_for_experimental(self) -> "ArmCreate":
        # Conditional validation: the same rule the Angular form enforces.
        if self.arm_type == ArmType.EXPERIMENTAL and not self.dose:
            raise ValueError("dose is required for experimental arms")
        return self


class ArmUpdate(BaseModel):
    version: DbInt
    name: str = Field(default=None, min_length=1, max_length=200)
    arm_type: ArmType = Field(default=None)
    description: str | None = None
    planned_size: int | None = Field(default=None, ge=1, le=1_000_000)
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
    version: DbInt
    level: ObjectiveLevel = Field(default=None)
    description: str = Field(default=None, min_length=1)
    endpoint: str = Field(default=None, min_length=1)


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


# PATCH bodies: every field may be left out, but fields the database requires are typed
# without `| None`, so an explicit null is a 422 instead of a database error.


class StudyUpdate(BaseModel):
    version: DbInt
    title: str = Field(default=None, min_length=3, max_length=300)
    acronym: str | None = Field(default=None, max_length=50)
    phase: StudyPhase = Field(default=None)
    therapeutic_area: str | None = Field(default=None, max_length=100)
    status: StudyStatus = Field(default=None)


class StudySummary(StudyBase, ORMModel):
    id: int
    status: StudyStatus
    version: int
    updated_at: UTCDateTime


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
    changed_at: UTCDateTime


class ConflictDetail(BaseModel):
    """Body of a 409: the client shows 'theirs' vs 'yours' from this."""

    message: str
    current: dict[str, Any]


# ---------- Auth ----------
class UserOut(ORMModel):
    id: int
    email: EmailStr
    display_name: str


class RegisterRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- Protocol digitization ----------
class JobOut(ORMModel):
    id: int
    study_id: int
    created_by: str
    filename: str
    size_bytes: int
    status: JobStatus
    progress: int
    stage: str
    attempts: int
    extractor: str | None
    error: str | None
    result: dict[str, Any] | None
    created_at: UTCDateTime
    updated_at: UTCDateTime
    finished_at: UTCDateTime | None
    applied_at: UTCDateTime | None


class ApplyRequest(BaseModel):
    """Which extracted items (by index in result.arms / result.objectives) to add."""

    arms: list[Annotated[int, Field(ge=0, le=1000)]] = Field(default_factory=list, max_length=200)
    objectives: list[Annotated[int, Field(ge=0, le=1000)]] = Field(
        default_factory=list, max_length=200
    )


class ApplyResult(BaseModel):
    arms_added: int
    objectives_added: int


# ---------- Eligibility criteria ----------
class CriterionCreate(BaseModel):
    category: CriterionCategory
    text: str = Field(min_length=3, max_length=2000)


class CriterionUpdate(BaseModel):
    version: DbInt
    text: str = Field(default=None, min_length=3, max_length=2000)


class CriterionOut(ORMModel):
    id: int
    study_id: int
    category: CriterionCategory
    ordinal: int
    identifier: str
    text: str
    version: int


class CriteriaOrder(BaseModel):
    """The full, new order of one category. Must list exactly the current criteria."""

    category: CriterionCategory
    ids: list[DbInt] = Field(min_length=1, max_length=500)


# ---------- Schedule of Activities ----------
class EncounterBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    day: int = Field(ge=-365, le=3650, description="Study day; Day 1 = first dose")
    window_before: int = Field(default=0, ge=0, le=90)
    window_after: int = Field(default=0, ge=0, le=90)


class EncounterCreate(EncounterBase):
    pass


class EncounterUpdate(BaseModel):
    version: DbInt
    name: str = Field(default=None, min_length=1, max_length=100)
    day: int = Field(default=None, ge=-365, le=3650)
    window_before: int = Field(default=None, ge=0, le=90)
    window_after: int = Field(default=None, ge=0, le=90)


class EncounterOut(EncounterBase, ORMModel):
    id: int
    study_id: int
    version: int


class ActivityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ActivityUpdate(BaseModel):
    version: DbInt
    name: str = Field(default=None, min_length=1, max_length=200)


class ActivityOut(ORMModel):
    id: int
    study_id: int
    name: str
    ordinal: int
    version: int


class ScheduleCell(BaseModel):
    encounter_id: DbInt
    activity_id: DbInt


class ScheduleOut(BaseModel):
    encounters: list[EncounterOut]
    activities: list[ActivityOut]
    cells: list[ScheduleCell]


class CellUpdate(ScheduleCell):
    planned: bool


class CellOut(ScheduleCell):
    planned: bool
    changed: bool
