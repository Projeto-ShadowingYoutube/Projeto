"""Configurações individuais de estudo (B8): velocidade preferida, salva por usuário."""
import pytest
from sqlmodel import Session, create_engine

from app.db import opcoes_de_conexao
from app.services import configuracoes

HTMX = {"HX-Request": "true"}


@pytest.fixture()
def ana(entrar_como):
    return entrar_como("ana@exemplo.com")


def test_quem_nunca_salvou_recebe_os_padroes(ana):
    assert ana.get("/api/configuracoes").json() == {"velocidade": 1.0, "volume": 1.0}


def test_alterar_velocidade_salva_e_devolve_a_configuracao_completa(ana):
    resposta = ana.patch("/api/configuracoes", json={"velocidade": 0.75})

    assert resposta.status_code == 200
    assert resposta.json() == {"velocidade": 0.75, "volume": 1.0}
    assert ana.get("/api/configuracoes").json() == {"velocidade": 0.75, "volume": 1.0}


def test_patch_vazio_nao_muda_nada(ana):
    ana.patch("/api/configuracoes", json={"velocidade": 1.25})

    assert ana.patch("/api/configuracoes", json={}).json() == {"velocidade": 1.25, "volume": 1.0}


def test_velocidade_e_arredondada_como_o_slider(ana):
    resposta = ana.patch("/api/configuracoes", json={"velocidade": 0.7500000001})
    assert resposta.json() == {"velocidade": 0.75, "volume": 1.0}


@pytest.mark.parametrize("corpo, mensagem", [
    ({"velocidade": 0.1}, "precisa ser maior ou igual a 0.25"),
    ({"velocidade": 50}, "precisa ser menor ou igual a 1.5"),
    ({"velocidade": None}, "não pode ser nulo"),
    ({"velocidade": "rápido"}, "precisa ser um número"),
    ({"velocidad": 0.75}, "campo desconhecido"),  # erro de digitação não passa em silêncio
])
def test_valores_invalidos_sao_recusados_com_422(ana, corpo, mensagem):
    resposta = ana.patch("/api/configuracoes", json=corpo)

    assert resposta.status_code == 422
    assert resposta.json()["codigo"] == "dados_invalidos"
    assert mensagem in resposta.json()["erros"][0]["mensagem"]
    assert ana.get("/api/configuracoes").json() == {"velocidade": 1.0, "volume": 1.0}  # nada foi salvo


def test_sem_login_401(client):
    assert client.get("/api/configuracoes").status_code == 401
    assert client.patch("/api/configuracoes", json={"velocidade": 0.75}).status_code == 401


def test_cada_usuario_tem_a_sua_velocidade(ana, entrar_como):
    bruno = entrar_como("bruno@exemplo.com")

    ana.patch("/api/configuracoes", json={"velocidade": 0.5})
    bruno.patch("/api/configuracoes", json={"velocidade": 1.25})

    assert ana.get("/api/configuracoes").json() == {"velocidade": 0.5, "volume": 1.0}
    assert bruno.get("/api/configuracoes").json() == {"velocidade": 1.25, "volume": 1.0}


def test_velocidade_persiste_depois_de_reiniciar_e_de_sair_e_entrar(ana, engine_teste):
    ana.patch("/api/configuracoes", json={"velocidade": 0.6})
    usuario_id = ana.get("/api/auth/me").json()["id"]

    # "Reinício do servidor": um engine novo, sem nada em memória, lendo o mesmo banco.
    url = engine_teste.url.render_as_string(hide_password=False)
    engine_novo = create_engine(url, connect_args=opcoes_de_conexao(url))
    with Session(engine_novo) as session:
        assert configuracoes.obter(session, usuario_id) == {"velocidade": 0.6, "volume": 1.0}
    engine_novo.dispose()

    ana.post("/api/auth/logout")
    ana.post("/api/auth/login", json={"email": "ana@exemplo.com", "senha": "senha-forte-123"})
    assert ana.get("/api/configuracoes").json() == {"velocidade": 0.6, "volume": 1.0}


def test_paginas_de_estudo_e_revisao_ja_vem_com_a_velocidade_salva(ana):
    assert 'data-velocidade="1.0"' in ana.get("/estudo?link=x", headers=HTMX).text

    ana.patch("/api/configuracoes", json={"velocidade": 0.85})

    assert 'data-velocidade="0.85"' in ana.get("/estudo?link=x", headers=HTMX).text
    assert 'data-velocidade="0.85"' in ana.get("/decks/1/revisao", headers=HTMX).text


def test_pedido_de_outro_site_nao_altera_a_velocidade(ana):
    resposta = ana.patch("/api/configuracoes", json={"velocidade": 0.25}, headers={"Origin": "https://malicioso.com"})

    assert resposta.status_code == 403
    assert ana.get("/api/configuracoes").json() == {"velocidade": 1.0, "volume": 1.0}


# --- Volume (B9.2): mesma estrutura da velocidade ---

def test_volume_e_salvo_e_nao_mexe_na_velocidade(ana):
    ana.patch("/api/configuracoes", json={"velocidade": 0.8})

    resposta = ana.patch("/api/configuracoes", json={"volume": 0.35})

    assert resposta.json() == {"velocidade": 0.8, "volume": 0.35}  # PATCH parcial: a velocidade ficou
    assert ana.get("/api/configuracoes").json() == {"velocidade": 0.8, "volume": 0.35}


def test_volume_zero_e_o_mudo_e_e_valido(ana):
    assert ana.patch("/api/configuracoes", json={"volume": 0}).json()["volume"] == 0.0


@pytest.mark.parametrize("volume, mensagem", [
    (-0.1, "precisa ser maior ou igual a 0"),
    (1.5, "precisa ser menor ou igual a 1"),
    (None, "não pode ser nulo"),
])
def test_volume_invalido_422(ana, volume, mensagem):
    resposta = ana.patch("/api/configuracoes", json={"volume": volume})

    assert resposta.status_code == 422
    assert mensagem in resposta.json()["erros"][0]["mensagem"]
    assert ana.get("/api/configuracoes").json()["volume"] == 1.0


def test_paginas_de_estudo_e_revisao_ja_vem_com_o_volume_salvo(ana):
    assert 'data-volume="1.0"' in ana.get("/estudo?link=x", headers=HTMX).text

    ana.patch("/api/configuracoes", json={"volume": 0.4})

    assert 'data-volume="0.4"' in ana.get("/estudo?link=x", headers=HTMX).text
    assert 'data-volume="0.4"' in ana.get("/decks/1/revisao", headers=HTMX).text
