"""Formatos de entrada e saída da API do Writing Challenge (Membro 3). Documentados em /docs."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.writing_desafios import MAX_CARACTERES
from app.services.writing_temas import CATEGORIAS

# --- Entrada ---


class NovoDesafio(BaseModel):
    """Sem categoria (ou sem corpo): "Surpresa", qualquer categoria."""
    model_config = ConfigDict(extra="forbid")

    categoria: str | None = None

    @field_validator("categoria")
    @classmethod
    def categoria_conhecida(cls, valor):
        if valor is not None and valor not in CATEGORIAS:
            raise ValueError(f"categoria desconhecida (use uma de: {', '.join(CATEGORIAS)})")
        return valor


class TextoRedacao(BaseModel):
    """Autosave e envio: só o texto. Estado, prazo e palavras nunca vêm do cliente (extra="forbid" → 422)."""
    model_config = ConfigDict(extra="forbid")

    texto: str = Field(max_length=MAX_CARACTERES)


# --- Saída ---


class CategoriaWriting(BaseModel):
    slug: str
    nome: str
    prova: str
    tempo_limite_segundos: int
    palavras_minimas: int


class TentativaWriting(BaseModel):
    id: int
    estado: str  # rascunho | enviada | avaliada | erro_avaliacao
    categoria: str
    categoria_nome: str
    enunciado: str
    tempo_limite_segundos: int
    palavras_minimas: int
    texto: str
    palavras: int  # contagem do servidor (a que vale)
    iniciada_em: datetime  # horário de Brasília, sem fuso (como o resto do app)
    prazo: datetime
    segundos_restantes: int  # pelo relógio do servidor: o timer da tela parte daqui
    salva_em: datetime | None
    enviada_em: datetime | None
    usou_ultimo_salvamento: bool = False  # só no envio: o prazo tinha acabado e foi enviado o último autosave


class ResumoTentativa(BaseModel):
    id: int
    estado: str
    categoria: str
    categoria_nome: str
    palavras: int
    iniciada_em: datetime
    enviada_em: datetime | None


class AutosaveSalvo(BaseModel):
    palavras: int
    salva_em: datetime
    segundos_restantes: int
