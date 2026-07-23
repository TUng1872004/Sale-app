## frozen constants. one place, not scattered literals.
from types import MappingProxyType

from app.domain.pipeline import STALE_THRESHOLD_DAYS
from app.core.schema.models import Stage

STAGE_WEIGHT: MappingProxyType[Stage, float] = MappingProxyType(
    {
        Stage.NEW: 0.10,
        Stage.QUALIFY: 0.25,
        Stage.PROPOSE: 0.45,
        Stage.NEGOTIATE: 0.70,
    }
)

STALE_IMPACT_CAP = 0.20  # max boost from staleness alone
VALUE_OUTLIER_MULTIPLE = 2.0  # deal > 2x agency mean counted as an outlier
VALUE_OUTLIER_PENALTY = -0.05
LOAD_IMPACT_CAP = 0.10
HIST_IMPACT_CAP = 0.10
