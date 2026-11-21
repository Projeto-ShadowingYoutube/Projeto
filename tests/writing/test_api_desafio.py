"""W3: API do desafio — criar (cota), ler, listar, autosave e envio, com prazo no servidor e isolamento entre contas."""
from datetime import timedelta

import pytest
from sqlmodel import Session

from app.models import agora
from app.models_writing import ENVIADA, RASCUNHO, WritingAttempt
from app.services.writing_desafios import MAX_CARACTERES, MIN_PALAVRAS_ENVIO, TOLERANCIA_PRAZO_SEGUNDOS

TEXTO_OK = "Education matters a lot. " * 15  # 60 palavras
OUTRO_TEXTO = "Cities should invest more in public transport. " * 10  # 70 palavras


def _palavras(n: int) -> str:
    return " ".join(["word"] * n)


@pytest.fixture()
def ana(entrar_como, temas):
    return entrar_como("ana@exemplo.com")


@pytest.fixture()
def bruno(entrar_como, temas):
    return entrar_como("bruno@exemplo.com")


def _criar(cliente, categoria: str | None = "ielts_opiniao") -> dict:
    resposta = cliente.post("/api/writing/challenges", json={"categoria": categoria} if categoria else {})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def _mover_prazo(engine, attempt_id: int, segundos_atras: int) -> None:
    """Simula o tempo passando: o prazo da redação fica `segundos_atras` segundos no passado."""
    with Session(engine) as session:
        tentativa = session.get(WritingAttempt, attempt_id)
        tentativa.prazo = agora() - timedelta(seconds=segundos_atras)
        session.add(tentativa)
        session.commit()


def _no_banco(engine, attempt_id: int) -> WritingAttempt:
    with Session(engine) as session:
        tentativa = session.get(WritingAttempt, attempt_id)
        session.expunge(tentativa)
        return tentativa


# --- Categorias ---

def test_lista_as_seis_categorias(ana):
    resposta = ana.get("/api/writing/categorias")
    assert resposta.status_code == 200
    categorias = {c["slug"]: c for c in resposta.json()}
    assert len(categorias) == 6
    assert categorias["ielts_opiniao"] == {
        "slug": "ielts_opiniao", "nome": "Opinião", "prova": "IELTS Writing Task 2",
        "tempo_limite_segundos": 2400, "palavras_minimas": 250,
    }


# --- Criar ---

def test_cria_redacao_da_categoria_com_prazo_gravado(ana, temas):
    redacao = _criar(ana, "ielts_opiniao")

    assert redacao["estado"] == RASCUNHO
    assert redacao["categoria"] == "ielts_opiniao" and redacao["categoria_nome"] == "Opinião"
    assert redacao["enunciado"] in {temas["opiniao_1"].enunciado, temas["opiniao_2"].enunciado}
    assert redacao["texto"] == "" and redacao["palavras"] == 0
    assert redacao["tempo_limite_segundos"] == 2400 and redacao["palavras_minimas"] == 250
    assert 2390 <= redacao["segundos_restantes"] <= 2400
    assert redacao["salva_em"] is None and redacao["enviada_em"] is None


def test_prazo_e_inicio_mais_tempo_do_tema(ana, engine_teste):
    redacao = _criar(ana, "toefl_discussao_academica")
    tentativa = _no_banco(engine_teste, redacao["id"])
    assert tentativa.prazo - tentativa.iniciada_em == timedelta(seconds=600)


@pytest.mark.parametrize("corpo", [None, {}, {"categoria": None}])
def test_surpresa_sem_categoria(ana, temas, corpo):
    resposta = ana.post("/api/writing/challenges", json=corpo) if corpo is not None else \
        ana.post("/api/writing/challenges")
    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["enunciado"] != temas["inativo"].enunciado


@pytest.mark.parametrize("corpo", [{"categoria": "nao_existe"}, {"categoria": "ielts_opiniao", "estado": "avaliada"}])
def test_criar_recusa_corpo_invalido(ana, corpo):
    resposta = ana.post("/api/writing/challenges", json=corpo)
    assert resposta.status_code == 422
    assert resposta.json()["codigo"] == "dados_invalidos"


def test_sem_temas_responde_503(entrar_como):
    cliente = entrar_como("ana@exemplo.com")  # sem a fixture "temas": tabela vazia
    resposta = cliente.post("/api/writing/challenges", json={})
    assert resposta.status_code == 503
    assert resposta.json()["codigo"] == "sem_temas"


def test_decimo_primeiro_desafio_do_dia_responde_429(ana):
    for _ in range(10):
        _criar(ana)

    resposta = ana.post("/api/writing/challenges", json={})

    assert resposta.status_code == 429
    assert resposta.json()["codigo"] == "limite_de_desafios"
    assert ana.get("/api/writing/attempts").status_code == 200  # ler não gasta cota


def test_cota_e_por_conta(ana, bruno):
    for _ in range(10):
        _criar(ana)
    assert bruno.post("/api/writing/challenges", json={}).status_code == 201


# --- Ler e listar ---

def test_le_a_propria_redacao(ana):
    redacao = _criar(ana)
    resposta = ana.get(f"/api/writing/attempts/{redacao['id']}")
    assert resposta.status_code == 200
    assert resposta.json()["id"] == redacao["id"]


def test_lista_so_as_proprias_mais_recentes_primeiro(ana, bruno):
    primeira, segunda = _criar(ana), _criar(ana, "toefl_discussao_academica")
    _criar(bruno)

    lista = ana.get("/api/writing/attempts").json()

    assert [r["id"] for r in lista] == [segunda["id"], primeira["id"]]
    assert lista[0]["categoria_nome"] == "Discussão acadêmica"


def test_redacao_inexistente_responde_404(ana):
    resposta = ana.get("/api/writing/attempts/999")
    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "Redação não encontrada.", "codigo": "nao_encontrado"}


# --- Autosave ---

def test_autosave_grava_texto_palavras_e_horario(ana, engine_teste):
    redacao = _criar(ana)

    resposta = ana.patch(f"/api/writing/attempts/{redacao['id']}", json={"texto": "I don't agree, it's well-known."})

    assert resposta.status_code == 200
    assert resposta.json()["palavras"] == 5
    assert resposta.json()["segundos_restantes"] > 0
    tentativa = _no_banco(engine_teste, redacao["id"])
    assert tentativa.texto == "I don't agree, it's well-known." and tentativa.salva_em is not None
    assert ana.get(f"/api/writing/attempts/{redacao['id']}").json()["texto"] == tentativa.texto  # recarregar traz


def test_autosave_guarda_acentos_e_caracteres_especiais(ana):
    redacao = _criar(ana)
    texto = "Café, naïve façade — “quotes” & <b>tags</b> 😀\nnew line"
    ana.patch(f"/api/writing/attempts/{redacao['id']}", json={"texto": texto})
    assert ana.get(f"/api/writing/attempts/{redacao['id']}").json()["texto"] == texto


def test_autosave_aceita_o_limite_e_recusa_acima(ana):
    redacao = _criar(ana)
    url = f"/api/writing/attempts/{redacao['id']}"
    assert ana.patch(url, json={"texto": "a" * MAX_CARACTERES}).status_code == 200
    resposta = ana.patch(url, json={"texto": "a" * (MAX_CARACTERES + 1)})
    assert resposta.status_code == 422
    assert resposta.json()["erros"][0]["campo"] == "texto"


def test_autosave_recusa_campos_alem_do_texto(ana):
    redacao = _criar(ana)
    resposta = ana.patch(f"/api/writing/attempts/{redacao['id']}", json={"texto": "x", "estado": "avaliada"})
    assert resposta.status_code == 422


def test_autosave_dentro_da_tolerancia_grava(ana, engine_teste):
    redacao = _criar(ana)
    _mover_prazo(engine_teste, redacao["id"], segundos_atras=TOLERANCIA_PRAZO_SEGUNDOS - 10)

    resposta = ana.patch(f"/api/writing/attempts/{redacao['id']}", json={"texto": "ainda deu tempo"})

    assert resposta.status_code == 200
    assert resposta.json()["segundos_restantes"] == 0


def test_autosave_depois_do_prazo_e_recusado_sem_gravar(ana, engine_teste):
    redacao = _criar(ana)
    ana.patch(f"/api/writing/attempts/{redacao['id']}", json={"texto": "antes do prazo"})
    _mover_prazo(engine_teste, redacao["id"], segundos_atras=TOLERANCIA_PRAZO_SEGUNDOS + 1)

    resposta = ana.patch(f"/api/writing/attempts/{redacao['id']}", json={"texto": "depois do prazo"})

    assert resposta.status_code == 409
    assert resposta.json()["codigo"] == "prazo_encerrado"
    assert _no_banco(engine_teste, redacao["id"]).texto == "antes do prazo"


def test_autosave_depois_do_envio_e_recusado(ana, engine_teste):
    redacao = _criar(ana)
    ana.post(f"/api/writing/attempts/{redacao['id']}/submissao", json={"texto": TEXTO_OK})

    resposta = ana.patch(f"/api/writing/attempts/{redacao['id']}", json={"texto": "tentando mudar"})

    assert resposta.status_code == 409
    assert resposta.json()["codigo"] == "redacao_ja_enviada"
    assert _no_banco(engine_teste, redacao["id"]).texto == TEXTO_OK


# --- Envio ---

def test_envio_congela_a_redacao(ana, engine_teste):
    redacao = _criar(ana)

    resposta = ana.post(f"/api/writing/attempts/{redacao['id']}/submissao", json={"texto": TEXTO_OK})

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["estado"] == ENVIADA and corpo["texto"] == TEXTO_OK and corpo["palavras"] == 60
    assert corpo["usou_ultimo_salvamento"] is False and corpo["segundos_restantes"] == 0
    tentativa = _no_banco(engine_teste, redacao["id"])
    assert tentativa.estado == ENVIADA and tentativa.texto == TEXTO_OK and tentativa.enviada_em is not None


def test_envio_exige_o_minimo_de_palavras(ana, engine_teste):
    redacao = _criar(ana)
    url = f"/api/writing/attempts/{redacao['id']}/submissao"

    curta = ana.post(url, json={"texto": _palavras(MIN_PALAVRAS_ENVIO - 1)})

    assert curta.status_code == 422
    assert curta.json() == {
        "detail": "A redação precisa de pelo menos 50 palavras para ser enviada (tem 49).",
        "codigo": "redacao_curta", "palavras": 49, "minimo": 50,
    }
    assert _no_banco(engine_teste, redacao["id"]).estado == RASCUNHO
    assert ana.post(url, json={"texto": _palavras(MIN_PALAVRAS_ENVIO)}).status_code == 200


@pytest.mark.parametrize("texto", ["", "   ", "!!! ???"])
def test_envio_vazio_ou_so_pontuacao_e_recusado(ana, texto):
    redacao = _criar(ana)
    resposta = ana.post(f"/api/writing/attempts/{redacao['id']}/submissao", json={"texto": texto})
    assert resposta.status_code == 422 and resposta.json()["codigo"] == "redacao_curta"


def test_envio_acima_do_limite_e_recusado(ana):
    redacao = _criar(ana)
    resposta = ana.post(f"/api/writing/attempts/{redacao['id']}/submissao",
                        json={"texto": "word " * (MAX_CARACTERES // 5) + "x"})
    assert resposta.status_code == 422 and resposta.json()["codigo"] == "dados_invalidos"


def test_segundo_envio_e_recusado(ana):
    redacao = _criar(ana)
    url = f"/api/writing/attempts/{redacao['id']}/submissao"
    ana.post(url, json={"texto": TEXTO_OK})

    resposta = ana.post(url, json={"texto": OUTRO_TEXTO})

    assert resposta.status_code == 409 and resposta.json()["codigo"] == "redacao_ja_enviada"


def test_envio_dentro_da_tolerancia_usa_o_texto_recebido(ana, engine_teste):
    redacao = _criar(ana)
    ana.patch(f"/api/writing/attempts/{redacao['id']}", json={"texto": TEXTO_OK})
    _mover_prazo(engine_teste, redacao["id"], segundos_atras=TOLERANCIA_PRAZO_SEGUNDOS - 10)

    corpo = ana.post(f"/api/writing/attempts/{redacao['id']}/submissao", json={"texto": OUTRO_TEXTO}).json()

    assert corpo["texto"] == OUTRO_TEXTO and corpo["usou_ultimo_salvamento"] is False


def test_envio_depois_do_prazo_envia_o_ultimo_autosave(ana, engine_teste):
    """D2: depois do prazo + tolerância, o texto que chega é ignorado (não dá para ganhar tempo extra)."""
    redacao = _criar(ana)
    ana.patch(f"/api/writing/attempts/{redacao['id']}", json={"texto": TEXTO_OK})
    _mover_prazo(engine_teste, redacao["id"], segundos_atras=TOLERANCIA_PRAZO_SEGUNDOS + 1)

    resposta = ana.post(f"/api/writing/attempts/{redacao['id']}/submissao", json={"texto": OUTRO_TEXTO})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["texto"] == TEXTO_OK and corpo["usou_ultimo_salvamento"] is True and corpo["estado"] == ENVIADA
    assert corpo["palavras"] == 60  # contadas no texto enviado de fato, não no que foi ignorado
    tentativa = _no_banco(engine_teste, redacao["id"])
    assert tentativa.texto == TEXTO_OK and tentativa.palavras == 60


def test_envio_depois_do_prazo_com_autosave_curto_e_recusado(ana, engine_teste):
    """D10: o último autosave tem menos de 50 palavras → 422, a redação fica como rascunho vencido."""
    redacao = _criar(ana)
    ana.patch(f"/api/writing/attempts/{redacao['id']}", json={"texto": _palavras(10)})
    _mover_prazo(engine_teste, redacao["id"], segundos_atras=TOLERANCIA_PRAZO_SEGUNDOS + 1)

    resposta = ana.post(f"/api/writing/attempts/{redacao['id']}/submissao", json={"texto": TEXTO_OK})

    assert resposta.status_code == 422
    assert resposta.json()["codigo"] == "redacao_curta" and resposta.json()["palavras"] == 10
    assert _no_banco(engine_teste, redacao["id"]).estado == RASCUNHO


# --- Isolamento entre contas ---

def test_outra_conta_recebe_404_em_tudo_e_nada_muda(ana, bruno, engine_teste):
    redacao = _criar(ana)
    ana.patch(f"/api/writing/attempts/{redacao['id']}", json={"texto": "texto da Ana"})
    url = f"/api/writing/attempts/{redacao['id']}"

    respostas = [
        bruno.get(url),
        bruno.patch(url, json={"texto": "invadido"}),
        bruno.post(f"{url}/submissao", json={"texto": TEXTO_OK}),
    ]

    for resposta in respostas:
        assert resposta.status_code == 404
        assert resposta.json() == {"detail": "Redação não encontrada.", "codigo": "nao_encontrado"}
    assert bruno.get("/api/writing/attempts").json() == []
    tentativa = _no_banco(engine_teste, redacao["id"])
    assert tentativa.texto == "texto da Ana" and tentativa.estado == RASCUNHO
