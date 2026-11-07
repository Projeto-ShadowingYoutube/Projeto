"""Volume do vídeo nas configurações de estudo (B9.2).

Revisão: 0006
Anterior: 0005
Criada em: 2026-11-07

Uma coluna nova com valor padrão no próprio banco (server_default 1.0): as linhas que já existem passam a ter
volume 100%, sem migração de dados. É o caso previsto no B8 ("preferência nova = uma coluna com valor padrão").
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("configuracaoestudo") as batch_op:
        batch_op.add_column(sa.Column("volume", sa.Float(), nullable=False, server_default=sa.text("1.0")))


def downgrade() -> None:
    with op.batch_alter_table("configuracaoestudo") as batch_op:
        batch_op.drop_column("volume")
