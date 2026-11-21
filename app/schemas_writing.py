"""Formatos do Writing Challenge (Membro 3): entrada e saída da API (documentados em /docs) e o contrato JSON que a
LLM precisa seguir na correção (AvaliacaoLLM)."""
from datetime import datetime
from typing import Literal, get_args

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
    avaliacoes_restantes: int  # tentativas de correção que ainda restam (D4)
    feedback: "FeedbackWriting | None" = None  # null até ser avaliada


class ResumoTentativa(BaseModel):
    id: int
    estado: str
    categoria: str
    categoria_nome: str
    palavras: int
    iniciada_em: datetime
    enviada_em: datetime | None
    nota_geral: float | None = None  # null até ser avaliada


class AutosaveSalvo(BaseModel):
    palavras: int
    salva_em: datetime
    segundos_restantes: int


# --- Contrato da correção por IA (W5) ---
# llm.gerar_json manda o JSON Schema destes modelos junto das instruções e valida a resposta com eles: nota fora de
# 0–10, categoria faltando ou texto grande demais = resposta inválida (o llm.py pede de novo uma vez). As
# "description" vão no schema e orientam a LLM.

CategoriaAvaliada = Literal["gramatica", "vocabulario", "coerencia", "organizacao", "atendimento_tarefa"]
CATEGORIAS_AVALIADAS: tuple[str, ...] = get_args(CategoriaAvaliada)


class NotaCategoria(BaseModel):
    nota: int = Field(ge=0, le=10, description="Nota inteira de 0 a 10.")
    comentario: str = Field(min_length=1, max_length=600, description="Comentário em português do Brasil.")


class NotasPorCategoria(BaseModel):
    """Chaves fixas, todas obrigatórias: faltar uma categoria é resposta inválida (numa lista, passaria)."""
    gramatica: NotaCategoria = Field(description="Correção gramatical.")
    vocabulario: NotaCategoria = Field(description="Variedade, precisão e ortografia das palavras.")
    coerencia: NotaCategoria = Field(description="Clareza e lógica das ideias e a ligação entre elas.")
    organizacao: NotaCategoria = Field(description="Estrutura do texto e divisão em parágrafos.")
    atendimento_tarefa: NotaCategoria = Field(description="Resposta ao tema e à tarefa, e o mínimo de palavras.")


class TrechoLLM(BaseModel):
    categoria: CategoriaAvaliada = Field(description="Categoria do problema.")
    citacao: str = Field(
        min_length=1, max_length=300,
        description="Cópia EXATA de um pedaço da redação, caractere por caractere, sem corrigir e sem aspas.",
    )
    gravidade: int = Field(ge=1, le=3, description="1 = leve, 2 = médio, 3 = grave.")
    explicacao: str = Field(min_length=1, max_length=400, description="O problema, explicado em português.")
    sugestao: str = Field(max_length=300, description="A versão corrigida do trecho, em inglês.")
    instrucao_reescrita: str = Field(
        min_length=1, max_length=300,
        description="O que o estudante deve mudar, em português, SEM dar a resposta pronta.",
    )


class AvaliacaoLLM(BaseModel):
    categorias: NotasPorCategoria
    resumo: str = Field(min_length=1, max_length=800, description="Comentário geral sobre a redação, em português.")
    trechos: list[TrechoLLM] = Field(
        default_factory=list, max_length=15, description="Trechos problemáticos (no máximo 10, os mais graves).",
    )


# --- Feedback gravado (saída da API, W6) ---

class TrechoAvaliado(BaseModel):
    """Trecho já localizado no texto. inicio/fim em caracteres Unicode (no JS: Array.from(texto), não slice)."""
    categoria: str
    citacao: str
    inicio: int
    fim: int
    gravidade: int
    explicacao: str
    sugestao: str
    instrucao_reescrita: str


class FeedbackWriting(BaseModel):
    notas: dict[str, NotaCategoria]
    nota_geral: float
    resumo: str
    trechos: list[TrechoAvaliado]
    modelo: str
    versao_prompt: int
    criado_em: datetime


TentativaWriting.model_rebuild()  # resolve a referência a FeedbackWriting, definido depois
