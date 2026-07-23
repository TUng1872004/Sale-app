from __future__ import annotations

import hashlib
import re
import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import delete, func
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, select

from app.core.config import get_settings
from app.db import engine, init_db
from app.core.schema.models import (
    Agency,
    AssignHist,
    LossReason,
    Oppo,
    Role,
    Sale,
    SaleStatus,
    SalerLog,
    ManagerLog,
    Stage,
)

DATA_DIR: Path = Path(__file__).resolve().parent.parent / "data"

## hash mapping, nondeterministic seed breaks reseed verification
_ENGAGING_TARGETS = [Stage.QUALIFY, Stage.PROPOSE, Stage.NEGOTIATE]
_LOSS_REASONS = list(LossReason)


@dataclass(frozen=True, slots=True)
class SeedSummary:
    sales: int
    agencies: int
    opportunities: int
    assignments: int
    won: int
    lost: int
    skipped: int

    def line(self, prefix: str = "Seeded") -> str:
        return (
            f"{prefix} {self.sales} Sale, {self.agencies} Agency, {self.opportunities} Oppo, "
            f"{self.assignments} AssignHist; WON={self.won}, LOST={self.lost}; skipped={self.skipped}."
        )


EXPECTED = SeedSummary(42, 85, 7375, 85, 4238, 2473, 1425)


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "unknown"


def stable_hash_int(key: str) -> int:
    return int(hashlib.md5(key.encode()).hexdigest(), 16)


def _hash_demo_password(password: str) -> str:
    from pwdlib import PasswordHash

    return PasswordHash.recommended().hash(password)


def load_csvs() -> dict[str, pd.DataFrame]:
    return {
        "pipeline": pd.read_csv(DATA_DIR / "sales_pipeline.csv"),
        "accounts": pd.read_csv(DATA_DIR / "accounts.csv"),
        "teams": pd.read_csv(DATA_DIR / "sales_teams.csv"),
        "products": pd.read_csv(DATA_DIR / "products.csv"),
    }


def map_stage(deal_stage: str, opportunity_id: str) -> Stage:
    if deal_stage == "Won":
        return Stage.WON
    if deal_stage == "Lost":
        return Stage.LOST
    if deal_stage == "Prospecting":
        return Stage.NEW
    if deal_stage == "Engaging":
        idx = stable_hash_int(opportunity_id) % 3
        return _ENGAGING_TARGETS[idx]
    raise ValueError(f"unknown deal_stage: {deal_stage!r}")


def pick_loss_reason(opportunity_id: str) -> LossReason:
    idx = stable_hash_int(opportunity_id) % len(_LOSS_REASONS)
    return _LOSS_REASONS[idx]


def seed_sales(session: Session, teams_df: pd.DataFrame) -> dict[str, Sale]:
    """Returns name -> Sale for agents and managers (director keyed by 'DIRECTOR')."""
    by_name: dict[str, Sale] = {}
    pass_hash = _hash_demo_password(get_settings().demo_password)

    director = Sale(
        name="Giám đốc kinh doanh",
        email="director@demo.local",
        pass_hash=pass_hash,
        role=Role.DIRECTOR,
        region="HQ",
        mgr_id=None,
    )
    session.add(director)
    session.flush()
    by_name["DIRECTOR"] = director

    ## pandas Hashable types, explicit string cast needed
    manager_regions: dict[str, str] = {
        str(k): str(v)
        for k, v in teams_df.groupby("manager")["regional_office"].agg(lambda s: s.value_counts().idxmax()).to_dict().items()
    }
    for mgr_name in sorted(manager_regions):
        mgr = Sale(
            name=mgr_name,
            email=f"{slugify(mgr_name)}@demo.local",
            pass_hash=pass_hash,
            role=Role.MANAGER,
            region=manager_regions[mgr_name],
            mgr_id=director.id,
        )
        session.add(mgr)
        session.flush()
        by_name[mgr_name] = mgr

    for _, row in teams_df.sort_values("sales_agent").iterrows():
        agent_name = row["sales_agent"]
        mgr = by_name[row["manager"]]
        saler = Sale(
            name=agent_name,
            email=f"{slugify(agent_name)}@demo.local",
            pass_hash=pass_hash,
            role=Role.SALER,
            region=row["regional_office"],
            mgr_id=mgr.id,
        )
        session.add(saler)
        session.flush()
        by_name[agent_name] = saler

    return by_name


def seed_agencies(session: Session, accounts_df: pd.DataFrame) -> dict[str, Agency]:
    by_name: dict[str, Agency] = {}
    for _, row in accounts_df.iterrows():
        agency = Agency(
            code=slugify(row["account"]),
            name=row["account"],
            sector=row["sector"] if pd.notna(row["sector"]) else None,
            est_year=int(row["year_established"]) if pd.notna(row["year_established"]) else None,
            revenue=float(row["revenue"]) if pd.notna(row["revenue"]) else None,
            employee=int(row["employees"]) if pd.notna(row["employees"]) else None,
            loc=row["office_location"] if pd.notna(row["office_location"]) else None,
            parent=row["subsidiary_of"] if pd.notna(row["subsidiary_of"]) else None,
            owner_id=None,
        )
        session.add(agency)
        session.flush()
        by_name[row["account"]] = agency
    return by_name


def assign_agency_owners(
    session: Session,
    pipeline_df: pd.DataFrame,
    agencies: dict[str, Agency],
    sales: dict[str, Sale],
) -> None:
    ## alphabetical tie-break, reseed output otherwise unstable
    named = pipeline_df[pipeline_df["account"].notna()]
    counts = named.groupby(["account", "sales_agent"]).size().reset_index(name="n")
    counts = counts.sort_values(["account", "n", "sales_agent"], ascending=[True, False, True])
    owner_per_account: dict[str, str] = {
        str(k): str(v) for k, v in counts.groupby("account").first()["sales_agent"].to_dict().items()
    }

    for account_name, agent_name in owner_per_account.items():
        agency = agencies[account_name]
        owner = sales[agent_name]
        agency.owner_id = owner.id
        session.add(agency)
        session.add(
            AssignHist(
                agency_id=agency.id,
                prev_owner_id=None,
                new_owner_id=owner.id,
                reason="Seed: giao ban đầu theo dữ liệu import",
            )
        )


def seed_opportunities(
    session: Session,
    pipeline_df: pd.DataFrame,
    agencies: dict[str, Agency],
    sales: dict[str, Sale],
    products_df: pd.DataFrame,
) -> int:
    price_by_product = dict(zip(products_df["product"], products_df["sales_price"]))
    named = pipeline_df[pipeline_df["account"].notna()]
    skipped = len(pipeline_df) - len(named)

    batch: list[Oppo] = []
    for _, row in named.iterrows():
        opp_id = row["opportunity_id"]
        stage = map_stage(row["deal_stage"], opp_id)
        agency = agencies[row["account"]]
        owner = sales[row["sales_agent"]]

        open_at = pd.to_datetime(row["engage_date"]) if pd.notna(row["engage_date"]) else datetime(2026, 1, 1)
        close_at = None
        if stage in (Stage.WON, Stage.LOST) and pd.notna(row["close_date"]):
            close_at = pd.to_datetime(row["close_date"])

        if pd.notna(row["close_value"]):
            value = float(row["close_value"])
        else:
            value = float(price_by_product.get(row["product"], 0.0))

        loss_reason = pick_loss_reason(opp_id) if stage == Stage.LOST else None

        oppo = Oppo(
            title=f"{row['product']} — {row['account']}",
            prod=row["product"] if pd.notna(row["product"]) else None,
            agency_id=agency.id,
            owner_id=owner.id,
            value=value,
            stage=stage,
            loss_reason=loss_reason,
            open_at=open_at.to_pydatetime() if hasattr(open_at, "to_pydatetime") else open_at,
            close_at=close_at.to_pydatetime() if close_at is not None and hasattr(close_at, "to_pydatetime") else close_at,
        )
        batch.append(oppo)

        if len(batch) >= 1000:
            session.add_all(batch)
            session.flush()
            batch = []

    if batch:
        session.add_all(batch)
        session.flush()

    return skipped


def seed_positions(
    session: Session,
    pipeline_df: pd.DataFrame,
    accounts_df: pd.DataFrame,
    sales: dict[str, Sale],
) -> None:
    won = pipeline_df[(pipeline_df["deal_stage"] == "Won") & pipeline_df["account"].notna()]
    won = won.merge(accounts_df[["account", "office_location"]], on="account", how="left")
    counts = won.groupby(["sales_agent", "office_location"]).size().reset_index(name="n")
    counts = counts.sort_values(["sales_agent", "n", "office_location"], ascending=[True, False, True])
    manager_by_agent = {
        name: sale.mgr_id for name, sale in sales.items() if sale.role == Role.SALER
    }
    team_positions: dict[str, list[str]] = {}
    for agent_name, group in counts.groupby("sales_agent"):
        sale = sales[str(agent_name)]
        sale.position = [str(loc) for loc in group["office_location"].dropna()]
        session.add(sale)
        if sale.mgr_id is not None:
            team_positions.setdefault(sale.mgr_id, [])
            for loc in sale.position:
                if loc not in team_positions[sale.mgr_id]:
                    team_positions[sale.mgr_id].append(loc)
    for agent_name, manager_id in manager_by_agent.items():
        sale = sales[agent_name]
        if not sale.position and manager_id is not None:
            sale.position = team_positions.get(manager_id, []).copy()
            session.add(sale)


def inspect_seed(session: Session, *, skipped: int = EXPECTED.skipped) -> SeedSummary:
    return SeedSummary(
        sales=int(session.exec(select(func.count()).select_from(Sale)).one()),
        agencies=int(session.exec(select(func.count()).select_from(Agency)).one()),
        opportunities=int(session.exec(select(func.count()).select_from(Oppo)).one()),
        assignments=int(session.exec(select(func.count()).select_from(AssignHist)).one()),
        won=int(session.exec(select(func.count()).select_from(Oppo).where(Oppo.stage == Stage.WON)).one()),
        lost=int(session.exec(select(func.count()).select_from(Oppo).where(Oppo.stage == Stage.LOST)).one()),
        skipped=skipped,
    )


def clear_seed(session: Session) -> None:
    for model in (SalerLog, ManagerLog, AssignHist, Oppo, Agency, Sale):
        session.execute(delete(model))


def _has_data(summary: SeedSummary) -> bool:
    return any((summary.sales, summary.agencies, summary.opportunities, summary.assignments))


def _validate(summary: SeedSummary) -> None:
    if summary != EXPECTED:
        raise RuntimeError(f"Seed validation failed. Expected {EXPECTED.line()}, observed {summary.line()}" )


def run(*, reseed: bool = False, db_engine: Engine = engine) -> SeedSummary:
    SQLModel.metadata.create_all(db_engine)
    with Session(db_engine) as session:
        observed = inspect_seed(session)
    if _has_data(observed) and not reseed:
        _validate(observed)
        print(observed.line("Verified existing"))
        return observed

    csvs = load_csvs()
    with Session(db_engine) as session, session.begin():
        if reseed:
            clear_seed(session)
        sales = seed_sales(session, csvs["teams"])
        agencies = seed_agencies(session, csvs["accounts"])
        assign_agency_owners(session, csvs["pipeline"], agencies, sales)
        skipped = seed_opportunities(session, csvs["pipeline"], agencies, sales, csvs["products"])
        seed_positions(session, csvs["pipeline"], csvs["accounts"], sales)
        summary = inspect_seed(session, skipped=skipped)
        _validate(summary)
    print(summary.line("Reseeded" if reseed else "Seeded"))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reseed", action="store_true")
    args = parser.parse_args()
    run(reseed=args.reseed)
