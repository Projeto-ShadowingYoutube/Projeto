import json


def dados_fake():
    return {
        "legenda_manual": True,
        "legendas": [
            {
                "id_do_bloco": 0,
                "texto_limpo": "Hello world",
                "tempo_inicio": 0.0,
                "tempo_fim": 2.0,
            }
        ],
    }


def test_salvar_e_carregar_cache(monkeypatch, tmp_path):
    import cache

    arquivo_cache = tmp_path / "ultimo_video.json"
    monkeypatch.setattr(cache, "ARQUIVO_CACHE", str(arquivo_cache))

    cache.salvar_na_cache("abcdefghijk", dados_fake())

    carregado = cache.carregar_da_cache("abcdefghijk")
    assert carregado["legenda_manual"] is True
    assert carregado["legendas"][0]["texto_limpo"] == "Hello world"

    conteudo_arquivo = json.loads(arquivo_cache.read_text(encoding="utf-8"))
    assert conteudo_arquivo["video_id"] == "abcdefghijk"


def test_cache_retorna_none_quando_video_id_diferente(monkeypatch, tmp_path):
    import cache

    arquivo_cache = tmp_path / "ultimo_video.json"
    monkeypatch.setattr(cache, "ARQUIVO_CACHE", str(arquivo_cache))

    cache.salvar_na_cache("abcdefghijk", dados_fake())

    assert cache.carregar_da_cache("zzzzzzzzzzz") is None


def test_cache_retorna_none_quando_arquivo_nao_existe(monkeypatch, tmp_path):
    import cache

    monkeypatch.setattr(cache, "ARQUIVO_CACHE", str(tmp_path / "nao_existe.json"))

    assert cache.carregar_da_cache("abcdefghijk") is None
