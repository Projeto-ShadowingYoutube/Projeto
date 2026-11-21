"""Categorias de redação (inspiradas no TOEFL e no IELTS) e sorteio do tema (Membro 3, W2).

As categorias ficam aqui, e não numa tabela: mudam junto com o código (prompts da LLM, telas). Os temas ficam no
banco (tabela writingprompt); os iniciais vêm da migração de dados 0302, que copia tempo e mínimo de palavras de cada
categoria. tests/writing/test_temas.py confere que a migração e esta lista não divergem.
"""
from dataclasses import dataclass

from sqlalchemy import func
from sqlmodel import Session, select

from app.models_writing import WritingPrompt


@dataclass(frozen=True)
class Categoria:
    nome: str  # como aparece na tela
    prova: str  # de onde vem o formato
    tempo_limite_segundos: int
    palavras_minimas: int  # recomendação: não bloqueia o envio, pesa no "atendimento à tarefa"


CATEGORIAS: dict[str, Categoria] = {
    "ielts_opiniao": Categoria("Opinião", "IELTS Writing Task 2", 40 * 60, 250),
    "ielts_discussao": Categoria("Discussão de dois lados", "IELTS Writing Task 2", 40 * 60, 250),
    "ielts_problema_solucao": Categoria("Problema e solução", "IELTS Writing Task 2", 40 * 60, 250),
    "ielts_vantagens": Categoria("Vantagens e desvantagens", "IELTS Writing Task 2", 40 * 60, 250),
    "toefl_discussao_academica": Categoria("Discussão acadêmica", "TOEFL (Academic Discussion)", 10 * 60, 100),
    "toefl_independente": Categoria("Preferência pessoal", "TOEFL (Independent Writing)", 30 * 60, 300),
}


def sortear_tema(session: Session, categoria: str | None = None) -> WritingPrompt | None:
    """Um tema ativo ao acaso: da categoria pedida ou, com None ("Surpresa"), de qualquer categoria.
    Devolve None se não houver tema ativo. O banco sorteia (func.random(): igual no SQLite e no Postgres)."""
    if categoria is not None and categoria not in CATEGORIAS:
        raise ValueError(f"categoria desconhecida: {categoria!r}")
    consulta = select(WritingPrompt).where(WritingPrompt.ativo.is_(True))
    if categoria is not None:
        consulta = consulta.where(WritingPrompt.categoria == categoria)
    return session.exec(consulta.order_by(func.random()).limit(1)).first()
