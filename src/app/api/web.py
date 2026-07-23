from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.auth import current_user, require_roles, verify_password
from app.db import get_session
from app.domain.result import Err
from app.core.schema.models import (
    LossReason,
    Role,
    Sale,
    SaleStatus,
    Seriousness,
    STAGE_ORDER,
    Stage,
    utcnow,
)
from app.rec.service import recommend
from app.repo.agency import find_agencies, get_agency
from app.repo.log import find_logs
from app.repo.oppo import find_oppo, get_oppo
from app.repo.sale import find_sales, get_sale, get_sale_by_email
from app.repo.scope import DataScope
from app.repo.stats import dashboard_kpis, loss_summaries, monthly_revenue, rep_workload, stage_summaries, team_rankings
from app.services import (
    agency_assignment,
    agency_management,
    opportunity_assignment,
    opportunity_management,
    report_access,
    report_submission,
    sale_management,
    sale_offboarding,
    stage_transition,
)
from app.services.overview import team_kanban
from app.storage import Storage, get_storage


router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")


def _redirect(path: str, status_code: int = status.HTTP_303_SEE_OTHER) -> RedirectResponse:
    return RedirectResponse(path, status_code=status_code)


def _flash(request: Request, message: str, kind: str = "info") -> None:
    request.session["flash"] = {"message": message, "kind": kind}


def _context(request: Request, user: Sale | None = None, **values: object) -> dict[str, object]:
    return {"request": request, "user": user, "flash": request.session.pop("flash", None), **values}


def _scope(session: Session, user: Sale) -> DataScope:
    return DataScope.for_actor(session, user)


@router.get("/login")
def login_page(request: Request) -> Response:
    return templates.TemplateResponse(request=request, name="login.html", context=_context(request))


@router.get("/health")
def health(storage: Storage = Depends(get_storage)) -> dict[str, str]:
    report_status = "ok" if storage.healthy() else "degraded"
    return {"status": "ok" if report_status == "ok" else "degraded", "database": "ok", "reports": report_status}


@router.post("/login")
def login(
    request: Request,
    email: str = Form(),
    password: str = Form(),
    session: Session = Depends(get_session),
) -> Response:
    user = get_sale_by_email(session, email.strip().lower())
    if user is None or user.status != SaleStatus.ACTIVE or not verify_password(password, user.pass_hash):
        _flash(request, "Email hoặc mật khẩu không đúng.", "error")
        return _redirect("/login")
    request.session["sale_id"] = user.id
    return _redirect("/dashboard")


@router.post("/logout")
def logout(request: Request) -> Response:
    request.session.clear()
    return _redirect("/login")


@router.get("/")
def home(user: Sale = Depends(current_user)) -> Response:
    return _redirect("/dashboard")


@router.get("/dashboard")
def dashboard(
    request: Request,
    user: Sale = Depends(current_user),
    session: Session = Depends(get_session),
) -> Response:
    scope = _scope(session, user)
    kpis = dashboard_kpis(session, scope)
    stages = stage_summaries(session, scope)
    losses = loss_summaries(session, scope)
    months = monthly_revenue(session, scope)
    workload = rep_workload(session, scope) if user.role != Role.SALER else []
    rankings = team_rankings(session, scope) if user.role != Role.SALER else []
    kanban = team_kanban(session, scope) if user.role == Role.MANAGER else None
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context=_context(
            request,
            user,
            kpis=kpis,
            stages=stages,
            losses=losses,
            months=months,
            workload=workload,
            rankings=rankings,
            kanban=kanban,
        ),
    )


@router.get("/sales")
def sales_page(
    request: Request,
    page: int = 1,
    user: Sale = Depends(current_user),
    session: Session = Depends(get_session),
) -> Response:
    sales = find_sales(session, _scope(session, user), page=page)
    managers = []
    if user.role == Role.DIRECTOR:
        managers = find_sales(
            session,
            DataScope.global_for(user.id),
            role=Role.MANAGER,
            status=SaleStatus.ACTIVE,
            per_page=100,
        ).items
    return templates.TemplateResponse(
        request=request,
        name="sales.html",
        context=_context(request, user, sales=sales, managers=managers, roles=list(Role), statuses=list(SaleStatus)),
    )


@router.get("/teams/{manager_id}")
def team_detail(
    manager_id: str,
    request: Request,
    user: Sale = Depends(require_roles(Role.MANAGER, Role.DIRECTOR)),
    session: Session = Depends(get_session),
) -> Response:
    if user.role == Role.MANAGER and manager_id != user.id:
        raise HTTPException(status_code=403, detail="Chỉ xem được đội của mình.")
    manager = get_sale(session, DataScope.global_for(user.id), manager_id)
    if manager is None or manager.role != Role.MANAGER:
        raise HTTPException(status_code=404, detail="Không tìm thấy Manager.")
    member_ids = tuple(sale.id for sale in find_sales(
        session,
        DataScope.global_for(user.id),
        role=Role.SALER,
        mgr_id=manager.id,
        per_page=100,
    ).items)
    team_scope = DataScope(actor_id=user.id, owner_ids=(manager.id, *member_ids))
    return templates.TemplateResponse(
        request=request,
        name="team.html",
        context=_context(
            request,
            user,
            manager=manager,
            kpis=dashboard_kpis(session, team_scope),
            stages=stage_summaries(session, team_scope),
            months=monthly_revenue(session, team_scope),
            workload=rep_workload(session, team_scope),
            kanban=team_kanban(session, team_scope),
        ),
    )


@router.post("/sales")
def create_sale(
    request: Request,
    name: str = Form(),
    email: str = Form(),
    password: str = Form(),
    role: Role = Form(),
    region: str = Form(),
    mgr_id: str | None = Form(default=None),
    phone: str | None = Form(default=None),
    user: Sale = Depends(require_roles(Role.DIRECTOR)),
    session: Session = Depends(get_session),
) -> Response:
    result = sale_management.create(session, user, name, email, password, role, region, mgr_id, phone)
    if isinstance(result, Err):
        _flash(request, f"{result.code}: {result.message}", "error")
        return _redirect("/sales")
    _flash(request, f"Đã tạo {result.data.name}.", "success")
    return _redirect("/sales")


@router.post("/sales/{sale_id}/position")
def update_position(
    sale_id: str,
    request: Request,
    countries: str = Form(),
    user: Sale = Depends(require_roles(Role.MANAGER, Role.DIRECTOR)),
    session: Session = Depends(get_session),
) -> Response:
    result = sale_management.update_position(session, _scope(session, user), user, sale_id, countries)
    if isinstance(result, Err):
        raise HTTPException(status_code=404, detail=result.message)
    _flash(request, "Đã cập nhật Position.", "success")
    return _redirect("/sales")


@router.get("/sales/{sale_id}")
def sale_detail(
    sale_id: str,
    request: Request,
    user: Sale = Depends(current_user),
    session: Session = Depends(get_session),
) -> Response:
    target = get_sale(session, _scope(session, user), sale_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Nhân sự ngoài phạm vi.")
    return templates.TemplateResponse(request=request, name="sale_detail.html", context=_context(request, user, target=target))


@router.post("/sales/{sale_id}/update")
def update_sale(
    sale_id: str,
    request: Request,
    name: str = Form(),
    region: str = Form(),
    phone: str | None = Form(default=None),
    user: Sale = Depends(require_roles(Role.MANAGER, Role.DIRECTOR)),
    session: Session = Depends(get_session),
) -> Response:
    result = sale_management.update_profile(session, _scope(session, user), user, sale_id, name, region, phone)
    if isinstance(result, Err):
        raise HTTPException(status_code=404, detail=result.message)
    _flash(request, "Đã cập nhật hồ sơ.", "success")
    return _redirect(f"/sales/{sale_id}")


@router.post("/sales/{sale_id}/kick/propose")
def propose_dismissal(
    sale_id: str,
    request: Request,
    summary: str = Form(),
    seriousness: Seriousness = Form(default=Seriousness.HIGH),
    user: Sale = Depends(require_roles(Role.MANAGER)),
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
) -> Response:
    result = sale_offboarding.propose(session, storage, _scope(session, user), user, sale_id, summary, seriousness)
    if isinstance(result, Err):
        raise HTTPException(status_code=404, detail=result.message)
    _flash(request, "Đã gửi đề xuất cho Director.", "success")
    return _redirect("/sales")


@router.post("/sales/{sale_id}/kick")
def dismiss_sale(
    sale_id: str,
    request: Request,
    summary: str = Form(),
    user: Sale = Depends(require_roles(Role.DIRECTOR)),
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
) -> Response:
    result = sale_offboarding.dismiss_directly(
        session, storage, DataScope.global_for(user.id), user, sale_id, summary
    )
    if isinstance(result, Err):
        if result.code == "SALE_NOT_FOUND":
            raise HTTPException(status_code=404, detail=result.message)
        _flash(request, f"{result.code}: {result.message}", "error")
        return _redirect("/sales")
    _flash(request, "Đã ngừng hoạt động nhân sự.", "success")
    return _redirect("/sales")


@router.get("/agencies")
def agencies_page(
    request: Request,
    page: int = 1,
    q: str | None = None,
    user: Sale = Depends(current_user),
    session: Session = Depends(get_session),
) -> Response:
    scope = _scope(session, user)
    agencies = find_agencies(session, scope, query=q, page=page)
    candidates = []
    if user.role != Role.SALER:
        candidates = find_sales(
            session,
            scope,
            role=Role.SALER,
            status=SaleStatus.ACTIVE,
            per_page=100,
        ).items
    names = {sale.id: sale.name for sale in candidates}
    if user.role == Role.SALER:
        names[user.id] = user.name
    return templates.TemplateResponse(
        request=request,
        name="agencies.html",
        context=_context(request, user, agencies=agencies, candidates=candidates, owner_names=names, q=q or ""),
    )


@router.post("/agencies")
def create_agency(
    request: Request,
    code: str = Form(),
    name: str = Form(),
    sector: str | None = Form(default=None),
    loc: str | None = Form(default=None),
    user: Sale = Depends(require_roles(Role.DIRECTOR)),
    session: Session = Depends(get_session),
) -> Response:
    result = agency_management.create(session, user, code, name, sector, loc)
    if isinstance(result, Err):
        raise HTTPException(status_code=403, detail=result.message)
    _flash(request, "Đã tạo Agency trong HQ pool.", "success")
    return _redirect("/agencies")


@router.post("/agencies/{agency_id}/assign")
def assign_agency(
    agency_id: str,
    request: Request,
    owner_id: str = Form(),
    reason: str | None = Form(default=None),
    user: Sale = Depends(require_roles(Role.MANAGER, Role.DIRECTOR)),
    session: Session = Depends(get_session),
) -> Response:
    result = agency_assignment.assign(session, _scope(session, user), user, agency_id, owner_id, reason)
    if isinstance(result, Err):
        raise HTTPException(status_code=404, detail=result.message)
    _flash(request, "Đã chuyển Agency và cơ hội mở.", "success")
    return _redirect("/agencies")


@router.get("/agencies/{agency_id}")
def agency_detail(
    agency_id: str,
    request: Request,
    user: Sale = Depends(current_user),
    session: Session = Depends(get_session),
) -> Response:
    agency = get_agency(session, _scope(session, user), agency_id)
    if agency is None:
        raise HTTPException(status_code=404, detail="Agency ngoài phạm vi.")
    owner = get_sale(session, _scope(session, user), agency.owner_id) if agency.owner_id else None
    return templates.TemplateResponse(
        request=request,
        name="agency_detail.html",
        context=_context(request, user, agency=agency, owner=owner),
    )


@router.post("/agencies/{agency_id}/update")
def update_agency(
    agency_id: str,
    request: Request,
    name: str = Form(),
    sector: str | None = Form(default=None),
    loc: str | None = Form(default=None),
    user: Sale = Depends(require_roles(Role.MANAGER, Role.DIRECTOR)),
    session: Session = Depends(get_session),
) -> Response:
    result = agency_management.update(session, _scope(session, user), user, agency_id, name, sector, loc)
    if isinstance(result, Err):
        raise HTTPException(status_code=404, detail=result.message)
    _flash(request, "Đã cập nhật Agency.", "success")
    return _redirect(f"/agencies/{agency_id}")


@router.get("/opportunities")
def opportunities_page(
    request: Request,
    page: int = 1,
    q: str | None = None,
    user: Sale = Depends(current_user),
    session: Session = Depends(get_session),
) -> Response:
    scope = _scope(session, user)
    opportunities = find_oppo(session, scope, query=q, page=page)
    agencies = find_agencies(session, scope, per_page=100).items
    candidates = []
    if user.role != Role.SALER:
        role = Role.MANAGER if user.role == Role.DIRECTOR else Role.SALER
        candidates = find_sales(session, scope, role=role, status=SaleStatus.ACTIVE, per_page=100).items
    owner_ids = {deal.owner_id for deal in opportunities.items}
    owner_names: dict[str, str] = {}
    for owner_id in owner_ids:
        owner = get_sale(session, scope, owner_id)
        if owner is not None:
            owner_names[owner_id] = owner.name
    agency_names = {agency.id: agency.name for agency in agencies}
    return templates.TemplateResponse(
        request=request,
        name="opportunities.html",
        context=_context(
            request,
            user,
            opportunities=opportunities,
            agencies=agencies,
            candidates=candidates,
            owner_names=owner_names,
            agency_names=agency_names,
            stages=[*STAGE_ORDER, Stage.LOST],
            loss_reasons=list(LossReason),
            seriousness=list(Seriousness),
            q=q or "",
        ),
    )


@router.post("/opportunities")
def create_opportunity(
    request: Request,
    title: str = Form(),
    agency_id: str = Form(),
    value: float = Form(),
    product: str | None = Form(default=None),
    due_at: str | None = Form(default=None),
    user: Sale = Depends(current_user),
    session: Session = Depends(get_session),
) -> Response:
    result = opportunity_management.create(
        session, _scope(session, user), user, title, agency_id, value, product, due_at
    )
    if isinstance(result, Err):
        raise HTTPException(status_code=404, detail=result.message)
    _flash(request, "Đã tạo Opportunity.", "success")
    return _redirect("/opportunities")


@router.post("/opportunities/{oppo_id}/assign")
def assign_opportunity(
    oppo_id: str,
    request: Request,
    owner_id: str = Form(),
    user: Sale = Depends(require_roles(Role.MANAGER, Role.DIRECTOR)),
    session: Session = Depends(get_session),
) -> Response:
    result = opportunity_assignment.assign(session, _scope(session, user), user, oppo_id, owner_id)
    if isinstance(result, Err):
        raise HTTPException(status_code=404, detail=result.message)
    _flash(request, "Đã phân công Opportunity.", "success")
    return _redirect("/opportunities")


@router.post("/opportunities/bulk-assign")
def bulk_assign_opportunities(
    request: Request,
    oppo_ids: list[str] | None = Form(default=None),
    owner_id: str = Form(),
    user: Sale = Depends(require_roles(Role.DIRECTOR)),
    session: Session = Depends(get_session),
) -> Response:
    result = opportunity_assignment.bulk_assign(
        session, DataScope.global_for(user.id), user, oppo_ids or [], owner_id
    )
    if isinstance(result, Err):
        _flash(request, f"{result.code}: {result.message}", "error")
        return _redirect("/opportunities")
    _flash(request, f"Đã phân công {len(result.data)} Opportunity.", "success")
    return _redirect("/opportunities")


@router.delete("/opportunities/{oppo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_opportunity(
    oppo_id: str,
    user: Sale = Depends(require_roles(Role.DIRECTOR)),
    session: Session = Depends(get_session),
) -> Response:
    result = opportunity_management.delete(
        session, DataScope.global_for(user.id), user, oppo_id
    )
    if isinstance(result, Err):
        if result.code == "OPPORTUNITY_NOT_FOUND":
            raise HTTPException(status_code=404, detail=result.message)
        if result.code == "ROLE_FORBIDDEN":
            raise HTTPException(status_code=403, detail=result.message)
        raise HTTPException(status_code=409, detail=f"{result.code}: {result.message}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/opportunities/{oppo_id}")
def opportunity_detail(
    oppo_id: str,
    request: Request,
    user: Sale = Depends(current_user),
    session: Session = Depends(get_session),
) -> Response:
    deal = get_oppo(session, _scope(session, user), oppo_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Opportunity ngoài phạm vi.")
    scope = _scope(session, user)
    agency = get_agency(session, scope, deal.agency_id)
    owner = get_sale(session, scope, deal.owner_id)
    return templates.TemplateResponse(
        request=request,
        name="opportunity_detail.html",
        context=_context(request, user, deal=deal, agency=agency, owner=owner, seriousness=list(Seriousness)),
    )


@router.post("/opportunities/{oppo_id}/update")
def update_opportunity(
    oppo_id: str,
    request: Request,
    title: str = Form(),
    value: float = Form(),
    product: str | None = Form(default=None),
    note: str | None = Form(default=None),
    due_at: str | None = Form(default=None),
    report_title: str = Form(default=""),
    report_body: str = Form(default=""),
    seriousness: Seriousness = Form(default=Seriousness.MED),
    user: Sale = Depends(current_user),
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
) -> Response:
    result = report_submission.update_opportunity(
        session,
        storage,
        _scope(session, user),
        user,
        oppo_id,
        title,
        value,
        product,
        note,
        due_at,
        report_title,
        report_body,
        seriousness,
    )
    if isinstance(result, Err):
        if result.code == "OPPORTUNITY_NOT_FOUND":
            raise HTTPException(status_code=404, detail=result.message)
        _flash(request, f"{result.code}: {result.message}", "error")
        return _redirect(f"/opportunities/{oppo_id}")
    _flash(request, "Đã cập nhật Opportunity.", "success")
    return _redirect(f"/opportunities/{oppo_id}")


@router.post("/opportunities/{oppo_id}/stage")
def change_stage(
    oppo_id: str,
    request: Request,
    to_stage: Stage = Form(),
    loss_reason: str | None = Form(default=None),
    report_title: str = Form(default=""),
    report_body: str = Form(default=""),
    seriousness: Seriousness = Form(default=Seriousness.MED),
    user: Sale = Depends(require_roles(Role.SALER)),
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
) -> Response:
    parsed_loss_reason = LossReason(loss_reason) if loss_reason else None
    result = stage_transition.transition_stage(
        session,
        storage,
        _scope(session, user),
        user,
        oppo_id,
        to_stage,
        parsed_loss_reason,
        report_title,
        report_body,
        seriousness,
    )
    if isinstance(result, Err):
        if result.code == "OPPORTUNITY_NOT_FOUND":
            raise HTTPException(status_code=404, detail=result.message)
        _flash(request, f"{result.code}: {result.message}", "error")
        return _redirect("/opportunities")
    _flash(request, "Đã đổi giai đoạn và lưu báo cáo.", "success")
    return _redirect("/opportunities")


@router.post("/opportunities/{oppo_id}/take-charge")
def request_take_charge(
    oppo_id: str,
    request: Request,
    summary: str = Form(),
    user: Sale = Depends(require_roles(Role.SALER)),
    session: Session = Depends(get_session),
) -> Response:
    result = opportunity_assignment.request_take_charge(session, user, oppo_id, summary)
    if isinstance(result, Err):
        raise HTTPException(status_code=403, detail=result.message)
    _flash(request, "Đã gửi yêu cầu nhận cơ hội.", "success")
    return _redirect("/opportunities")


@router.get("/opportunities/{oppo_id}/recommendations")
def recommendations(
    oppo_id: str,
    request: Request,
    user: Sale = Depends(require_roles(Role.MANAGER, Role.DIRECTOR)),
    session: Session = Depends(get_session),
) -> Response:
    scope = _scope(session, user)
    deal = get_oppo(session, scope, oppo_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Cơ hội ngoài phạm vi.")
    candidate_scope = scope
    candidates = find_sales(
        session,
        candidate_scope,
        role=Role.SALER,
        status=SaleStatus.ACTIVE,
        per_page=100,
    ).items
    ranked = recommend(session, deal, candidates, utcnow())
    names = {sale.id: sale.name for sale in candidates}
    return templates.TemplateResponse(
        request=request,
        name="recommendations.html",
        context=_context(request, user, deal=deal, ranked=ranked[:5], names=names),
    )


@router.post("/reports")
def create_report(
    request: Request,
    kind: str = Form(),
    title: str = Form(),
    body: str = Form(),
    seriousness: Seriousness = Form(default=Seriousness.MED),
    oppo_id: str | None = Form(default=None),
    user: Sale = Depends(current_user),
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
) -> Response:
    result = report_submission.submit(
        session, storage, _scope(session, user), user, kind, title, body, seriousness, oppo_id or None
    )
    if isinstance(result, Err):
        raise HTTPException(status_code=404, detail=result.message)
    _flash(request, "Đã lưu báo cáo.", "success")
    return _redirect("/logs")


@router.get("/logs")
def logs_page(
    request: Request,
    q: str | None = None,
    user: Sale = Depends(current_user),
    session: Session = Depends(get_session),
) -> Response:
    scope = _scope(session, user)
    manager_logs, saler_logs = find_logs(session, scope, q)
    sale_ids = {log.actor_id for log in manager_logs}
    sale_ids.update(log.actor_id for log in saler_logs)
    sale_ids.update(log.subject_sale_id for log in manager_logs if log.subject_sale_id)
    sale_ids.update(log.subject_sale_id for log in saler_logs if log.subject_sale_id)
    names = {sale_id: sale.name for sale_id in sale_ids if (sale := get_sale(session, scope, sale_id)) is not None}
    return templates.TemplateResponse(
        request=request,
        name="logs.html",
        context=_context(
            request,
            user,
            manager_logs=manager_logs,
            saler_logs=saler_logs,
            names=names,
            seriousness=list(Seriousness),
            q=q or "",
        ),
    )


@router.get("/logs/{kind}/{log_id}/report")
def open_report(
    kind: str,
    log_id: str,
    user: Sale = Depends(current_user),
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
) -> Response:
    scope = _scope(session, user)
    result = report_access.presign(session, storage, scope, kind, log_id)
    if isinstance(result, Err):
        raise HTTPException(status_code=404, detail=result.message)
    return RedirectResponse(result.data, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.post("/logs/manager/{log_id}/decision")
def decide_dismissal(
    log_id: str,
    request: Request,
    decision: str = Form(),
    user: Sale = Depends(require_roles(Role.DIRECTOR)),
    session: Session = Depends(get_session),
) -> Response:
    result = sale_offboarding.decide(session, DataScope.global_for(user.id), user, log_id, decision)
    if isinstance(result, Err):
        if result.code in {"PROPOSAL_NOT_FOUND", "SALE_NOT_FOUND"}:
            raise HTTPException(status_code=404, detail=result.message)
        _flash(request, f"{result.code}: {result.message}", "error")
        return _redirect("/logs")
    _flash(request, "Đã ghi nhận quyết định.", "success")
    return _redirect("/logs")


@router.post("/logs/saler/{log_id}/decision")
def decide_take_charge(
    log_id: str,
    request: Request,
    decision: str = Form(),
    user: Sale = Depends(require_roles(Role.MANAGER)),
    session: Session = Depends(get_session),
) -> Response:
    result = opportunity_assignment.decide_take_charge(session, _scope(session, user), user, log_id, decision)
    if isinstance(result, Err):
        if result.code == "REQUEST_NOT_FOUND":
            raise HTTPException(status_code=404, detail=result.message)
        if result.code == "REQUEST_OUT_OF_SCOPE":
            raise HTTPException(status_code=403, detail=result.message)
        _flash(request, f"{result.code}: {result.message}", "error")
        return _redirect("/logs")
    _flash(request, "Đã xử lý yêu cầu nhận cơ hội.", "success")
    return _redirect("/logs")
