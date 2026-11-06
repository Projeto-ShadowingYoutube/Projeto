"""Posse dos Decks (B5): cada Deck pertence a um usuário; o nome passa a ser único por usuário.

Revisão: 0003
Anterior: 0002
Criada em: 2026-11-06

- deck.usuario_id: FK para usuario, obrigatória, com índice.
- Sai o UNIQUE global de deck.nome; entra UNIQUE (usuario_id, nome).
- Cards não mudam: o dono de um Card é o dono do Deck dele.

Decks já existentes não têm dono, e esta migração NÃO inventa um (decisão D3 do plano): se houver Decks, ela
para antes de alterar qualquer coisa. Usa "batch" para o SQLite, que só altera restrições recriando a tabela.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.migrar import BancoIncompativel

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FK_DONO = "fk_deck_usuario_id_usuario"
UNICO_POR_USUARIO = "uq_deck_usuario_nome"


def upgrade() -> None:
    decks_sem_dono = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM deck")).scalar()
    if decks_sem_dono:
        raise BancoIncompativel(
            f"Existem {decks_sem_dono} Deck(s) criados antes das contas de usuário, sem dono. Esta migração não "
            "escolhe um dono por você: associe-os a um usuário (ou apague-os) e rode python -m app.migrar de novo."
        )

    with op.batch_alter_table("deck") as batch_op:
        batch_op.add_column(sa.Column("usuario_id", sa.Integer(), nullable=False))
        batch_op.create_foreign_key(FK_DONO, "usuario", ["usuario_id"], ["id"])
        batch_op.create_index("ix_deck_usuario_id", ["usuario_id"], unique=False)
        batch_op.drop_index("ix_deck_nome")
        batch_op.create_index("ix_deck_nome", ["nome"], unique=False)
        batch_op.create_unique_constraint(UNICO_POR_USUARIO, ["usuario_id", "nome"])


def downgrade() -> None:
    # Atenção: descer apaga a informação de quem é o dono de cada Deck, e falha se duas contas
    # tiverem Decks com o mesmo nome (o nome volta a ser único no app inteiro).
    with op.batch_alter_table("deck") as batch_op:
        batch_op.drop_constraint(UNICO_POR_USUARIO, type_="unique")
        batch_op.drop_index("ix_deck_nome")
        batch_op.create_index("ix_deck_nome", ["nome"], unique=True)
        batch_op.drop_index("ix_deck_usuario_id")
        batch_op.drop_constraint(FK_DONO, type_="foreignkey")
        batch_op.drop_column("usuario_id")
