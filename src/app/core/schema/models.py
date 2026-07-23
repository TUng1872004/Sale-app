
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, Index, Relationship, SQLModel


def new_id() -> str:
    return uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class SaleStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class Role(str, Enum):
    SALER = "SALER"
    MANAGER = "MANAGER"
    DIRECTOR = "DIRECTOR"


class Stage(str, Enum):
    NEW = "NEW"
    QUALIFY = "QUALIFY"
    PROPOSE = "PROPOSE"
    NEGOTIATE = "NEGOTIATE"
    WON = "WON"
    LOST = "LOST"
    CLOSED = "CLOSED"


## order matters, forward-only transitions walk this list
STAGE_ORDER: list[Stage] = [Stage.NEW, Stage.QUALIFY, Stage.PROPOSE, Stage.NEGOTIATE, Stage.WON]
OPEN_STAGES: set[Stage] = {Stage.NEW, Stage.QUALIFY, Stage.PROPOSE, Stage.NEGOTIATE}
TERMINAL_STAGES: set[Stage] = {Stage.WON, Stage.LOST, Stage.CLOSED}


class LossReason(str, Enum):
    PRICE = "PRICE"
    COMPETITOR = "COMPETITOR"
    NO_DECISION = "NO_DECISION"
    POOR_FIT = "POOR_FIT"
    CANCELLED = "CANCELLED"
    TIMING = "TIMING"


class Seriousness(str, Enum):
    LOW = "LOW"
    MED = "MED"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ManagerAction(str, Enum):
    ASSIGN_TEAM = "ASSIGN_TEAM"
    ASSIGN_SALER = "ASSIGN_SALER"
    KICK_PROPOSED = "KICK_PROPOSED"
    KICK_APPROVED = "KICK_APPROVED"
    KICK_REJECTED = "KICK_REJECTED"
    KICK_DIRECT = "KICK_DIRECT"
    MANAGER_REPORT = "MANAGER_REPORT"


class SalerAction(str, Enum):
    SALE_REPORT = "SALE_REPORT"
    FREQUENT_REPORT = "FREQUENT_REPORT"
    TAKE_CHARGE_REQUEST = "TAKE_CHARGE_REQUEST"
    TAKE_CHARGE_APPROVED = "TAKE_CHARGE_APPROVED"
    TAKE_CHARGE_REJECTED = "TAKE_CHARGE_REJECTED"
    STAGE_CHANGED = "STAGE_CHANGED"


class Sale(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    name: str
    email: str = Field(unique=True, index=True)
    pass_hash: str
    role: Role = Field(default=Role.SALER, index=True)
    phone: str | None = None
    region: str
    mgr_id: str | None = Field(default=None, foreign_key="sale.id")
    status: SaleStatus = Field(default=SaleStatus.ACTIVE, index=True)
    position: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    join_at: datetime = Field(default_factory=utcnow)
    create_at: datetime = Field(default_factory=utcnow)
    update_at: datetime = Field(default_factory=utcnow)

    mgr: "Sale" = Relationship(
        back_populates="team",
        sa_relationship_kwargs={"remote_side": "Sale.id"},
    )
    team: list["Sale"] = Relationship(back_populates="mgr")
    agency: list["Agency"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"foreign_keys": "Agency.owner_id"},
    )
    oppo: list["Oppo"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"foreign_keys": "Oppo.owner_id"},
    )


class Agency(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    code: str = Field(unique=True, index=True)
    name: str
    sector: str | None = None
    est_year: int | None = None
    revenue: float | None = None
    employee: int | None = None
    loc: str | None = None
    parent: str | None = None
    owner_id: str | None = Field(default=None, foreign_key="sale.id", index=True)
    create_at: datetime = Field(default_factory=utcnow)
    update_at: datetime = Field(default_factory=utcnow)

    owner: Sale | None = Relationship(
        back_populates="agency",
        sa_relationship_kwargs={"foreign_keys": "Agency.owner_id"},
    )
    oppo: list["Oppo"] = Relationship(back_populates="agency")


class Oppo(SQLModel, table=True):
    ## composite index for the stale-deal query: filter open stages, then compare age
    __table_args__ = (Index("ix_oppo_stage_open_at", "stage", "open_at"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    title: str
    prod: str | None = None
    agency_id: str = Field(foreign_key="agency.id", index=True)
    owner_id: str = Field(foreign_key="sale.id", index=True)
    value: float
    stage: Stage = Field(default=Stage.NEW, index=True)
    loss_reason: LossReason | None = None
    open_at: datetime
    due_at: datetime | None = None
    close_at: datetime | None = None
    note: str | None = None
    create_at: datetime = Field(default_factory=utcnow)
    update_at: datetime = Field(default_factory=utcnow)

    agency: Agency = Relationship(back_populates="oppo")
    owner: Sale = Relationship(
        back_populates="oppo",
        sa_relationship_kwargs={"foreign_keys": "Oppo.owner_id"},
    )


class AssignHist(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    agency_id: str = Field(foreign_key="agency.id", index=True)
    prev_owner_id: str | None = Field(default=None, foreign_key="sale.id")
    new_owner_id: str = Field(foreign_key="sale.id")
    reason: str | None = None
    at: datetime = Field(default_factory=utcnow)


class ManagerLog(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    actor_id: str = Field(foreign_key="sale.id", index=True)
    action: ManagerAction = Field(index=True)
    subject_sale_id: str | None = Field(default=None, foreign_key="sale.id", index=True)
    oppo_id: str | None = Field(default=None, foreign_key="oppo.id", index=True)
    report_id: str | None = Field(default=None, index=True)
    object_key: str | None = None
    seriousness: Seriousness = Field(default=Seriousness.MED, index=True)
    summary: str
    at: datetime = Field(default_factory=utcnow, index=True)


class SalerLog(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    actor_id: str = Field(foreign_key="sale.id", index=True)
    action: SalerAction = Field(index=True)
    subject_sale_id: str | None = Field(default=None, foreign_key="sale.id", index=True)
    oppo_id: str | None = Field(default=None, foreign_key="oppo.id", index=True)
    report_id: str | None = Field(default=None, index=True)
    object_key: str | None = None
    seriousness: Seriousness = Field(default=Seriousness.MED, index=True)
    summary: str
    at: datetime = Field(default_factory=utcnow, index=True)
