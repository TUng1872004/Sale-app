from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session, select

from app.core.schema.models import Role, Sale


@dataclass(frozen=True, slots=True)
class DataScope:
    actor_id: str
    owner_ids: tuple[str, ...]
    global_access: bool = False

    @classmethod
    def for_actor(cls, session: Session, actor: Sale) -> DataScope:
        if actor.role == Role.DIRECTOR:
            return cls(actor_id=actor.id, owner_ids=(), global_access=True)
        if actor.role == Role.MANAGER:
            team_ids = tuple(session.exec(select(Sale.id).where(Sale.mgr_id == actor.id)))
            return cls(actor_id=actor.id, owner_ids=(actor.id, *team_ids))
        return cls(actor_id=actor.id, owner_ids=(actor.id,))

    @classmethod
    def global_for(cls, actor_id: str) -> DataScope:
        return cls(actor_id=actor_id, owner_ids=(), global_access=True)
