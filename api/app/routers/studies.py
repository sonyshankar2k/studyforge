"""REST endpoints for studies, arms, objectives and the audit trail."""

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.deps import SessionDep, UserDep
from app.editing import apply_update, check_version, notify, record_audit, to_dict
from app.models import Arm, ArmType, AuditLog, Objective, Study
from app.schemas import (
    ArmCreate,
    ArmOut,
    ArmUpdate,
    AuditEntryOut,
    ObjectiveCreate,
    ObjectiveOut,
    ObjectiveUpdate,
    StudyCreate,
    StudyDetail,
    StudySummary,
    StudyUpdate,
)

router = APIRouter(prefix="/api", tags=["studies"])

STUDY_FIELDS = ["title", "acronym", "phase", "therapeutic_area", "status"]
ARM_FIELDS = ["name", "arm_type", "description", "planned_size", "dose"]
OBJECTIVE_FIELDS = ["level", "description", "endpoint"]

CONFLICT_RESPONSE = {409: {"description": "Version conflict; body contains the current record"}}


async def _get_or_404(session, model, entity_id: int):
    entity = await session.get(model, entity_id)
    if entity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} {entity_id} not found")
    return entity


async def _load_study_detail(session, study_id: int) -> Study:
    stmt = (
        select(Study)
        .where(Study.id == study_id)
        .options(selectinload(Study.arms), selectinload(Study.objectives))
        .execution_options(populate_existing=True)
    )
    study = (await session.execute(stmt)).scalar_one_or_none()
    if study is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Study {study_id} not found")
    return study


# ---------------- Studies ----------------
@router.get("/studies", response_model=list[StudySummary])
async def list_studies(session: SessionDep):
    result = await session.execute(select(Study).order_by(Study.updated_at.desc()))
    return result.scalars().all()


async def _acronym_taken(session, acronym: str, exclude_id: int | None = None) -> bool:
    stmt = select(Study.id).where(func.lower(Study.acronym) == acronym.strip().lower())
    if exclude_id is not None:
        stmt = stmt.where(Study.id != exclude_id)
    return (await session.execute(stmt.limit(1))).first() is not None


@router.get("/studies/acronym-available")
async def acronym_available(
    session: SessionDep, acronym: str = Query(min_length=1), exclude_id: int | None = None
) -> dict[str, bool]:
    """Backs the Angular async validator on the acronym field."""
    return {"available": not await _acronym_taken(session, acronym, exclude_id)}


@router.post("/studies", response_model=StudyDetail, status_code=status.HTTP_201_CREATED)
async def create_study(body: StudyCreate, session: SessionDep, user: UserDep):
    if body.acronym and await _acronym_taken(session, body.acronym):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "acronym is already in use")
    study = Study(**body.model_dump())
    session.add(study)
    await session.flush()
    record_audit(
        session,
        study_id=study.id,
        entity_type="study",
        entity_id=study.id,
        action="create",
        changes=to_dict(study, STUDY_FIELDS),
        user=user,
    )
    await session.commit()
    return await _load_study_detail(session, study.id)


@router.get("/studies/{study_id}", response_model=StudyDetail)
async def get_study(study_id: int, session: SessionDep):
    return await _load_study_detail(session, study_id)


@router.patch("/studies/{study_id}", response_model=StudyDetail, responses=CONFLICT_RESPONSE)
async def update_study(study_id: int, body: StudyUpdate, session: SessionDep, user: UserDep):
    study = await _get_or_404(session, Study, study_id)
    check_version(study, body.version, STUDY_FIELDS)
    if body.acronym and await _acronym_taken(session, body.acronym, exclude_id=study_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "acronym is already in use")
    changes = apply_update(study, body)
    if changes:
        record_audit(
            session,
            study_id=study.id,
            entity_type="study",
            entity_id=study.id,
            action="update",
            changes=changes,
            user=user,
        )
        await session.commit()
        await notify(study.id, "study", study.id, "update", user)
    return await _load_study_detail(session, study_id)


@router.get("/studies/{study_id}/audit", response_model=list[AuditEntryOut])
async def get_audit_trail(study_id: int, session: SessionDep, limit: int = Query(100, le=500)):
    stmt = (
        select(AuditLog)
        .where(AuditLog.study_id == study_id)
        .order_by(AuditLog.id.desc())
        .limit(limit)
    )
    return (await session.execute(stmt)).scalars().all()


# ---------------- Arms ----------------
@router.post("/studies/{study_id}/arms", response_model=ArmOut, status_code=status.HTTP_201_CREATED)
async def create_arm(study_id: int, body: ArmCreate, session: SessionDep, user: UserDep):
    await _get_or_404(session, Study, study_id)
    arm = Arm(study_id=study_id, **body.model_dump())
    session.add(arm)
    await session.flush()
    record_audit(
        session,
        study_id=study_id,
        entity_type="arm",
        entity_id=arm.id,
        action="create",
        changes=to_dict(arm, ARM_FIELDS),
        user=user,
    )
    await session.commit()
    await notify(study_id, "arm", arm.id, "create", user)
    return arm


@router.patch("/arms/{arm_id}", response_model=ArmOut, responses=CONFLICT_RESPONSE)
async def update_arm(arm_id: int, body: ArmUpdate, session: SessionDep, user: UserDep):
    arm = await _get_or_404(session, Arm, arm_id)
    check_version(arm, body.version, ARM_FIELDS)

    # Conditional rule must hold on the *merged* record, not just the patch.
    merged_type = body.arm_type or arm.arm_type
    merged_dose = body.dose if "dose" in body.model_fields_set else arm.dose
    if merged_type == ArmType.EXPERIMENTAL and not merged_dose:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "dose is required for experimental arms"
        )

    changes = apply_update(arm, body)
    if changes:
        record_audit(
            session,
            study_id=arm.study_id,
            entity_type="arm",
            entity_id=arm.id,
            action="update",
            changes=changes,
            user=user,
        )
        await session.commit()
        await notify(arm.study_id, "arm", arm.id, "update", user)
    return arm


@router.delete(
    "/arms/{arm_id}", status_code=status.HTTP_204_NO_CONTENT, responses=CONFLICT_RESPONSE
)
async def delete_arm(arm_id: int, session: SessionDep, user: UserDep, version: int = Query()):
    arm = await _get_or_404(session, Arm, arm_id)
    check_version(arm, version, ARM_FIELDS)
    study_id = arm.study_id
    # The audit entry keeps the full deleted record, so "undo" can re-create it.
    record_audit(
        session,
        study_id=study_id,
        entity_type="arm",
        entity_id=arm.id,
        action="delete",
        changes=to_dict(arm, ARM_FIELDS),
        user=user,
    )
    await session.delete(arm)
    await session.commit()
    await notify(study_id, "arm", arm_id, "delete", user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------- Objectives ----------------
@router.post(
    "/studies/{study_id}/objectives",
    response_model=ObjectiveOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_objective(
    study_id: int, body: ObjectiveCreate, session: SessionDep, user: UserDep
):
    await _get_or_404(session, Study, study_id)
    obj = Objective(study_id=study_id, **body.model_dump())
    session.add(obj)
    await session.flush()
    record_audit(
        session,
        study_id=study_id,
        entity_type="objective",
        entity_id=obj.id,
        action="create",
        changes=to_dict(obj, OBJECTIVE_FIELDS),
        user=user,
    )
    await session.commit()
    await notify(study_id, "objective", obj.id, "create", user)
    return obj


@router.patch(
    "/objectives/{objective_id}", response_model=ObjectiveOut, responses=CONFLICT_RESPONSE
)
async def update_objective(
    objective_id: int, body: ObjectiveUpdate, session: SessionDep, user: UserDep
):
    obj = await _get_or_404(session, Objective, objective_id)
    check_version(obj, body.version, OBJECTIVE_FIELDS)
    changes = apply_update(obj, body)
    if changes:
        record_audit(
            session,
            study_id=obj.study_id,
            entity_type="objective",
            entity_id=obj.id,
            action="update",
            changes=changes,
            user=user,
        )
        await session.commit()
        await notify(obj.study_id, "objective", obj.id, "update", user)
    return obj


@router.delete(
    "/objectives/{objective_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=CONFLICT_RESPONSE,
)
async def delete_objective(
    objective_id: int, session: SessionDep, user: UserDep, version: int = Query()
):
    obj = await _get_or_404(session, Objective, objective_id)
    check_version(obj, version, OBJECTIVE_FIELDS)
    study_id = obj.study_id
    record_audit(
        session,
        study_id=study_id,
        entity_type="objective",
        entity_id=obj.id,
        action="delete",
        changes=to_dict(obj, OBJECTIVE_FIELDS),
        user=user,
    )
    await session.delete(obj)
    await session.commit()
    await notify(study_id, "objective", objective_id, "delete", user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
