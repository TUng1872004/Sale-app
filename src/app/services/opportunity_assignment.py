from __future__ import annotations

from sqlmodel import Session

from app.core.schema.models import (
    ManagerAction,
    ManagerLog,
    OPEN_STAGES,
    Role,
    Sale,
    SalerAction,
    SalerLog,
    Seriousness,
    utcnow,
)
from app.domain.result import Err, Ok, Result
from app.repo.log import get_saler_log
from app.repo.oppo import get_oppo, get_oppo_many
from app.repo.sale import get_sale
from app.repo.scope import DataScope


def assign(
    session: Session,
    scope: DataScope,
    actor: Sale,
    oppo_id: str,
    owner_id: str,
) -> Result[ManagerLog]:
    if actor.role not in {Role.MANAGER, Role.DIRECTOR}:
        return Err("ROLE_FORBIDDEN", "Chỉ Manager hoặc Director được phân công Opportunity.")
    deal = get_oppo(session, scope, oppo_id)
    target = get_sale(session, scope, owner_id)
    expected_role = Role.MANAGER if actor.role == Role.DIRECTOR else Role.SALER
    if deal is None or target is None or target.role != expected_role:
        return Err("ASSIGNMENT_NOT_FOUND", "Cơ hội hoặc người nhận ngoài phạm vi.")
    if deal.stage not in OPEN_STAGES:
        return Err("OPPORTUNITY_CLOSED", "Không thể phân công Opportunity đã đóng.")
    deal.owner_id = target.id
    deal.update_at = utcnow()
    log = ManagerLog(
        actor_id=actor.id,
        action=ManagerAction.ASSIGN_TEAM if expected_role == Role.MANAGER else ManagerAction.ASSIGN_SALER,
        subject_sale_id=target.id,
        oppo_id=deal.id,
        summary=f"Phân công {deal.title} cho {target.name}",
    )
    session.add(deal)
    session.add(log)
    session.commit()
    return Ok(log)


def bulk_assign(
    session: Session,
    scope: DataScope,
    actor: Sale,
    oppo_ids: list[str],
    owner_id: str,
) -> Result[list[ManagerLog]]:
    if actor.role != Role.DIRECTOR:
        return Err("ROLE_FORBIDDEN", "Chỉ Director được bulk assign Opportunity.")
    unique_ids = list(dict.fromkeys(oppo_ids))
    if not unique_ids:
        return Err("SELECTION_REQUIRED", "Hãy chọn ít nhất một Opportunity.")
    target = get_sale(session, scope, owner_id)
    if target is None or target.role != Role.MANAGER:
        return Err("ASSIGNMENT_NOT_FOUND", "Team nhận Opportunity ngoài phạm vi.")
    deals = get_oppo_many(session, scope, unique_ids)
    if len(deals) != len(unique_ids):
        return Err("ASSIGNMENT_NOT_FOUND", "Có Opportunity ngoài phạm vi.")
    if any(deal.stage not in OPEN_STAGES for deal in deals):
        return Err("OPPORTUNITY_CLOSED", "Danh sách có Opportunity đã đóng.")
    logs: list[ManagerLog] = []
    for deal in deals:
        deal.owner_id = target.id
        deal.update_at = utcnow()
        log = ManagerLog(
            actor_id=actor.id,
            action=ManagerAction.ASSIGN_TEAM,
            subject_sale_id=target.id,
            oppo_id=deal.id,
            summary=f"Bulk assign {deal.title} cho {target.name}",
        )
        session.add(deal)
        session.add(log)
        logs.append(log)
    session.commit()
    return Ok(logs)


def request_take_charge(
    session: Session,
    actor: Sale,
    oppo_id: str,
    summary: str,
) -> Result[SalerLog]:
    if actor.role != Role.SALER:
        return Err("ROLE_FORBIDDEN", "Chỉ Saler được yêu cầu nhận cơ hội.")
    if actor.mgr_id is None:
        return Err("TEAM_POOL_REQUIRED", "Saler chưa thuộc đội.")
    pool_scope = DataScope(actor_id=actor.id, owner_ids=(actor.mgr_id,))
    deal = get_oppo(session, pool_scope, oppo_id)
    owner = get_sale(session, pool_scope, actor.mgr_id)
    if deal is None or owner is None or owner.role != Role.MANAGER:
        return Err("TEAM_POOL_REQUIRED", "Chỉ yêu cầu cơ hội trong pool của đội.")
    log = SalerLog(
        actor_id=actor.id,
        action=SalerAction.TAKE_CHARGE_REQUEST,
        subject_sale_id=actor.id,
        oppo_id=deal.id,
        seriousness=Seriousness.MED,
        summary=summary.strip(),
    )
    session.add(log)
    session.commit()
    return Ok(log)


def decide_take_charge(
    session: Session,
    scope: DataScope,
    actor: Sale,
    log_id: str,
    decision: str,
) -> Result[SalerLog]:
    if actor.role != Role.MANAGER:
        return Err("ROLE_FORBIDDEN", "Chỉ Manager được xử lý yêu cầu nhận cơ hội.")
    if decision not in {"approve", "reject"}:
        return Err("INVALID_DECISION", "Quyết định không hợp lệ.")
    proposal = get_saler_log(session, scope, log_id)
    if proposal is None or proposal.action != SalerAction.TAKE_CHARGE_REQUEST or proposal.oppo_id is None:
        return Err("REQUEST_NOT_FOUND", "Không tìm thấy yêu cầu.")
    requester = get_sale(session, scope, proposal.actor_id)
    deal = get_oppo(session, scope, proposal.oppo_id)
    if requester is None or requester.mgr_id != actor.id or deal is None:
        return Err("REQUEST_OUT_OF_SCOPE", "Yêu cầu ngoài phạm vi đội.")
    action = SalerAction.TAKE_CHARGE_REJECTED
    if decision == "approve":
        if deal.owner_id != actor.id or deal.stage not in OPEN_STAGES:
            return Err("TEAM_POOL_CHANGED", "Cơ hội không còn trong pool của đội.")
        deal.owner_id = requester.id
        deal.update_at = utcnow()
        session.add(deal)
        action = SalerAction.TAKE_CHARGE_APPROVED
    log = SalerLog(
        actor_id=actor.id,
        action=action,
        subject_sale_id=requester.id,
        oppo_id=deal.id,
        seriousness=proposal.seriousness,
        summary=f"{decision}: {proposal.summary}",
    )
    session.add(log)
    session.commit()
    return Ok(log)
