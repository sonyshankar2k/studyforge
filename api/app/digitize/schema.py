"""The structured result of reading a protocol: what the AI proposes to add to the study."""

from pydantic import BaseModel, Field

from app.models import ArmType, ObjectiveLevel


class ExtractedArm(BaseModel):
    name: str = Field(min_length=1, max_length=200, description="Arm name, e.g. 'SF-202 20 mg'")
    arm_type: ArmType = Field(description="experimental, active_comparator or placebo")
    dose: str | None = Field(
        default=None, max_length=100, description="Dose and frequency, e.g. '20 mg once daily'"
    )
    planned_size: int | None = Field(default=None, ge=1, description="Planned participants")
    description: str | None = Field(default=None, description="Short description of the arm")


class ExtractedObjective(BaseModel):
    level: ObjectiveLevel = Field(description="primary, secondary or exploratory")
    description: str = Field(min_length=1, description="The objective")
    endpoint: str = Field(min_length=1, description="How the objective is measured")


class ExtractedProtocol(BaseModel):
    arms: list[ExtractedArm] = Field(default_factory=list)
    objectives: list[ExtractedObjective] = Field(default_factory=list)
    notes: str | None = Field(
        default=None, description="Anything ambiguous a reviewer should double-check"
    )
