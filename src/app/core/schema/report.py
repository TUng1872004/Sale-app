from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.core.schema.models import Sale, Seriousness


def report_id(kind: str, now: datetime | None = None) -> str:
    at = now or datetime.now()
    return f"{at:%Y%m%d}-{kind.upper()}-{uuid4().hex[:6]}"


def report_document(kind: str, title: str, body: str, seriousness: Seriousness, at: datetime | None = None) -> bytes:
    created = at or datetime.now()
    text = (
        "---\n"
        f"kind: {kind}\n"
        f"title: {title}\n"
        f"seriousness: {seriousness.value}\n"
        f"created_at: {created.isoformat()}\n"
        "---\n\n"
        f"# {title}\n\n{body.strip()}\n"
    )
    return text.encode("utf-8")


def report_key(actor: Sale, kind: str, rid: str) -> str:
    team_id = actor.mgr_id or actor.id
    return f"team_{team_id}/saler_{actor.id}/{kind.lower()}_{rid}.md"
