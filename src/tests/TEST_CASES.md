# Test Cases

Automated tests are organized by construction phase. Run from the repository root:

```bash
uv run pytest src/tests
uv run mypy src/app
```

| Phase | Test files | Main testcase coverage |
|---|---|---|
| Phase 0 — Scope, seed, benchmark | `test_repo.py`, `test_seed.py`, `test_benchmark.py` | `DataScope` enforcement, SQL pagination/counts, scoped detail reads, manager own-team inclusion, SQL aggregates, exact seed counts, first/second seed behavior, partial DB rejection, `--reseed` output capture, chronological split, no leakage, Recall@3/5, Precision@3/5, composite score, coverage fallback, global/team-local ranking, Position-first order, deterministic artifact, invalid-artifact fallback, and explicit no-`@10` assertion. |
| Phase 1 — Runnable flow | `test_http.py`, `test_stage.py`, `test_sale.py` | Login redirect, Opportunity hard delete without logs, audited delete to terminal `CLOSED`, Director bulk assign with per-item logs, stage/report rules, and `REASSIGN_REQUIRED`. |
| Phase 2 — Dashboards | `test_repo.py`, `test_http.py` | Monthly won revenue, zero denominators, three-month EMA, latest completed-month team order, workload, win rate, stage counts including zero-count stages, stale boundaries, and team drill-down inputs. |
| Phase 3 — Pools, reports, logs | `test_http.py`, `test_storage_workflow.py` | Named workflow services, HQ/team/saler assignment, take-charge decisions, Markdown storage, upload/SQL compensation, one-log rule, scoped presigned access, health degradation, and dismissal separation. |
| Phase 4 — Recommendations | `test_benchmark.py`, `test_rec_service.py`, benchmark CLI | Runtime candidate filtering, Position-first ordering, deterministic score factors, normalized feature values, selected artifact loading, GLM gate behavior, deterministic fallback, benchmark inputs/formulas/results/coverage/CIs/limitations, and machine-readable benchmark output. |

| Manual check | Evidence |
|---|---|
| Director dashboard | Browser verification rendered seeded dashboard data and charts. |
| `REASSIGN_REQUIRED` demo | Browser verification triggered the dismissal modal and server rejection. |
| Full flow repeatability | Covered by `test_http.py`, so screenshots are supporting evidence rather than the only proof. |
