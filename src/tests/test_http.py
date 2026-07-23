from __future__ import annotations

from collections.abc import Generator
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.auth import hash_password
from app.db import get_session
from app.main import app
from app.core.schema.models import Agency, ManagerLog, Oppo, Role, Sale, SalerLog, Stage
from app.storage import MemoryStorage, set_storage


@pytest.fixture
def web() -> Generator[tuple[TestClient, object, MemoryStorage], None, None]:
    db_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(db_engine)
    password = hash_password("secret123")
    with Session(db_engine) as session:
        director = Sale(id="director", name="Director", email="director@test.local", pass_hash=password, role=Role.DIRECTOR, region="HQ")
        manager = Sale(id="manager", name="Manager", email="manager@test.local", pass_hash=password, role=Role.MANAGER, region="VN")
        saler = Sale(id="saler", name="Saler", email="saler@test.local", pass_hash=password, role=Role.SALER, region="VN", mgr_id=manager.id, position=["Vietnam"])
        other_manager = Sale(id="manager-2", name="Other Manager", email="manager2@test.local", pass_hash=password, role=Role.MANAGER, region="SG")
        outsider = Sale(id="outsider", name="Outsider", email="outsider@test.local", pass_hash=password, role=Role.SALER, region="SG", mgr_id=other_manager.id)
        agency = Agency(id="agency", code="agency", name="Agency", sector="SaaS", loc="Vietnam", owner_id=saler.id)
        deal = Oppo(id="deal", title="Renewal", prod="Cloud", agency_id=agency.id, owner_id=saler.id, value=1000, stage=Stage.NEW, open_at=datetime(2026, 1, 1))
        pooled = Oppo(id="pooled", title="Team pool", prod="Cloud", agency_id=agency.id, owner_id=manager.id, value=500, stage=Stage.NEW, open_at=datetime(2026, 1, 2))
        session.add_all([director, manager, saler, other_manager, outsider, agency, deal, pooled])
        session.commit()

    def override_session() -> Generator[Session, None, None]:
        with Session(db_engine) as session:
            yield session

    storage = MemoryStorage()
    app.dependency_overrides[get_session] = override_session
    set_storage(storage)
    client = TestClient(app)
    try:
        yield client, db_engine, storage
    finally:
        client.close()
        app.dependency_overrides.clear()
        set_storage(None)


def _login(client: TestClient, email: str) -> None:
    response = client.post("/login", data={"email": email, "password": "secret123"})
    assert response.status_code == 200


def test_protected_page_redirects_to_login_instead_of_json(
    web: tuple[TestClient, object, MemoryStorage],
):
    client, _, _ = web
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert response.headers.get("content-type") is None
    assert response.url.path == "/dashboard"


def test_login_role_landing_and_cross_scope_denial(web: tuple[TestClient, object, MemoryStorage]):
    client, _, _ = web
    _login(client, "manager@test.local")
    assert "MANAGER workspace" in client.get("/dashboard").text
    response = client.post("/sales/outsider/position", data={"countries": "Vietnam"})
    assert response.status_code == 404


def test_manager_overview_and_director_team_detail_show_scoped_kanban(
    web: tuple[TestClient, object, MemoryStorage],
):
    client, db_engine, _ = web
    with Session(db_engine) as session:  # type: ignore[arg-type]
        session.add(
            Oppo(
                id="outside-deal",
                title="Outside pipeline",
                prod="Cloud",
                agency_id="agency",
                owner_id="outsider",
                value=900,
                stage=Stage.PROPOSE,
                open_at=datetime(2026, 1, 3),
            )
        )
        session.commit()
    _login(client, "manager@test.local")
    manager_dashboard = client.get("/dashboard")
    assert "Kanban tiến độ Saler" in manager_dashboard.text
    assert "Renewal" in manager_dashboard.text
    assert "Team pool" in manager_dashboard.text
    assert "Outside pipeline" not in manager_dashboard.text
    assert manager_dashboard.text.count('class="kanban-column"') == 4

    _login(client, "director@test.local")
    assert "Kanban tiến độ Saler" not in client.get("/dashboard").text
    team = client.get("/teams/manager")
    assert "Kanban tiến độ Saler" in team.text
    assert "Renewal" in team.text
    assert "Team pool" in team.text
    assert "Outside pipeline" not in team.text


def test_director_compliance_flow_and_reassign_required(web: tuple[TestClient, object, MemoryStorage]):
    client, db_engine, _ = web
    _login(client, "director@test.local")
    assert client.post(
        "/sales",
        data={"name": "New Saler", "email": "new@test.local", "password": "pw123456", "role": "SALER", "region": "VN", "mgr_id": "manager"},
    ).status_code == 200
    assert client.post("/agencies", data={"code": "new-agency", "name": "New Agency", "sector": "Finance", "loc": "Vietnam"}).status_code == 200
    with Session(db_engine) as session:  # type: ignore[arg-type]
        new_sale = session.exec(select(Sale).where(Sale.email == "new@test.local")).one()
        new_agency = session.exec(select(Agency).where(Agency.code == "new-agency")).one()
    assert client.post(f"/agencies/{new_agency.id}/assign", data={"owner_id": new_sale.id, "reason": "coverage"}).status_code == 200
    assert client.post(
        "/opportunities",
        data={"title": "New deal", "agency_id": new_agency.id, "product": "Analytics", "value": "2500", "due_at": ""},
    ).status_code == 200
    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert "Tổng quan kinh doanh" in dashboard.text
    blocked = client.post("/sales/saler/kick", data={"summary": "demo"})
    assert blocked.status_code == 200
    assert "REASSIGN_REQUIRED" in blocked.text


def test_director_bulk_assigns_and_deletes_opportunities(web: tuple[TestClient, object, MemoryStorage]):
    client, db_engine, _ = web
    _login(client, "director@test.local")
    for title in ("Bulk one", "Bulk two", "Delete me"):
        response = client.post(
            "/opportunities",
            data={"title": title, "agency_id": "agency", "product": "Cloud", "value": "100", "due_at": ""},
        )
        assert response.status_code == 200
    page = client.get("/opportunities")
    assert 'action="/opportunities/bulk-assign"' in page.text
    assert "method:'DELETE'" in page.text
    with Session(db_engine) as session:  # type: ignore[arg-type]
        deals = {
            deal.title: deal
            for deal in session.exec(select(Oppo).where(Oppo.title.in_(["Bulk one", "Bulk two", "Delete me"])))
        }
    assigned_ids = [deals["Bulk one"].id, deals["Bulk two"].id]
    response = client.post(
        "/opportunities/bulk-assign",
        data={"oppo_ids": assigned_ids, "owner_id": "manager"},
    )
    assert response.status_code == 200
    assert "Đã phân công 2 Opportunity" in response.text
    with Session(db_engine) as session:  # type: ignore[arg-type]
        assert {session.get(Oppo, oppo_id).owner_id for oppo_id in assigned_ids} == {"manager"}  # type: ignore[union-attr]
        logs = list(session.exec(select(ManagerLog).where(ManagerLog.oppo_id.in_(assigned_ids))))
        assert len(logs) == 2
    protected = client.delete(f"/opportunities/{assigned_ids[0]}")
    assert protected.status_code == 204
    with Session(db_engine) as session:  # type: ignore[arg-type]
        closed = session.get(Oppo, assigned_ids[0])
        assert closed is not None
        assert closed.stage == Stage.CLOSED
        assert closed.close_at is not None
    deleted = client.delete(f"/opportunities/{deals['Delete me'].id}")
    assert deleted.status_code == 204
    with Session(db_engine) as session:  # type: ignore[arg-type]
        assert session.get(Oppo, deals["Delete me"].id) is None


def test_stage_change_requires_report_and_writes_exactly_one_log(web: tuple[TestClient, object, MemoryStorage]):
    client, db_engine, storage = web
    _login(client, "saler@test.local")
    missing = client.post(
        "/opportunities/deal/stage",
        data={"to_stage": "QUALIFY", "loss_reason": "", "report_title": "", "report_body": "", "seriousness": "MED"},
    )
    assert "REPORT_REQUIRED" in missing.text
    response = client.post(
        "/opportunities/deal/stage",
        data={"to_stage": "QUALIFY", "loss_reason": "", "report_title": "Discovery", "report_body": "Khách hàng xác nhận nhu cầu.", "seriousness": "HIGH"},
    )
    assert response.status_code == 200
    with Session(db_engine) as session:  # type: ignore[arg-type]
        assert session.get(Oppo, "deal").stage == Stage.QUALIFY  # type: ignore[union-attr]
        logs = list(session.exec(select(SalerLog).where(SalerLog.oppo_id == "deal")))
        assert len(logs) == 1
        assert logs[0].object_key in storage.objects


def test_team_pool_take_charge_request_is_audited(web: tuple[TestClient, object, MemoryStorage]):
    client, db_engine, _ = web
    _login(client, "saler@test.local")
    response = client.post("/opportunities/pooled/take-charge", data={"summary": "Có quan hệ trong ngành"})
    assert response.status_code == 200
    with Session(db_engine) as session:  # type: ignore[arg-type]
        log = session.exec(select(SalerLog).where(SalerLog.oppo_id == "pooled")).one()
        assert log.action.value == "TAKE_CHARGE_REQUEST"
        request_id = log.id
    client.post("/logout")
    _login(client, "manager@test.local")
    assert client.post(f"/logs/saler/{request_id}/decision", data={"decision": "approve"}).status_code == 200
    with Session(db_engine) as session:  # type: ignore[arg-type]
        assert session.get(Oppo, "pooled").owner_id == "saler"  # type: ignore[union-attr]
        actions = {log.action.value for log in session.exec(select(SalerLog).where(SalerLog.oppo_id == "pooled"))}
        assert actions == {"TAKE_CHARGE_REQUEST", "TAKE_CHARGE_APPROVED"}


def test_direct_dismissal_stores_reason_document_and_manager_report_uses_manager_log(
    web: tuple[TestClient, object, MemoryStorage],
):
    client, db_engine, storage = web
    _login(client, "director@test.local")
    response = client.post("/sales/outsider/kick", data={"summary": "Role removed; no open portfolio."})
    assert response.status_code == 200
    assert client.post(
        "/reports",
        data={"kind": "frequent", "title": "Director note", "body": "Review team capacity.", "seriousness": "HIGH"},
    ).status_code == 200
    with Session(db_engine) as session:  # type: ignore[arg-type]
        assert session.get(Sale, "outsider").status.value == "INACTIVE"  # type: ignore[union-attr]
        logs = list(session.exec(select(ManagerLog).where(ManagerLog.actor_id == "director")))
        assert {log.action.value for log in logs} == {"KICK_DIRECT", "MANAGER_REPORT"}
        assert all(log.object_key in storage.objects for log in logs)
