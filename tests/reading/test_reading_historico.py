"""Bloco R10: histórico dos desafios (GET /api/reading/challenges).

Os desafios saem da reserva (fonte fora e sem LLM). Relógio falso (rd.agora) para a ordem por data ser determinística.
"""
from datetime import datetime, timedelta

import pytest

from app.services import reading_desafios as rd

URL = "/api/reading/challenges"
INICIO = datetime(2026, 11, 23, 10, 0, 0)



pytestmark = pytest.mark.usefixtures("ambiente")  # tests/reading/conftest.py



def _criar(cliente, relogio, modalidade: str = "multipla_escolha") -> int:
    desafio_id = cliente.post(URL, json={"modalidade": modalidade}).json()["id"]
    relogio.avancar(60)
    return desafio_id


def _responder(cliente, desafio_id: int, respostas: list[str]) -> None:
    assert cliente.post(f"{URL}/{desafio_id}/encerrar-leitura").status_code == 200
    assert cliente.post(f"{URL}/{desafio_id}/respostas", json={"respostas": respostas}).status_code == 201


def test_historico_vazio(entrar_como):
    resposta = entrar_como("ana@exemplo.com").get(URL)
    assert resposta.status_code == 200 and resposta.json() == []


def test_historico_do_mais_novo_ao_mais_antigo_com_nota_e_estado(entrar_como, relogio):
    ana = entrar_como("ana@exemplo.com")
    corrigido = _criar(ana, relogio)
    _responder(ana, corrigido, ["Right 1", "Right 2", "Right 3", "", "Wrong A 5"])
    em_leitura = _criar(ana, relogio, "aberta")

    itens = ana.get(URL).json()

    assert [i["id"] for i in itens] == [em_leitura, corrigido]
    recente, antigo = itens
    assert recente == {"id": em_leitura, "iniciado_em": (INICIO + timedelta(seconds=60)).isoformat(),
                       "titulo": "Honey bee", "modalidade": "aberta", "estado": "lendo", "usou_reserva": True,
                       "nota": None, "acertos": None}
    assert (antigo["estado"], antigo["nota"], antigo["acertos"]) == ("corrigido", 6.0, 3)
    assert antigo["modalidade"] == "multipla_escolha"


def test_historico_mostra_so_os_da_conta(entrar_como, relogio):
    ana, bruno = entrar_como("ana@exemplo.com"), entrar_como("bruno@exemplo.com")
    da_ana = _criar(ana, relogio)
    do_bruno = _criar(bruno, relogio)
    assert [i["id"] for i in ana.get(URL).json()] == [da_ana]
    assert [i["id"] for i in bruno.get(URL).json()] == [do_bruno]


def test_historico_tem_no_maximo_o_limite(entrar_como, relogio, monkeypatch):
    monkeypatch.setattr(rd, "LIMITE_HISTORICO", 3)
    monkeypatch.setattr(rd.historico, "__defaults__", (3,))
    ana = entrar_como("ana@exemplo.com")
    ids = [_criar(ana, relogio) for _ in range(5)]
    assert [i["id"] for i in ana.get(URL).json()] == ids[::-1][:3]  # os 3 mais recentes


def test_limite_padrao_e_50():
    assert rd.LIMITE_HISTORICO == 50 and rd.historico.__defaults__ == (50,)


def test_desafios_com_o_mesmo_horario_saem_do_id_maior_ao_menor(entrar_como, relogio):
    """Empate na data (dois desafios no mesmo instante): o id decide, e a ordem não muda entre as chamadas."""
    ana = entrar_como("ana@exemplo.com")
    primeiro = ana.post(URL, json={"modalidade": "aberta"}).json()["id"]
    segundo = ana.post(URL, json={"modalidade": "aberta"}).json()["id"]
    assert [i["id"] for i in ana.get(URL).json()] == [segundo, primeiro]


def test_sem_login_responde_401(client):
    assert client.get(URL).status_code == 401
