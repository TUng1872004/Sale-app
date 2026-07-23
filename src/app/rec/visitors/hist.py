## agency win history nudges the score: proven agencies rank up, historically-losing ones rank down
from app.rec.types import DealCtx, Factor
from app.rec.weight import HIST_IMPACT_CAP


def visit(ctx: DealCtx) -> Factor | None:
    if ctx.agency_win_rate is None:  # no closed history yet
        return None
    ## centered on 0.5: win_rate 1.0 -> +cap, win_rate 0.0 -> -cap
    impact = (ctx.agency_win_rate - 0.5) * 2 * HIST_IMPACT_CAP
    return Factor(
        signal="hist",
        impact=impact,
        detail=f"Tỷ lệ thắng lịch sử của đại lý: {ctx.agency_win_rate:.0%}",
    )
