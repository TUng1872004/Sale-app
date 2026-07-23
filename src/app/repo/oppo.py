from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, col, select

from app.core.schema.models import OPEN_STAGES, Oppo, Stage
from app.repo.scope import DataScope
from app.repo.types import Page


def get_oppo(session: Session, scope: DataScope, oppo_id: str) -> Oppo | None:
    statement = select(Oppo).where(Oppo.id == oppo_id)
    if not scope.global_access:
        statement = statement.where(col(Oppo.owner_id).in_(scope.owner_ids))
    return session.exec(statement).first()


def get_oppo_many(session: Session, scope: DataScope, oppo_ids: list[str]) -> list[Oppo]:
    if not oppo_ids:
        return []
    statement = select(Oppo).where(col(Oppo.id).in_(oppo_ids))
    if not scope.global_access:
        statement = statement.where(col(Oppo.owner_id).in_(scope.owner_ids))
    found = {deal.id: deal for deal in session.exec(statement)}
    return [found[oppo_id] for oppo_id in oppo_ids if oppo_id in found]


def find_oppo(
    session: Session,
    scope: DataScope,
    *,
    agency_id: str | None = None,
    stages: Sequence[Stage] | None = None,
    query: str | None = None,
    page: int = 1,
    per_page: int = 25,
) -> Page[Oppo]:
    _validate_page(page, per_page)
    conditions: list[ColumnElement[bool]] = []
    if not scope.global_access:
        conditions.append(col(Oppo.owner_id).in_(scope.owner_ids))
    if agency_id is not None:
        conditions.append(col(Oppo.agency_id) == agency_id)
    if stages is not None:
        conditions.append(col(Oppo.stage).in_(stages))
    if query:
        conditions.append(col(Oppo.title).ilike(f"%{query.strip()}%"))

    total = int(session.exec(select(func.count()).select_from(Oppo).where(*conditions)).one())
    offset = (page - 1) * per_page
    statement = (
        select(Oppo)
        .where(*conditions)
        .order_by(col(Oppo.open_at).desc(), Oppo.id)
        .offset(offset)
        .limit(per_page)
    )
    return Page(items=list(session.exec(statement)), total=total, page=page, per_page=per_page)


def owned_open_oppo_count(session: Session, scope: DataScope, sale_id: str) -> int:
    if not scope.global_access and sale_id not in scope.owner_ids:
        return 0
    statement = select(func.count()).select_from(Oppo).where(Oppo.owner_id == sale_id, col(Oppo.stage).in_(OPEN_STAGES))
    return int(session.exec(statement).one())


def _validate_page(page: int, per_page: int) -> None:
    if page < 1:
        raise ValueError("page must be at least 1")
    if not 1 <= per_page <= 100:
        raise ValueError("per_page must be between 1 and 100")
