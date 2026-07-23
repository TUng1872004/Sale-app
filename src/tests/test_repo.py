from datetime import datetime

from sqlmodel import Session, SQLModel, create_engine

from app.core.schema.models import Agency, LossReason, Oppo, Role, Sale, Stage
from app.repo.agency import find_agencies, owned_agency_count
from app.repo.oppo import find_oppo
from app.repo.sale import find_sales, team_member_ids
from app.repo.scope import DataScope
from app.repo.stats import dashboard_kpis, loss_summaries, monthly_revenue, rep_workload, stage_summaries, team_rankings


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _sale(name: str, *, role: Role = Role.SALER, mgr_id: str | None = None) -> Sale:
    return Sale(name=name, email=f"{name}@demo.local", pass_hash="x", role=role, region="HQ", mgr_id=mgr_id)


def _oppo(
    agency: Agency,
    owner: Sale,
    *,
    stage: Stage,
    value: float,
    open_at: datetime = datetime(2026, 1, 1),
    loss_reason: LossReason | None = None,
) -> Oppo:
    return Oppo(
        title=f"{stage.value} deal",
        agency_id=agency.id,
        owner_id=owner.id,
        value=value,
        stage=stage,
        open_at=open_at,
        loss_reason=loss_reason,
    )


def test_agency_and_oppo_lists_scope_and_paginate():
    with _session() as session:
        alice, bob = _sale("alice"), _sale("bob")
        a1 = Agency(code="a1", name="Alpha", owner=alice)
        a2 = Agency(code="a2", name="Beta", owner=bob)
        a3 = Agency(code="a3", name="Gamma")
        session.add_all([alice, bob, a1, a2, a3])
        session.commit()
        session.add_all([_oppo(a1, alice, stage=Stage.NEW, value=100), _oppo(a2, bob, stage=Stage.WON, value=200)])
        session.commit()

        alice_scope = DataScope(actor_id=alice.id, owner_ids=(alice.id,))
        global_scope = DataScope.global_for("director")
        page = find_agencies(session, alice_scope, page=1, per_page=1)
        assert [agency.name for agency in page.items] == ["Alpha"]
        assert page.total == 1
        assert owned_agency_count(session, alice_scope, alice.id) == 1
        assert [agency.name for agency in find_agencies(session, global_scope, unassigned=True).items] == ["Gamma"]
        assert [oppo.owner_id for oppo in find_oppo(session, alice_scope).items] == [alice.id]


def test_sale_lists_team_members_and_stats_formulas():
    with _session() as session:
        manager = _sale("manager", role=Role.MANAGER)
        alice = _sale("alice", mgr_id=manager.id)
        bob = _sale("bob", mgr_id=manager.id)
        agency_a = Agency(code="alpha", name="Alpha", owner=alice)
        agency_b = Agency(code="beta", name="Beta", owner=bob)
        unassigned = Agency(code="none", name="None")
        session.add_all([manager, alice, bob, agency_a, agency_b, unassigned])
        session.commit()
        session.add_all(
            [
                _oppo(agency_a, alice, stage=Stage.NEW, value=100, open_at=datetime(2026, 1, 1)),
                _oppo(agency_a, alice, stage=Stage.WON, value=200),
                _oppo(agency_a, alice, stage=Stage.LOST, value=300, loss_reason=LossReason.PRICE),
                _oppo(agency_b, bob, stage=Stage.NEGOTIATE, value=400, open_at=datetime(2026, 2, 25)),
            ]
        )
        session.commit()

        global_scope = DataScope.global_for("director")
        assert [sale.name for sale in find_sales(session, global_scope, role=Role.SALER).items] == ["alice", "bob"]
        assert team_member_ids(session, manager.id) == [manager.id, alice.id, bob.id]

        kpis = dashboard_kpis(session, global_scope, now=datetime(2026, 3, 1))
        assert kpis.pipeline_value == 500
        assert kpis.won_revenue == 200
        assert kpis.win_rate == 0.5
        assert kpis.unassigned_agency_count == 1
        assert kpis.stale_oppo_count == 1

        stages = {row.stage: row for row in stage_summaries(session, global_scope)}
        assert stages[Stage.NEW].count == 1
        assert stages[Stage.PROPOSE].count == 0
        assert stages[Stage.NEGOTIATE].value == 400
        assert loss_summaries(session, global_scope)[0].reason == LossReason.PRICE

        workload = rep_workload(session, global_scope, now=datetime(2026, 3, 1))
        assert [row.sale_name for row in workload] == ["bob", "alice"]
        assert workload[1].win_rate == 0.5
        assert workload[1].stale_oppo_count == 1


def test_completed_month_revenue_ema_team_order_and_stale_boundary():
    with _session() as session:
        manager_a = _sale("manager-a", role=Role.MANAGER)
        manager_b = _sale("manager-b", role=Role.MANAGER)
        alice = _sale("alice-ema", mgr_id=manager_a.id)
        bob = _sale("bob-ema", mgr_id=manager_b.id)
        agency_a = Agency(code="ema-a", name="EMA A", owner=alice)
        agency_b = Agency(code="ema-b", name="EMA B", owner=bob)
        session.add_all([manager_a, manager_b, alice, bob, agency_a, agency_b])
        session.commit()
        rows = [
            (agency_a, alice, 100, datetime(2026, 1, 15)),
            (agency_a, alice, 200, datetime(2026, 2, 15)),
            (agency_a, alice, 300, datetime(2026, 3, 15)),
            (agency_a, alice, 400, datetime(2026, 4, 15)),
            (agency_a, alice, 9999, datetime(2026, 5, 2)),
            (agency_b, bob, 200, datetime(2026, 4, 10)),
        ]
        for agency, owner, value, closed in rows:
            deal = _oppo(agency, owner, stage=Stage.WON, value=value)
            deal.close_at = closed
            session.add(deal)
        boundary = _oppo(agency_a, alice, stage=Stage.NEW, value=50, open_at=datetime(2026, 4, 1))
        session.add(boundary)
        session.commit()

        global_scope = DataScope.global_for("director")
        months = monthly_revenue(session, global_scope, now=datetime(2026, 5, 1))
        assert [row.month for row in months] == ["2026-01", "2026-02", "2026-03", "2026-04"]
        assert months[-1].ema == 225
        assert dashboard_kpis(session, global_scope, now=datetime(2026, 5, 1)).stale_oppo_count == 0
        rankings = team_rankings(session, global_scope, now=datetime(2026, 5, 1))
        assert [row.manager_name for row in rankings] == ["manager-b", "manager-a"]
        assert rankings[1].prior_ema == 225
