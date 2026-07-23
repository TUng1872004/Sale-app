## tie-break determinism: same CSV input seeded twice must assign identical owners.
## guards the pandas idxmax/sort_values tie-break behavior called out in the plan.
import pandas as pd

from app.seed import DATA_DIR, EXPECTED, assign_agency_owners, inspect_seed, run, seed_agencies, seed_sales
from app.db import init_db
from app.core.schema.models import Role, Sale
from sqlmodel import Session, SQLModel, create_engine, select


def _fresh_session():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _owner_snapshot(teams_df, accounts_df, pipeline_df):
    with _fresh_session() as session:
        sales = seed_sales(session, teams_df)
        agencies = seed_agencies(session, accounts_df)
        assign_agency_owners(session, pipeline_df, agencies, sales)
        return {name: (agency.owner_id and sales_by_id_name(sales, agency.owner_id)) for name, agency in agencies.items()}


def sales_by_id_name(sales: dict, owner_id: str) -> str:
    for name, sale in sales.items():
        if sale.id == owner_id:
            return name
    raise KeyError(owner_id)


def test_owner_tiebreak_deterministic():
    teams_df = pd.read_csv(DATA_DIR / "sales_teams.csv")
    accounts_df = pd.read_csv(DATA_DIR / "accounts.csv")
    pipeline_df = pd.read_csv(DATA_DIR / "sales_pipeline.csv")

    snap1 = _owner_snapshot(teams_df, accounts_df, pipeline_df)
    snap2 = _owner_snapshot(teams_df, accounts_df, pipeline_df)

    assert snap1 == snap2
    assert len(snap1) == 85


def test_seed_output_verify_and_reseed(tmp_path, capsys):
    db_engine = create_engine(f"sqlite:///{tmp_path / 'seed.db'}")

    assert run(db_engine=db_engine) == EXPECTED
    assert capsys.readouterr().out.strip() == EXPECTED.line("Seeded")
    assert run(db_engine=db_engine) == EXPECTED
    assert capsys.readouterr().out.strip() == EXPECTED.line("Verified existing")
    assert run(db_engine=db_engine, reseed=True) == EXPECTED
    assert capsys.readouterr().out.strip() == EXPECTED.line("Reseeded")

    with Session(db_engine) as session:
        assert inspect_seed(session) == EXPECTED
        salers = list(session.exec(select(Sale).where(Sale.role == Role.SALER)))
        assert all(sale.position for sale in salers)
