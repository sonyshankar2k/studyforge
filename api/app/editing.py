"""Shared logic for every save: version check, apply changes, audit, broadcast.

Keeping this in one place means arms, objectives and studies all follow the
same rules, the kind of "service boundary" standard a tech lead sets.
"""

from typing import Any

from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog
from app.realtime import hub


def to_dict(obj: Any, fields: list[str]) -> dict[str, Any]:
    return {f: _plain(getattr(obj, f)) for f in fields}


def _plain(value: Any) -> Any:
    # Enums and datetimes -> JSON-friendly values for the audit log
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return getattr(value, "value", value)


def check_version(entity: Any, expected: int, fields: list[str]) -> None:
    """Optimistic concurrency: reject stale writes with 409 + the current state."""
    if entity.version != expected:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "This record was changed by someone else. Review and retry.",
                "current": {**to_dict(entity, fields), "id": entity.id, "version": entity.version},
            },
        )


def apply_update(entity: Any, payload: BaseModel) -> dict[str, dict[str, Any]]:
    """Copy changed fields onto the entity; return {field: {old, new}} for the audit log."""
    changes: dict[str, dict[str, Any]] = {}
    for field, new in payload.model_dump(exclude_unset=True, exclude={"version"}).items():
        old = getattr(entity, field)
        if _plain(old) != _plain(new):
            setattr(entity, field, new)
            changes[field] = {"old": _plain(old), "new": _plain(new)}
    if changes:
        entity.version += 1
    return changes


def record_audit(
    session: AsyncSession,
    *,
    study_id: int,
    entity_type: str,
    entity_id: int,
    action: str,
    changes: dict[str, Any],
    user: str,
) -> None:
    session.add(
        AuditLog(
            study_id=study_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            changes=changes,
            changed_by=user,
        )
    )


async def notify(study_id: int, entity_type: str, entity_id: int, action: str, user: str) -> None:
    await hub.broadcast(
        study_id,
        {
            "type": "changed",
            "entity_type": entity_type,
            "entity_id": entity_id,
            "action": action,
            "changed_by": user,
        },
    )
