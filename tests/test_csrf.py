"""Proteção contra CSRF (B6): requisições que alteram dados vindas de outro site são recusadas."""
import pytest

DO_PROPRIO_SITE = {"Origin": "http://testserver"}  # o TestClient usa o host "testserver"


@pytest.mark.parametrize("origem", ["https://malicioso.com", "http://testserver.malicioso.com", "null"])
def test_post_de_outro_site_e_recusado_antes_de_chegar_na_rota(entrar_como, origem):
    ana = entrar_como("ana@exemplo.com")  # mesmo com o cookie de sessão válido

    resposta = ana.post("/api/decks", json={"nome": "Criado por outro site"}, headers={"Origin": origem})

    assert resposta.status_code == 403
    assert resposta.json() == {
        "detail": "Requisição bloqueada: origem não permitida.", "codigo": "origem_nao_permitida",
    }
    assert ana.get("/api/decks").json() == []  # nada foi criado


@pytest.mark.parametrize("metodo", ["PATCH", "DELETE"])
def test_outros_metodos_que_alteram_dados_tambem_sao_verificados(entrar_como, metodo):
    ana = entrar_como("ana@exemplo.com")
    deck_id = ana.post("/api/decks", json={"nome": "Meu"}).json()["id"]

    resposta = ana.request(metodo, f"/api/decks/{deck_id}", json={"nome": "X"}, headers={"Origin": "https://malicioso.com"})

    assert resposta.status_code == 403
    assert [d["nome"] for d in ana.get("/api/decks").json()] == ["Meu"]


def test_logout_forcado_por_outro_site_tambem_e_recusado(entrar_como):
    ana = entrar_como("ana@exemplo.com")

    assert ana.post("/api/auth/logout", headers={"Origin": "https://malicioso.com"}).status_code == 403
    assert ana.get("/api/auth/me").status_code == 200


def test_mesmo_site_e_clientes_sem_origin_passam(entrar_como):
    ana = entrar_como("ana@exemplo.com")

    assert ana.post("/api/decks", json={"nome": "Do site"}, headers=DO_PROPRIO_SITE).status_code == 201
    assert ana.post("/api/decks", json={"nome": "Sem Origin"}).status_code == 201  # curl, scripts, testes


def test_leitura_nao_e_bloqueada_pela_origem(entrar_como):
    """GET não altera dados; e o navegador não deixa outro site ler a resposta (política de mesma origem)."""
    ana = entrar_como("ana@exemplo.com")

    assert ana.get("/api/decks", headers={"Origin": "https://malicioso.com"}).status_code == 200
