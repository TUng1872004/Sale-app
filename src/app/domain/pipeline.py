from types import MappingProxyType

from app.core.schema.models import Stage


STALE_THRESHOLD_DAYS: MappingProxyType[Stage, int] = MappingProxyType(
    {
        Stage.NEW: 30,
        Stage.QUALIFY: 21,
        Stage.PROPOSE: 14,
        Stage.NEGOTIATE: 10,
    }
)
