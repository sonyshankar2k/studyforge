"""Study design endpoints: eligibility criteria, Schedule of Activities, USDM export.

Criteria      GET/POST /api/studies/{id}/criteria, PATCH/DELETE /api/criteria/{id},
              PUT /api/studies/{id}/criteria/order       (drag-and-drop reorder)
Schedule      GET /api/studies/{id}/schedule              (visits x activities grid)
              POST /api/studies/{id}/encounters, PATCH/DELETE /api/encounters/{id}
              POST /api/studies/{id}/activities, PATCH/DELETE /api/activities/{id}
              PUT /api/studies/{id}/schedule/cells         (tick / untick one cell)
Export        GET /api/studies/{id}/usdm                  (USDM-style JSON)

Same rules as the rest of the API: every edit carries `version` (409 on conflict),
every change is audited, and every change is broadcast to open browsers.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.deps import Id, SessionDep, UserDep, VersionQuery, current_user
from app.editing import apply_update, check_version, notify, record_audit, to_dict
from app.errors import unprocessable
from app.models import (
    Activity,
    CriterionCategory,
    EligibilityCriterion,
    Encounter,
    ScheduledActivity,
    Study,
)
from app.routers.studies import CONFLICT_RESPONSE, _get_or_404, _load_study_detail
from app.schemas import (
    ActivityCreate,
    ActivityOut,
    ActivityUpdate,
    CellOut,
    CellUpdate,
    CriteriaOrder,
    CriterionCreate,
    CriterionOut,
    CriterionUpdate,
    EncounterCreate,
    EncounterOut,
    EncounterUpdate,
    ScheduleCell,
    ScheduleOut,
)

router = APIRouter(prefix="/api", tags=["study design"], dependencies=[Depends(current_user)])

CRITERION_FIELDS = ["category", "ordinal", "text"]
ENCOUNTER_FIELDS = ["name", "day", "window_before", "window_after"]
ACTIVITY_FIELDS = ["name", "ordinal"]


# ============================================================ Eligibility criteria


async def _criteria(session, study_id: Id, category: str | None = None):
    stmt = select(EligibilityCriterion).where(EligibilityCriterion.study_id == study_id)
    if category:
        stmt = stmt.where(EligibilityCriterion.category == category)
    stmt = stmt.order_by(EligibilityCriterion.category.desc(), EligibilityCriterion.ordinal)
    return list((await session.execute(stmt)).scalars().all())


def _renumber(items: list[EligibilityCriterion]) -> None:
    """Keep numbering gapless (I1, I2, I3...) after a delete or a reorder."""
    for position, item in enumerate(items, start=1):
        if item.ordinal != position:
            item.ordinal = position
            item.version += 1


@router.get("/studies/{study_id}/criteria", response_model=list[CriterionOut])
async def list_criteria(study_id: Id, session: SessionDep):
    await _get_or_404(session, Study, study_id)
    return await _criteria(session, study_id)


@router.post(
    "/studies/{study_id}/criteria",
    response_model=CriterionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_criterion(study_id: Id, body: CriterionCreate, session: SessionDep, user: UserDep):
    await _get_or_404(session, Study, study_id)
    last = await session.scalar(
        select(func.max(EligibilityCriterion.ordinal)).where(
            EligibilityCriterion.study_id == study_id,
            EligibilityCriterion.category == body.category,
        )
    )
    criterion = EligibilityCriterion(
        study_id=study_id, category=body.category, ordinal=(last or 0) + 1, text=body.text.strip()
    )
    session.add(criterion)
    await session.flush()
    record_audit(
        session,
        study_id=study_id,
        entity_type="criterion",
        entity_id=criterion.id,
        action="create",
        changes=to_dict(criterion, CRITERION_FIELDS),
        user=user,
    )
    await session.commit()
    await notify(study_id, "criterion", criterion.id, "create", user)
    return criterion


@router.patch("/criteria/{criterion_id}", response_model=CriterionOut, responses=CONFLICT_RESPONSE)
async def update_criterion(
    criterion_id: Id, body: CriterionUpdate, session: SessionDep, user: UserDep
):
    criterion = await _get_or_404(session, EligibilityCriterion, criterion_id)
    check_version(criterion, body.version, CRITERION_FIELDS)
    if body.text is not None:
        body.text = body.text.strip()
    changes = apply_update(criterion, body)
    if changes:
        record_audit(
            session,
            study_id=criterion.study_id,
            entity_type="criterion",
            entity_id=criterion.id,
            action="update",
            changes=changes,
            user=user,
        )
        await session.commit()
        await notify(criterion.study_id, "criterion", criterion.id, "update", user)
    return criterion


@router.delete(
    "/criteria/{criterion_id}", status_code=status.HTTP_204_NO_CONTENT, responses=CONFLICT_RESPONSE
)
async def delete_criterion(
    criterion_id: Id, session: SessionDep, user: UserDep, version: VersionQuery
):
    criterion = await _get_or_404(session, EligibilityCriterion, criterion_id)
    check_version(criterion, version, CRITERION_FIELDS)
    study_id, category = criterion.study_id, criterion.category
    record_audit(
        session,
        study_id=study_id,
        entity_type="criterion",
        entity_id=criterion.id,
        action="delete",
        changes={**to_dict(criterion, CRITERION_FIELDS), "identifier": criterion.identifier},
        user=user,
    )
    await session.delete(criterion)
    await session.flush()
    _renumber(await _criteria(session, study_id, category))
    await session.commit()
    await notify(study_id, "criterion", criterion_id, "delete", user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/studies/{study_id}/criteria/order",
    response_model=list[CriterionOut],
    responses=CONFLICT_RESPONSE,
)
async def reorder_criteria(study_id: Id, body: CriteriaOrder, session: SessionDep, user: UserDep):
    """Set the order of one category. `ids` must be exactly the current criteria in it;
    if someone added or deleted one meanwhile, you get 409 and should reload."""
    await _get_or_404(session, Study, study_id)
    current = await _criteria(session, study_id, body.category)
    if len(body.ids) != len(set(body.ids)) or set(body.ids) != {c.id for c in current}:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The list of criteria changed while you were reordering. Reload and try again.",
        )
    by_id = {c.id: c for c in current}
    before = [c.identifier for c in current]
    ordered = [by_id[i] for i in body.ids]
    _renumber(ordered)
    if [c.id for c in current] != body.ids:
        record_audit(
            session,
            study_id=study_id,
            entity_type="criterion",
            entity_id=0,
            action="reorder",
            changes={
                "category": body.category.value,
                "order": {
                    "old": before,
                    "new": [f"{c.identifier} (was {before[current.index(c)]})" for c in ordered],
                },
            },
            user=user,
        )
        await session.commit()
        await notify(study_id, "criterion", 0, "update", user)
    return await _criteria(session, study_id)


# ============================================================ Schedule of Activities


async def _schedule(session, study_id: Id) -> ScheduleOut:
    encounters = (
        (
            await session.execute(
                select(Encounter)
                .where(Encounter.study_id == study_id)
                .order_by(Encounter.day, Encounter.id)
            )
        )
        .scalars()
        .all()
    )
    activities = (
        (
            await session.execute(
                select(Activity).where(Activity.study_id == study_id).order_by(Activity.ordinal)
            )
        )
        .scalars()
        .all()
    )
    cells = (
        (
            await session.execute(
                select(ScheduledActivity).where(ScheduledActivity.study_id == study_id)
            )
        )
        .scalars()
        .all()
    )
    return ScheduleOut(
        encounters=[EncounterOut.model_validate(e) for e in encounters],
        activities=[ActivityOut.model_validate(a) for a in activities],
        cells=[ScheduleCell(encounter_id=c.encounter_id, activity_id=c.activity_id) for c in cells],
    )


async def _flush_unique(session, message: str) -> None:
    """Flush, turning a unique-name violation into a 422.

    The friendly pre-check (_name_taken) covers the normal case; this covers the rest:
    two people adding the same name at the same moment, or case rules that differ
    between Python and the database (e.g. SQLite only lowercases ASCII).
    """
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise unprocessable(message, "name") from None


async def _name_taken(session, model, study_id: Id, name: str, exclude_id: int | None = None):
    stmt = select(model.id).where(
        model.study_id == study_id, func.lower(model.name) == name.strip().lower()
    )
    if exclude_id is not None:
        stmt = stmt.where(model.id != exclude_id)
    return (await session.execute(stmt.limit(1))).first() is not None


@router.get("/studies/{study_id}/schedule", response_model=ScheduleOut)
async def get_schedule(study_id: Id, session: SessionDep):
    await _get_or_404(session, Study, study_id)
    return await _schedule(session, study_id)


# ---------------- encounters (visits / columns)
@router.post(
    "/studies/{study_id}/encounters",
    response_model=EncounterOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_encounter(study_id: Id, body: EncounterCreate, session: SessionDep, user: UserDep):
    await _get_or_404(session, Study, study_id)
    if await _name_taken(session, Encounter, study_id, body.name):
        raise unprocessable(f'A visit named "{body.name.strip()}" already exists.', "name")
    encounter = Encounter(study_id=study_id, **{**body.model_dump(), "name": body.name.strip()})
    session.add(encounter)
    await _flush_unique(session, f'A visit named "{encounter.name}" already exists.')
    record_audit(
        session,
        study_id=study_id,
        entity_type="encounter",
        entity_id=encounter.id,
        action="create",
        changes=to_dict(encounter, ENCOUNTER_FIELDS),
        user=user,
    )
    await session.commit()
    await notify(study_id, "encounter", encounter.id, "create", user)
    return encounter


@router.patch(
    "/encounters/{encounter_id}", response_model=EncounterOut, responses=CONFLICT_RESPONSE
)
async def update_encounter(
    encounter_id: Id, body: EncounterUpdate, session: SessionDep, user: UserDep
):
    encounter = await _get_or_404(session, Encounter, encounter_id)
    check_version(encounter, body.version, ENCOUNTER_FIELDS)
    if body.name is not None:
        body.name = body.name.strip()
        if await _name_taken(session, Encounter, encounter.study_id, body.name, encounter.id):
            raise unprocessable(f'A visit named "{body.name}" already exists.', "name")
    changes = apply_update(encounter, body)
    if changes:
        await _flush_unique(session, f'A visit named "{encounter.name}" already exists.')
        record_audit(
            session,
            study_id=encounter.study_id,
            entity_type="encounter",
            entity_id=encounter.id,
            action="update",
            changes=changes,
            user=user,
        )
        await session.commit()
        await notify(encounter.study_id, "encounter", encounter.id, "update", user)
    return encounter


@router.delete(
    "/encounters/{encounter_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=CONFLICT_RESPONSE,
)
async def delete_encounter(
    encounter_id: Id, session: SessionDep, user: UserDep, version: VersionQuery
):
    encounter = await _get_or_404(session, Encounter, encounter_id)
    check_version(encounter, version, ENCOUNTER_FIELDS)
    study_id = encounter.study_id
    planned = await session.scalar(
        select(func.count())
        .select_from(ScheduledActivity)
        .where(ScheduledActivity.encounter_id == encounter_id)
    )
    record_audit(
        session,
        study_id=study_id,
        entity_type="encounter",
        entity_id=encounter.id,
        action="delete",
        changes={**to_dict(encounter, ENCOUNTER_FIELDS), "planned_activities_removed": planned},
        user=user,
    )
    await session.execute(
        ScheduledActivity.__table__.delete().where(ScheduledActivity.encounter_id == encounter_id)
    )
    await session.delete(encounter)
    await session.commit()
    await notify(study_id, "encounter", encounter_id, "delete", user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------- activities (rows)
@router.post(
    "/studies/{study_id}/activities",
    response_model=ActivityOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_activity(study_id: Id, body: ActivityCreate, session: SessionDep, user: UserDep):
    await _get_or_404(session, Study, study_id)
    name = body.name.strip()
    if await _name_taken(session, Activity, study_id, name):
        raise unprocessable(f'An activity named "{name}" already exists.', "name")
    last = await session.scalar(
        select(func.max(Activity.ordinal)).where(Activity.study_id == study_id)
    )
    activity = Activity(study_id=study_id, name=name, ordinal=(last or 0) + 1)
    session.add(activity)
    await _flush_unique(session, f'An activity named "{name}" already exists.')
    record_audit(
        session,
        study_id=study_id,
        entity_type="activity",
        entity_id=activity.id,
        action="create",
        changes=to_dict(activity, ACTIVITY_FIELDS),
        user=user,
    )
    await session.commit()
    await notify(study_id, "activity", activity.id, "create", user)
    return activity


@router.patch("/activities/{activity_id}", response_model=ActivityOut, responses=CONFLICT_RESPONSE)
async def update_activity(
    activity_id: Id, body: ActivityUpdate, session: SessionDep, user: UserDep
):
    activity = await _get_or_404(session, Activity, activity_id)
    check_version(activity, body.version, ACTIVITY_FIELDS)
    if body.name is not None:
        body.name = body.name.strip()
        if await _name_taken(session, Activity, activity.study_id, body.name, activity.id):
            raise unprocessable(f'An activity named "{body.name}" already exists.', "name")
    changes = apply_update(activity, body)
    if changes:
        await _flush_unique(session, f'An activity named "{activity.name}" already exists.')
        record_audit(
            session,
            study_id=activity.study_id,
            entity_type="activity",
            entity_id=activity.id,
            action="update",
            changes=changes,
            user=user,
        )
        await session.commit()
        await notify(activity.study_id, "activity", activity.id, "update", user)
    return activity


@router.delete(
    "/activities/{activity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=CONFLICT_RESPONSE,
)
async def delete_activity(
    activity_id: Id, session: SessionDep, user: UserDep, version: VersionQuery
):
    activity = await _get_or_404(session, Activity, activity_id)
    check_version(activity, version, ACTIVITY_FIELDS)
    study_id = activity.study_id
    record_audit(
        session,
        study_id=study_id,
        entity_type="activity",
        entity_id=activity.id,
        action="delete",
        changes=to_dict(activity, ACTIVITY_FIELDS),
        user=user,
    )
    await session.execute(
        ScheduledActivity.__table__.delete().where(ScheduledActivity.activity_id == activity_id)
    )
    await session.delete(activity)
    await session.commit()
    await notify(study_id, "activity", activity_id, "delete", user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------- cells
@router.put("/studies/{study_id}/schedule/cells", response_model=CellOut)
async def set_cell(study_id: Id, body: CellUpdate, session: SessionDep, user: UserDep):
    """Plan or unplan one activity at one visit.

    Idempotent by design: the body says the state you want ("planned": true/false),
    not "toggle". Sending it twice is harmless, and two people ticking the same cell
    can't undo each other by accident, so no version number is needed here.
    """
    encounter = await session.get(Encounter, body.encounter_id)
    activity = await session.get(Activity, body.activity_id)
    if encounter is None or activity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Visit or activity not found")
    if encounter.study_id != study_id or activity.study_id != study_id:
        raise unprocessable("The visit and activity must belong to this study.")

    existing = (
        await session.execute(
            select(ScheduledActivity).where(
                ScheduledActivity.encounter_id == body.encounter_id,
                ScheduledActivity.activity_id == body.activity_id,
            )
        )
    ).scalar_one_or_none()

    changed = False
    if body.planned and existing is None:
        session.add(
            ScheduledActivity(
                study_id=study_id, encounter_id=body.encounter_id, activity_id=body.activity_id
            )
        )
        changed = True
    elif not body.planned and existing is not None:
        await session.delete(existing)
        changed = True

    if changed:
        record_audit(
            session,
            study_id=study_id,
            entity_type="schedule",
            entity_id=activity.id,
            action="update",
            changes={
                f"{activity.name} @ {encounter.name}": {
                    "old": "not planned" if body.planned else "planned",
                    "new": "planned" if body.planned else "not planned",
                }
            },
            user=user,
        )
        await session.commit()
        await notify(study_id, "schedule", activity.id, "update", user)

    return CellOut(**body.model_dump(), changed=changed)


# ============================================================ USDM export

_ARM_TYPE = {
    "experimental": "Experimental Arm",
    "active_comparator": "Active Comparator Arm",
    "placebo": "Placebo Comparator Arm",
}
_LEVEL = {
    "primary": "Primary Objective",
    "secondary": "Secondary Objective",
    "exploratory": "Exploratory Objective",
}


@router.get("/studies/{study_id}/usdm")
async def export_usdm(study_id: Id, session: SessionDep) -> dict[str, Any]:
    """The study design as JSON shaped like the CDISC Unified Study Definitions Model.

    Uses USDM entity and attribute names (StudyDesign, StudyArm, Objective, Endpoint,
    EligibilityCriterion, Encounter, Activity, ScheduleTimeline,
    ScheduledActivityInstance) so it can feed USDM-based tools. It is a practical
    subset, not validated against the official CDISC schema.
    """
    study = await _load_study_detail(session, study_id)
    criteria = await _criteria(session, study_id)
    schedule = await _schedule(session, study_id)

    planned: dict[int, list[int]] = {}
    for cell in schedule.cells:
        planned.setdefault(cell.encounter_id, []).append(cell.activity_id)

    def code(decode: str) -> dict[str, str]:
        return {"decode": decode}

    design = {
        "id": "StudyDesign_1",
        "instanceType": "StudyDesign",
        "name": study.acronym or study.title,
        "studyPhase": code(study.phase),
        "therapeuticAreas": [code(study.therapeutic_area)] if study.therapeutic_area else [],
        "arms": [
            {
                "id": f"StudyArm_{arm.id}",
                "instanceType": "StudyArm",
                "name": arm.name,
                "type": code(_ARM_TYPE.get(arm.arm_type, arm.arm_type)),
                "description": "; ".join(
                    part
                    for part in [
                        arm.description,
                        f"Dose: {arm.dose}" if arm.dose else None,
                        f"Planned enrollment: {arm.planned_size}" if arm.planned_size else None,
                    ]
                    if part
                ),
            }
            for arm in study.arms
        ],
        "objectives": [
            {
                "id": f"Objective_{obj.id}",
                "instanceType": "Objective",
                "text": obj.description,
                "level": code(_LEVEL.get(obj.level, obj.level)),
                "endpoints": [
                    {"id": f"Endpoint_{obj.id}", "instanceType": "Endpoint", "text": obj.endpoint}
                ],
            }
            for obj in study.objectives
        ],
        "eligibilityCriteria": [
            {
                "id": f"EligibilityCriterion_{c.id}",
                "instanceType": "EligibilityCriterion",
                "identifier": c.identifier,
                "category": code(
                    "Inclusion Criteria"
                    if c.category == CriterionCategory.INCLUSION
                    else "Exclusion Criteria"
                ),
                "text": c.text,
            }
            for c in criteria
        ],
        "encounters": [
            {
                "id": f"Encounter_{e.id}",
                "instanceType": "Encounter",
                "name": e.name,
                "label": e.name,
                "description": f"Study day {e.day} "
                f"(window -{e.window_before}/+{e.window_after} days)",
            }
            for e in schedule.encounters
        ],
        "activities": [
            {"id": f"Activity_{a.id}", "instanceType": "Activity", "name": a.name, "label": a.name}
            for a in schedule.activities
        ],
        "scheduleTimelines": [
            {
                "id": "ScheduleTimeline_1",
                "instanceType": "ScheduleTimeline",
                "name": "Main Timeline",
                "mainTimeline": True,
                "instances": [
                    {
                        "id": f"ScheduledActivityInstance_{e.id}",
                        "instanceType": "ScheduledActivityInstance",
                        "encounterId": f"Encounter_{e.id}",
                        "activityIds": [f"Activity_{a}" for a in sorted(planned.get(e.id, []))],
                    }
                    for e in schedule.encounters
                ],
            }
        ],
    }
    return {
        "usdmVersion": "3.0.0",
        "systemName": "StudyForge",
        "note": "USDM-shaped subset; not validated against the CDISC schema",
        "study": {
            "id": f"Study_{study.id}",
            "instanceType": "Study",
            "name": study.acronym or study.title,
            "versions": [
                {
                    "id": "StudyVersion_1",
                    "instanceType": "StudyVersion",
                    "versionIdentifier": str(study.version),
                    "titles": [{"text": study.title, "type": code("Official Study Title")}],
                    "studyDesigns": [design],
                }
            ],
        },
    }
