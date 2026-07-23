## folds visitor outputs into a priority score. adding a visitor = adding a file to this list.
from app.core.schema.models import TERMINAL_STAGES
from app.rec.types import DealCtx, Factor, Score, Visitor
from app.rec.visitors import hist, load, stage, stale, value

VISITORS: list[Visitor] = [stage.visit, stale.visit, value.visit, load.visit, hist.visit]


def score(ctx: DealCtx) -> Score:
    if ctx.stage in TERMINAL_STAGES:
        return Score(oppo_id=ctx.oppo_id, priority=0.0, factors=[])

    factors: list[Factor] = [f for f in (v(ctx) for v in VISITORS) if f is not None]
    priority = sum(f.impact for f in factors)
    return Score(oppo_id=ctx.oppo_id, priority=priority, factors=factors)


def rank(ctxs: list[DealCtx]) -> list[Score]:
    scores = [score(c) for c in ctxs]
    return sorted(scores, key=lambda s: s.priority, reverse=True)
