import pandas as pd

from app.rec.benchmark import (
    evaluate,
)
from app.rec.candidate import CandidateScore, order_candidates


def test_evaluate_calculates_exact_top_three_and_five_metrics():
    teams = pd.DataFrame(
        {
            "sales_agent": ["a", "b", "c", "d", "e", "f"],
            "manager": ["m", "m", "m", "m", "m", "m"],
        }
    )
    holdout = pd.DataFrame(
        [
            {"sales_agent": "a", "manager": "m", "sector": "tech", "product": "p", "deal_stage": "Won"},
            {"sales_agent": "b", "manager": "m", "sector": "tech", "product": "p", "deal_stage": "Won"},
        ]
    )

    metrics = evaluate(holdout, teams, lambda row, candidates: ["a", "c", "d", "b", "e", "f"], team_local=False)

    assert metrics.recall_at_3 == 0.5
    assert metrics.recall_at_5 == 1.0
    assert metrics.precision_at_3 == 1 / 3
    assert metrics.precision_at_5 == 2 / 5
    assert metrics.coverage == 1.0


def test_position_matches_always_rank_before_higher_non_match_score():
    ranked = order_candidates(
        [
            CandidateScore("high", 99.0, False, {}, ()),
            CandidateScore("match", -2.0, True, {}, ()),
        ]
    )
    assert [row.saler_id for row in ranked] == ["match", "high"]

