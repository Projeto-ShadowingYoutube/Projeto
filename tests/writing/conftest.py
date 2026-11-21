"""Fixtures do Writing Challenge. As de tests/conftest.py (engine_teste, entrar_como, llm_falsa...) continuam valendo.

O banco de teste é criado com create_all, que não roda migrações de DADOS: a tabela de temas começa vazia. Quem
precisa de temas usa a fixture "temas".
"""
import pytest
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter
from sqlmodel import Session

from app.api import llm as rota_llm
from app.models_writing import WritingPrompt
from app.services.writing_temas import CATEGORIAS


@pytest.fixture(autouse=True)
def cota_nova(monkeypatch):
    """A cota diária fica num limitador global ao processo (app/api/llm.py), e os ids de usuário recomeçam em cada
    banco de teste: sem isto, um teste herdaria os desafios gastos por outro. Mesmo padrão de tests/test_llm.py."""
    monkeypatch.setattr(rota_llm, "limitador", FixedWindowRateLimiter(MemoryStorage()))


# Resposta válida da LLM no contrato AvaliacaoLLM (média 7,4). Sem trechos: cada teste acrescenta os que precisa.
RESPOSTA_LLM = {
    "categorias": {
        "gramatica": {"nota": 6, "comentario": "Erros de concordância."},
        "vocabulario": {"nota": 7, "comentario": "Vocabulário simples."},
        "coerencia": {"nota": 8, "comentario": "Ideias claras."},
        "organizacao": {"nota": 7, "comentario": "Parágrafos bem divididos."},
        "atendimento_tarefa": {"nota": 9, "comentario": "Responde ao tema."},
    },
    "resumo": "Boa redação.",
    "trechos": [],
}


@pytest.fixture()
def llm_corrige(llm_falsa):
    """LLM simulada que responde RESPOSTA_LLM às próximas chamadas (para testes em que a correção não é o foco)."""
    for _ in range(5):
        llm_falsa.responder(RESPOSTA_LLM)
    return llm_falsa


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
