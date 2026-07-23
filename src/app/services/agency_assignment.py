from __future__ import annotations

from sqlmodel import Session, col, select

from app.core.schema.models import AssignHist, OPEN_STAGES, Oppo, Role, Sale, utcnow
from app.domain.result import Err, Ok, Result
from app.repo.agency import get_agency
from app.repo.sale import get_sale
from app.repo.scope import DataScope


def assign(
    session: Session,
    scope: DataScope,
    actor: Sale,
    agency_id: str,
    owner_id: str,
    reason: str | None,
) -> Result[AssignHist]:
    if actor.role not in {Role.MANAGER, Role.DIRECTOR}:
        return Err("ROLE_FORBIDDEN", "Chỉ Manager hoặc Director được phân công Agency.")
    agency = get_agency(session, scope, agency_id)
    target = get_sale(session, scope, owner_id)
    if agency is None or target is None or target.role != Role.SALER:
        return Err("ASSIGNMENT_NOT_FOUND", "Agency hoặc Saler ngoài phạm vi.")
    previous = agency.owner_id
    agency.owner_id = target.id
    agency.update_at = utcnow()
    history = AssignHist(agency_id=agency.id, prev_owner_id=previous, new_owner_id=target.id, reason=reason)
    session.add(agency)
    session.add(history)
    for deal in session.exec(select(Oppo).where(Oppo.agency_id == agency.id, col(Oppo.stage).in_(OPEN_STAGES))):
        deal.owner_id = target.id
        deal.update_at = utcnow()
        session.add(deal)
    session.commit()
    return Ok(history)
