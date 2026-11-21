"""Avaliação de uma redação enviada: estados, limite de tentativas e gravação do feedback (Membro 3, W6).

Separado de writing_desafios.py (rascunho e envio) e de writing_llm.py (a conversa com a IA). Sem FastAPI: as falhas
de regra são ErroDesafio, e as da LLM são as de app/services/llm.py, relançadas com uma mensagem que avisa que a
redação está salva.

Fluxo (o texto já foi gravado pelo envio, ANTES de chegar aqui):
    sem LLM configurada → erro_avaliacao, 503, a tentativa NÃO conta (D16)
    tentativas += 1 (gravado antes da chamada: uma chamada que trava também conta, e o limite D4 não é furado)
    LLM ok    → WritingFeedback + estado "avaliada"
    LLM falha → estado "erro_avaliacao" e relança (o "avaliar de novo" fica disponível até MAX_AVALIACOES)
"""
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models_writing import AVALIADA, ERRO_AVALIACAO, RASCUNHO, WritingAttempt, WritingFeedback, WritingPrompt
from app.services import llm, writing_llm
from app.services.writing_desafios import ErroDesafio

MAX_AVALIACOES = 3  # D4: chamadas à LLM por redação (a cota diária só conta a criação do desafio)
_SALVA = "A sua redação foi salva; tente avaliar de novo."


class RedacaoJaAvaliada(ErroDesafio):
    mensagem = "Esta redação já foi avaliada."


class RedacaoNaoEnviada(ErroDesafio):
    mensagem = "Envie a redação antes de pedir a avaliação."


class LimiteDeAvaliacoes(ErroDesafio):
    mensagem = f"Esta redação já usou as {MAX_AVALIACOES} tentativas de avaliação."


def avaliacoes_restantes(tentativa: WritingAttempt) -> int:
    return max(0, MAX_AVALIACOES - tentativa.avaliacoes_tentadas)


def feedback_de(session: Session, tentativa: WritingAttempt) -> WritingFeedback | None:
    return session.exec(select(WritingFeedback).where(WritingFeedback.attempt_id == tentativa.id)).first()


def notas_gerais(session: Session, ids: list[int]) -> dict[int, float]:
    """{attempt_id: nota_geral} das redações avaliadas, numa consulta só (para a lista)."""
    if not ids:
        return {}
    consulta = select(WritingFeedback.attempt_id, WritingFeedback.nota_geral).where(WritingFeedback.attempt_id.in_(ids))
    return dict(session.exec(consulta).all())


def avaliar_redacao(session: Session, tentativa: WritingAttempt) -> WritingFeedback:
    if tentativa.estado == RASCUNHO:
        raise RedacaoNaoEnviada()
    if tentativa.estado == AVALIADA:
        raise RedacaoJaAvaliada()
    if tentativa.avaliacoes_tentadas >= MAX_AVALIACOES:
        raise LimiteDeAvaliacoes()
    if not llm.configurada():
        _marcar_erro(session, tentativa)
        raise llm.LLMNaoConfigurada(f"{llm.LLMNaoConfigurada.mensagem_padrao} A sua redação foi salva.")

    tentativa.avaliacoes_tentadas += 1
    _gravar(session, tentativa)

    tema = session.get(WritingPrompt, tentativa.prompt_id)
    try:
        resultado = writing_llm.avaliar(
            texto=tentativa.texto, enunciado=tema.enunciado, categoria=tema.categoria,
            palavras_minimas=tema.palavras_minimas, palavras=tentativa.palavras,
        )
    except llm.ErroLLM as erro:
        _marcar_erro(session, tentativa)
        if isinstance(erro, llm.LLMTempoEsgotado):
            raise llm.LLMTempoEsgotado(f"A correção demorou demais. {_SALVA}") from erro
        raise type(erro)(f"{erro.mensagem} {_SALVA}") from erro

    feedback = WritingFeedback(
        attempt_id=tentativa.id, notas=resultado.notas, nota_geral=resultado.nota_geral, resumo=resultado.resumo,
        trechos=resultado.trechos, modelo=resultado.modelo, versao_prompt=resultado.versao_prompt,
    )
    tentativa.estado = AVALIADA
    session.add(feedback)
    session.add(tentativa)
    try:
        session.commit()
    except IntegrityError as erro:  # duplo clique: outra requisição gravou o feedback primeiro (UNIQUE attempt_id)
        session.rollback()
        raise RedacaoJaAvaliada() from erro
    session.refresh(feedback)
    return feedback


def _marcar_erro(session: Session, tentativa: WritingAttempt) -> None:
    tentativa.estado = ERRO_AVALIACAO
    _gravar(session, tentativa)


def _gravar(session: Session, tentativa: WritingAttempt) -> None:
    session.add(tentativa)
    session.commit()
    session.refresh(tentativa)
