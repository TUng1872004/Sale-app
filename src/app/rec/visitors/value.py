## outlier-large deals penalized slightly: harder to close, shouldn't dominate the list alone
from app.rec.types import DealCtx, Factor
from app.rec.weight import VALUE_OUTLIER_MULTIPLE, VALUE_OUTLIER_PENALTY


def visit(ctx: DealCtx) -> Factor | None:
    if ctx.agency_avg_value <= 0:
        return None
    if ctx.value <= ctx.agency_avg_value * VALUE_OUTLIER_MULTIPLE:
        return None
    return Factor(
        signal="value",
        impact=VALUE_OUTLIER_PENALTY,
        detail=f"Giá trị gấp {ctx.value / ctx.agency_avg_value:.1f}x trung bình đại lý",
    )
