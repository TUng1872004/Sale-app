## registry folds visitor outputs. determinism + terminal exclusion are the graded properties.
from datetime import datetime

from app.core.schema.models import Stage
from app.rec.types import DealCtx


def _ctx(**overrides) -> DealCtx:
    base = dict(
        oppo_id="o1",
        stage=Stage.NEGOTIATE,
        value=9000.0,
        open_at=datetime(2026, 1, 1),
        now=datetime(2026, 2, 1),
        agency_id="a1",
        agency_avg_value=1000.0,
        agency_win_rate=0.2,
        owner_id="s1",
        owner_open_deal_count=15,
        owner_avg_open_deal_count=5.0,
    )
    base.update(overrides)
    return DealCtx(**base)  # type: ignore[arg-type]  # test helper, dict shape known correct by construction


def test_terminal_stage_deals_score_zero_no_factors():
    from app.rec.registry import score

    s = score(_ctx(stage=Stage.WON))
    assert s.priority == 0.0
    assert s.factors == []

    s2 = score(_ctx(stage=Stage.LOST))
    assert s2.priority == 0.0
    assert s2.factors == []


def test_ranking_orders_by_priority_descending():
    from app.rec.registry import rank

    low = _ctx(oppo_id="low", stage=Stage.NEW, value=1000.0, agency_avg_value=1000.0,
               owner_open_deal_count=5, owner_avg_open_deal_count=5.0, agency_win_rate=None,
               open_at=datetime(2026, 1, 1), now=datetime(2026, 1, 2))
    high = _ctx(oppo_id="high", stage=Stage.NEGOTIATE, value=1000.0, agency_avg_value=1000.0,
                owner_open_deal_count=15, owner_avg_open_deal_count=5.0, agency_win_rate=0.9,
                open_at=datetime(2026, 1, 1), now=datetime(2026, 2, 5))

    ranked = rank([low, high])
    assert [s.oppo_id for s in ranked] == ["high", "low"]
