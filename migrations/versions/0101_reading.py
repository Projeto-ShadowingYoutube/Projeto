"""Reading Challenge (Membro 1, bloco R1): textos, desafios, perguntas e tentativas.

Revisão: 0101
Anterior: 0006
Criada em: 2026-11-21

Só cria as quatro tabelas (vazias). Os textos de reserva entram numa migração de dados separada (0102, bloco R3).
Toda FK e todo UNIQUE têm nome: o autogenerate gera FK sem nome, e o downgrade quebra (ver 0003).
Na integração, as migrações dos Membros 2 e 3 também partem da 0006: o Membro 4 junta as cabeças com "alembic merge".
"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0101"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TEXTO = sqlmodel.sql.sqltypes.AutoString


def upgrade() -> None:
    op.create_table(
        "readingtext",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("fonte", TEXTO(), nullable=False),
        sa.Column("id_origem", TEXTO(), nullable=False),
        sa.Column("titulo", TEXTO(), nullable=False),
        sa.Column("url", TEXTO(), nullable=True),
        sa.Column("conteudo", TEXTO(), nullable=False),
        sa.Column("palavras", sa.Integer(), nullable=False),
        sa.Column("perguntas_reserva", sa.JSON(), nullable=True),
        sa.Column("data_criacao", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fonte", "id_origem", name="uq_readingtext_fonte_origem"),
    )
    op.create_index("ix_readingtext_fonte", "readingtext", ["fonte"], unique=False)

    op.create_table(
        "readingchallenge",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("texto_id", sa.Integer(), nullable=False),
        sa.Column("modalidade", TEXTO(), nullable=False),
        sa.Column("ppm", sa.Integer(), nullable=False),
        sa.Column("limite_segundos", sa.Integer(), nullable=False),
        sa.Column("estado", TEXTO(), nullable=False),
        sa.Column("usou_reserva", sa.Boolean(), nullable=False),
        sa.Column("modelo_llm", TEXTO(), nullable=True),
        sa.Column("iniciado_em", sa.DateTime(), nullable=False),
        sa.Column("leitura_encerrada_em", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"], name="fk_readingchallenge_usuario_id_usuario"),
        sa.ForeignKeyConstraint(["texto_id"], ["readingtext.id"], name="fk_readingchallenge_texto_id_readingtext"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_readingchallenge_usuario_id", "readingchallenge", ["usuario_id"], unique=False)
    op.create_index("ix_readingchallenge_texto_id", "readingchallenge", ["texto_id"], unique=False)

    op.create_table(
        "readingquestion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("desafio_id", sa.Integer(), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("tipo", TEXTO(), nullable=False),
        sa.Column("enunciado", TEXTO(), nullable=False),
        sa.Column("alternativas", sa.JSON(), nullable=False),
        sa.Column("resposta_correta", TEXTO(), nullable=False),
        sa.Column("justificativa", TEXTO(), nullable=False),
        sa.ForeignKeyConstraint(["desafio_id"], ["readingchallenge.id"],
                                name="fk_readingquestion_desafio_id_readingchallenge"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("desafio_id", "ordem", name="uq_readingquestion_desafio_ordem"),
    )
    op.create_index("ix_readingquestion_desafio_id", "readingquestion", ["desafio_id"], unique=False)

    op.create_table(
        "readingattempt",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("desafio_id", sa.Integer(), nullable=False),
        sa.Column("modalidade", TEXTO(), nullable=False),
        sa.Column("respostas", sa.JSON(), nullable=False),
        sa.Column("avaliacao", sa.JSON(), nullable=False),
        sa.Column("acertos", sa.Integer(), nullable=True),
        sa.Column("nota", sa.Float(), nullable=True),
        sa.Column("tempo_leitura_segundos", sa.Integer(), nullable=False),
        sa.Column("tempo_resposta_segundos", sa.Integer(), nullable=False),
        sa.Column("modelo_llm", TEXTO(), nullable=True),
        sa.Column("enviado_em", sa.DateTime(), nullable=False),
        sa.Column("avaliado_em", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"], name="fk_readingattempt_usuario_id_usuario"),
        sa.ForeignKeyConstraint(["desafio_id"], ["readingchallenge.id"],
                                name="fk_readingattempt_desafio_id_readingchallenge"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("desafio_id", name="uq_readingattempt_desafio"),
    )
    op.create_index("ix_readingattempt_usuario_id", "readingattempt", ["usuario_id"], unique=False)


def downgrade() -> None:
    # Ordem inversa: primeiro quem aponta para as outras tabelas.
    op.drop_index("ix_readingattempt_usuario_id", table_name="readingattempt")
    op.drop_table("readingattempt")
    op.drop_index("ix_readingquestion_desafio_id", table_name="readingquestion")
    op.drop_table("readingquestion")
    op.drop_index("ix_readingchallenge_texto_id", table_name="readingchallenge")
    op.drop_index("ix_readingchallenge_usuario_id", table_name="readingchallenge")
    op.drop_table("readingchallenge")
    op.drop_index("ix_readingtext_fonte", table_name="readingtext")
    op.drop_table("readingtext")
