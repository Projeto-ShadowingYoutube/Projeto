"""Formato único dos erros da API (B7): {"detail": texto, "codigo": identificador, ...extras}."""
import logging
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import legendas as rota_legendas
from app.services import dicionario

ORIGEM_DE_OUTRO_SITE = {"Origin": "https://malicioso.com"}


def _formato_padrao(resposta, status, codigo):
    """Todo erro: JSON com detail (texto não vazio, sem inglês do framework) e codigo estável."""
    assert resposta.status_code == status, resposta.text
    assert resposta.headers["content-type"].startswith("application/json")
    corpo = resposta.json()
    assert isinstance(corpo["detail"], str) and corpo["detail"]
    assert corpo["detail"] not in ("Not Found", "Method Not Allowed", "Internal Server Error")
    assert corpo["codigo"] == codigo
    return corpo


@pytest.fixture()
def ana(entrar_como):
    return entrar_como("ana@exemplo.com")


def test_400_requisicao_invalida(ana):
    corpo = _formato_padrao(ana.get("/api/legendas", params={"url": "nao-e-youtube"}), 400, "requisicao_invalida")
    assert corpo["detail"] == "URL do YouTube inválida."


def test_401_nao_autenticado(client):
    _formato_padrao(client.get("/api/decks"), 401, "nao_autenticado")


def test_403_origem_nao_permitida(ana):
    _formato_padrao(ana.post("/api/decks", json={"nome": "X"}, headers=ORIGEM_DE_OUTRO_SITE), 403,
                    "origem_nao_permitida")


def test_404_recurso_da_rota_e_rota_inexistente(ana):
    corpo = _formato_padrao(ana.get("/api/decks/999/revisao"), 404, "nao_encontrado")
    assert corpo["detail"] == "Deck não encontrado."  # a mensagem da rota é mantida

    corpo = _formato_padrao(ana.get("/api/nao-existe"), 404, "nao_encontrado")
    assert corpo["detail"] == "Recurso não encontrado."  # no lugar do "Not Found" do framework


def test_405_metodo_nao_permitido_mantem_o_header_allow(ana):
    resposta = ana.delete("/api/decks")
    _formato_padrao(resposta, 405, "metodo_nao_permitido")
    assert "GET" in resposta.headers["allow"]


def test_409_conflito(client):
    client.post("/api/auth/cadastro", json={"email": "ana@exemplo.com", "senha": "senha-forte-123"})
    resposta = client.post("/api/auth/cadastro", json={"email": "ana@exemplo.com", "senha": "senha-forte-123"})
    _formato_padrao(resposta, 409, "conflito")


def test_413_conteudo_grande_demais(ana):
    dados = {"video_id": "abcdefghijk", "inicio": "0", "fim": "2", "texto": "Hello", "duracao": "2"}
    gravacao = {"gravacao": ("g.webm", b"0" * (10 * 1024 * 1024 + 1), "audio/webm")}
    _formato_padrao(ana.post("/api/avaliacoes", data=dados, files=gravacao), 413, "conteudo_grande_demais")


def test_422_detail_em_texto_e_lista_de_erros_por_campo(client):
    resposta = client.post("/api/auth/cadastro", json={"email": "nao-e-email", "senha": "curta"})

    corpo = _formato_padrao(resposta, 422, "dados_invalidos")
    assert corpo["erros"] == [
        {"campo": "email", "mensagem": "e-mail inválido"},
        {"campo": "senha", "mensagem": "mínimo de 8 caracteres"},
    ]
    assert corpo["detail"] == "Dados inválidos: email: e-mail inválido; senha: mínimo de 8 caracteres."


def test_422_tambem_para_parametros_da_url_e_validadores_proprios(ana):
    corpo = _formato_padrao(ana.get("/api/videos/curto/status"), 422, "dados_invalidos")
    assert corpo["erros"] == [{"campo": "video_id", "mensagem": "formato inválido"}]

    deck_id = ana.post("/api/decks", json={"nome": "D"}).json()["id"]
    card_invertido = {"video_id": "abcdefghijk", "texto_legenda": "x", "start_time": 5, "end_time": 2}
    corpo = _formato_padrao(ana.post(f"/api/decks/{deck_id}/cards", json=card_invertido), 422, "dados_invalidos")
    assert corpo["erros"][0]["mensagem"] == "end_time precisa ser maior que start_time."

    corpo = _formato_padrao(ana.post("/api/decks"), 422, "dados_invalidos")  # sem corpo
    assert corpo["erros"] == [{"campo": "corpo", "mensagem": "campo obrigatório"}]


def test_429_limite_de_tokens_informa_quando_tentar_de_novo(ana, monkeypatch):
    class LimitadorEsgotado:
        def hit(self, *args, **kwargs):
            return False

        def get_window_stats(self, *args, **kwargs):
            return SimpleNamespace(remaining=0, reset_time=time.time() + 252)

    monkeypatch.setattr(rota_legendas, "limitador", LimitadorEsgotado())
    monkeypatch.setattr(rota_legendas.legendas, "da_cache", lambda video_id: None)

    resposta = ana.get("/api/legendas", params={"url": "https://youtu.be/abcdefghijk"})

    corpo = _formato_padrao(resposta, 429, "limite_de_tokens")
    assert corpo["tokens_restantes"] == 0
    assert corpo["limite"] == 5
    assert corpo["tentar_novamente_em"] in (252, 253)
    assert resposta.headers["retry-after"] == str(corpo["tentar_novamente_em"])


def test_502_servico_externo_indisponivel(ana, monkeypatch):
    def fora_do_ar(*args, **kwargs):
        raise dicionario.DicionarioIndisponivel

    monkeypatch.setattr(dicionario, "buscar", fora_do_ar)

    _formato_padrao(ana.get("/api/dicionario", params={"palavra": "hello"}), 502, "servico_externo_indisponivel")


def test_500_inesperado_nao_vaza_detalhes_e_registra_a_stack_no_log(app_de_teste, monkeypatch, caplog):
    def com_bug(*args, **kwargs):
        raise RuntimeError("segredo interno: C:/servidor/config.py, SELECT * FROM usuario")

    monkeypatch.setattr(dicionario, "buscar", com_bug)
    # raise_server_exceptions=False: garante que vemos a resposta que o navegador veria, e não uma exceção.
    with TestClient(app_de_teste, raise_server_exceptions=False) as cliente, caplog.at_level(logging.ERROR):
        cliente.post("/api/auth/cadastro", json={"email": "erro@exemplo.com", "senha": "senha-forte-123"})  # B13
        resposta = cliente.get("/api/dicionario", params={"palavra": "hello"})

    corpo = _formato_padrao(resposta, 500, "erro_interno")
    assert corpo == {"detail": "Erro interno. Tente novamente em instantes.", "codigo": "erro_interno"}
    assert "segredo" not in resposta.text and "SELECT" not in resposta.text
    # Quem mantém o sistema vê tudo no log: rota, exceção e stack.
    registro = next(r for r in caplog.records if "Erro inesperado" in r.getMessage())
    assert "GET /api/dicionario" in registro.getMessage()
    assert registro.exc_info and "segredo interno" in str(registro.exc_info[1])


def test_paginas_html_continuam_sendo_paginas(client):
    """O handler de erros vale para a API; as páginas seguem com redirecionamento e HTML."""
    assert client.get("/decks", follow_redirects=False).status_code == 303
    assert client.get("/login").headers["content-type"].startswith("text/html")


def test_erro_inesperado_dentro_de_um_middleware_tambem_vira_500_padrao(app_de_teste, monkeypatch):
    """O capturador é o middleware mais externo: cobre até falhas no middleware de CSRF."""
    from app import seguranca

    def com_bug(*args, **kwargs):
        raise RuntimeError("falha no middleware")

    monkeypatch.setattr(seguranca, "mesma_origem", com_bug)
    with TestClient(app_de_teste, raise_server_exceptions=False) as cliente:
        resposta = cliente.post("/api/decks", json={"nome": "X"}, headers=ORIGEM_DE_OUTRO_SITE)

    _formato_padrao(resposta, 500, "erro_interno")
