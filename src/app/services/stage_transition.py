from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from app.core.schema.models import LossReason, Oppo, Role, Sale, SalerAction, SalerLog, Seriousness, Stage, utcnow
from app.core.schema.report import report_document, report_id, report_key
from app.domain.result import Err, Ok, Result
from app.domain.stage import can_transition
from app.repo.oppo import get_oppo
from app.repo.scope import DataScope
from app.storage import Storage


def transition_stage(
    session: Session,
    storage: Storage,
    scope: DataScope,
    actor: Sale,
    oppo_id: str,
    to_stage: Stage,
    loss_reason: LossReason | None,
    title: str,
    body: str,
    seriousness: Seriousness,
) -> Result[SalerLog]:
    if actor.role != Role.SALER:
        return Err("ROLE_FORBIDDEN", "Chỉ Saler được đổi giai đoạn.")
    deal = get_oppo(session, scope, oppo_id)
    if deal is None or deal.owner_id != actor.id:
        return Err("OPPORTUNITY_NOT_FOUND", "Chỉ Saler đang phụ trách mới được đổi giai đoạn.")
    guard = can_transition(
        {"stage": deal.stage},
        to_stage,
        loss_reason,
        report_present=bool(title.strip() and body.strip()),
    )
    if isinstance(guard, Err):
        return guard

    return Ok(
        persist_stage_transition(
            session,
            storage,
            deal,
            actor,
            to_stage,
            loss_reason,
            title,
            body,
            seriousness,
        )
    )


def persist_stage_transition(
    session: Session,
    storage: Storage,
    deal: Oppo,
    actor: Sale,
    to_stage: Stage,
    loss_reason: LossReason | None,
    title: str,
    body: str,
    seriousness: Seriousness,
) -> SalerLog:
    rid = report_id("stage")
    key = report_key(actor, "stage", rid)
    storage.put(key, report_document("stage_transition", title, body, seriousness))
    log = SalerLog(
        actor_id=actor.id,
        action=SalerAction.STAGE_CHANGED,
        subject_sale_id=actor.id,
        oppo_id=deal.id,
        report_id=rid,
        object_key=key,
        seriousness=seriousness,
        summary=f"{deal.title}: {to_stage.value} — {title.strip()}",
    )
    try:
        deal.stage = to_stage
        deal.loss_reason = loss_reason if to_stage == Stage.LOST else None
        deal.close_at = utcnow() if to_stage in {Stage.WON, Stage.LOST} else None
        deal.update_at = utcnow()
        session.add(deal)
        session.add(log)
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        storage.delete(key)
        raise
    return log
