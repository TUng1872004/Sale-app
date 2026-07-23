from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, col, select

from app.core.schema.models import Agency
from app.repo.scope import DataScope
from app.repo.types import Page


def get_agency(session: Session, scope: DataScope, agency_id: str) -> Agency | None:
    statement = select(Agency).where(Agency.id == agency_id)
    if not scope.global_access:
        statement = statement.where(col(Agency.owner_id).in_(scope.owner_ids))
    return session.exec(statement).first()


def find_agencies(
    session: Session,
    scope: DataScope,
    *,
    unassigned: bool = False,
    query: str | None = None,
    sector: str | None = None,
    page: int = 1,
    per_page: int = 25,
) -> Page[Agency]:
    _validate_page(page, per_page)
    conditions: list[ColumnElement[bool]] = []
    if unassigned:
        if not scope.global_access:
            return Page(items=[], total=0, page=page, per_page=per_page)
        conditions.append(col(Agency.owner_id).is_(None))
    elif not scope.global_access:
        conditions.append(col(Agency.owner_id).in_(scope.owner_ids))
    if query:
        conditions.append(col(Agency.name).ilike(f"%{query.strip()}%"))
    if sector:
        conditions.append(col(Agency.sector) == sector)

    total = int(session.exec(select(func.count()).select_from(Agency).where(*conditions)).one())
    offset = (page - 1) * per_page
    statement = select(Agency).where(*conditions).order_by(Agency.name).offset(offset).limit(per_page)
    return Page(items=list(session.exec(statement)), total=total, page=page, per_page=per_page)


def owned_agency_count(session: Session, scope: DataScope, sale_id: str) -> int:
    if not scope.global_access and sale_id not in scope.owner_ids:
        return 0
    statement = select(func.count()).select_from(Agency).where(Agency.owner_id == sale_id)
    return int(session.exec(statement).one())


def _validate_page(page: int, per_page: int) -> None:
    if page < 1:
        raise ValueError("page must be at least 1")
    if not 1 <= per_page <= 100:
        raise ValueError("per_page must be between 1 and 100")
