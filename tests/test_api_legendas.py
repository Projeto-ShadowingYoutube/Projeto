import time
from types import SimpleNamespace

import pytest
from youtube_transcript_api import NoTranscriptFound

from app.api import legendas as rota
from app.services import legendas as servico
from app.services import youtube


@pytest.fixture()
def client(entrar_como):
    """Desde o B11, as legendas exigem login (o limite de tokens é por conta). Esta fixture troca o client destes
    testes por um navegador já logado; o corpo dos testes não mudou."""
    return entrar_como("legendas@exemplo.com")


class FakeLimitador:
    def hit(self, *args, **kwargs):
        return True

    def get_window_stats(self, *args, **kwargs):
        return SimpleNamespace(remaining=4, reset_time=time.time() + 120)


class FakeOEmbedResponse:
    status_code = 200

    def json(self):
        return {"title": "Título fake do YouTube"}


class FakeHTTPSession:
    def get(self, url, **kwargs):
        return FakeOEmbedResponse()


class FakeBloco:
    def __init__(self, text, start, duration):
        self.text = text
        self.start = start
        self.duration = duration


class FakeTranscript:
    def __init__(self, blocos, language_code="en", is_generated=False):
        self._blocos = blocos
        self.language_code = language_code
        self.is_generated = is_generated

    def fetch(self):
        return self._blocos


class FakeListaLegendasManual:
    def __iter__(self):  # desde o B10, a escolha percorre a lista para ver os códigos de inglês disponíveis
        return iter([FakeTranscript([], "en", is_generated=False)])

    def find_manually_created_transcript(self, idiomas):
        return FakeTranscript([
            FakeBloco("  Hello    world.  ", 0.0, 2.5),
            FakeBloco("Yes.", 2.6, 0.5),
            FakeBloco("Next line", 3.2, 1.0),
            FakeBloco("goes here.", 4.2, 2.0),
        ])

    def find_generated_transcript(self, idiomas):  # pragma: no cover
        raise AssertionError("Não deveria procurar legenda automática quando manual existe.")


class FakeListaLegendasAutomatica:
    def __iter__(self):
        return iter([FakeTranscript([], "en", is_generated=True)])

    def find_manually_created_transcript(self, idiomas):
        raise NoTranscriptFound("abcdefghijk", ["en"], None)

    def find_generated_transcript(self, idiomas):
        return FakeTranscript([
            FakeBloco("Automatic caption", 10.0, 2.0),
        ], is_generated=True)


class FakeYouTubeManual:
    chamadas = []

    def __init__(self, http_client=None):
        self.http_client = http_client

    def list(self, video_id):
        self.__class__.chamadas.append(video_id)
        return FakeListaLegendasManual()


class FakeYouTubeAutomatica:
    def __init__(self, http_client=None):
        self.http_client = http_client

    def list(self, video_id):
        return FakeListaLegendasAutomatica()


@pytest.fixture(autouse=True)
def mocks_basicos(monkeypatch):
    monkeypatch.setattr(rota, "limitador", FakeLimitador())
    monkeypatch.setattr(youtube, "http_session", FakeHTTPSession())
    monkeypatch.setattr(servico, "carregar_da_cache", lambda video_id: None)
    monkeypatch.setattr(servico, "salvar_na_cache", lambda video_id, dados: None)


def test_api_legenda_com_mock_youtube_manual(client, monkeypatch):
    salvos = []
    monkeypatch.setattr(youtube, "YouTubeTranscriptApi", FakeYouTubeManual)
    monkeypatch.setattr(
        servico,
        "salvar_na_cache",
        lambda video_id, dados: salvos.append((video_id, dados)),
    )

    resposta = client.get("/api/legendas", params={"url": "https://www.youtube.com/watch?v=abcdefghijk"})

    assert resposta.status_code == 200
    body = resposta.json()
    assert body["video_id"] == "abcdefghijk"
    assert body["legenda_manual"] is True
    assert body["titulo_video"] == "Título fake do YouTube"
    assert body["tokens_restantes"] == 4

    # As frases são reagrupadas pela pontuação; o "Yes." curto é juntado à frase seguinte.
    chaves = ("id_do_bloco", "texto_limpo", "tempo_inicio", "tempo_fim")
    frases = [{chave: f[chave] for chave in chaves} for f in body["dados"]]
    assert frases == [
        {"id_do_bloco": 0, "texto_limpo": "Hello world.", "tempo_inicio": 0.0, "tempo_fim": 2.5},
        {"id_do_bloco": 1, "texto_limpo": "Yes. Next line goes here.", "tempo_inicio": 2.6, "tempo_fim": 6.2},
    ]
    # Um [início, fim] por palavra, para o modo karaokê.
    assert [len(f["tempos_palavras"]) for f in body["dados"]] == [2, 5]
    assert FakeYouTubeManual.chamadas == ["abcdefghijk"]
    assert salvos[0][0] == "abcdefghijk"
    assert salvos[0][1]["titulo_video"] == "Título fake do YouTube"
    # A cache guarda os blocos brutos, para a divisão em frases poder evoluir sem baixar de novo.
    assert salvos[0][1]["blocos"][0] == {"text": "  Hello    world.  ", "start": 0.0, "duration": 2.5}


def test_api_legenda_faz_fallback_para_legenda_automatica(client, monkeypatch):
    monkeypatch.setattr(youtube, "YouTubeTranscriptApi", FakeYouTubeAutomatica)

    resposta = client.get("/api/legendas", params={"url": "https://youtu.be/abcdefghijk"})

    assert resposta.status_code == 200
    body = resposta.json()
    assert body["legenda_manual"] is False
    assert "AUTOMÁTICA" in body["aviso_legenda"]
    assert body["dados"][0]["texto_limpo"] == "Automatic caption"


def test_api_legenda_usa_cache_e_nao_chama_youtube(client, monkeypatch):
    monkeypatch.setattr(
        servico,
        "carregar_da_cache",
        lambda video_id: {
            "legenda_manual": True,
            "titulo_video": "Título vindo da cache",
            "blocos": [{"text": "Cached text", "start": 1.0, "duration": 2.0}],
        },
    )

    class YouTubeNaoPodeSerChamado:
        def __init__(self, *args, **kwargs):
            raise AssertionError("YouTube não deveria ser chamado quando existe cache.")

    monkeypatch.setattr(youtube, "YouTubeTranscriptApi", YouTubeNaoPodeSerChamado)

    resposta = client.get("/api/legendas", params={"url": "https://www.youtube.com/watch?v=abcdefghijk"})

    assert resposta.status_code == 200
    body = resposta.json()
    assert body["titulo_video"] == "Título vindo da cache"
    assert body["dados"][0]["texto_limpo"] == "Cached text"


def test_api_legenda_url_invalida_retorna_400(client):
    resposta = client.get("/api/legendas", params={"url": "nao-e-youtube"})

    assert resposta.status_code == 400


def test_api_legenda_video_sem_legenda_retorna_404(client, monkeypatch):
    class ListaSemLegendas:
        def __iter__(self):
            return iter([])

        def find_manually_created_transcript(self, idiomas):
            raise NoTranscriptFound("abcdefghijk", ["en"], None)

        find_generated_transcript = find_manually_created_transcript

    class YouTubeSemLegendas:
        def __init__(self, http_client=None):
            pass

        def list(self, video_id):
            return ListaSemLegendas()

    monkeypatch.setattr(youtube, "YouTubeTranscriptApi", YouTubeSemLegendas)

    resposta = client.get("/api/legendas", params={"url": "https://youtu.be/abcdefghijk"})

    assert resposta.status_code == 404
