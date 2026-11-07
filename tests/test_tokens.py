"""Limite de tokens por conta (B11): cada usuário tem os próprios tokens, e quem esgota recebe quando tentar de novo.

Usa o limitador de verdade (novo a cada teste, com limite de 2) e simula só o YouTube.
"""
import pytest
from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter

from app.api import legendas as rota
from app.services import youtube

LIMITE = 2
JANELA_S = 300


def _url(numero: int) -> str:
    return f"https://youtu.be/video{numero:06d}"  # IDs de 11 caracteres, todos diferentes


@pytest.fixture(autouse=True)
def limite_real_de_2_tokens(monkeypatch):
    monkeypatch.setattr(rota, "LIMITE_TOKENS", parse(f"{LIMITE}/5 minute"))
    monkeypatch.setattr(rota, "limitador", FixedWindowRateLimiter(MemoryStorage()))


@pytest.fixture()
def youtube_simulado(monkeypatch):
    """Cada vídeo pedido ao "YouTube" fica registrado; a cache real (arquivo temporário) continua funcionando."""
    pedidos = []

    def baixar_legendas(video_id):
        pedidos.append(video_id)
        if video_id.startswith("semlg"):
            raise youtube.SemLegenda(video_id)
        return [{"text": "Hello world.", "start": 0.0, "duration": 2.0}], True

    monkeypatch.setattr(youtube, "baixar_legendas", baixar_legendas)
    monkeypatch.setattr(youtube, "buscar_titulo", lambda video_id: "Vídeo simulado")
    return pedidos


@pytest.fixture()
def ana(entrar_como):
    return entrar_como("ana@exemplo.com")


@pytest.fixture()
def bruno(entrar_como):
    return entrar_como("bruno@exemplo.com")


def test_sem_login_legendas_e_tokens_respondem_401(client):
    assert client.get("/api/tokens").status_code == 401
    assert client.get("/api/legendas", params={"url": _url(1)}).status_code == 401


def test_conta_nova_tem_todos_os_tokens_e_nada_a_renovar(ana):
    assert ana.get("/api/tokens").json() == {"tokens_restantes": LIMITE, "limite": LIMITE, "renova_em": None}


def test_cada_video_novo_gasta_um_token_e_informa_a_renovacao(ana, youtube_simulado):
    resposta = ana.get("/api/legendas", params={"url": _url(1)}).json()

    assert resposta["tokens_restantes"] == LIMITE - 1
    assert 0 < resposta["renova_em"] <= JANELA_S
    tokens = ana.get("/api/tokens").json()
    assert tokens["tokens_restantes"] == LIMITE - 1 and 0 < tokens["renova_em"] <= JANELA_S


def test_quem_esgota_recebe_429_com_o_tempo_e_o_youtube_nao_e_chamado(ana, youtube_simulado):
    for numero in range(LIMITE):
        assert ana.get("/api/legendas", params={"url": _url(numero)}).status_code == 200

    resposta = ana.get("/api/legendas", params={"url": _url(99)})

    assert resposta.status_code == 429
    corpo = resposta.json()
    assert corpo["codigo"] == "limite_de_tokens"
    assert corpo["tokens_restantes"] == 0 and corpo["limite"] == LIMITE
    assert 0 < corpo["tentar_novamente_em"] <= JANELA_S
    assert resposta.headers["retry-after"] == str(corpo["tentar_novamente_em"])
    assert corpo["detail"].startswith("Seus tokens acabaram. Novos tokens em ")
    assert "revisar seus Decks" in corpo["detail"]
    assert "video000099" not in youtube_simulado  # o limite não foi contornado: o YouTube nem foi consultado


def test_contas_tem_tokens_independentes(ana, bruno, youtube_simulado):
    for numero in range(LIMITE):
        ana.get("/api/legendas", params={"url": _url(numero)})
    assert ana.get("/api/legendas", params={"url": _url(50)}).status_code == 429

    assert bruno.get("/api/tokens").json()["tokens_restantes"] == LIMITE
    assert bruno.get("/api/legendas", params={"url": _url(60)}).status_code == 200
    assert bruno.get("/api/tokens").json()["tokens_restantes"] == LIMITE - 1


def test_video_na_cache_nao_gasta_token_nem_com_os_tokens_zerados(ana, youtube_simulado):
    for numero in range(LIMITE):
        ana.get("/api/legendas", params={"url": _url(numero)})
    ultimo = _url(LIMITE - 1)  # a cache guarda o último vídeo carregado

    resposta = ana.get("/api/legendas", params={"url": ultimo})

    assert resposta.status_code == 200
    assert resposta.json()["tokens_restantes"] == 0
    assert youtube_simulado.count(ultimo[-11:]) == 1  # veio da cache, sem nova consulta ao YouTube


def test_url_invalida_nao_gasta_token(ana, youtube_simulado):
    assert ana.get("/api/legendas", params={"url": "nao-e-youtube"}).status_code == 400
    assert ana.get("/api/tokens").json()["tokens_restantes"] == LIMITE


def test_video_sem_legenda_gasta_token_porque_o_youtube_foi_consultado(ana, youtube_simulado):
    """Regra documentada: o token protege a consulta ao YouTube, e ela aconteceu. Devolver o token permitiria
    consultar o YouTube sem limite usando vídeos sem legenda."""
    resposta = ana.get("/api/legendas", params={"url": "https://youtu.be/semlg000001"})

    assert resposta.status_code == 404
    assert ana.get("/api/tokens").json()["tokens_restantes"] == LIMITE - 1


@pytest.mark.parametrize("segundos, texto", [(45, "45 s"), (60, "1 min"), (252, "4 min 12 s"), (300, "5 min")])
def test_tempo_legivel(segundos, texto):
    assert rota.tempo_legivel(segundos) == texto

