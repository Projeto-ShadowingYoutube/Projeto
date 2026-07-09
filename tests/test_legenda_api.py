from types import SimpleNamespace


class FakeLimitadorInterno:
    def hit(self, *args, **kwargs):
        return True

    def get_window_stats(self, *args, **kwargs):
        return SimpleNamespace(remaining=4)


class FakeLimitador:
    limiter = FakeLimitadorInterno()


class FakeOEmbedResponse:
    status_code = 200

    def json(self):
        return {"title": "Título fake do YouTube"}


class FakeHTTPSession:
    def get(self, url):
        return FakeOEmbedResponse()


class FakeBloco:
    def __init__(self, text, start, duration):
        self.text = text
        self.start = start
        self.duration = duration


class FakeTranscript:
    def __init__(self, blocos):
        self._blocos = blocos

    def fetch(self):
        return self._blocos


class FakeListaLegendasManual:
    def find_manually_created_transcript(self, idiomas):
        return FakeTranscript([
            FakeBloco("  Hello    world  ", 0.0, 2.5),
            FakeBloco("curto demais", 2.5, 0.5),
            FakeBloco("Hello world", 3.0, 2.0),
            FakeBloco("Next line", 5.0, 3.0),
        ])

    def find_generated_transcript(self, idiomas):  # pragma: no cover
        raise AssertionError("Não deveria procurar legenda automática quando manual existe.")


class FakeListaLegendasAutomatica:
    def find_manually_created_transcript(self, idiomas):
        raise Exception("sem legenda manual")

    def find_generated_transcript(self, idiomas):
        return FakeTranscript([
            FakeBloco("Automatic caption", 10.0, 2.0),
        ])


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


def preparar_mocks_basicos(monkeypatch, main_module):
    monkeypatch.setattr(main_module, "limitador", FakeLimitador())
    monkeypatch.setattr(main_module, "http_session", FakeHTTPSession())
    monkeypatch.setattr(main_module, "carregar_da_cache", lambda video_id: None)


def test_api_legenda_com_mock_youtube_manual(client, main_module, monkeypatch):
    preparar_mocks_basicos(monkeypatch, main_module)
    salvos = []
    monkeypatch.setattr(main_module, "YouTubeTranscriptApi", FakeYouTubeManual)
    monkeypatch.setattr(
        main_module,
        "salvar_na_cache",
        lambda video_id, dados: salvos.append((video_id, dados)),
    )

    resposta = client.get("/api/legenda", params={"url": "https://www.youtube.com/watch?v=abcdefghijk"})

    assert resposta.status_code == 200
    body = resposta.json()
    assert body["legenda_manual"] is True
    assert body["titulo_video"] == "Título fake do YouTube"
    assert body["tokens_restantes"] == 4

    # O código deve limpar espaços, remover bloco <= 1s e remover repetição consecutiva.
    assert body["dados"] == [
        {
            "id_do_bloco": 0,
            "texto_limpo": "Hello world",
            "tempo_inicio": 0.0,
            "tempo_fim": 2.5,
        },
        {
            "id_do_bloco": 1,
            "texto_limpo": "Next line",
            "tempo_inicio": 5.0,
            "tempo_fim": 8.0,
        },
    ]
    assert FakeYouTubeManual.chamadas == ["abcdefghijk"]
    assert salvos[0][0] == "abcdefghijk"


def test_api_legenda_faz_fallback_para_legenda_automatica(client, main_module, monkeypatch):
    preparar_mocks_basicos(monkeypatch, main_module)
    monkeypatch.setattr(main_module, "YouTubeTranscriptApi", FakeYouTubeAutomatica)
    monkeypatch.setattr(main_module, "salvar_na_cache", lambda video_id, dados: None)

    resposta = client.get("/api/legenda", params={"url": "https://youtu.be/abcdefghijk"})

    assert resposta.status_code == 200
    body = resposta.json()
    assert body["legenda_manual"] is False
    assert "AUTOMÁTICA" in body["aviso_legenda"]
    assert body["dados"][0]["texto_limpo"] == "Automatic caption"


def test_api_legenda_usa_cache_e_nao_chama_youtube(client, main_module, monkeypatch):
    monkeypatch.setattr(main_module, "limitador", FakeLimitador())
    monkeypatch.setattr(
        main_module,
        "carregar_da_cache",
        lambda video_id: {
            "legenda_manual": True,
            "titulo_video": "Título vindo da cache",
            "legendas": [
                {
                    "id_do_bloco": 0,
                    "texto_limpo": "Cached text",
                    "tempo_inicio": 1.0,
                    "tempo_fim": 3.0,
                }
            ],
        },
    )

    class YouTubeNaoPodeSerChamado:
        def __init__(self, *args, **kwargs):
            raise AssertionError("YouTube não deveria ser chamado quando existe cache.")

    monkeypatch.setattr(main_module, "YouTubeTranscriptApi", YouTubeNaoPodeSerChamado)

    resposta = client.get("/api/legenda", params={"url": "https://www.youtube.com/watch?v=abcdefghijk"})

    assert resposta.status_code == 200
    body = resposta.json()
    assert body["titulo_video"] == "Título vindo da cache"
    assert body["dados"][0]["texto_limpo"] == "Cached text"


def test_api_legenda_url_invalida_retorna_400(client):
    resposta = client.get("/api/legenda", params={"url": "nao-e-youtube"})

    assert resposta.status_code == 400
