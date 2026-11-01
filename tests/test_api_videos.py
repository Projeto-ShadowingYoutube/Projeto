import os

import pytest

from app import config
from app.services import midia

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
