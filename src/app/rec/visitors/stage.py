## later stage = closer to closing = more worth saving
from app.core.schema.models import Stage
from app.rec.types import DealCtx, Factor
from app.rec.weight import STAGE_WEIGHT


def visit(ctx: DealCtx) -> Factor | None:
    weight = STAGE_WEIGHT.get(ctx.stage)
    if weight is None:  # terminal stage, no signal
        return None
    return Factor(signal="stage", impact=weight, detail=f"Giai đoạn {ctx.stage.value}: cơ sở {weight:.0%}")
