from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from app.core.schema.models import ManagerAction, ManagerLog, Role, Sale, SaleStatus, Seriousness, utcnow
from app.core.schema.report import report_document, report_id, report_key
from app.domain.result import Err, Ok, Result
from app.domain.sale import can_deactivate
from app.repo.agency import owned_agency_count
from app.repo.log import get_manager_log
from app.repo.oppo import owned_open_oppo_count
from app.repo.sale import get_sale
from app.repo.scope import DataScope
from app.storage import Storage


def propose(
    session: Session,
    storage: Storage,
    scope: DataScope,
    actor: Sale,
    sale_id: str,
    summary: str,
    seriousness: Seriousness,
) -> Result[ManagerLog]:
    if actor.role != Role.MANAGER:
        return Err("ROLE_FORBIDDEN", "Chỉ Manager được đề xuất nghỉ việc.")
    target = get_sale(session, scope, sale_id)
    if target is None or target.role != Role.SALER or target.mgr_id != actor.id:
        return Err("SALE_NOT_FOUND", "Không tìm thấy Saler trong đội.")
    rid = report_id("kick")
    key = report_key(actor, "kick", rid)
    storage.put(key, report_document("dismissal_proposal", f"Đề xuất nghỉ việc: {target.name}", summary, seriousness))
    log = ManagerLog(
        actor_id=actor.id,
        action=ManagerAction.KICK_PROPOSED,
        subject_sale_id=target.id,
        report_id=rid,
        object_key=key,
        seriousness=seriousness,
        summary=summary.strip(),
    )
    try:
        session.add(log)
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        storage.delete(key)
        raise
    return Ok(log)


def dismiss_directly(
    session: Session,
    storage: Storage,
    scope: DataScope,
    actor: Sale,
    sale_id: str,
    summary: str,
) -> Result[ManagerLog]:
    if actor.role != Role.DIRECTOR:
        return Err("ROLE_FORBIDDEN", "Chỉ Director được dismiss trực tiếp.")
    target = get_sale(session, scope, sale_id)
    if target is None or target.role != Role.SALER:
        return Err("SALE_NOT_FOUND", "Không tìm thấy nhân sự.")
    guard = can_deactivate(
        target.status,
        owned_agency_count(session, scope, target.id),
        owned_open_oppo_count(session, scope, target.id),
    )
    if isinstance(guard, Err):
        return guard
    rid = report_id("kick")
    key = report_key(actor, "kick", rid)
    storage.put(key, report_document("direct_dismissal", f"Dismiss: {target.name}", summary, Seriousness.CRITICAL))
    log = ManagerLog(
        actor_id=actor.id,
        action=ManagerAction.KICK_DIRECT,
        subject_sale_id=target.id,
        report_id=rid,
        object_key=key,
        seriousness=Seriousness.CRITICAL,
        summary=summary.strip(),
    )
    try:
        target.status = SaleStatus.INACTIVE
        target.update_at = utcnow()
        session.add(target)
        session.add(log)
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        storage.delete(key)
        raise
    return Ok(log)


def decide(
    session: Session,
    scope: DataScope,
    actor: Sale,
    log_id: str,
    decision: str,
) -> Result[ManagerLog]:
    if actor.role != Role.DIRECTOR:
        return Err("ROLE_FORBIDDEN", "Chỉ Director được xử lý đề xuất nghỉ việc.")
    if decision not in {"approve", "reject"}:
        return Err("INVALID_DECISION", "Quyết định không hợp lệ.")
    proposal = get_manager_log(session, scope, log_id)
    if proposal is None or proposal.action != ManagerAction.KICK_PROPOSED or proposal.subject_sale_id is None:
        return Err("PROPOSAL_NOT_FOUND", "Không tìm thấy đề xuất.")
    target = get_sale(session, scope, proposal.subject_sale_id)
    if target is None:
        return Err("SALE_NOT_FOUND", "Không tìm thấy nhân sự.")
    action = ManagerAction.KICK_REJECTED
    if decision == "approve":
        guard = can_deactivate(
            target.status,
            owned_agency_count(session, scope, target.id),
            owned_open_oppo_count(session, scope, target.id),
        )
        if isinstance(guard, Err):
            return guard
        target.status = SaleStatus.INACTIVE
        target.update_at = utcnow()
        session.add(target)
        action = ManagerAction.KICK_APPROVED
    log = ManagerLog(
        actor_id=actor.id,
        action=action,
        subject_sale_id=target.id,
        report_id=proposal.report_id,
        object_key=proposal.object_key,
        seriousness=proposal.seriousness,
        summary=f"{decision}: {proposal.summary}",
    )
    session.add(log)
    session.commit()
    return Ok(log)
