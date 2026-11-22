"""Reading Challenge (Membro 1): schemas Pydantic da feature.

Blocos R5 a R7: entrada e saída da API (fim do arquivo).

Bloco R4: o formato das 5 perguntas. O mesmo schema serve para duas coisas:
- vai para a LLM como JSON Schema (o llm.gerar_json o anexa às instruções) e valida a resposta dela;
- valida as perguntas prontas dos textos de reserva (migração 0102), para as duas origens terem a mesma garantia.

Um schema por modalidade (e não um genérico com "tipo"): a LLM recebe a forma exata do que deve devolver, e a
validação recusa, por exemplo, uma pergunta aberta com alternativas.
"""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

QUANTIDADE_PERGUNTAS = 5
QUANTIDADE_ALTERNATIVAS = 4

# Limites de tamanho: protegem o banco e a tela de uma resposta desproporcional da LLM.
LIMITE_ENUNCIADO = 300
LIMITE_ALTERNATIVA = 200
LIMITE_RESPOSTA = 400
LIMITE_JUSTIFICATIVA = 600

Alternativa = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=LIMITE_ALTERNATIVA)]


def _chave(texto: str) -> str:
    """Forma de comparar textos ignorando maiúsculas e espaços ("Honey" e " honey " são a mesma alternativa)."""
    return " ".join(texto.split()).casefold()


class _Pergunta(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    enunciado: str = Field(min_length=5, max_length=LIMITE_ENUNCIADO,
                           description="A pergunta, em inglês, respondível só com o trecho.")
    resposta_correta: str = Field(min_length=1, max_length=LIMITE_RESPOSTA)
    justificativa: str = Field(min_length=5, max_length=LIMITE_JUSTIFICATIVA,
                               description="Em português, citando entre aspas o trecho do texto (em inglês).")


class PerguntaMultiplaEscolha(_Pergunta):
    tipo: Literal["multipla_escolha"] = "multipla_escolha"
    alternativas: list[Alternativa] = Field(min_length=QUANTIDADE_ALTERNATIVAS, max_length=QUANTIDADE_ALTERNATIVAS,
                                            description="4 alternativas em inglês, diferentes, só uma correta.")
    resposta_correta: str = Field(min_length=1, max_length=LIMITE_ALTERNATIVA,
                                  description="Cópia exata de uma das alternativas.")

    @model_validator(mode="after")
    def _alternativas_coerentes(self):
        chaves = [_chave(a) for a in self.alternativas]
        if len(set(chaves)) != len(chaves):
            raise ValueError("as alternativas devem ser diferentes entre si")
        if _chave(self.resposta_correta) not in chaves:
            raise ValueError("a resposta_correta deve ser uma das alternativas")
        # Guarda a resposta com a grafia exata da alternativa: a correção (R7) compara strings iguais.
        self.resposta_correta = self.alternativas[chaves.index(_chave(self.resposta_correta))]
        return self


class PerguntaAberta(_Pergunta):
    tipo: Literal["aberta"] = "aberta"
    alternativas: list[str] = Field(default_factory=list, max_length=0,
                                    description="Sempre vazia: a pergunta aberta não tem alternativas.")
    resposta_correta: str = Field(min_length=1, max_length=LIMITE_RESPOSTA,
                                  description="A resposta esperada, em inglês, em uma ou duas frases.")


def _enunciados_diferentes(perguntas: list[_Pergunta]) -> list[_Pergunta]:
    chaves = [_chave(p.enunciado) for p in perguntas]
    if len(set(chaves)) != len(chaves):
        raise ValueError("as perguntas devem ser diferentes entre si")
    return perguntas


class PerguntasMultiplaEscolha(BaseModel):
    perguntas: list[PerguntaMultiplaEscolha] = Field(min_length=QUANTIDADE_PERGUNTAS,
                                                     max_length=QUANTIDADE_PERGUNTAS)

    _diferentes = field_validator("perguntas")(_enunciados_diferentes)


class PerguntasAbertas(BaseModel):
    perguntas: list[PerguntaAberta] = Field(min_length=QUANTIDADE_PERGUNTAS, max_length=QUANTIDADE_PERGUNTAS)

    _diferentes = field_validator("perguntas")(_enunciados_diferentes)


SCHEMA_DA_MODALIDADE: dict[str, type[PerguntasMultiplaEscolha] | type[PerguntasAbertas]] = {
    "multipla_escolha": PerguntasMultiplaEscolha,
    "aberta": PerguntasAbertas,
}


# --- Bloco R5: criação do desafio (API) ---

class NovoDesafio(BaseModel):
    """Corpo de POST /api/reading/challenges. Campo desconhecido é recusado (422), para um erro de digitação no front
    não passar despercebido."""
    model_config = ConfigDict(extra="forbid")

    modalidade: Literal["multipla_escolha", "aberta"]
    fonte: Literal["wikipedia", "gutenberg"] = "wikipedia"
    ppm: Literal[150, 200, 250] = 200  # palavras por minuto (DR4)


class TextoDoDesafio(BaseModel):
    titulo: str
    conteudo: str
    palavras: int
    fonte: str
    url: str | None
    credito: str  # crédito e licença, obrigatórios na tela (CC BY-SA da Wikipedia)


class ResumoDesafio(BaseModel):
    """O desafio sem o texto e sem as perguntas (GET /api/reading/challenges/{id})."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    estado: str
    modalidade: str
    ppm: int
    limite_segundos: int
    iniciado_em: datetime
    leitura_encerrada_em: datetime | None
    usou_reserva: bool
    segundos_restantes: int  # calculado no servidor (R6): o timer da tela não depende do relógio do navegador


class DesafioCriado(ResumoDesafio):
    """Resposta da criação: o texto para ler. As perguntas ficam no servidor até a leitura terminar (R6)."""
    texto: TextoDoDesafio


# --- Bloco R6: leitura com o tempo validado no servidor ---

class TextoParaLer(TextoDoDesafio):
    """GET /api/reading/challenges/{id}/texto: o texto de novo (ex.: F5), só dentro do prazo."""
    segundos_restantes: int


class PerguntaParaResponder(BaseModel):
    """A pergunta como a pessoa a vê: sem a resposta correta e sem a justificativa (só no resultado, R7)."""
    model_config = ConfigDict(from_attributes=True)

    ordem: int
    tipo: str
    enunciado: str
    alternativas: list[str]


class LeituraEncerrada(ResumoDesafio):
    """POST /api/reading/challenges/{id}/encerrar-leitura."""
    perguntas: list[PerguntaParaResponder]


# --- Bloco R7: respostas e resultado ---

LIMITE_RESPOSTA_DO_USUARIO = 1000  # a resposta aberta é de uma ou duas frases; protege o banco e o custo da LLM (R8)

RespostaDoUsuario = Annotated[str, StringConstraints(strip_whitespace=True, max_length=LIMITE_RESPOSTA_DO_USUARIO)]


class RespostasEnviadas(BaseModel):
    """Corpo de POST /api/reading/challenges/{id}/respostas: uma resposta por pergunta, na ordem 1 a 5.
    Texto vazio ("") é uma pergunta não respondida e conta como erro (DR25)."""
    model_config = ConfigDict(extra="forbid")

    respostas: list[RespostaDoUsuario] = Field(min_length=QUANTIDADE_PERGUNTAS, max_length=QUANTIDADE_PERGUNTAS)


class PerguntaCorrigida(BaseModel):
    ordem: int
    tipo: str
    enunciado: str
    alternativas: list[str]
    resposta: str                 # a da pessoa ("" = não respondida)
    correta: bool | None          # None enquanto a aberta não foi corrigida (R8)
    resposta_correta: str
    justificativa: str
    comentario: str | None = None  # comentário da correção da aberta (R8)


class ResultadoDesafio(BaseModel):
    """POST /respostas e GET /resultado. A leitura acabou: o texto volta, para conferir as justificativas (DR26)."""
    id: int
    estado: str
    modalidade: str
    usou_reserva: bool
    acertos: int | None
    nota: float | None  # 0 a 10 (cada acerto vale 2, DR27)
    tempo_leitura_segundos: int
    tempo_resposta_segundos: int
    enviado_em: datetime
    avaliado_em: datetime | None
    texto: TextoDoDesafio
    perguntas: list[PerguntaCorrigida]
