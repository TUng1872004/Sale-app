## overloaded reps are likelier to neglect a deal, so rank it up; underloaded reps rank neutral
from app.rec.types import DealCtx, Factor
from app.rec.weight import LOAD_IMPACT_CAP


def visit(ctx: DealCtx) -> Factor | None:
    if ctx.owner_avg_open_deal_count <= 0:
        return None
    ratio = ctx.owner_open_deal_count / ctx.owner_avg_open_deal_count
    if ratio <= 1.2:  # not meaningfully above average
        return None
    excess = min(ratio - 1.0, 2.0)  # cap at 3x average
    impact = (excess / 2.0) * LOAD_IMPACT_CAP
    return Factor(
        signal="load",
        impact=impact,
        detail=f"Người phụ trách đang xử lý {ctx.owner_open_deal_count} cơ hội (TB {ctx.owner_avg_open_deal_count:.0f})",
    )
