import asyncio
import os
import threading

import pytest

from app import config
from app.services import midia, youtube

VIDEO_ID = "fNk_zzaMoSs"


@pytest.fixture(autouse=True)
def downloads_limpos():
    midia._downloads.clear()
    midia._progresso.clear()


def test_video_ja_baixado_esta_pronto_e_aceita_range(client):
    (midia.pasta() / f"{VIDEO_ID}.webm").write_bytes(b"0123456789")

    assert client.get(f"/api/videos/{VIDEO_ID}/status").json() == {"pronto": True, "progresso": 1.0}
    resposta = client.get(f"/api/videos/{VIDEO_ID}", headers={"Range": "bytes=2-5"})
    assert resposta.status_code == 206
    assert resposta.content == b"2345"
    assert resposta.headers["content-type"] == "video/webm"


def test_video_nao_baixado_retorna_404(client):
    assert client.get(f"/api/videos/{VIDEO_ID}").status_code == 404


def test_status_inicia_o_download(client, monkeypatch):
    baixados = []

    def baixar(video_id, pasta, ao_progredir):
        baixados.append(video_id)
        ao_progredir(0.5)
        (pasta / f"{video_id}.mp4").write_bytes(b"video")

    monkeypatch.setattr(midia.youtube, "baixar_video", baixar)
    client.get(f"/api/videos/{VIDEO_ID}/status")
    # O TestClient espera as tarefas da requisição; numa segunda consulta o vídeo já está lá.
    for _ in range(50):
        if client.get(f"/api/videos/{VIDEO_ID}/status").json()["pronto"]:
            break
    assert baixados == [VIDEO_ID]


def test_id_de_video_invalido(client):
    assert client.get("/api/videos/curto/status").status_code == 422
    assert client.get("/api/videos/curto/audio", params={"inicio": 0, "fim": 2}).status_code == 422


def test_audio_rejeita_intervalo_invalido(client):
    resposta = client.get(f"/api/videos/{VIDEO_ID}/audio", params={"inicio": 5, "fim": 2})
    assert resposta.status_code == 400


def test_limpa_videos_antigos(monkeypatch):
    monkeypatch.setattr(config, "MAX_VIDEOS_GUARDADOS", 2)
    for i, nome in enumerate(["aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"]):
        (midia.pasta() / f"{nome}.webm").write_bytes(b"v")
        (midia.pasta() / f"{nome}_1.00_2.00.wav").write_bytes(b"a")
        os.utime(midia.pasta() / f"{nome}.webm", (i, i))
    midia._limpar_antigos()
    restantes = sorted(p.name for p in midia.pasta().iterdir())
    assert restantes == [
        "bbbbbbbbbbb.webm", "bbbbbbbbbbb_1.00_2.00.wav", "ccccccccccc.webm", "ccccccccccc_1.00_2.00.wav",
    ]


def _youtube_que_baixa(monkeypatch, downloads, liberar=None):
    """baixar_video falso: registra a chamada e cria o arquivo (se liberar for um Event, espera por ele antes)."""
    def baixar_video(video_id, pasta, ao_progredir):
        downloads.append(video_id)
        if liberar is not None:
            liberar.wait(5)
        (pasta / f"{video_id}.webm").write_bytes(b"x")

    monkeypatch.setattr(youtube, "baixar_video", baixar_video)


def test_video_apagado_pela_limpeza_e_baixado_de_novo(monkeypatch):
    """B9.1 (bug anterior a este trabalho): a limpeza apaga os vídeos antigos, mas o registro em memória dizia "já
    baixado" e o download nunca era refeito: o player ficava em "Baixando o vídeo... 0%" até reiniciar o servidor."""
    downloads = []
    _youtube_que_baixa(monkeypatch, downloads)

    async def cenario():
        await midia.garantir_video(VIDEO_ID)
        midia.arquivo_do_video(VIDEO_ID).unlink()  # a limpeza (_limpar_antigos) apagou o vídeo
        assert not midia.download_falhou(VIDEO_ID)
        return await asyncio.wait_for(midia.garantir_video(VIDEO_ID), 5)

    caminho = asyncio.run(cenario())

    assert caminho.exists()
    assert downloads == [VIDEO_ID, VIDEO_ID]  # baixou de novo


def test_download_em_andamento_nao_e_iniciado_duas_vezes(monkeypatch):
    downloads, liberar = [], threading.Event()
    _youtube_que_baixa(monkeypatch, downloads, liberar)

    async def cenario():
        primeira = midia.iniciar_download(VIDEO_ID)
        await asyncio.sleep(0.05)  # o download começou e ainda não terminou (sem arquivo)
        segunda = midia.iniciar_download(VIDEO_ID)
        liberar.set()
        await primeira
        return primeira is segunda

    assert asyncio.run(cenario()) is True
    assert downloads == [VIDEO_ID]
