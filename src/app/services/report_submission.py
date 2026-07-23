from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from app.core.schema.models import ManagerAction, ManagerLog, Oppo, Role, Sale, SalerAction, SalerLog, Seriousness, utcnow
from app.core.schema.report import report_document, report_id, report_key
from app.domain.result import Err, Ok, Result
from app.repo.oppo import get_oppo
from app.repo.scope import DataScope
from app.storage import Storage


def submit(
    session: Session,
    storage: Storage,
    scope: DataScope,
    actor: Sale,
    kind: str,
    title: str,
    body: str,
    seriousness: Seriousness,
    oppo_id: str | None,
) -> Result[ManagerLog | SalerLog]:
    if oppo_id is not None and get_oppo(session, scope, oppo_id) is None:
        return Err("OPPORTUNITY_NOT_FOUND", "Opportunity ngoài phạm vi.")
    rid = report_id(kind)
    key = report_key(actor, kind, rid)
    storage.put(key, report_document(kind, title, body, seriousness))
    if actor.role == Role.SALER:
        action = SalerAction.FREQUENT_REPORT if kind == "frequent" else SalerAction.SALE_REPORT
        log: ManagerLog | SalerLog = SalerLog(
            actor_id=actor.id,
            action=action,
            subject_sale_id=actor.id,
            oppo_id=oppo_id,
            report_id=rid,
            object_key=key,
            seriousness=seriousness,
            summary=title.strip(),
        )
    else:
        log = ManagerLog(
            actor_id=actor.id,
            action=ManagerAction.MANAGER_REPORT,
            oppo_id=oppo_id,
            report_id=rid,
            object_key=key,
            seriousness=seriousness,
            summary=title.strip(),
        )
    try:
        session.add(log)
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        storage.delete(key)
        raise
    return Ok(log)


def update_opportunity(
    session: Session,
    storage: Storage,
    scope: DataScope,
    actor: Sale,
    oppo_id: str,
    title: str,
    value: float,
    product: str | None,
    note: str | None,
    due_at: str | None,
    report_title: str,
    report_body: str,
    seriousness: Seriousness,
) -> Result[Oppo]:
    deal = get_oppo(session, scope, oppo_id)
    if deal is None:
        return Err("OPPORTUNITY_NOT_FOUND", "Opportunity ngoài phạm vi.")
    if actor.role == Role.SALER and (deal.owner_id != actor.id or not report_title.strip() or not report_body.strip()):
        return Err("REPORT_REQUIRED", "Saler cần Sale Report đầy đủ khi sửa cơ hội.")
    object_key: str | None = None
    rid: str | None = None
    if actor.role == Role.SALER:
        rid = report_id("sale")
        object_key = report_key(actor, "sale", rid)
        storage.put(object_key, report_document("sale_update", report_title, report_body, seriousness))
    try:
        deal.title = title.strip()
        deal.value = value
        deal.prod = product or None
        deal.note = note or None
        deal.due_at = datetime.fromisoformat(due_at) if due_at else None
        deal.update_at = utcnow()
        session.add(deal)
        if actor.role == Role.SALER:
            session.add(
                SalerLog(
                    actor_id=actor.id,
                    action=SalerAction.SALE_REPORT,
                    subject_sale_id=actor.id,
                    oppo_id=deal.id,
                    report_id=rid,
                    object_key=object_key,
                    seriousness=seriousness,
                    summary=report_title.strip(),
                )
            )
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        if object_key is not None:
            storage.delete(object_key)
        raise
    return Ok(deal)
