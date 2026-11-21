"""Modelos do Writing Challenge e do Rewrite Challenge (Membro 3; ver README_MEMBRO3.md).

    Usuario ──1:N──► WritingAttempt ──N:1──► WritingPrompt   (tema: compartilhado, sem dono)
                          │
                          └──1:1──► WritingFeedback ──1:N──► WritingRewrite

- O dono de tudo é o dono da tentativa (usuario_id): o feedback e as reescritas pertencem a ela, como o Card
  pertence ao Deck. Recurso de outra conta responde 404 nas rotas.
- O texto enviado nunca é sobrescrito: depois da submissão a tentativa sai de "rascunho" e o autosave é recusado.
  As reescritas são linhas novas (nada é atualizado), e o histórico original → feedback → rewrite sai das ligações.
- Notas e trechos em JSON (como Waveform.peaks): são sempre lidos e gravados junto com o feedback.
"""
from pydantic import NaiveDatetime
from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models import agora

# Estados da tentativa (validados no código; o banco não tem CHECK, como no resto do projeto).
RASCUNHO = "rascunho"
ENVIADA = "enviada"
AVALIADA = "avaliada"
ERRO_AVALIACAO = "erro_avaliacao"
ESTADOS = (RASCUNHO, ENVIADA, AVALIADA, ERRO_AVALIACAO)


class WritingPrompt(SQLModel, table=True):
    """Tema de redação, compartilhado por todos (sem dono). Os iniciais vêm da migração de dados 0302.
    "ativo" aposenta um tema sem apagá-lo: tentativas antigas continuam apontando para ele."""
    id: int | None = Field(default=None, primary_key=True)
    categoria: str = Field(index=True)  # ex.: "ielts_opiniao" (lista em services/writing_temas.py)
    enunciado: str
    tempo_limite_segundos: int
    palavras_minimas: int  # recomendação do tema: não bloqueia o envio, pesa no "atendimento à tarefa"
    ativo: bool = Field(default=True)


class WritingAttempt(SQLModel, table=True):
    """Uma redação de um usuário sobre um tema: rascunho → enviada → avaliada (ou erro_avaliacao)."""
    id: int | None = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuario.id", index=True)
    prompt_id: int = Field(foreign_key="writingprompt.id", index=True)

    texto: str = Field(default="")
    estado: str = Field(default=RASCUNHO)
    palavras: int = Field(default=0)  # contagem do servidor (a que vale)

    iniciada_em: NaiveDatetime = Field(default_factory=agora)
    # Gravado ao criar (início + tempo do tema): mudar o tempo do tema depois não afeta tentativas abertas.
    prazo: NaiveDatetime
    salva_em: NaiveDatetime | None = None  # último autosave
    enviada_em: NaiveDatetime | None = None

    avaliacoes_tentadas: int = Field(default=0)  # chamadas à LLM já feitas (limite de reavaliações, D4)


class WritingFeedback(SQLModel, table=True):
    """Correção por IA de uma tentativa. No máximo uma por tentativa (garantido pelo banco)."""
    __table_args__ = (UniqueConstraint("attempt_id", name="uq_writingfeedback_attempt"),)

    id: int | None = Field(default=None, primary_key=True)
    attempt_id: int = Field(foreign_key="writingattempt.id")

    # {"gramatica": {"nota": 7, "comentario": "..."}, "vocabulario": {...}, ...}
    notas: dict = Field(sa_column=Column(JSON, nullable=False))
    nota_geral: float  # média das notas, calculada pelo servidor (D1)
    resumo: str
    # [{"categoria", "citacao", "inicio", "fim", "gravidade", "explicacao", "sugestao", "instrucao_reescrita"}]
    trechos: list[dict] = Field(sa_column=Column(JSON, nullable=False))

    # Quem gerou: permite comparar avaliações depois que o prompt ou o modelo mudarem.
    modelo: str
    versao_prompt: int
    criado_em: NaiveDatetime = Field(default_factory=agora)


class WritingRewrite(SQLModel, table=True):
    """Uma reescrita de um trecho apontado no feedback, numa rodada do Rewrite Challenge. Nunca é atualizada:
    cada envio é uma linha nova. Trecho original e instrução são copiados para o histórico ficar legível sozinho."""
    __table_args__ = (
        UniqueConstraint("feedback_id", "rodada", "indice_trecho", name="uq_writingrewrite_rodada_trecho"),
    )

    id: int | None = Field(default=None, primary_key=True)
    feedback_id: int = Field(foreign_key="writingfeedback.id", index=True)
    rodada: int  # 1 ou 2 (D4)
    indice_trecho: int  # posição do trecho em WritingFeedback.trechos

    trecho_original: str
    instrucao: str
    reescrita: str
    # {"melhorou": true, "nota": 8, "comentario": "..."}
    avaliacao: dict = Field(sa_column=Column(JSON, nullable=False))

    modelo: str
    versao_prompt: int
    criado_em: NaiveDatetime = Field(default_factory=agora)
