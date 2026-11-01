import pytest

from app.services import alinhamento, karaoke

VIDEO_ID = "fNk_zzaMoSs"


def test_alinha_mesmo_com_apostrofo_e_numero_diferentes():
    referencia = [("in", 0.0, 0.2), ("nineteen", 0.2, 0.6), ("ninety", 0.6, 1.0), ("its", 1.0, 1.2), ("bob", 1.2, 1.5)]
    tempos, cobertura = alinhamento.alinhar("In 1990 it's Bob.".split(), referencia, 2.0)

    assert cobertura == 0.75
    # "1990" não casou com nada: fica entre "In" e "it's".
    assert tempos == [[0.0, 0.2], [0.2, 1.0], [1.0, 1.2], [1.2, 1.5]]


def test_tempos_ficam_em_ordem_e_dentro_da_frase():
    referencia = [("b", 0.9, 1.0), ("a", 0.5, 0.6), ("c", 5.0, 6.0)]
    tempos, _ = alinhamento.alinhar(["a", "b", "c"], referencia, 2.0)
    inicios = [inicio for inicio, _ in tempos]
    assert inicios == sorted(inicios)
    assert all(0 <= inicio <= fim <= 2.0 for inicio, fim in tempos)


def test_palavras_do_json3():
    dados = {"events": [
        {"tStartMs": 0, "dDurationMs": 2000, "segs": [{"utf8": "[Music]"}]},
        {"tStartMs": 1000, "dDurationMs": 3000, "segs": [{"utf8": "hello"}, {"utf8": " world", "tOffsetMs": 500}]},
        {"tStartMs": 3900, "aAppend": 1, "segs": [{"utf8": "\n"}]},
    ]}
    assert alinhamento.palavras_do_json3(dados) == [("hello", 1.0, 1.5), ("world", 1.5, 4.0)]


@pytest.fixture
def fontes(monkeypatch, tmp_path):
    karaoke._resultados.clear()
    chamadas = {"youtube": 0, "audio": 0}

    def youtube(video_id):
        chamadas["youtube"] += 1
        return fontes.youtube

    def audio(video, palavras_frase, inicio, fim):
        chamadas["audio"] += 1
        return fontes.audio

    async def video(video_id):
        return tmp_path / "video.webm"

    monkeypatch.setattr(karaoke.youtube, "baixar_legenda_automatica_json3", youtube)
    monkeypatch.setattr(alinhamento, "tempos_pelo_audio", audio)
    monkeypatch.setattr(karaoke.midia, "garantir_video", video)
    fontes.chamadas = chamadas
    return fontes


def json3(palavras, fim):
    """Legenda automática no formato do YouTube: um evento com o início de cada palavra."""
    inicio = palavras[0][1]
    return {"events": [{
        "tStartMs": round(inicio * 1000),
        "dDurationMs": round((fim - inicio) * 1000),
        "segs": [{"utf8": p, "tOffsetMs": round((t - inicio) * 1000)} for p, t in palavras],
    }]}


def consultar(client, texto="hello world"):
    return client.get(f"/api/videos/{VIDEO_ID}/palavras", params={"inicio": 10, "fim": 12, "texto": texto}).json()


def test_usa_a_legenda_automatica_quando_bate_com_o_texto(client, fontes):
    fontes.youtube = json3([("hello", 10.0), ("world", 10.6)], fim=11.5)
    fontes.audio = (None, 0)

    assert consultar(client) == {"tempos": [[0.0, 0.6], [0.6, 1.5]], "fonte": "youtube"}
    consultar(client, "hello world again")
    # A legenda automática é baixada uma vez só por vídeo; o áudio nem foi preciso.
    assert fontes.chamadas == {"youtube": 1, "audio": 0}


def test_alinha_o_audio_quando_nao_ha_legenda_automatica(client, fontes):
    fontes.youtube = None
    fontes.audio = ([[0.1, 0.7], [0.7, 1.4]], 1.0)

    assert consultar(client) == {"tempos": [[0.1, 0.7], [0.7, 1.4]], "fonte": "audio"}


def test_sem_fonte_confiavel_fica_a_estimativa(client, fontes):
    fontes.youtube = json3([("something", 10.0), ("else", 11.0)], fim=12.0)
    fontes.audio = (None, 0)

    assert consultar(client) == {"tempos": None, "fonte": "estimativa"}
