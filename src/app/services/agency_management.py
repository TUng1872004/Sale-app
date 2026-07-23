from __future__ import annotations

from sqlmodel import Session

from app.core.schema.models import Agency, Role, Sale, utcnow
from app.domain.result import Err, Ok, Result
from app.repo.agency import get_agency
from app.repo.scope import DataScope


def create(
    session: Session,
    actor: Sale,
    code: str,
    name: str,
    sector: str | None,
    loc: str | None,
) -> Result[Agency]:
    if actor.role != Role.DIRECTOR:
        return Err("ROLE_FORBIDDEN", "Chỉ Director được tạo Agency.")
    agency = Agency(code=code.strip(), name=name.strip(), sector=sector or None, loc=loc or None)
    session.add(agency)
    session.commit()
    return Ok(agency)


def update(
    session: Session,
    scope: DataScope,
    actor: Sale,
    agency_id: str,
    name: str,
    sector: str | None,
    loc: str | None,
) -> Result[Agency]:
    if actor.role not in {Role.MANAGER, Role.DIRECTOR}:
        return Err("ROLE_FORBIDDEN", "Không được cập nhật Agency.")
    agency = get_agency(session, scope, agency_id)
    if agency is None:
        return Err("AGENCY_NOT_FOUND", "Agency ngoài phạm vi.")
    agency.name = name.strip()
    agency.sector = sector or None
    agency.loc = loc or None
    agency.update_at = utcnow()
    session.add(agency)
    session.commit()
    return Ok(agency)
