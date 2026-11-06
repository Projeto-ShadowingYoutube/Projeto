"""Modelos do banco: usuários e suas sessões de login, Decks (baralhos) e os Cards de revisão espaçada de cada um."""
from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import NaiveDatetime
from sqlmodel import Field, Relationship, SQLModel

FUSO = ZoneInfo("America/Sao_Paulo")


def agora() -> datetime:
    """Momento atual no horário de Brasília, sem fuso (é assim que as datas ficam gravadas no banco)."""
    return datetime.now(FUSO).replace(tzinfo=None)


class Usuario(SQLModel, table=True):
    """Conta de quem usa o app. A senha nunca é guardada: só o hash Argon2 dela (ver services/auth.py)."""
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)  # sempre em minúsculas e sem espaços
    senha_hash: str
    data_criacao: NaiveDatetime = Field(default_factory=agora)


class Sessao(SQLModel, table=True):
    """Um login ativo. O cookie leva o token; aqui fica só o SHA-256 dele (um vazamento do banco não dá acesso)."""
    id: int | None = Field(default=None, primary_key=True)
    token_hash: str = Field(index=True, unique=True)
    usuario_id: int = Field(foreign_key="usuario.id", index=True)
    data_criacao: NaiveDatetime = Field(default_factory=agora)
    expira_em: NaiveDatetime


class Deck(SQLModel, table=True):
    """Baralho que agrupa os Cards criados pelo usuário."""
    id: int | None = Field(default=None, primary_key=True)
    nome: str = Field(min_length=1, index=True, unique=True)

    # Ao deletar um Deck, todos os seus Cards são deletados junto.
    cards: list["Card"] = Relationship(back_populates="deck", cascade_delete=True)


class Card(SQLModel, table=True):
    """Trecho de legenda salvo para revisão espaçada, ligado ao vídeo de origem."""
    id: int | None = Field(default=None, primary_key=True)
    texto_legenda: str = Field(min_length=1)

    # Vídeo do YouTube (ID de 11 caracteres) e o intervalo, em segundos, em que a frase aparece:
    video_id: str = Field(index=True)
    start_time: float
    end_time: float

    data_criacao: NaiveDatetime = Field(default_factory=agora)
    data_proxima_revisao: NaiveDatetime = Field(default_factory=agora)

    # Quantas vezes o Card já foi revisado (0 = Card "Novo"):
    revisao: int = Field(default=0)

    deck_id: int = Field(foreign_key="deck.id", index=True)
    deck: Deck | None = Relationship(back_populates="cards")


class EntradaDicionario(SQLModel, table=True):
    """Cache das consultas ao dicionário, para não buscar a mesma palavra duas vezes."""
    palavra: str = Field(primary_key=True)
    dados: str  # JSON com as definições; "null" quando a palavra não foi encontrada
    data_consulta: NaiveDatetime = Field(default_factory=agora)
