"""Reading Challenge (Membro 1, bloco R7): envio das respostas e correção da múltipla escolha, sem FastAPI.

    tentativa = enviar_respostas(session, desafio, ["Right 1", "", ...])

- Só com o desafio em "respondendo" (a leitura foi encerrada no R6); em "lendo", LeituraEmAndamento (DR28).
- Uma tentativa por desafio: o UNIQUE do banco (uq_readingattempt_desafio) garante, mesmo com duas requisições ao
  mesmo tempo; a segunda vira JaRespondido.
- Múltipla escolha: corrigida aqui, na hora (o cliente nunca recebeu a resposta certa). Cada resposta tem de ser uma
  das alternativas ou "" (não respondida, conta como erro, DR25). nota = acertos × 2, de 0 a 10 (DR27).
  Estado → "corrigido".
- Aberta: as respostas são gravadas e o estado vai para "avaliando"; a correção pela LLM é o bloco R8.
- Tempos: leitura = leitura_encerrada_em − iniciado_em (nunca passa do limite, R6); resposta = envio − fim da leitura.
A tentativa e o novo estado do desafio vão num único commit.
"""
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models_reading import ReadingAttempt, ReadingChallenge, ReadingQuestion
from app.services import reading_desafios as rd

CORRIGIDO = "corrigido"
AVALIANDO = "avaliando"
PONTOS_POR_ACERTO = 2  # 5 perguntas → nota de 0 a 10


class LeituraEmAndamento(Exception):
    """As respostas chegaram com o desafio ainda em "lendo"."""


class JaRespondido(Exception):
    """O desafio já tem uma tentativa."""


class SemResultado(Exception):
    """Pediram o resultado de um desafio sem tentativa."""


class RespostaInvalida(ValueError):
    """Na múltipla escolha, a resposta não é uma das alternativas da pergunta."""

    def __init__(self, ordem: int):
        self.ordem = ordem
        super().__init__(f"a resposta da pergunta {ordem} não é uma das alternativas")


def corrigir_multipla_escolha(perguntas: list[ReadingQuestion], respostas: list[str]) -> list[dict]:
    """Correção por pergunta ({ordem, resposta, correta}). Função pura: compara com a grafia exata (R4)."""
    if len(perguntas) != len(respostas):
        raise ValueError("uma resposta por pergunta")
    avaliacao = []
    for pergunta, resposta in zip(perguntas, respostas, strict=True):
        if resposta and resposta not in pergunta.alternativas:
            raise RespostaInvalida(pergunta.ordem)
        avaliacao.append({"ordem": pergunta.ordem, "resposta": resposta,
                          "correta": resposta == pergunta.resposta_correta})
    return avaliacao


def nota_de(acertos: int) -> float:
    return float(acertos * PONTOS_POR_ACERTO)


def enviar_respostas(session: Session, desafio: ReadingChallenge, respostas: list[str],
                     momento: datetime | None = None) -> ReadingAttempt:
    """Grava a tentativa (e corrige, na múltipla escolha). Levanta LeituraEmAndamento, JaRespondido ou
    RespostaInvalida."""
    if desafio.estado == rd.LENDO:
        raise LeituraEmAndamento()
    if desafio.estado != rd.RESPONDENDO or tentativa_do_desafio(session, desafio) is not None:
        raise JaRespondido()
    momento = momento or rd.agora()
    perguntas = rd.perguntas_do_desafio(session, desafio)

    tentativa = ReadingAttempt(
        usuario_id=desafio.usuario_id, desafio_id=desafio.id, modalidade=desafio.modalidade, respostas=respostas,
        tempo_leitura_segundos=_segundos(desafio.leitura_encerrada_em - desafio.iniciado_em),
        tempo_resposta_segundos=_segundos(momento - desafio.leitura_encerrada_em),
        enviado_em=momento,
    )
    if desafio.modalidade == "multipla_escolha":
        tentativa.avaliacao = corrigir_multipla_escolha(perguntas, respostas)
        tentativa.acertos = sum(item["correta"] for item in tentativa.avaliacao)
        tentativa.nota = nota_de(tentativa.acertos)
        tentativa.avaliado_em = momento
        desafio.estado = CORRIGIDO
    else:
        desafio.estado = AVALIANDO  # R8: correção pela LLM

    session.add(tentativa)
    session.add(desafio)
    try:
        session.commit()
    except IntegrityError:
        # Outra requisição gravou a tentativa entre a consulta e o commit (UNIQUE do desafio_id).
        session.rollback()
        raise JaRespondido() from None
    session.refresh(tentativa)
    return tentativa


def tentativa_do_desafio(session: Session, desafio: ReadingChallenge) -> ReadingAttempt | None:
    return session.exec(select(ReadingAttempt).where(ReadingAttempt.desafio_id == desafio.id)).first()


def _segundos(intervalo) -> int:
    return max(0, round(intervalo.total_seconds()))
