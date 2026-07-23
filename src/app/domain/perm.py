## one function per Cannot row in the role table. scope = write authority + one level down.
from app.domain.result import Err, Ok, Result
from app.core.schema.models import Role

_FORBIDDEN = Err("FORBIDDEN", "Bạn không có quyền thực hiện thao tác này.")


def can_view_oppo(
    actor: dict,
    oppo_owner_id: str,
    oppo_owner_mgr_id: str | None = None,
) -> Result[None]:
    role = actor["role"]
    if role == Role.DIRECTOR:
        return Ok(None)
    if role == Role.SALER:
        return Ok(None) if actor["id"] == oppo_owner_id else _FORBIDDEN
    if role == Role.MANAGER:
        if actor["id"] == oppo_owner_id:
            return Ok(None)
        if oppo_owner_mgr_id == actor["id"]:
            return Ok(None)
        return _FORBIDDEN
    return _FORBIDDEN


def can_reassign_in_team(actor: dict, mgr_id_of_target_agency_owner: str | None) -> Result[None]:
    role = actor["role"]
    if role == Role.DIRECTOR:
        return Ok(None)
    if role == Role.MANAGER and mgr_id_of_target_agency_owner == actor["id"]:
        return Ok(None)
    return _FORBIDDEN


def can_cross_team_reassign(actor: dict) -> Result[None]:
    return Ok(None) if actor["role"] == Role.DIRECTOR else _FORBIDDEN


def can_deactivate_target(actor: dict, target: dict) -> Result[None]:
    role = actor["role"]
    if role == Role.DIRECTOR:
        return Ok(None)
    if role == Role.MANAGER and target.get("mgr_id") == actor["id"]:
        return Ok(None)
    return _FORBIDDEN


def can_export_global(actor: dict) -> Result[None]:
    return Ok(None) if actor["role"] == Role.DIRECTOR else _FORBIDDEN
