"""Reading Challenge (Membro 1): schemas Pydantic da feature.

Bloco R4: o formato das 5 perguntas. O mesmo schema serve para duas coisas:
- vai para a LLM como JSON Schema (o llm.gerar_json o anexa às instruções) e valida a resposta dela;
- valida as perguntas prontas dos textos de reserva (migração 0102), para as duas origens terem a mesma garantia.

Um schema por modalidade (e não um genérico com "tipo"): a LLM recebe a forma exata do que deve devolver, e a
validação recusa, por exemplo, uma pergunta aberta com alternativas.
"""
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
