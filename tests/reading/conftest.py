"""Fixtures do Reading Challenge (Membro 1), para os testes de tests/reading/.

As fixtures da base (tests/conftest.py) continuam disponíveis: engine_teste, client, entrar_como, llm_falsa...

    pytestmark = pytest.mark.usefixtures("ambiente")   # desafios saem da reserva: sem rede e sem LLM

- relogio: relógio falso no lugar de reading_desafios.agora (começa no INICIO do arquivo de teste, se houver).
- cota_nova: a cota diária fica em memória no processo; cada teste começa com as 10 do dia.
- fonte_fora: Wikipedia e Gutenberg fora do ar (nenhuma chamada de rede).
- texto_reserva: o único texto de reserva do banco (450 palavras: limite de 135 s a 200 ppm); a resposta certa da
  pergunta n é "Right n".
- ambiente: as três acima juntas; devolve o texto de reserva.
"""
from datetime import datetime, timedelta

import pytest
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter
from sqlmodel import Session

from app.api import llm as rota_llm
from app.models_reading import ReadingText
from app.services import reading_desafios as rd
from app.services import reading_fontes as rf

INICIO_PADRAO = datetime(2026, 11, 22, 10, 0, 0)
PALAVRAS_RESERVA = 450


def pergunta_de_reserva(n: int) -> dict:
    """Pergunta pronta n (formato da migração 0102): a certa é "Right n"."""
    return {"enunciado": f"What does the text say about item {n}?",
            "alternativas": [f"Right {n}", f"Wrong A {n}", f"Wrong B {n}", f"Wrong C {n}"],
            "resposta_correta": f"Right {n}", "justificativa": f"O texto diz \"item {n}\"."}


class Relogio:
    """Relógio falso: o teste avança o tempo sem esperar."""

    def __init__(self, inicio: datetime):
        self.agora = inicio

    def __call__(self) -> datetime:
        return self.agora

    def avancar(self, segundos: float) -> None:
        self.agora += timedelta(seconds=segundos)


@pytest.fixture()
def relogio(monkeypatch, request) -> Relogio:
    falso = Relogio(getattr(request.module, "INICIO", INICIO_PADRAO))
    monkeypatch.setattr(rd, "agora", falso)
    return falso


@pytest.fixture()
def cota_nova(monkeypatch):
    monkeypatch.setattr(rota_llm, "limitador", FixedWindowRateLimiter(MemoryStorage()))


@pytest.fixture()
def fonte_fora(monkeypatch):
    def fora():
        raise rf.FonteIndisponivel("simulada")

    monkeypatch.setattr(rf, "FONTES", {"wikipedia": fora, "gutenberg": fora})


@pytest.fixture()
def texto_reserva(engine_teste) -> ReadingText:
    with Session(engine_teste) as s:
        texto = ReadingText(fonte="wikipedia", id_origem="reserva", titulo="Honey bee", url="https://x/Honey_bee",
                            conteudo=" ".join(["honey"] * PALAVRAS_RESERVA), palavras=PALAVRAS_RESERVA,
                            perguntas_reserva=[pergunta_de_reserva(n) for n in range(1, 6)])
        s.add(texto)
        s.commit()
        s.refresh(texto)
        return texto


@pytest.fixture()
def ambiente(cota_nova, fonte_fora, texto_reserva) -> ReadingText:
    return texto_reserva
