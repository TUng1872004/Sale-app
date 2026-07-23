from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, col, select

from app.core.schema.models import Role, Sale, SaleStatus
from app.repo.scope import DataScope
from app.repo.types import Page


def get_sale(session: Session, scope: DataScope, sale_id: str) -> Sale | None:
    statement = select(Sale).where(Sale.id == sale_id)
    if not scope.global_access:
        statement = statement.where(col(Sale.id).in_(scope.owner_ids))
    return session.exec(statement).first()


def get_sale_by_email(session: Session, email: str) -> Sale | None:
    return session.exec(select(Sale).where(Sale.email == email)).first()


def find_sales(
    session: Session,
    scope: DataScope,
    *,
    role: Role | None = None,
    status: SaleStatus | None = None,
    mgr_id: str | None = None,
    page: int = 1,
    per_page: int = 25,
) -> Page[Sale]:
    _validate_page(page, per_page)
    conditions: list[ColumnElement[bool]] = []
    if not scope.global_access:
        conditions.append(col(Sale.id).in_(scope.owner_ids))
    if role is not None:
        conditions.append(col(Sale.role) == role)
    if status is not None:
        conditions.append(col(Sale.status) == status)
    if mgr_id is not None:
        conditions.append(col(Sale.mgr_id) == mgr_id)

    total = int(session.exec(select(func.count()).select_from(Sale).where(*conditions)).one())
    offset = (page - 1) * per_page
    statement = select(Sale).where(*conditions).order_by(Sale.name).offset(offset).limit(per_page)
    return Page(items=list(session.exec(statement)), total=total, page=page, per_page=per_page)


def team_member_ids(session: Session, manager_id: str, *, include_manager: bool = True) -> list[str]:
    statement = select(Sale.id).where(Sale.mgr_id == manager_id, Sale.role == Role.SALER).order_by(Sale.name)
    ids = list(session.exec(statement))
    return [manager_id, *ids] if include_manager else ids


def _validate_page(page: int, per_page: int) -> None:
    if page < 1:
        raise ValueError("page must be at least 1")
    if not 1 <= per_page <= 100:
        raise ValueError("per_page must be between 1 and 100")
