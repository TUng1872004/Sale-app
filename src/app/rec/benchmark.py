from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.preprocessing import StandardScaler

from app.rec.candidate import FEATURE_NAMES
from app.seed import DATA_DIR


ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
KS = (3, 5)
METRIC_WEIGHTS = {
    "recall_at_3": 0.32,
    "recall_at_5": 0.28,
    "precision_at_3": 0.22,
    "precision_at_5": 0.18,
}


@dataclass(frozen=True, slots=True)
class Metrics:
    recall_at_3: float
    recall_at_5: float
    precision_at_3: float
    precision_at_5: float
    coverage: float
    actual_owner_hit_at_3: float
    actual_owner_hit_at_5: float
    confidence_intervals: dict[str, tuple[float, float]] = field(default_factory=dict)

    @property
    def composite(self) -> float:
        values = asdict(self)
        return sum(float(values[name]) * weight for name, weight in METRIC_WEIGHTS.items())


class History:
    def __init__(self) -> None:
        self.overall: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
        self.agent_sector: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
        self.team_sector: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
        self.revenue: dict[tuple[str, str], float] = defaultdict(float)
        self.win_days: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
        self.positions: dict[str, set[str]] = defaultdict(set)
        self.all_win_days: list[float] = []

    def features(self, agent: str, manager: str, sector: str) -> np.ndarray:
        wins, closed = self.overall[agent]
        sector_wins, sector_closed = self.agent_sector[(agent, sector)]
        team_wins, team_closed = self.team_sector[(manager, sector)]
        days_sum, days_count = self.win_days[agent]
        fallback_days = float(np.mean(self.all_win_days)) if self.all_win_days else 30.0
        avg_days = days_sum / days_count if days_count else fallback_days
        return np.array(
            [
                (wins + 1) / (closed + 2),
                (sector_wins + 1) / (sector_closed + 2),
                (team_wins + 1) / (team_closed + 2),
                np.log1p(self.revenue[(agent, sector)]),
                avg_days,
            ],
            dtype=float,
        )

    def update(self, row: pd.Series) -> None:
        agent = str(row["sales_agent"])
        manager = str(row["manager"])
        sector = str(row["sector"])
        won = row["deal_stage"] == "Won"
        self.overall[agent][1] += 1
        self.agent_sector[(agent, sector)][1] += 1
        self.team_sector[(manager, sector)][1] += 1
        if won:
            self.overall[agent][0] += 1
            self.agent_sector[(agent, sector)][0] += 1
            self.team_sector[(manager, sector)][0] += 1
            self.revenue[(agent, sector)] += float(row["close_value"])
            days = float(row["sales_cycle_days"])
            self.win_days[agent][0] += days
            self.win_days[agent][1] += 1
            self.all_win_days.append(days)
            if pd.notna(row["office_location"]):
                self.positions[agent].add(str(row["office_location"]))


def load_closed() -> tuple[pd.DataFrame, pd.DataFrame]:
    pipeline = pd.read_csv(DATA_DIR / "sales_pipeline.csv")
    accounts = pd.read_csv(DATA_DIR / "accounts.csv")
    teams = pd.read_csv(DATA_DIR / "sales_teams.csv")
    closed = pipeline[pipeline["deal_stage"].isin(["Won", "Lost"]) & pipeline["account"].notna()].copy()
    closed["engage_date"] = pd.to_datetime(closed["engage_date"])
    closed["close_date"] = pd.to_datetime(closed["close_date"])
    closed["sales_cycle_days"] = (closed["close_date"] - closed["engage_date"]).dt.days.clip(lower=0)
    closed = closed.merge(accounts[["account", "sector", "office_location"]], on="account", how="left")
    closed = closed.merge(teams[["sales_agent", "manager"]], on="sales_agent", how="left")
    closed = closed.sort_values(["close_date", "opportunity_id"]).reset_index(drop=True)
    return closed, teams


def fit_model(train: pd.DataFrame) -> tuple[History, StandardScaler, np.ndarray]:
    history = History()
    feature_rows: list[np.ndarray] = []
    targets: list[int] = []
    for _, row in train.iterrows():
        feature_rows.append(history.features(str(row["sales_agent"]), str(row["manager"]), str(row["sector"])))
        targets.append(1 if row["deal_stage"] == "Won" else 0)
        history.update(row)
    scaler = StandardScaler().fit(np.vstack(feature_rows))
    design = sm.add_constant(scaler.transform(np.vstack(feature_rows)), has_constant="add")
    result = sm.GLM(np.array(targets), design, family=sm.families.Binomial()).fit()
    coefficients = np.asarray(result.params, dtype=float)
    if not np.isfinite(coefficients).all():
        raise RuntimeError("GLM produced non-finite coefficients")
    return history, scaler, coefficients


def candidate_rankers(
    history: History,
    scaler: StandardScaler,
    coefficients: np.ndarray,
    teams: pd.DataFrame,
) -> dict[str, Callable[[pd.Series, list[str]], list[str]]]:
    managers = dict(zip(teams["sales_agent"].astype(str), teams["manager"].astype(str)))

    def feature(agent: str, row: pd.Series) -> np.ndarray:
        return history.features(agent, managers[agent], str(row["sector"]))

    def ordered(row: pd.Series, candidates: list[str], score_fn: Callable[[str, pd.Series], float], position: bool) -> list[str]:
        location = str(row["office_location"])
        return sorted(
            candidates,
            key=lambda agent: (
                not (position and location in history.positions[agent]),
                -score_fn(agent, row),
                agent,
            ),
        )

    def overall(agent: str, row: pd.Series) -> float:
        return float(feature(agent, row)[0])

    def sector(agent: str, row: pd.Series) -> float:
        return float(feature(agent, row)[1])

    def weighted(agent: str, row: pd.Series) -> float:
        values = scaler.transform(feature(agent, row).reshape(1, -1))[0]
        return float(0.30 * values[0] + 0.30 * values[1] + 0.20 * values[2] + 0.15 * values[3] - 0.05 * values[4])

    def glm(agent: str, row: pd.Series) -> float:
        values = scaler.transform(feature(agent, row).reshape(1, -1))[0]
        linear = coefficients[0] + float(np.dot(coefficients[1:], values))
        return float(1 / (1 + np.exp(-np.clip(linear, -30, 30))))

    return {
        "overall": lambda row, candidates: ordered(row, candidates, overall, False),
        "sector": lambda row, candidates: ordered(row, candidates, sector, False),
        "position_sector": lambda row, candidates: ordered(row, candidates, sector, True),
        "deterministic": lambda row, candidates: ordered(row, candidates, weighted, True),
        "glm": lambda row, candidates: ordered(row, candidates, glm, True),
    }


def evaluate(
    holdout: pd.DataFrame,
    teams: pd.DataFrame,
    ranker: Callable[[pd.Series, list[str]], list[str]],
    *,
    team_local: bool,
) -> Metrics:
    all_agents = sorted(teams["sales_agent"].astype(str).unique())
    team_agents = teams.groupby("manager")["sales_agent"].apply(lambda rows: sorted(rows.astype(str))).to_dict()
    won = holdout[holdout["deal_stage"] == "Won"]
    segment_winners = won.groupby(["sector", "product"])["sales_agent"].apply(lambda rows: set(rows.astype(str))).to_dict()
    sector_winners = won.groupby("sector")["sales_agent"].apply(lambda rows: set(rows.astype(str))).to_dict()
    per_query: list[dict[str, float]] = []
    eligible = 0
    owner_hits = {3: 0, 5: 0}
    for _, row in holdout.iterrows():
        candidates = team_agents[str(row["manager"])] if team_local else all_agents
        relevant = set(segment_winners.get((row["sector"], row["product"]), set()))
        if not relevant:
            relevant = set(sector_winners.get(row["sector"], set()))
        relevant.intersection_update(candidates)
        if not relevant:
            continue
        eligible += 1
        ranked = ranker(row, candidates)
        query_metrics: dict[str, float] = {}
        for k in KS:
            top = set(ranked[:k])
            hits = len(top & relevant)
            query_metrics[f"recall_at_{k}"] = hits / len(relevant)
            query_metrics[f"precision_at_{k}"] = hits / k
            owner_hits[k] += int(str(row["sales_agent"]) in top)
        per_query.append(query_metrics)
    total = len(holdout)
    if not per_query:
        return Metrics(0, 0, 0, 0, 0, 0, 0)
    confidence = _bootstrap_confidence(per_query)
    return Metrics(
        recall_at_3=float(np.mean([row["recall_at_3"] for row in per_query])),
        recall_at_5=float(np.mean([row["recall_at_5"] for row in per_query])),
        precision_at_3=float(np.mean([row["precision_at_3"] for row in per_query])),
        precision_at_5=float(np.mean([row["precision_at_5"] for row in per_query])),
        coverage=eligible / total,
        actual_owner_hit_at_3=owner_hits[3] / eligible,
        actual_owner_hit_at_5=owner_hits[5] / eligible,
        confidence_intervals=confidence,
    )


def _bootstrap_confidence(per_query: list[dict[str, float]], *, samples: int = 500) -> dict[str, tuple[float, float]]:
    names = tuple(METRIC_WEIGHTS)
    matrix = np.array([[row[name] for name in names] for row in per_query], dtype=float)
    rng = np.random.default_rng(20260723)
    indices = rng.integers(0, len(matrix), size=(samples, len(matrix)))
    sample_means = matrix[indices].mean(axis=1)
    return {
        name: (float(np.quantile(sample_means[:, index], 0.025)), float(np.quantile(sample_means[:, index], 0.975)))
        for index, name in enumerate(names)
    }


def choose(results: dict[str, dict[str, Metrics]]) -> str:
    baselines = [name for name in results if name != "glm"]
    strongest = max(baselines, key=lambda name: results[name]["global"].composite)
    glm_global = results["glm"]["global"]
    base_global = results[strongest]["global"]
    team_floor = results[strongest]["team"].recall_at_3 - 0.01
    if (
        _finite_metrics(glm_global)
        and _finite_metrics(results["glm"]["team"])
        and glm_global.composite > base_global.composite
        and glm_global.recall_at_3 > base_global.recall_at_3
        and results["glm"]["team"].recall_at_3 >= team_floor
        and glm_global.coverage >= 0.80
    ):
        return "glm"
    return strongest


def chronological_split(closed: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    split = int(len(closed) * 0.70)
    return closed.iloc[:split].copy(), closed.iloc[split:].copy()


def _finite_metrics(metrics: Metrics) -> bool:
    values = asdict(metrics)
    return all(np.isfinite(float(values[name])) for name in (*METRIC_WEIGHTS, "coverage"))


def run_benchmark(*, write: bool = True) -> dict[str, object]:
    closed, teams = load_closed()
    train, holdout = chronological_split(closed)
    history, scaler, coefficients = fit_model(train)
    rankers = candidate_rankers(history, scaler, coefficients, teams)
    results = {
        name: {
            "global": evaluate(holdout, teams, ranker, team_local=False),
            "team": evaluate(holdout, teams, ranker, team_local=True),
        }
        for name, ranker in rankers.items()
    }
    selected = choose(results)
    payload: dict[str, object] = {
        "feature_version": 1,
        "features": list(FEATURE_NAMES),
        "train_rows": len(train),
        "holdout_rows": len(holdout),
        "training_cutoff": str(train.iloc[-1]["close_date"].date()),
        "selected": selected,
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "coefficients": coefficients.tolist(),
        "metrics": {name: {scope: {**asdict(metrics), "composite": metrics.composite} for scope, metrics in views.items()} for name, views in results.items()},
    }
    if write:
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        (ARTIFACT_DIR / "benchmark.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def format_report(payload: dict[str, object]) -> str:
    metrics = payload["metrics"]
    assert isinstance(metrics, dict)
    lines = [
        "Recommendation benchmark",
        f"Chronological split: {payload['train_rows']} train / {payload['holdout_rows']} holdout",
        f"Selected model: {payload['selected']}",
        "Only Recall@3, Recall@5, Precision@3, and Precision@5 select the model.",
        "",
        "| Model | View | R@3 | R@5 | P@3 | P@5 | Coverage | Composite |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, views in metrics.items():
        for view, row in views.items():
            lines.append(
                f"| {name} | {view} | {row['recall_at_3']:.3f} | {row['recall_at_5']:.3f} | "
                f"{row['precision_at_3']:.3f} | {row['precision_at_5']:.3f} | {row['coverage']:.3f} | {row['composite']:.3f} |"
            )
    lines.extend(
        [
            "",
            f"Selected global 95% bootstrap intervals: `{metrics[str(payload['selected'])]['global']['confidence_intervals']}`.",
            "",
            "Relevance is future holdout winners in the same sector/product, falling back to sector. This is an offline proxy, not counterfactual proof that another saler would have won a specific deal.",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    result = run_benchmark()
    print(format_report(result))
