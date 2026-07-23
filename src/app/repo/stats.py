from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import case, func, or_
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, col, select

from app.domain.pipeline import STALE_THRESHOLD_DAYS
from app.core.schema.models import Agency, LossReason, OPEN_STAGES, Oppo, Role, Sale, Stage
from app.repo.scope import DataScope


class DashboardKpis(BaseModel):
    pipeline_value: float
    won_revenue: float
    win_rate: float | None
    unassigned_agency_count: int
    stale_oppo_count: int


class StageSummary(BaseModel):
    stage: Stage
    count: int
    value: float


class LossSummary(BaseModel):
    reason: LossReason
    count: int


class RepWorkload(BaseModel):
    sale_id: str
    sale_name: str
    agency_count: int
    open_oppo_count: int
    open_pipeline_value: float
    win_rate: float | None
    stale_oppo_count: int


class MonthlyRevenue(BaseModel):
    month: str
    revenue: float
    ema: float | None = None


class TeamRank(BaseModel):
    manager_id: str
    manager_name: str
    latest_month: str
    revenue: float
    prior_ema: float
    delta: float


def dashboard_kpis(session: Session, scope: DataScope, *, now: datetime | None = None) -> DashboardKpis:
    scope_conditions = _oppo_scope(scope)
    pipeline = _sum_value(session, [*scope_conditions, col(Oppo.stage).in_(OPEN_STAGES)])
    won_revenue = _sum_value(session, [*scope_conditions, col(Oppo.stage) == Stage.WON])
    won = _count_oppo(session, [*scope_conditions, col(Oppo.stage) == Stage.WON])
    lost = _count_oppo(session, [*scope_conditions, col(Oppo.stage) == Stage.LOST])
    stale = _count_oppo(session, [*scope_conditions, _stale_condition(now or datetime.now())])
    unassigned = 0
    if scope.global_access:
        statement = select(func.count()).select_from(Agency).where(col(Agency.owner_id).is_(None))
        unassigned = int(session.exec(statement).one())
    return DashboardKpis(
        pipeline_value=pipeline,
        won_revenue=won_revenue,
        win_rate=_win_rate(won, lost),
        unassigned_agency_count=unassigned,
        stale_oppo_count=stale,
    )


def stage_summaries(session: Session, scope: DataScope) -> list[StageSummary]:
    statement = (
        select(col(Oppo.stage), func.count(col(Oppo.id)), func.coalesce(func.sum(col(Oppo.value)), 0.0))
        .where(*_oppo_scope(scope))
        .group_by(Oppo.stage)
    )
    found = {stage: (int(count), float(value)) for stage, count, value in session.exec(statement)}
    return [StageSummary(stage=stage, count=found.get(stage, (0, 0.0))[0], value=found.get(stage, (0, 0.0))[1]) for stage in Stage]


def loss_summaries(session: Session, scope: DataScope) -> list[LossSummary]:
    statement = (
        select(col(Oppo.loss_reason), func.count(col(Oppo.id)))
        .where(*_oppo_scope(scope), Oppo.stage == Stage.LOST, col(Oppo.loss_reason).is_not(None))
        .group_by(Oppo.loss_reason)
        .order_by(func.count(col(Oppo.id)).desc(), col(Oppo.loss_reason))
    )
    return [LossSummary(reason=LossReason(reason), count=int(count)) for reason, count in session.exec(statement) if reason is not None]


def rep_workload(session: Session, scope: DataScope, *, now: datetime | None = None) -> list[RepWorkload]:
    sale_statement = select(Sale).where(Sale.role == Role.SALER)
    if not scope.global_access:
        sale_statement = sale_statement.where(col(Sale.id).in_(scope.owner_ids))
    sales = list(session.exec(sale_statement))

    agency_statement = select(col(Agency.owner_id), func.count(col(Agency.id))).where(col(Agency.owner_id).is_not(None))
    if not scope.global_access:
        agency_statement = agency_statement.where(col(Agency.owner_id).in_(scope.owner_ids))
    agency_statement = agency_statement.group_by(Agency.owner_id)
    agency_counts = {owner_id: int(count) for owner_id, count in session.exec(agency_statement)}

    open_case = case((col(Oppo.stage).in_(OPEN_STAGES), 1), else_=0)
    pipeline_case = case((col(Oppo.stage).in_(OPEN_STAGES), Oppo.value), else_=0.0)
    stale_case = case((_stale_condition(now or datetime.now()), 1), else_=0)
    open_statement = select(
        col(Oppo.owner_id),
        func.sum(open_case),
        func.sum(pipeline_case),
        func.sum(stale_case),
    )
    if not scope.global_access:
        open_statement = open_statement.where(col(Oppo.owner_id).in_(scope.owner_ids))
    open_statement = open_statement.group_by(Oppo.owner_id)
    open_stats = {owner_id: values for owner_id, *values in session.exec(open_statement)}

    won_case = case((col(Oppo.stage) == Stage.WON, 1), else_=0)
    lost_case = case((col(Oppo.stage) == Stage.LOST, 1), else_=0)
    closed_statement = select(col(Oppo.owner_id), func.sum(won_case), func.sum(lost_case))
    if not scope.global_access:
        closed_statement = closed_statement.where(col(Oppo.owner_id).in_(scope.owner_ids))
    closed_statement = closed_statement.group_by(Oppo.owner_id)
    closed_stats = {owner_id: values for owner_id, *values in session.exec(closed_statement)}

    result: list[RepWorkload] = []
    for sale in sales:
        open_count, pipeline, stale = open_stats.get(sale.id, [0, 0.0, 0])
        won, lost = closed_stats.get(sale.id, [0, 0])
        result.append(
            RepWorkload(
                sale_id=sale.id,
                sale_name=sale.name,
                agency_count=agency_counts.get(sale.id, 0),
                open_oppo_count=int(open_count or 0),
                open_pipeline_value=float(pipeline or 0.0),
                win_rate=_win_rate(int(won or 0), int(lost or 0)),
                stale_oppo_count=int(stale or 0),
            )
        )
    return sorted(result, key=lambda row: (-row.open_pipeline_value, row.sale_name))


def monthly_revenue(
    session: Session,
    scope: DataScope,
    *,
    ema_months: int = 3,
    now: datetime | None = None,
) -> list[MonthlyRevenue]:
    current = now or datetime.now()
    completed_cutoff = datetime(current.year, current.month, 1)
    month = func.strftime("%Y-%m", Oppo.close_at)
    statement = (
        select(month, func.coalesce(func.sum(Oppo.value), 0.0))
        .where(
            *_oppo_scope(scope),
            Oppo.stage == Stage.WON,
            col(Oppo.close_at).is_not(None),
            col(Oppo.close_at) < completed_cutoff,
        )
        .group_by(month)
        .order_by(month)
    )
    rows = [MonthlyRevenue(month=str(key), revenue=float(value)) for key, value in session.exec(statement)]
    alpha = 2 / (ema_months + 1)
    ema: float | None = None
    for row in rows:
        row.ema = ema
        ema = row.revenue if ema is None else alpha * row.revenue + (1 - alpha) * ema
    return rows


def team_rankings(session: Session, scope: DataScope, *, now: datetime | None = None) -> list[TeamRank]:
    current = now or datetime.now()
    current_start = datetime(current.year, current.month, 1)
    latest_statement = select(func.max(Oppo.close_at)).where(
        *_oppo_scope(scope),
        Oppo.stage == Stage.WON,
        col(Oppo.close_at) < current_start,
    )
    latest_close = session.exec(latest_statement).one()
    latest_start = (
        datetime(latest_close.year, latest_close.month, 1)
        if latest_close is not None
        else _shift_month(current_start, -1)
    )
    history_start = _shift_month(latest_start, -3)
    managers_statement = select(Sale).where(Sale.role == Role.MANAGER)
    if not scope.global_access:
        managers_statement = managers_statement.where(col(Sale.id).in_(scope.owner_ids))
    managers = list(session.exec(managers_statement))
    result: list[TeamRank] = []
    for manager in managers:
        owner_ids = [manager.id, *list(session.exec(select(Sale.id).where(Sale.mgr_id == manager.id)))]
        month = func.strftime("%Y-%m", Oppo.close_at)
        statement = (
            select(month, func.coalesce(func.sum(Oppo.value), 0.0))
            .where(
                col(Oppo.owner_id).in_(owner_ids),
                Oppo.stage == Stage.WON,
                col(Oppo.close_at) >= history_start,
                col(Oppo.close_at) < current_start,
            )
            .group_by(month)
        )
        found = {str(key): float(value) for key, value in session.exec(statement)}
        prior_values = [found.get(_shift_month(latest_start, -offset).strftime("%Y-%m"), 0.0) for offset in (3, 2, 1)]
        ema = prior_values[0]
        for value in prior_values[1:]:
            ema = 0.5 * value + 0.5 * ema
        revenue = found.get(latest_start.strftime("%Y-%m"), 0.0)
        result.append(
            TeamRank(
                manager_id=manager.id,
                manager_name=manager.name,
                latest_month=latest_start.strftime("%Y-%m"),
                revenue=revenue,
                prior_ema=ema,
                delta=revenue - ema,
            )
        )
    return sorted(result, key=lambda row: (-row.delta, -row.revenue, row.manager_name))


def _oppo_scope(scope: DataScope) -> list[ColumnElement[bool]]:
    if scope.global_access:
        return []
    return [col(Oppo.owner_id).in_(scope.owner_ids)]


def _sum_value(session: Session, conditions: list[ColumnElement[bool]]) -> float:
    statement = select(func.coalesce(func.sum(col(Oppo.value)), 0.0)).where(*conditions)
    return float(session.exec(statement).one())


def _count_oppo(session: Session, conditions: list[ColumnElement[bool]]) -> int:
    statement = select(func.count()).select_from(Oppo).where(*conditions)
    return int(session.exec(statement).one())


def _stale_condition(now: datetime) -> ColumnElement[bool]:
    return or_(
        *[
            (col(Oppo.stage) == stage) & (col(Oppo.open_at) < now - timedelta(days=days))
            for stage, days in STALE_THRESHOLD_DAYS.items()
        ]
    )


def _win_rate(won: int, lost: int) -> float | None:
    closed = won + lost
    return won / closed if closed else None


def _shift_month(value: datetime, offset: int) -> datetime:
    month_index = value.year * 12 + value.month - 1 + offset
    return datetime(month_index // 12, month_index % 12 + 1, 1)
