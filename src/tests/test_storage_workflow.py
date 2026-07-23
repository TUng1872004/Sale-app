from datetime import datetime

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.schema.models import Oppo, Role, Sale, Seriousness, Stage
from app.services.stage_transition import persist_stage_transition
from app.storage import MemoryStorage


class FailingCommitSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.rolled_back = False

    def add(self, value: object) -> None:
        self.added.append(value)

    def commit(self) -> None:
        raise SQLAlchemyError("forced commit failure")

    def rollback(self) -> None:
        self.rolled_back = True


class FailingUploadStorage(MemoryStorage):
    def put(self, object_key: str, content: bytes, content_type: str = "text/markdown") -> None:
        raise RuntimeError("storage unavailable")


def _actor_and_deal() -> tuple[Sale, Oppo]:
    actor = Sale(id="saler", name="Saler", email="saler@test", pass_hash="x", role=Role.SALER, region="VN", mgr_id="manager")
    deal = Oppo(
        id="deal",
        title="Deal",
        agency_id="agency",
        owner_id=actor.id,
        value=100,
        stage=Stage.NEW,
        open_at=datetime(2026, 1, 1),
    )
    return actor, deal


def test_sql_failure_deletes_uploaded_object_as_compensation():
    actor, deal = _actor_and_deal()
    session = FailingCommitSession()
    storage = MemoryStorage()
    with pytest.raises(SQLAlchemyError):
        persist_stage_transition(
            session,  # type: ignore[arg-type]
            storage,
            deal,
            actor,
            Stage.QUALIFY,
            None,
            "Discovery",
            "Notes",
            Seriousness.MED,
        )
    assert session.rolled_back
    assert storage.objects == {}


def test_upload_failure_never_attempts_sql_write():
    actor, deal = _actor_and_deal()
    session = FailingCommitSession()
    with pytest.raises(RuntimeError, match="storage unavailable"):
        persist_stage_transition(
            session,  # type: ignore[arg-type]
            FailingUploadStorage(),
            deal,
            actor,
            Stage.QUALIFY,
            None,
            "Discovery",
            "Notes",
            Seriousness.MED,
        )
    assert session.added == []
    assert not session.rolled_back
