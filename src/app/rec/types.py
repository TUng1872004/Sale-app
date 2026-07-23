## shared types for the visitor pipeline. no DB access here, ctx is plain data passed in.
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.core.schema.models import Stage


@dataclass(frozen=True, slots=True)
class DealCtx:
    ## everything a visitor might need, pre-fetched by the caller - visitors do no I/O
    oppo_id: str
    stage: Stage
    value: float
    open_at: datetime
    now: datetime
    agency_id: str
    agency_avg_value: float
    agency_win_rate: float | None  # None if agency has no closed deals yet
    owner_id: str
    owner_open_deal_count: int
    owner_avg_open_deal_count: float  # average across all active salers, for load comparison


@dataclass(frozen=True, slots=True)
class Factor:
    signal: str
    impact: float  # positive = more urgent/valuable, negative = less
    detail: str  # Vietnamese, display-ready


@dataclass(frozen=True, slots=True)
class Score:
    oppo_id: str
    priority: float
    factors: list[Factor]


class Visitor(Protocol):
    def __call__(self, ctx: DealCtx) -> Factor | None: ...
