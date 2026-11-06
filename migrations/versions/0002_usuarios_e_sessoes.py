"""Usuários e sessões de login (B4).

Revisão: 0002
Anterior: 0001
Criada em: 2026-11-06

Só cria tabelas novas: Decks e Cards não mudam aqui (a posse dos Decks entra no B5).
"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "usuario",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("senha_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("data_criacao", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_usuario_email", "usuario", ["email"], unique=True)

    op.create_table(
        "sessao",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("data_criacao", sa.DateTime(), nullable=False),
        sa.Column("expira_em", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sessao_token_hash", "sessao", ["token_hash"], unique=True)
    op.create_index("ix_sessao_usuario_id", "sessao", ["usuario_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_sessao_usuario_id", table_name="sessao")
    op.drop_index("ix_sessao_token_hash", table_name="sessao")
    op.drop_table("sessao")
    op.drop_index("ix_usuario_email", table_name="usuario")
    op.drop_table("usuario")
