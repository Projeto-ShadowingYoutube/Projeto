"""Writing Challenge (Membro 3, W1): temas, tentativas, feedbacks da IA e reescritas.

Revisão: 0301
Anterior: 0006
Criada em: 2026-11-21

Só cria tabelas novas (nenhuma tabela existente é alterada):
- writingprompt: temas, compartilhados (sem dono). Os iniciais entram na migração de dados 0302.
- writingattempt: redação de um usuário (FK usuario). O prazo é gravado ao criar; o estado controla o autosave.
- writingfeedback: correção por IA, no máximo uma por tentativa (UNIQUE attempt_id). Notas e trechos em JSON.
- writingrewrite: reescritas de trechos, uma linha por envio (UNIQUE feedback_id + rodada + indice_trecho).

As FKs têm nome (o autogenerate as gera sem nome, e o downgrade em batch do SQLite precisa dele; ver a 0003).
"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0301"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "writingprompt",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("categoria", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("enunciado", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("tempo_limite_segundos", sa.Integer(), nullable=False),
        sa.Column("palavras_minimas", sa.Integer(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_writingprompt_categoria", "writingprompt", ["categoria"], unique=False)

    op.create_table(
        "writingattempt",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("prompt_id", sa.Integer(), nullable=False),
        sa.Column("texto", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("estado", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("palavras", sa.Integer(), nullable=False),
        sa.Column("iniciada_em", sa.DateTime(), nullable=False),
        sa.Column("prazo", sa.DateTime(), nullable=False),
        sa.Column("salva_em", sa.DateTime(), nullable=True),
        sa.Column("enviada_em", sa.DateTime(), nullable=True),
        sa.Column("avaliacoes_tentadas", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"], name="fk_writingattempt_usuario_id_usuario"),
        sa.ForeignKeyConstraint(["prompt_id"], ["writingprompt.id"], name="fk_writingattempt_prompt_id_writingprompt"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_writingattempt_usuario_id", "writingattempt", ["usuario_id"], unique=False)
    op.create_index("ix_writingattempt_prompt_id", "writingattempt", ["prompt_id"], unique=False)

    op.create_table(
        "writingfeedback",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("attempt_id", sa.Integer(), nullable=False),
        sa.Column("notas", sa.JSON(), nullable=False),
        sa.Column("nota_geral", sa.Float(), nullable=False),
        sa.Column("resumo", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("trechos", sa.JSON(), nullable=False),
        sa.Column("modelo", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("versao_prompt", sa.Integer(), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["attempt_id"], ["writingattempt.id"], name="fk_writingfeedback_attempt_id_writingattempt",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attempt_id", name="uq_writingfeedback_attempt"),
    )

    op.create_table(
        "writingrewrite",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("feedback_id", sa.Integer(), nullable=False),
        sa.Column("rodada", sa.Integer(), nullable=False),
        sa.Column("indice_trecho", sa.Integer(), nullable=False),
        sa.Column("trecho_original", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("instrucao", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("reescrita", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("avaliacao", sa.JSON(), nullable=False),
        sa.Column("modelo", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("versao_prompt", sa.Integer(), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["feedback_id"], ["writingfeedback.id"], name="fk_writingrewrite_feedback_id_writingfeedback",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("feedback_id", "rodada", "indice_trecho", name="uq_writingrewrite_rodada_trecho"),
    )
    op.create_index("ix_writingrewrite_feedback_id", "writingrewrite", ["feedback_id"], unique=False)


def downgrade() -> None:
    # Ordem inversa das dependências: quem aponta para outra tabela sai antes dela.
    op.drop_index("ix_writingrewrite_feedback_id", table_name="writingrewrite")
    op.drop_table("writingrewrite")
    op.drop_table("writingfeedback")
    op.drop_index("ix_writingattempt_prompt_id", table_name="writingattempt")
    op.drop_index("ix_writingattempt_usuario_id", table_name="writingattempt")
    op.drop_table("writingattempt")
    op.drop_index("ix_writingprompt_categoria", table_name="writingprompt")
    op.drop_table("writingprompt")
