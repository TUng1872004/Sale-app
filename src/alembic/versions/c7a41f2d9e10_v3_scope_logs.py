"""v3 scope, position, and logs

Revision ID: c7a41f2d9e10
Revises: be6ccfa034ef
Create Date: 2026-07-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


revision: str = "c7a41f2d9e10"
down_revision: Union[str, Sequence[str], None] = "be6ccfa034ef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sale", sa.Column("position", sa.JSON(), nullable=False, server_default="[]"))
    op.create_table(
        "managerlog",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("actor_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "action",
            sa.Enum(
                "ASSIGN_TEAM",
                "ASSIGN_SALER",
                "KICK_PROPOSED",
                "KICK_APPROVED",
                "KICK_REJECTED",
                "KICK_DIRECT",
                "MANAGER_REPORT",
                name="manageraction",
            ),
            nullable=False,
        ),
        sa.Column("subject_sale_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("oppo_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("report_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("object_key", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("seriousness", sa.Enum("LOW", "MED", "HIGH", "CRITICAL", name="seriousness"), nullable=False),
        sa.Column("summary", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["sale.id"]),
        sa.ForeignKeyConstraint(["subject_sale_id"], ["sale.id"]),
        sa.ForeignKeyConstraint(["oppo_id"], ["oppo.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_managerlog_actor_id"), "managerlog", ["actor_id"])
    op.create_index(op.f("ix_managerlog_action"), "managerlog", ["action"])
    op.create_index(op.f("ix_managerlog_subject_sale_id"), "managerlog", ["subject_sale_id"])
    op.create_index(op.f("ix_managerlog_oppo_id"), "managerlog", ["oppo_id"])
    op.create_index(op.f("ix_managerlog_report_id"), "managerlog", ["report_id"])
    op.create_index(op.f("ix_managerlog_seriousness"), "managerlog", ["seriousness"])
    op.create_index(op.f("ix_managerlog_at"), "managerlog", ["at"])
    op.create_table(
        "salerlog",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("actor_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "action",
            sa.Enum(
                "SALE_REPORT",
                "FREQUENT_REPORT",
                "TAKE_CHARGE_REQUEST",
                "TAKE_CHARGE_APPROVED",
                "TAKE_CHARGE_REJECTED",
                "STAGE_CHANGED",
                name="saleraction",
            ),
            nullable=False,
        ),
        sa.Column("subject_sale_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("oppo_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("report_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("object_key", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("seriousness", sa.Enum("LOW", "MED", "HIGH", "CRITICAL", name="seriousness"), nullable=False),
        sa.Column("summary", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["sale.id"]),
        sa.ForeignKeyConstraint(["subject_sale_id"], ["sale.id"]),
        sa.ForeignKeyConstraint(["oppo_id"], ["oppo.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_salerlog_actor_id"), "salerlog", ["actor_id"])
    op.create_index(op.f("ix_salerlog_action"), "salerlog", ["action"])
    op.create_index(op.f("ix_salerlog_subject_sale_id"), "salerlog", ["subject_sale_id"])
    op.create_index(op.f("ix_salerlog_oppo_id"), "salerlog", ["oppo_id"])
    op.create_index(op.f("ix_salerlog_report_id"), "salerlog", ["report_id"])
    op.create_index(op.f("ix_salerlog_seriousness"), "salerlog", ["seriousness"])
    op.create_index(op.f("ix_salerlog_at"), "salerlog", ["at"])


def downgrade() -> None:
    op.drop_table("salerlog")
    op.drop_table("managerlog")
    op.drop_column("sale", "position")
