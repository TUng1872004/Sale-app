from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, col, select

from app.core.schema.models import ManagerLog, SalerLog
from app.repo.scope import DataScope


def get_manager_log(session: Session, scope: DataScope, log_id: str) -> ManagerLog | None:
    statement = select(ManagerLog).where(ManagerLog.id == log_id)
    if not scope.global_access:
        statement = statement.where(col(ManagerLog.actor_id).in_(scope.owner_ids))
    return session.exec(statement).first()


def get_saler_log(session: Session, scope: DataScope, log_id: str) -> SalerLog | None:
    statement = select(SalerLog).where(SalerLog.id == log_id)
    if not scope.global_access:
        statement = statement.where(col(SalerLog.actor_id).in_(scope.owner_ids))
    return session.exec(statement).first()


def find_logs(
    session: Session,
    scope: DataScope,
    query: str | None = None,
    *,
    limit: int = 100,
) -> tuple[list[ManagerLog], list[SalerLog]]:
    manager_stmt = select(ManagerLog)
    saler_stmt = select(SalerLog)
    if not scope.global_access:
        manager_stmt = manager_stmt.where(col(ManagerLog.actor_id).in_(scope.owner_ids))
        saler_stmt = saler_stmt.where(col(SalerLog.actor_id).in_(scope.owner_ids))
    if query:
        manager_stmt = manager_stmt.where(col(ManagerLog.summary).ilike(f"%{query.strip()}%"))
        saler_stmt = saler_stmt.where(col(SalerLog.summary).ilike(f"%{query.strip()}%"))
    manager_logs = list(session.exec(manager_stmt.order_by(col(ManagerLog.at).desc()).limit(limit)))
    saler_logs = list(session.exec(saler_stmt.order_by(col(SalerLog.at).desc()).limit(limit)))
    return manager_logs, saler_logs


def opportunity_log_count(session: Session, scope: DataScope, oppo_id: str) -> int:
    manager_conditions: list[ColumnElement[bool]] = [col(ManagerLog.oppo_id) == oppo_id]
    saler_conditions: list[ColumnElement[bool]] = [col(SalerLog.oppo_id) == oppo_id]
    if not scope.global_access:
        manager_conditions.append(col(ManagerLog.actor_id).in_(scope.owner_ids))
        saler_conditions.append(col(SalerLog.actor_id).in_(scope.owner_ids))
    manager_count = session.exec(select(func.count()).select_from(ManagerLog).where(*manager_conditions)).one()
    saler_count = session.exec(select(func.count()).select_from(SalerLog).where(*saler_conditions)).one()
    return int(manager_count) + int(saler_count)
