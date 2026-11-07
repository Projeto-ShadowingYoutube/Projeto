"""Legendas em qualquer variante de inglês (B10): manual antes de automática; "en" antes de "en-XX"."""
import json

import pytest
from youtube_transcript_api import NoTranscriptFound

from app import config
from app.services import cache_legendas, youtube


class Legenda:
    """Imita youtube_transcript_api.Transcript."""

    def __init__(self, codigo, automatica=False):
        self.language_code = codigo
        self.is_generated = automatica

    def fetch(self):
        tipo = "auto" if self.is_generated else "manual"
        return [type("Bloco", (), {"text": f"{tipo} {self.language_code}", "start": 0.0, "duration": 1.0})()]

    def __str__(self):
        return self.language_code


class ListaDeLegendas:
    """Imita youtube_transcript_api.TranscriptList: find_* procura os códigos NA ORDEM dada, e lança
    NoTranscriptFound quando não acha nenhum (como a biblioteca)."""

    def __init__(self, *legendas):
        self._legendas = legendas

    def __iter__(self):
        return iter(self._legendas)

    def _achar(self, codigos, automatica):
        for codigo in codigos:
            for legenda in self._legendas:
                if legenda.language_code == codigo and legenda.is_generated == automatica:
                    return legenda
        raise NoTranscriptFound("abcdefghijk", codigos, self)

    def find_manually_created_transcript(self, codigos):
        return self._achar(codigos, automatica=False)

    def find_generated_transcript(self, codigos):
        return self._achar(codigos, automatica=True)

    def __str__(self):
        return ", ".join(map(str, self._legendas))


def _escolher(monkeypatch, *legendas):
    class YouTubeFalso:
        def __init__(self, http_client=None):
            pass

        def list(self, video_id):
            return ListaDeLegendas(*legendas)

    monkeypatch.setattr(youtube, "YouTubeTranscriptApi", YouTubeFalso)
    blocos, manual, idioma = youtube.baixar_legendas("abcdefghijk")
    return manual, idioma, blocos[0]["text"]


def test_manual_en_gb_vence_a_automatica_en(monkeypatch):
    """O caso que motivou o B10: antes, só a manual "en" exata era aceita, e este vídeo caía na automática."""
    escolha = _escolher(monkeypatch, Legenda("en", automatica=True), Legenda("en-GB"))
    assert escolha == (True, "en-GB", "manual en-GB")


def test_entre_manuais_en_vem_antes_das_variantes(monkeypatch):
    assert _escolher(monkeypatch, Legenda("en-US"), Legenda("en"))[:2] == (True, "en")


def test_sem_en_puro_as_variantes_seguem_ordem_alfabetica(monkeypatch):
    assert _escolher(monkeypatch, Legenda("en-US"), Legenda("en-GB"))[:2] == (True, "en-GB")


def test_so_automatica_em_variante_de_ingles(monkeypatch):
    assert _escolher(monkeypatch, Legenda("pt"), Legenda("en-US", automatica=True))[:2] == (False, "en-US")


def test_automatica_en_antes_das_variantes(monkeypatch):
    escolha = _escolher(monkeypatch, Legenda("en-GB", automatica=True), Legenda("en", automatica=True))
    assert escolha[:2] == (False, "en")


def test_maiusculas_no_codigo_tambem_sao_ingles(monkeypatch):
    assert _escolher(monkeypatch, Legenda("EN-gb"))[:2] == (True, "EN-gb")


@pytest.mark.parametrize("legendas", [
    (),
    (Legenda("pt"), Legenda("pt", automatica=True)),
    (Legenda("enm"), Legenda("eng", automatica=True)),  # "en" só como prefixo de outro código não é inglês
])
def test_sem_nenhuma_legenda_em_ingles_lanca_sem_legenda(monkeypatch, legendas):
    with pytest.raises(youtube.SemLegenda):
        _escolher(monkeypatch, *legendas)


@pytest.mark.parametrize("codigo, esperado", [
    ("en", True), ("en-US", True), ("en-orig", True), ("EN", True), ("eng", False), ("pt-BR", False), ("", False),
])
def test_eh_ingles(codigo, esperado):
    assert youtube.eh_ingles(codigo) is esperado


# --- Karaokê: legenda automática json3 ---

@pytest.mark.parametrize("disponiveis, escolhida", [
    (["en-orig", "en", "en-US"], "en-orig"),  # o reconhecimento de fala original é o preferido
    (["en-US", "en"], "en"),
    (["pt", "en-US", "en-GB"], "en-GB"),       # B10: sem en-orig/en, qualquer variante (ordem alfabética)
    (["pt", "es"], None),
])
def test_karaoke_escolhe_a_legenda_automatica_em_ingles(monkeypatch, disponiveis, escolhida):
    pedidas = []

    class Resposta:
        def __init__(self, url):
            self.url = url

        def read(self):
            pedidas.append(self.url)
            return json.dumps({"events": []}).encode()

    class YoutubeDLFalso:
        def __init__(self, opcoes):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download):
            return {"automatic_captions": {c: [{"ext": "json3", "url": f"https://legenda/{c}"}] for c in disponiveis}}

        def urlopen(self, url):
            return Resposta(url)

    monkeypatch.setattr(youtube.yt_dlp, "YoutubeDL", YoutubeDLFalso)

    resultado = youtube.baixar_legenda_automatica_json3("abcdefghijk")

    if escolhida is None:
        assert resultado is None and pedidas == []
    else:
        assert pedidas == [f"https://legenda/{escolhida}"]


# --- Cache ---

def test_cache_anterior_ao_b10_e_lida_como_en_sem_ser_invalidada():
    antiga = {"video_id": "abcdefghijk", "dados": {
        "legenda_manual": True, "blocos": [{"text": "Hi", "start": 0, "duration": 1}], "titulo_video": "T",
    }}
    config.ARQUIVO_CACHE_LEGENDAS.write_text(json.dumps(antiga), encoding="utf-8")

    dados = cache_legendas.carregar_da_cache("abcdefghijk")

    assert dados is not None and dados["idioma_legenda"] == "en"


def test_idioma_vai_para_a_cache_e_volta():
    dados = {"legenda_manual": False, "blocos": [], "titulo_video": "T", "idioma_legenda": "en-US"}
    cache_legendas.salvar_na_cache("abcdefghijk", dados)

    assert cache_legendas.carregar_da_cache("abcdefghijk")["idioma_legenda"] == "en-US"
