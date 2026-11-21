"""Modelos do Reading Challenge (Membro 1): textos, desafios, perguntas e tentativas.

Posse: o desafio e a tentativa pertencem a um usuário (usuario_id); a pergunta pertence ao desafio. O texto é
compartilhado entre usuários (como a Waveform): o mesmo artigo é gravado uma vez só e reaproveitado.

Os valores possíveis de "fonte", "modalidade", "estado" e "tipo" ficam como texto e são validados pelos schemas e
pelos serviços do Reading (um Enum no banco exigiria uma migração a cada valor novo).
"""
from pydantic import NaiveDatetime
from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models import agora


class ReadingText(SQLModel, table=True):
    """Texto já limpo, pronto para leitura. Não pertence a um usuário."""
    # O mesmo artigo (mesma fonte e mesmo id na origem) não é gravado duas vezes.
    __table_args__ = (UniqueConstraint("fonte", "id_origem", name="uq_readingtext_fonte_origem"),)

    id: int | None = Field(default=None, primary_key=True)
    fonte: str = Field(index=True)  # "wikipedia", "gutenberg" ou "reserva"
    id_origem: str                  # id do artigo/livro na fonte (na reserva, um apelido fixo)
    titulo: str
    url: str | None = None
    conteudo: str                   # texto limpo (sem HTML, referências, listas)
    palavras: int
    # Só nos textos de reserva: as cinco perguntas prontas, usadas quando a LLM falha (decisão DR3).
    perguntas_reserva: list[dict] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    data_criacao: NaiveDatetime = Field(default_factory=agora)


class ReadingChallenge(SQLModel, table=True):
    """Um desafio de leitura de um usuário: o texto escolhido, a modalidade e o tempo da leitura."""
    id: int | None = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuario.id", index=True)
    texto_id: int = Field(foreign_key="readingtext.id", index=True)
    modalidade: str            # "multipla_escolha" ou "aberta"
    ppm: int                   # velocidade de leitura escolhida (palavras por minuto)
    limite_segundos: int       # tempo de leitura permitido (palavras ÷ ppm × 60)
    estado: str = "lendo"      # lendo → respondendo → concluido (ou erro_avaliacao)
    usou_reserva: bool = False  # as perguntas vieram do texto de reserva (fallback), e não da LLM
    modelo_llm: str | None = None  # modelo que gerou as perguntas
    iniciado_em: NaiveDatetime = Field(default_factory=agora)  # base da conferência do tempo no servidor
    leitura_encerrada_em: NaiveDatetime | None = None


class ReadingQuestion(SQLModel, table=True):
    """Uma das cinco perguntas de um desafio."""
    __table_args__ = (UniqueConstraint("desafio_id", "ordem", name="uq_readingquestion_desafio_ordem"),)

    id: int | None = Field(default=None, primary_key=True)
    desafio_id: int = Field(foreign_key="readingchallenge.id", index=True)
    ordem: int                 # 1 a 5
    tipo: str                  # "multipla_escolha" ou "aberta"
    enunciado: str
    alternativas: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))  # vazia na aberta
    resposta_correta: str      # na múltipla escolha, uma das alternativas; na aberta, a resposta esperada
    justificativa: str         # por que essa é a resposta (trecho do texto que a sustenta)


class ReadingAttempt(SQLModel, table=True):
    """As respostas de um usuário a um desafio e o resultado da correção. No máximo uma por desafio."""
    __table_args__ = (UniqueConstraint("desafio_id", name="uq_readingattempt_desafio"),)

    id: int | None = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuario.id", index=True)
    desafio_id: int = Field(foreign_key="readingchallenge.id")  # o UNIQUE acima já serve de índice
    modalidade: str
    respostas: list[str] = Field(sa_column=Column(JSON, nullable=False))  # uma por pergunta, na ordem
    # Correção por pergunta ({ordem, correta, comentario...}); vazia até a correção terminar.
    avaliacao: list[dict] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    acertos: int | None = None
    nota: float | None = None  # 0 a 10
    tempo_leitura_segundos: int
    tempo_resposta_segundos: int
    modelo_llm: str | None = None  # modelo que corrigiu as abertas
    enviado_em: NaiveDatetime = Field(default_factory=agora)
    avaliado_em: NaiveDatetime | None = None
