import pytest

from app.services import dicionario

DEFINICOES = {
    "light": [
        {"classe": "Noun", "definicoes": [{"definicao": "Visible radiation.", "exemplo": None}]},
        {"classe": "Adjective", "definicoes": [{"definicao": "Bright.", "exemplo": None}]},
        {"classe": "Adjective", "definicoes": [{"definicao": "Of low weight.", "exemplo": "a light bag"}]},
    ],
    "be": [{"classe": "Verb", "definicoes": [{"definicao": "To exist.", "exemplo": None}]}],
}


@pytest.fixture(autouse=True)
def sem_internet(monkeypatch):
    chamadas = []

    def buscar_definicoes(palavra):
        chamadas.append(palavra)
        return DEFINICOES.get(palavra)

    monkeypatch.setattr(dicionario, "buscar_definicoes", buscar_definicoes)
    monkeypatch.setattr(dicionario, "buscar_pronuncia", lambda palavra: {"fonetica": "/x/", "audio": None})
    return chamadas


def test_usa_forma_base_e_classe_da_frase(client):
    resposta = client.get("/api/dicionario", params={"palavra": "light", "frase": "I carry a light bag.", "indice": 3})

    assert resposta.status_code == 200
    body = resposta.json()
    assert body["lema"] == "light"
    assert body["classe_no_contexto"] == "Adjective"
    # As duas entradas de adjetivo vêm primeiro, marcadas como sendo do contexto.
    assert [(c["classe"], c["do_contexto"]) for c in body["classes"]] == [
        ("Adjective", True), ("Adjective", True), ("Noun", False),
    ]


def test_forma_flexionada_busca_o_lema(client):
    body = client.get("/api/dicionario", params={"palavra": "is", "frase": "This is it.", "indice": 1}).json()
    assert body["palavra"] == "is"
    assert body["lema"] == "be"


def test_apostrofo_curvo_e_pontuacao_sao_normalizados():
    assert dicionario.normalizar("don’t,") == "don't"
    assert dicionario.normalizar("“word”") == "word"


def test_cache_evita_nova_consulta(client, sem_internet):
    params = {"palavra": "light"}
    client.get("/api/dicionario", params=params)
    client.get("/api/dicionario", params=params)
    assert sem_internet == ["light"]


def test_palavra_inexistente_retorna_404(client):
    assert client.get("/api/dicionario", params={"palavra": "xqzw"}).status_code == 404


def test_html_do_wiktionary_vira_texto():
    html = '<span class="usage-label-sense"></span> <a href="/wiki/x">Electromagnetic radiation</a> visible.'
    assert dicionario.html_para_texto(html) == "Electromagnetic radiation visible."


def test_definicao_longa_e_resumida():
    assert dicionario.resumir_definicao("To move swiftly. To move forward quickly upon two feet.") == "To move swiftly."
    longa = (
        "Electromagnetic radiation in the wavelength range visible to the human eye "
        "(about 400–750 nanometers): visible light."
    )
    esperado = "Electromagnetic radiation in the wavelength range visible to the human eye: visible light."
    assert dicionario.resumir_definicao(longa) == esperado
    assert len(dicionario.resumir_definicao("word " * 50)) <= dicionario.LIMITE_DEFINICAO + 1


def test_resposta_curta_e_sem_definicoes_remissivas():
    definicoes = [{"definicao": f"Sense {i}.", "exemplo": f"example {i}"} for i in range(5)]
    classes = [
        {"classe": "Verb", "definicoes": definicoes},
        {"classe": "Verb", "definicoes": [{"definicao": "past participle of rin", "exemplo": None}]},
        {"classe": "Noun", "definicoes": definicoes},
        {"classe": "Adjective", "definicoes": definicoes},
    ]
    resultado = dicionario._ordenar_por_contexto(classes, "Verb")

    assert [c["classe"] for c in resultado] == ["Verb", "Noun"]
    assert [len(c["definicoes"]) for c in resultado] == [2, 1]
    exemplos = [d["exemplo"] for c in resultado for d in c["definicoes"]]
    assert exemplos == ["example 0", None, None]
