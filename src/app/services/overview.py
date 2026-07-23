from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlmodel import Session

from app.core.schema.models import STAGE_ORDER, Stage
from app.repo.oppo import find_oppo
from app.repo.sale import find_sales
from app.repo.scope import DataScope


@dataclass(frozen=True, slots=True)
class KanbanCard:
    id: str
    title: str
    owner_name: str
    value: float
    due_at: datetime | None


@dataclass(frozen=True, slots=True)
class KanbanColumn:
    stage: Stage
    cards: tuple[KanbanCard, ...]


@dataclass(frozen=True, slots=True)
class KanbanBoard:
    columns: tuple[KanbanColumn, ...]
    total: int
    shown: int


def team_kanban(session: Session, scope: DataScope, *, limit: int = 100) -> KanbanBoard:
    stages = tuple(STAGE_ORDER[:-1])
    page = find_oppo(session, scope, stages=stages, per_page=limit)
    owners = {sale.id: sale.name for sale in find_sales(session, scope, per_page=100).items}
    columns = tuple(
        KanbanColumn(
            stage=stage,
            cards=tuple(
                KanbanCard(
                    id=deal.id,
                    title=deal.title,
                    owner_name=owners.get(deal.owner_id, deal.owner_id),
                    value=deal.value,
                    due_at=deal.due_at,
                )
                for deal in page.items
                if deal.stage == stage
            ),
        )
        for stage in stages
    )
    return KanbanBoard(columns=columns, total=page.total, shown=len(page.items))
