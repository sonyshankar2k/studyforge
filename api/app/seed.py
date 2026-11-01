"""Demo data so the app isn't empty on first run. (Fictional study and users.)"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Activity,
    Arm,
    ArmType,
    AuditLog,
    CriterionCategory,
    EligibilityCriterion,
    Encounter,
    Objective,
    ObjectiveLevel,
    ScheduledActivity,
    Study,
    StudyPhase,
    User,
)
from app.security import hash_password

# Demo accounts for trying collaboration in two browser windows.
# They are only created when SEED_DEMO_DATA=true (the local default).
DEMO_PASSWORD = "studyforge"
DEMO_USERS = [
    ("alice@studyforge.dev", "Alice"),
    ("bob@studyforge.dev", "Bob"),
    ("carol@studyforge.dev", "Carol"),
]


async def seed_demo_data(session: AsyncSession) -> None:
    await _seed_users(session)
    await _seed_study(session)
    await _seed_design(session)


async def _seed_users(session: AsyncSession) -> None:
    if await session.scalar(select(func.count()).select_from(User)):
        return
    hashed = hash_password(DEMO_PASSWORD)
    session.add_all(
        User(email=email, display_name=name, password_hash=hashed) for email, name in DEMO_USERS
    )
    await session.commit()


async def _seed_study(session: AsyncSession) -> None:
    if await session.scalar(select(func.count()).select_from(Study)):
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


INCLUSION = [
    "Adults aged 18 to 65 years at screening",
    "Physician-diagnosed asthma for at least 6 months",
    "Pre-bronchodilator FEV1 of 70% to 90% of predicted",
]
EXCLUSION = [
    "Current smoker or more than 10 pack-years of smoking history",
    "Asthma exacerbation requiring systemic corticosteroids within 3 months",
    "Pregnant or breastfeeding",
]
# (name, study day, window before, window after)
VISITS = [
    ("Screening", -14, 0, 0),
    ("Baseline", 1, 0, 0),
    ("Week 4", 29, 3, 3),
    ("Week 8", 57, 3, 3),
    ("Week 12", 85, 3, 3),
    ("Follow-up", 99, 3, 3),
]
# activity -> visits (by index) where it happens
ACTIVITIES = {
    "Informed consent": [0],
    "Eligibility check": [0, 1],
    "Vital signs": [0, 1, 2, 3, 4, 5],
    "Spirometry (FEV1)": [0, 1, 2, 3, 4],
    "Safety labs": [0, 4],
    "Dispense study drug": [1, 2, 3],
    "Adverse event review": [1, 2, 3, 4, 5],
}


async def _seed_design(session: AsyncSession) -> None:
    """Criteria and a Schedule of Activities for the demo study, added once.

    Runs on existing databases too (after the Week 3 migration), but only if the
    demo study has never had any design items, so it never re-adds things a user deleted.
    """
    study = await session.scalar(select(Study).where(Study.acronym == "BREATHE-1"))
    if study is None:
        return
    touched = await session.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(
            AuditLog.study_id == study.id,
            AuditLog.entity_type.in_(["criterion", "encounter", "activity", "schedule"]),
        )
    )
    existing = await session.scalar(
        select(func.count()).select_from(Encounter).where(Encounter.study_id == study.id)
    )
    if touched or existing:
        return

    for category, texts in (
        (CriterionCategory.INCLUSION, INCLUSION),
        (CriterionCategory.EXCLUSION, EXCLUSION),
    ):
        for ordinal, text in enumerate(texts, start=1):
            session.add(
                EligibilityCriterion(
                    study_id=study.id, category=category, ordinal=ordinal, text=text
                )
            )

    encounters = [
        Encounter(study_id=study.id, name=n, day=d, window_before=b, window_after=a)
        for n, d, b, a in VISITS
    ]
    session.add_all(encounters)
    await session.flush()
    for ordinal, (name, visits) in enumerate(ACTIVITIES.items(), start=1):
        activity = Activity(study_id=study.id, name=name, ordinal=ordinal)
        session.add(activity)
        await session.flush()
        session.add_all(
            ScheduledActivity(
                study_id=study.id, encounter_id=encounters[i].id, activity_id=activity.id
            )
            for i in visits
        )
    await session.commit()
