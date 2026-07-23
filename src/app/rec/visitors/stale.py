## days past the per-stage threshold, scaled and capped so one ancient deal can't dominate
from app.rec.types import DealCtx, Factor
from app.rec.weight import STALE_IMPACT_CAP, STALE_THRESHOLD_DAYS


def visit(ctx: DealCtx) -> Factor | None:
    threshold = STALE_THRESHOLD_DAYS.get(ctx.stage)
    if threshold is None:  # terminal stage
        return None

    days_open = (ctx.now - ctx.open_at).days
    overage = days_open - threshold
    if overage <= 0:
        return None

    ## scale: +overage days past threshold, capped, so very-old deals don't blow out the score
    impact = min(overage / threshold, 1.0) * STALE_IMPACT_CAP
    return Factor(
        signal="stale",
        impact=impact,
        detail=f"Quá hạn {overage} ngày so với mức bình thường ({threshold} ngày)",
    )
