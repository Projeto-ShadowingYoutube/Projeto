import pytest


@pytest.fixture()
def client(entrar_como):
    """Desde o B5, as rotas de Decks exigem login. Esta fixture troca o client destes testes de agosto por um
    navegador já logado; o corpo dos testes abaixo não mudou (é a prova de que o comportamento foi preservado)."""
    return entrar_como("agosto@exemplo.com")


def criar_deck(client, nome="Inglês"):
    resposta = client.post("/api/decks", json={"nome": nome})
    assert resposta.status_code == 201
    return resposta.json()


def salvar_card(client, deck_id, texto="Hello world"):
    return client.post(
        f"/api/decks/{deck_id}/cards",
        json={"video_id": "abcdefghijk", "texto_legenda": texto, "start_time": 0.0, "end_time": 2.0},
    )


def test_criar_deck_e_listar_dashboard(client):
    deck1 = criar_deck(client, "Inglês")
    deck2 = criar_deck(client, "Inglês")

    assert deck1["nome"] == "Inglês"
    assert deck2["nome"] == "Inglês (2)"

    resposta = client.get("/api/decks")
    assert resposta.status_code == 200
    decks = resposta.json()

    assert [d["nome"] for d in decks] == ["Inglês", "Inglês (2)"]
    assert decks[0]["novos"] == 0
    assert decks[0]["revisar"] == 0
    assert decks[0]["quantidade_total"] == 0


def test_salvar_card_e_bloquear_duplicado_no_mesmo_deck(client):
    deck = criar_deck(client, "Shadowing")

    primeira = salvar_card(client, deck["id"], texto="Hello world")
    segunda = salvar_card(client, deck["id"], texto="Hello world")

    assert primeira.status_code == 201
    assert segunda.status_code == 409
    assert "já foi salvo" in segunda.json()["detail"]

    dashboard = client.get("/api/decks").json()
    assert dashboard[0]["quantidade_total"] == 1
    assert dashboard[0]["novos"] == 1


def test_revisar_deck_retorna_cards_novos(client):
    deck = criar_deck(client, "Revisão")
    salvar_card(client, deck["id"], texto="First card")

    resposta = client.get(f"/api/decks/{deck['id']}/revisao")

    assert resposta.status_code == 200
    cards = resposta.json()
    assert len(cards) == 1
    assert cards[0]["texto_legenda"] == "First card"
    assert cards[0]["video_id"] == "abcdefghijk"


def test_atualizar_revisao_incrementa_card_e_valida_dificuldade(client):
    deck = criar_deck(client, "SRS")
    salvar_card(client, deck["id"], texto="Review me")
    card_id = client.get(f"/api/decks/{deck['id']}/revisao").json()[0]["id"]

    resposta = client.post(f"/api/cards/{card_id}/avaliacao", json={"dificuldade": "facil"})
    assert resposta.status_code == 200
    body = resposta.json()
    assert body["numero_revisoes"] == 1
    assert "nova_revisao" in body

    invalida = client.post(f"/api/cards/{card_id}/avaliacao", json={"dificuldade": "impossivel"})
    assert invalida.status_code == 422


def test_deletar_card(client):
    deck = criar_deck(client, "Delete")
    salvar_card(client, deck["id"], texto="Delete me")
    card_id = client.get(f"/api/decks/{deck['id']}/revisao").json()[0]["id"]

    resposta = client.delete(f"/api/cards/{card_id}")
    assert resposta.status_code == 204

    cards = client.get(f"/api/decks/{deck['id']}/revisao").json()
    assert cards == []


def test_deletar_deck_remove_deck(client):
    deck = criar_deck(client, "Deck para apagar")

    resposta = client.delete(f"/api/decks/{deck['id']}")

    assert resposta.status_code == 204
    assert client.get("/api/decks").json() == []


def test_criar_deck_com_nome_vazio_usa_nome_padrao(client):
    assert criar_deck(client, "   ")["nome"] == "Deck"


def test_renomear_deck_mantem_nomes_unicos(client):
    criar_deck(client, "Inglês")
    outro = criar_deck(client, "Outro")

    resposta = client.patch(f"/api/decks/{outro['id']}", json={"nome": "Inglês"})

    assert resposta.status_code == 200
    assert resposta.json()["nome"] == "Inglês (2)"


def test_revisar_deck_inexistente_retorna_404(client):
    assert client.get("/api/decks/999/revisao").status_code == 404


def test_card_com_fim_antes_do_inicio_e_rejeitado(client):
    deck = criar_deck(client)
    resposta = client.post(
        f"/api/decks/{deck['id']}/cards",
        json={"video_id": "abcdefghijk", "texto_legenda": "x", "start_time": 5, "end_time": 2},
    )
    assert resposta.status_code == 422


def test_deletar_deck_apaga_os_cards_dele(client):
    deck = criar_deck(client)
    salvar_card(client, deck["id"])
    client.delete(f"/api/decks/{deck['id']}")

    novo = criar_deck(client)
    assert client.get(f"/api/decks/{novo['id']}/revisao").json() == []
