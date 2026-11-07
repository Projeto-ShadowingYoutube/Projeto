"""Configurações individuais de estudo (B8): por enquanto, a velocidade preferida do vídeo.

Revisão: 0004
Anterior: 0003
Criada em: 2026-11-06

Tabela 1:1 com usuario (usuario_id é a chave primária: no máximo uma linha por usuário). Só cria a tabela:
a linha de cada usuário nasce no primeiro salvamento, e até lá valem os padrões do código.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "configuracaoestudo",
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("velocidade", sa.Float(), nullable=False),
        sa.Column("data_atualizacao", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"], name="fk_configuracaoestudo_usuario_id_usuario"),
        sa.PrimaryKeyConstraint("usuario_id"),
    )


def downgrade() -> None:
    op.drop_table("configuracaoestudo")
