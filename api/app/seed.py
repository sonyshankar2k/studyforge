"""Demo data so the app isn't empty on first run. (Fictional study.)"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Arm, ArmType, Objective, ObjectiveLevel, Study, StudyPhase


async def seed_demo_data(session: AsyncSession) -> None:
    count = await session.scalar(select(func.count()).select_from(Study))
    if count:
        return

    study = Study(
        title="A Randomized, Placebo-Controlled Study of SF-101 in Adults with Mild Asthma",
        acronym="BREATHE-1",
        phase=StudyPhase.PHASE_2,
        therapeutic_area="Respiratory",
    )
    study.arms = [
        Arm(
            name="SF-101 10 mg",
            arm_type=ArmType.EXPERIMENTAL,
            dose="10 mg once daily",
            planned_size=120,
            description="Oral tablet for 12 weeks",
        ),
        Arm(
            name="Placebo",
            arm_type=ArmType.PLACEBO,
            planned_size=120,
            description="Matching placebo tablet for 12 weeks",
        ),
    ]
    study.objectives = [
        Objective(
            level=ObjectiveLevel.PRIMARY,
            description="Evaluate the efficacy of SF-101 compared with placebo",
            endpoint="Change from baseline in FEV1 at Week 12",
        ),
        Objective(
            level=ObjectiveLevel.SECONDARY,
            description="Evaluate the safety and tolerability of SF-101",
            endpoint="Incidence of treatment-emergent adverse events through Week 14",
        ),
    ]
    session.add(study)
    await session.commit()
