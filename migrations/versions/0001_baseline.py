"""Baseline: o esquema como ele era antes do Alembic (Decks, Cards e cache do dicionário).

Revisão: 0001
Anterior: nenhuma
Criada em: 2026-11-06

Gerada pelo autogenerate a partir dos modelos e conferida com o esquema real de dados/estudos.db.
Bancos criados antes do Alembic já têm estas tabelas: "python -m app.migrar" só os marca como 0001 (stamp).
"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "deck",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deck_nome", "deck", ["nome"], unique=True)

    op.create_table(
        "entradadicionario",
        sa.Column("palavra", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("dados", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("data_consulta", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("palavra"),
    )

    op.create_table(
        "card",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("texto_legenda", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("video_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("start_time", sa.Float(), nullable=False),
        sa.Column("end_time", sa.Float(), nullable=False),
        sa.Column("data_criacao", sa.DateTime(), nullable=False),
        sa.Column("data_proxima_revisao", sa.DateTime(), nullable=False),
        sa.Column("revisao", sa.Integer(), nullable=False),
        sa.Column("deck_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["deck_id"], ["deck.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_card_deck_id", "card", ["deck_id"], unique=False)
    op.create_index("ix_card_video_id", "card", ["video_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_card_video_id", table_name="card")
    op.drop_index("ix_card_deck_id", table_name="card")
    op.drop_table("card")
    op.drop_table("entradadicionario")
    op.drop_index("ix_deck_nome", table_name="deck")
    op.drop_table("deck")
