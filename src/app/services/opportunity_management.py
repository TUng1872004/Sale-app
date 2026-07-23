from __future__ import annotations

from datetime import datetime

from sqlmodel import Session

from app.core.schema.models import OPEN_STAGES, Oppo, Role, Sale, Stage, utcnow
from app.domain.result import Err, Ok, Result
from app.repo.agency import get_agency
from app.repo.log import opportunity_log_count
from app.repo.oppo import get_oppo
from app.repo.scope import DataScope


def create(
    session: Session,
    scope: DataScope,
    actor: Sale,
    title: str,
    agency_id: str,
    value: float,
    product: str | None,
    due_at: str | None,
) -> Result[Oppo]:
    agency = get_agency(session, scope, agency_id)
    if agency is None:
        return Err("AGENCY_NOT_FOUND", "Agency ngoài phạm vi.")
    deal = Oppo(
        title=title.strip(),
        prod=product or None,
        agency_id=agency.id,
        owner_id=actor.id,
        value=value,
        open_at=utcnow(),
        due_at=datetime.fromisoformat(due_at) if due_at else None,
    )
    session.add(deal)
    session.commit()
    return Ok(deal)


def delete(
    session: Session,
    scope: DataScope,
    actor: Sale,
    oppo_id: str,
) -> Result[str]:
    if actor.role != Role.DIRECTOR:
        return Err("ROLE_FORBIDDEN", "Chỉ Director được xóa Opportunity.")
    deal = get_oppo(session, scope, oppo_id)
    if deal is None:
        return Err("OPPORTUNITY_NOT_FOUND", "Opportunity ngoài phạm vi.")
    if deal.stage not in OPEN_STAGES:
        return Err("HISTORY_PROTECTED", "Không thể xóa Opportunity đã đóng.")
    if opportunity_log_count(session, scope, deal.id) > 0:
        deal.stage = Stage.CLOSED
        deal.close_at = utcnow()
        deal.update_at = utcnow()
        session.add(deal)
        session.commit()
        return Ok("closed")
    session.delete(deal)
    session.commit()
    return Ok("deleted")
