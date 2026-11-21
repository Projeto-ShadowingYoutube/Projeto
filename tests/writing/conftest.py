"""Fixtures do Writing Challenge. As de tests/conftest.py (engine_teste, entrar_como, llm_falsa...) continuam valendo.

O banco de teste é criado com create_all, que não roda migrações de DADOS: a tabela de temas começa vazia. Quem
precisa de temas usa a fixture "temas".
"""
import pytest
from sqlmodel import Session

from app.models_writing import WritingPrompt
from app.services.writing_temas import CATEGORIAS


def criar_tema(session: Session, categoria: str, enunciado: str, ativo: bool = True) -> WritingPrompt:
    formato = CATEGORIAS[categoria]
    tema = WritingPrompt(
        categoria=categoria, enunciado=enunciado, tempo_limite_segundos=formato.tempo_limite_segundos,
        palavras_minimas=formato.palavras_minimas, ativo=ativo,
    )
    session.add(tema)
    session.commit()
    session.refresh(tema)
    return tema


@pytest.fixture()
def temas(engine_teste) -> dict[str, WritingPrompt]:
    """Dois temas ativos de opinião, um ativo do TOEFL e um INATIVO de opinião (nunca deve ser sorteado)."""
    with Session(engine_teste) as session:
        criados = {
            "opiniao_1": criar_tema(session, "ielts_opiniao", "Opinion topic one. Do you agree?"),
            "opiniao_2": criar_tema(session, "ielts_opiniao", "Opinion topic two. Do you agree?"),
            "toefl": criar_tema(session, "toefl_discussao_academica", "Academic discussion topic."),
            "inativo": criar_tema(session, "ielts_opiniao", "Retired opinion topic.", ativo=False),
        }
        for tema in criados.values():
            session.refresh(tema)  # cada commit expira os objetos anteriores: recarrega antes de desligar
            session.expunge(tema)  # continua legível depois que a sessão fecha
    return criados
