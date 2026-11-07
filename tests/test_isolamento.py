"""Isolamento entre contas (B5): cada usuário só enxerga e altera os próprios Decks e Cards."""
import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.models import Deck, Usuario

CARD = {"video_id": "abcdefghijk", "texto_legenda": "Hello world", "start_time": 0.0, "end_time": 2.0}


@pytest.fixture()
def ana(entrar_como):
    return entrar_como("ana@exemplo.com")


@pytest.fixture()
def bruno(entrar_como):
    return entrar_como("bruno@exemplo.com")


def _deck_com_card(cliente, nome="Inglês"):
    deck_id = cliente.post("/api/decks", json={"nome": nome}).json()["id"]
    assert cliente.post(f"/api/decks/{deck_id}/cards", json=CARD).status_code == 201
    card_id = cliente.get(f"/api/decks/{deck_id}/revisao").json()[0]["id"]
    return deck_id, card_id


def test_sem_login_todas_as_rotas_de_decks_e_cards_respondem_401(client):
    pedidos = [
        ("GET", "/api/decks", None),
        ("POST", "/api/decks", {"nome": "X"}),
        ("PATCH", "/api/decks/1", {"nome": "X"}),
        ("DELETE", "/api/decks/1", None),
        ("POST", "/api/decks/1/cards", CARD),
        ("GET", "/api/decks/1/revisao", None),
        ("POST", "/api/cards/1/avaliacao", {"dificuldade": "facil"}),
        ("DELETE", "/api/cards/1", None),
    ]
    for metodo, url, corpo in pedidos:
        resposta = client.request(metodo, url, json=corpo)
        assert resposta.status_code == 401, f"{metodo} {url}"
        assert resposta.json() == {"detail": "Faça login para continuar.", "codigo": "nao_autenticado"}


def test_cada_usuario_lista_so_os_proprios_decks(ana, bruno):
    _deck_com_card(ana, "Deck da Ana")
    bruno.post("/api/decks", json={"nome": "Deck do Bruno"})

    assert [d["nome"] for d in ana.get("/api/decks").json()] == ["Deck da Ana"]
    assert [d["nome"] for d in bruno.get("/api/decks").json()] == ["Deck do Bruno"]
    # As contagens do dashboard também só consideram os Cards do próprio usuário:
    assert bruno.get("/api/decks").json()[0]["quantidade_total"] == 0


def test_outro_usuario_recebe_404_e_nao_altera_nada(ana, bruno):
    deck_id, card_id = _deck_com_card(ana)

    tentativas = [
        bruno.get(f"/api/decks/{deck_id}/revisao"),
        bruno.patch(f"/api/decks/{deck_id}", json={"nome": "Roubado"}),
        bruno.delete(f"/api/decks/{deck_id}"),
        bruno.post(f"/api/decks/{deck_id}/cards", json={**CARD, "texto_legenda": "Intruso"}),
        bruno.post(f"/api/cards/{card_id}/avaliacao", json={"dificuldade": "facil"}),
        bruno.delete(f"/api/cards/{card_id}"),
    ]

    assert [r.status_code for r in tentativas] == [404] * len(tentativas)
    # A resposta é idêntica à de um recurso que não existe: não dá para saber que o Deck da Ana existe.
    assert tentativas[0].json() == bruno.get("/api/decks/999999/revisao").json()
    assert tentativas[4].json() == bruno.post("/api/cards/999999/avaliacao", json={"dificuldade": "facil"}).json()

    # Nada da Ana mudou: mesmo nome, mesmo Card, ainda "novo" (a avaliação do Bruno não foi aplicada).
    resumo = ana.get("/api/decks").json()
    assert [(d["nome"], d["novos"], d["quantidade_total"]) for d in resumo] == [("Inglês", 1, 1)]
    assert [c["id"] for c in ana.get(f"/api/decks/{deck_id}/revisao").json()] == [card_id]


def test_mesmo_nome_e_permitido_em_contas_diferentes_mas_nao_na_mesma(ana, bruno):
    assert ana.post("/api/decks", json={"nome": "Inglês"}).json()["nome"] == "Inglês"
    assert bruno.post("/api/decks", json={"nome": "Inglês"}).json()["nome"] == "Inglês"
    assert ana.post("/api/decks", json={"nome": "Inglês"}).json()["nome"] == "Inglês (2)"

    deck_do_bruno = bruno.post("/api/decks", json={"nome": "Outro"}).json()["id"]
    renomeado = bruno.patch(f"/api/decks/{deck_do_bruno}", json={"nome": "Inglês"}).json()
    assert renomeado["nome"] == "Inglês (2)"  # conflita com o Deck do próprio Bruno, não com os da Ana


def test_banco_garante_nome_unico_por_usuario(engine_teste):
    """A regra não depende só do código: o banco recusa (por exemplo, duas requisições ao mesmo tempo)."""
    with Session(engine_teste) as session:
        usuario = Usuario(email="c@exemplo.com", senha_hash="x")
        session.add(usuario)
        session.commit()
        session.add(Deck(nome="Repetido", usuario_id=usuario.id))
        session.commit()
        session.add(Deck(nome="Repetido", usuario_id=usuario.id))
        with pytest.raises(IntegrityError):
            session.commit()


def test_depois_do_logout_o_acesso_aos_decks_e_cortado(ana):
    assert ana.get("/api/decks").status_code == 200
    ana.post("/api/auth/logout")
    assert ana.get("/api/decks").status_code == 401
