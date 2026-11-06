"""Formatos de entrada e saída da API (validados pelo FastAPI e documentados em /docs)."""
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.config import PADRAO_VIDEO_ID

Dificuldade = Literal["dificil", "medio", "facil"]


# --- Entrada ---

class NovoUsuario(BaseModel):
    email: EmailStr = Field(max_length=254)
    # Mínimo de 8 (recomendação do NIST); o máximo evita que senhas enormes sobrecarreguem o Argon2.
    senha: str = Field(min_length=8, max_length=128)


class Credenciais(BaseModel):
    # No login não se valida o formato: qualquer erro vira o mesmo 401 genérico.
    email: str = Field(max_length=254)
    senha: str = Field(max_length=128)


class NomeDeck(BaseModel):
    nome: str = Field(max_length=100)


class NovoCard(BaseModel):
    video_id: str = Field(pattern=PADRAO_VIDEO_ID)
    texto_legenda: str = Field(min_length=1, max_length=1000)
    start_time: float = Field(ge=0)
    end_time: float = Field(gt=0)

    @model_validator(mode="after")
    def fim_depois_do_inicio(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time precisa ser maior que start_time.")
        return self


class AvaliacaoCard(BaseModel):
    dificuldade: Dificuldade


# --- Saída ---

class UsuarioPublico(BaseModel):
    """O que a API mostra de um usuário (nunca o hash da senha)."""
    id: int
    email: str


class Frase(BaseModel):
    id_do_bloco: int
    texto_limpo: str
    tempo_inicio: float
    tempo_fim: float
    tempos_palavras: list[list[float]]


class Legendas(BaseModel):
    video_id: str
    dados: list[Frase]
    tokens_restantes: int
    legenda_manual: bool
    titulo_video: str
    aviso_legenda: str


class ResumoDeck(BaseModel):
    id: int
    nome: str
    novos: int
    revisar: int
    quantidade_total: int


class DeckSalvo(BaseModel):
    id: int
    nome: str


class CardParaRevisar(BaseModel):
    id: int
    texto_legenda: str
    start_time: float
    end_time: float
    video_id: str


class RevisaoSalva(BaseModel):
    card_id: int
    nova_revisao: str
    numero_revisoes: int


class StatusVideo(BaseModel):
    pronto: bool
    progresso: float


class TemposPalavras(BaseModel):
    tempos: list[list[float]] | None
    fonte: Literal["youtube", "audio", "estimativa"]


class NotaPalavras(BaseModel):
    nota: int
    ditas: list[bool]
    reconhecido: str


class NotaRitmo(BaseModel):
    nota: int
    erro_medio: float


class NotaEntonacao(BaseModel):
    nota: int
    correlacao: float
    curva_original: list[float]
    curva_usuario: list[float]


class ResultadoAvaliacao(BaseModel):
    nota: int
    palavras: NotaPalavras
    ritmo: NotaRitmo | None
    entonacao: NotaEntonacao | None
    razao_velocidade: float | None
