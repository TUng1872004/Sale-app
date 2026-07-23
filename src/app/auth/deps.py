from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from pwdlib import PasswordHash
from sqlmodel import Session

from app.db import get_session
from app.core.schema.models import Role, Sale, SaleStatus


password_hash = PasswordHash.recommended()


class LoginRequired(Exception):
    pass


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    return password_hash.verify(password, encoded)


def current_user(request: Request, session: Session = Depends(get_session)) -> Sale:
    sale_id = request.session.get("sale_id")
    user = session.get(Sale, sale_id) if sale_id else None
    if user is None or user.status != SaleStatus.ACTIVE:
        raise LoginRequired
    return user


def require_roles(*roles: Role) -> Callable[..., Sale]:
    def dependency(user: Sale = Depends(current_user)) -> Sale:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bạn không có quyền thực hiện thao tác này.")
        return user

    return dependency
