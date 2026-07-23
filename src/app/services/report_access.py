from __future__ import annotations

from sqlmodel import Session

from app.domain.result import Err, Ok, Result
from app.repo.log import get_manager_log, get_saler_log
from app.repo.scope import DataScope
from app.storage import Storage


def presign(
    session: Session,
    storage: Storage,
    scope: DataScope,
    kind: str,
    log_id: str,
) -> Result[str]:
    if kind == "manager":
        manager_log = get_manager_log(session, scope, log_id)
        object_key = manager_log.object_key if manager_log is not None else None
    else:
        saler_log = get_saler_log(session, scope, log_id)
        object_key = saler_log.object_key if saler_log is not None else None
    if object_key is None:
        return Err("REPORT_NOT_FOUND", "Không có báo cáo trong phạm vi.")
    return Ok(storage.presign(object_key))
