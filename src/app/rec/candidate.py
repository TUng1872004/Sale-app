from __future__ import annotations

from dataclasses import dataclass


FEATURE_NAMES = (
    "overall_win_rate",
    "sector_win_rate",
    "team_sector_win_rate",
    "sector_won_revenue",
    "avg_days_to_win",
)


@dataclass(frozen=True, slots=True)
class CandidateScore:
    saler_id: str
    score: float
    position_match: bool
    features: dict[str, float]
    factors: tuple[str, ...]


def order_candidates(scores: list[CandidateScore]) -> list[CandidateScore]:
    return sorted(scores, key=lambda row: (not row.position_match, -row.score, row.saler_id))
