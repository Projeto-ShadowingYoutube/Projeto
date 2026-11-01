import json

from app import config
from app.services import cache_legendas as cache


def dados_fake():
    return {
        "legenda_manual": True,
        "blocos": [{"text": "Hello world", "start": 0.0, "duration": 2.0}],
    }


def test_salvar_e_carregar_cache(monkeypatch, tmp_path):
    arquivo_cache = tmp_path / "ultimo_video.json"
    monkeypatch.setattr(config, "ARQUIVO_CACHE_LEGENDAS", arquivo_cache)

    cache.salvar_na_cache("abcdefghijk", dados_fake())

    carregado = cache.carregar_da_cache("abcdefghijk")
    assert carregado["legenda_manual"] is True
    assert carregado["blocos"][0]["text"] == "Hello world"

    conteudo_arquivo = json.loads(arquivo_cache.read_text(encoding="utf-8"))
    assert conteudo_arquivo["video_id"] == "abcdefghijk"


def test_cache_retorna_none_quando_video_id_diferente(monkeypatch, tmp_path):
    arquivo_cache = tmp_path / "ultimo_video.json"
    monkeypatch.setattr(config, "ARQUIVO_CACHE_LEGENDAS", arquivo_cache)

    cache.salvar_na_cache("abcdefghijk", dados_fake())

    assert cache.carregar_da_cache("zzzzzzzzzzz") is None


def test_cache_retorna_none_quando_arquivo_nao_existe(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ARQUIVO_CACHE_LEGENDAS", tmp_path / "nao_existe.json")

    assert cache.carregar_da_cache("abcdefghijk") is None


def test_cache_preserva_titulo_do_video(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ARQUIVO_CACHE_LEGENDAS", tmp_path / "ultimo_video.json")

    cache.salvar_na_cache("abcdefghijk", {**dados_fake(), "titulo_video": "Meu vídeo"})

    assert cache.carregar_da_cache("abcdefghijk")["titulo_video"] == "Meu vídeo"


def test_cache_em_formato_antigo_e_ignorado(monkeypatch, tmp_path):
    arquivo_cache = tmp_path / "ultimo_video.json"
    formato_antigo = {"video_id": "abcdefghijk", "dados": [{"texto_limpo": "velho"}]}
    arquivo_cache.write_text(json.dumps(formato_antigo), encoding="utf-8")
    monkeypatch.setattr(config, "ARQUIVO_CACHE_LEGENDAS", arquivo_cache)

    assert cache.carregar_da_cache("abcdefghijk") is None
