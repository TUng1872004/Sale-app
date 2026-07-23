from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from functools import cache
from pathlib import Path

import numpy as np
from sqlmodel import Session, col, select

from app.core.schema.models import Agency, Oppo, Sale, Stage
from app.rec.candidate import CandidateScore, FEATURE_NAMES, order_candidates


ARTIFACT_PATH = Path(__file__).resolve().parent / "artifacts" / "benchmark.json"


def recommend(session: Session, oppo: Oppo, candidates: list[Sale], as_of: datetime | None = None) -> list[CandidateScore]:
    agency = session.get(Agency, oppo.agency_id)
    if agency is None:
        return []
    history = _history(session, as_of)
    artifact = load_artifact()
    feature_rows = [_features(history, candidate, agency.sector or "unknown") for candidate in candidates]
    if not feature_rows:
        return []
    feature_matrix = np.vstack(feature_rows)
    means = np.array(artifact.get("scaler_mean", feature_matrix.mean(axis=0)), dtype=float)
    scales = np.array(artifact.get("scaler_scale", feature_matrix.std(axis=0)), dtype=float)
    scales[scales == 0] = 1.0
    scores: list[CandidateScore] = []
    for candidate, values in zip(candidates, feature_rows):
        normalized = (values - means) / scales
        coefficients = artifact.get("coefficients")
        if artifact.get("selected") == "glm" and isinstance(coefficients, list) and len(coefficients) == 6:
            linear = float(coefficients[0]) + float(np.dot(np.array(coefficients[1:], dtype=float), normalized))
            score = float(1 / (1 + np.exp(-np.clip(linear, -30, 30))))
        else:
            score = float(
                0.30 * normalized[0]
                + 0.30 * normalized[1]
                + 0.20 * normalized[2]
                + 0.15 * normalized[3]
                - 0.05 * normalized[4]
            )
        match = bool(agency.loc and agency.loc in candidate.position)
        scores.append(
            CandidateScore(
                saler_id=candidate.id,
                score=score,
                position_match=match,
                features={name: float(value) for name, value in zip(FEATURE_NAMES, normalized)},
                factors=(
                    f"Tỷ lệ thắng {values[0]:.1%}",
                    f"Tỷ lệ thắng ngành {values[1]:.1%}",
                    f"Tỷ lệ đội trong ngành {values[2]:.1%}",
                    f"Doanh thu ngành {np.expm1(values[3]):,.0f}",
                    f"Trung bình {values[4]:.0f} ngày để thắng",
                ),
            )
        )
    return order_candidates(scores)


def _history(session: Session, as_of: datetime | None) -> dict[str, object]:
    statement = (
        select(Oppo, Agency, Sale)
        .join(Agency, col(Oppo.agency_id) == col(Agency.id))
        .join(Sale, col(Oppo.owner_id) == col(Sale.id))
        .where(col(Oppo.stage).in_([Stage.WON, Stage.LOST]))
    )
    if as_of is not None:
        statement = statement.where(col(Oppo.close_at) < as_of)
    overall: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    agent_sector: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
    team_sector: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
    revenue: dict[tuple[str, str], float] = defaultdict(float)
    days: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    all_days: list[float] = []
    for deal, agency, owner in session.exec(statement):
        sector = agency.sector or "unknown"
        manager = owner.mgr_id or owner.id
        overall[owner.id][1] += 1
        agent_sector[(owner.id, sector)][1] += 1
        team_sector[(manager, sector)][1] += 1
        if deal.stage == Stage.WON:
            overall[owner.id][0] += 1
            agent_sector[(owner.id, sector)][0] += 1
            team_sector[(manager, sector)][0] += 1
            revenue[(owner.id, sector)] += deal.value
            if deal.close_at is not None:
                cycle = max((deal.close_at - deal.open_at).days, 0)
                days[owner.id][0] += cycle
                days[owner.id][1] += 1
                all_days.append(float(cycle))
    return {
        "overall": overall,
        "agent_sector": agent_sector,
        "team_sector": team_sector,
        "revenue": revenue,
        "days": days,
        "fallback_days": float(np.mean(all_days)) if all_days else 30.0,
    }


def _features(history: dict[str, object], candidate: Sale, sector: str) -> np.ndarray:
    overall = history["overall"]
    agent_sector = history["agent_sector"]
    team_sector = history["team_sector"]
    revenue = history["revenue"]
    days = history["days"]
    assert isinstance(overall, dict)
    assert isinstance(agent_sector, dict)
    assert isinstance(team_sector, dict)
    assert isinstance(revenue, dict)
    assert isinstance(days, dict)
    wins, closed = overall.get(candidate.id, [0.0, 0.0])
    sector_wins, sector_closed = agent_sector.get((candidate.id, sector), [0.0, 0.0])
    manager = candidate.mgr_id or candidate.id
    team_wins, team_closed = team_sector.get((manager, sector), [0.0, 0.0])
    days_sum, days_count = days.get(candidate.id, [0.0, 0.0])
    fallback_days = history["fallback_days"]
    assert isinstance(fallback_days, float)
    avg_days = days_sum / days_count if days_count else fallback_days
    return np.array(
        [
            (wins + 1) / (closed + 2),
            (sector_wins + 1) / (sector_closed + 2),
            (team_wins + 1) / (team_closed + 2),
            np.log1p(float(revenue.get((candidate.id, sector), 0.0))),
            avg_days,
        ],
        dtype=float,
    )


@cache
def load_artifact() -> dict[str, object]:
    if not ARTIFACT_PATH.exists():
        return {"selected": "deterministic"}
    try:
        payload = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"selected": "deterministic"}
    if not isinstance(payload, dict) or payload.get("feature_version") != 1 or payload.get("features") != list(FEATURE_NAMES):
        return {"selected": "deterministic"}
    numeric = [*payload.get("scaler_mean", []), *payload.get("scaler_scale", []), *payload.get("coefficients", [])]
    if not numeric or not all(isinstance(value, (int, float)) and np.isfinite(value) for value in numeric):
        return {"selected": "deterministic"}
    return payload
