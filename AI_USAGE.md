# AI Usage

Workflow: README and requirements first, then planned modules, approved stack, test cases, implementation, and self-check.

The project used AI as a coding assistant under human direction. The human reviewed the sales-domain assumptions, chose the final recommendation benchmark objective, and corrected the plan when earlier AI output drifted from the functional requirements.

## Human-Guided Setup

The initial schema, module direction, and modular FastAPI style were chosen with heavy human guidance. Dataset claims and seed counts were verified against the raw CSVs before implementation.

## Consolidated v3 Implementation

AI created consolidated v3 plan, implemented the FastAPI/SQLModel/Jinja application through phases 0-4.

| Phase | AI contribution | Verification |
|---|---|---|
| Phase 0 | Added `DataScope`, SQL pagination, SQL aggregates, shared stale rules, JSON Position, deterministic seed/reseed, and recommendation benchmark. | Real CSV seed tests, repository tests, benchmark tests, CLI output, and JSON artifact. |
| Phase 1 | Built login redirects, hybrid Opportunity delete (`CLOSED` when audited), and Director bulk assign. | HTTP tests cover auth, bulk logs, hard/soft delete, terminal stages, and dismissal. |
| Phase 2 | Added dashboard metrics, EMA, team ranking, drill-down data, and management actions. | Aggregate tests cover zero denominators, completed months, workload, stale stages, and team order. |
| Phase 3 | Added named application services for assignment, stage changes, reports, and offboarding, plus storage and logs. | Workflow tests cover rollback cleanup, one-log rule, scope, health degradation, and presigned access. |
| Phase 4 | Integrated the selected recommender artifact, scoped candidates, Position-first ordering, score factors, top-3/top-5 UI, and deterministic fallback. | Recommendation tests cover no leakage, exact Recall/Precision metrics, no `@10`, fallback, and deterministic artifacts. |

## Benchmark Note

Codex initially had to correct deterministic-score normalization so the baseline comparison was fair. After rerun, the deterministic candidate-Saler scorer beat GLM on the locked composite score due to the lack of sufficient data and was selected.

## Final Check

Final verification passed with `42` pytest cases and clean `mypy` on `src/app`. One FastAPI `TestClient` deprecation warning remains and does not affect behavior.

## Report Documentation

Human structured the technical report, gave outlines and wrote the methodology as well as design choices while Codex contributed to most technical deep sections. Codex drew some SVG too.
