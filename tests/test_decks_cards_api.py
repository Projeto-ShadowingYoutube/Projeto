def criar_deck(client, nome="Inglês"):
    resposta = client.post("/api/criar_deck", data={"nome": nome})
    assert resposta.status_code == 200
    return resposta.json()


def salvar_card(client, deck_id, texto="Hello world"):
    resposta = client.post(
        "/salvar_card",
        data={
            "deck_id": deck_id,
            "video_id": "abcdefghijk",
            "texto_legenda": texto,
            "start_time": "0.0",
            "end_time": "2.0",
        },
    )
    assert resposta.status_code == 200
    return resposta.json()


def test_criar_deck_e_listar_dashboard(client):
    deck1 = criar_deck(client, "Inglês")
    deck2 = criar_deck(client, "Inglês")

    assert deck1["nome"] == "Inglês"
    assert deck2["nome"] == "Inglês (2)"

    resposta = client.get("/api/listar_decks")
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

    assert primeira["status"] == "sucesso"
    assert segunda["status"] == "duplicado"

    dashboard = client.get("/api/listar_decks").json()
    assert dashboard[0]["quantidade_total"] == 1
    assert dashboard[0]["novos"] == 1


def test_revisar_deck_retorna_cards_novos(client):
    deck = criar_deck(client, "Revisão")
    salvar_card(client, deck["id"], texto="First card")

    resposta = client.get(f"/api/revisar_deck/{deck['id']}")

    assert resposta.status_code == 200
    cards = resposta.json()
    assert len(cards) == 1
    assert cards[0]["texto_legenda"] == "First card"
    assert cards[0]["video_id"] == "abcdefghijk"


def test_atualizar_revisao_incrementa_card_e_valida_dificuldade(client):
    deck = criar_deck(client, "SRS")
    salvar_card(client, deck["id"], texto="Review me")
    card_id = client.get(f"/api/revisar_deck/{deck['id']}").json()[0]["id"]

    resposta = client.post(f"/api/atualizar_revisao/{card_id}/facil")
    assert resposta.status_code == 200
    body = resposta.json()
    assert body["status"] == "sucesso"
    assert body["numero_revisoes"] == 1
    assert "nova_revisao" in body

    invalida = client.post(f"/api/atualizar_revisao/{card_id}/impossivel")
    assert invalida.status_code == 400


def test_deletar_card(client):
    deck = criar_deck(client, "Delete")
    salvar_card(client, deck["id"], texto="Delete me")
    card_id = client.get(f"/api/revisar_deck/{deck['id']}").json()[0]["id"]

    resposta = client.delete(f"/api/deletar_card/{card_id}")
    assert resposta.status_code == 200
    assert resposta.json()["status"] == "sucesso"

    cards = client.get(f"/api/revisar_deck/{deck['id']}").json()
    assert cards == []


def test_deletar_deck_remove_deck(client):
    deck = criar_deck(client, "Deck para apagar")

    resposta = client.post("/api/deletar_deck", data={"deck_id": deck["id"]})

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "sucesso"
    assert client.get("/api/listar_decks").json() == []
