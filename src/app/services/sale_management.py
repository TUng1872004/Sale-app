from __future__ import annotations

from sqlmodel import Session

from app.auth import hash_password
from app.core.schema.models import Role, Sale, utcnow
from app.domain.result import Err, Ok, Result
from app.repo.sale import get_sale
from app.repo.scope import DataScope


def create(
    session: Session,
    actor: Sale,
    name: str,
    email: str,
    password: str,
    role: Role,
    region: str,
    mgr_id: str | None,
    phone: str | None,
) -> Result[Sale]:
    if actor.role != Role.DIRECTOR:
        return Err("ROLE_FORBIDDEN", "Chỉ Director được tạo nhân sự.")
    if role == Role.SALER and not mgr_id:
        return Err("MANAGER_REQUIRED", "Saler cần thuộc một Manager.")
    sale = Sale(
        name=name.strip(),
        email=email.strip().lower(),
        pass_hash=hash_password(password),
        role=role,
        region=region.strip(),
        mgr_id=mgr_id or None,
        phone=phone or None,
    )
    session.add(sale)
    session.commit()
    return Ok(sale)


def update_position(
    session: Session,
    scope: DataScope,
    actor: Sale,
    sale_id: str,
    countries: str,
) -> Result[Sale]:
    if actor.role not in {Role.MANAGER, Role.DIRECTOR}:
        return Err("ROLE_FORBIDDEN", "Không được cập nhật Position.")
    target = get_sale(session, scope, sale_id)
    if target is None or target.role != Role.SALER:
        return Err("SALE_NOT_FOUND", "Không tìm thấy Saler trong phạm vi.")
    target.position = sorted({part.strip() for part in countries.split(",") if part.strip()})
    target.update_at = utcnow()
    session.add(target)
    session.commit()
    return Ok(target)


def update_profile(
    session: Session,
    scope: DataScope,
    actor: Sale,
    sale_id: str,
    name: str,
    region: str,
    phone: str | None,
) -> Result[Sale]:
    if actor.role not in {Role.MANAGER, Role.DIRECTOR}:
        return Err("ROLE_FORBIDDEN", "Không được cập nhật nhân sự.")
    target = get_sale(session, scope, sale_id)
    if target is None:
        return Err("SALE_NOT_FOUND", "Nhân sự ngoài phạm vi.")
    target.name = name.strip()
    target.region = region.strip()
    target.phone = phone or None
    target.update_at = utcnow()
    session.add(target)
    session.commit()
    return Ok(target)
