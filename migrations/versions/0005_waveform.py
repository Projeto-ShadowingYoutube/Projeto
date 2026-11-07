"""Waveform (B9): peaks de cada trecho em JSON, com os metadados do cálculo.

Revisão: 0005
Anterior: 0004
Criada em: 2026-11-07

Só cria a tabela (cache: vazia no início, preenchida conforme as frases são estudadas). Não pertence a usuários.
Chave única (video_id, inicio, fim, versao): duas requisições simultâneas não gravam a mesma onda duas vezes, e
mudar a versão do algoritmo invalida as ondas antigas sem precisar apagá-las.
"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "waveform",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("video_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("inicio", sa.Float(), nullable=False),
        sa.Column("fim", sa.Float(), nullable=False),
        sa.Column("versao", sa.Integer(), nullable=False),
        sa.Column("duracao", sa.Float(), nullable=False),
        sa.Column("quantidade", sa.Integer(), nullable=False),
        sa.Column("peaks", sa.JSON(), nullable=False),
        sa.Column("data_criacao", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("video_id", "inicio", "fim", "versao", name="uq_waveform_trecho_versao"),
    )
    op.create_index("ix_waveform_video_id", "waveform", ["video_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_waveform_video_id", table_name="waveform")
    op.drop_table("waveform")
