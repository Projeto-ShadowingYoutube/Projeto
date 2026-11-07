"""Waveform (B9): peaks calculados uma vez no servidor, guardados no banco em JSON, e reaproveitados."""
import subprocess
from pathlib import Path

import numpy as np
import pytest
from sqlmodel import Session, select

from app import config
from app.models import Waveform
from app.services import midia
from app.services.waveform import calcular_peaks


@pytest.fixture()
def client(entrar_como):
    """Desde o B13, as rotas de conteúdo (vídeos, onda, karaokê, avaliação, dicionário) exigem login. Esta fixture
    troca o client destes testes por um navegador já logado; o corpo dos testes não mudou."""
    return entrar_como("conteudo@exemplo.com")


N = config.WAVEFORM_QUANTIDADE_PEAKS
URL = "/api/videos/abcdefghijk/waveform"


def _pcm(segundos=2.0, taxa=config.WAVEFORM_TAXA_AMOSTRAGEM, volume=0.5) -> bytes:
    t = np.arange(int(segundos * taxa)) / taxa
    # Volume crescente: o fim do trecho é mais alto que o começo (dá para conferir o formato da onda).
    onda = np.sin(2 * np.pi * 220 * t) * np.linspace(0.1, 1, t.size) * volume
    return (onda * 32767).astype("<i2").tobytes()


# --- Cálculo ---

def test_peaks_tem_a_quantidade_certa_entre_0_e_1_e_seguem_o_volume():
    peaks = calcular_peaks(_pcm(), N)

    assert len(peaks) == N
    assert all(0 <= p <= 1 for p in peaks)
    assert max(peaks) == 1.0  # normalizado pelo maior volume do trecho
    assert peaks[-1] > peaks[0] * 5  # o fim é bem mais alto que o começo, como o sinal


def test_silencio_e_trecho_vazio_dao_zeros():
    assert calcular_peaks(bytes(16000), N) == [0.0] * N
    assert calcular_peaks(b"", N) == [0.0] * N


def test_trecho_com_menos_amostras_que_peaks_ainda_tem_n_peaks():
    assert len(calcular_peaks(_pcm(segundos=0.01), N)) == N  # 80 amostras para 400 peaks


# --- Rota e cache ---

@pytest.fixture()
def ffmpeg_falso(monkeypatch, tmp_path):
    """Conta quantas vezes o vídeo e o FFmpeg foram usados (o cache existe para evitar isso)."""
    chamadas = {"video": 0, "ffmpeg": 0}

    async def garantir_video(video_id):
        chamadas["video"] += 1
        return Path(tmp_path / f"{video_id}.webm")

    def audio_pcm(video, inicio, fim, taxa):
        chamadas["ffmpeg"] += 1
        assert taxa == config.WAVEFORM_TAXA_AMOSTRAGEM
        return _pcm(segundos=fim - inicio)

    monkeypatch.setattr(midia, "garantir_video", garantir_video)
    monkeypatch.setattr(midia, "audio_pcm", audio_pcm)
    return chamadas


def test_primeira_vez_calcula_e_grava_segunda_vez_vem_do_banco_sem_ffmpeg(client, ffmpeg_falso, engine_teste):
    primeira = client.get(URL, params={"inicio": 1, "fim": 3}).json()
    segunda = client.get(URL, params={"inicio": 1, "fim": 3}).json()

    assert primeira["cache"] is False and segunda["cache"] is True
    assert primeira["peaks"] == segunda["peaks"] and len(segunda["peaks"]) == N
    assert segunda | {"peaks": None} == {
        "video_id": "abcdefghijk", "inicio": 1.0, "fim": 3.0, "duracao": 2.0,
        "versao": config.WAVEFORM_VERSAO_ALGORITMO, "peaks": None, "cache": True,
    }
    assert ffmpeg_falso == {"video": 1, "ffmpeg": 1}  # a segunda nem precisou do vídeo
    with Session(engine_teste) as session:
        registro = session.exec(select(Waveform)).one()
    assert registro.quantidade == N and isinstance(registro.peaks, list)  # JSON de verdade no banco


def test_trecho_e_identificado_com_2_casas_como_o_resto_do_app(client, ffmpeg_falso):
    client.get(URL, params={"inicio": 12.671, "fim": 19.669})

    assert client.get(URL, params={"inicio": 12.67, "fim": 19.67}).json()["cache"] is True
    assert ffmpeg_falso["ffmpeg"] == 1


def test_frases_diferentes_tem_ondas_diferentes(client, ffmpeg_falso):
    client.get(URL, params={"inicio": 0, "fim": 2})
    client.get(URL, params={"inicio": 2, "fim": 4})

    assert ffmpeg_falso["ffmpeg"] == 2


def test_nova_versao_do_algoritmo_invalida_o_cache_antigo(client, ffmpeg_falso, monkeypatch, engine_teste):
    client.get(URL, params={"inicio": 0, "fim": 2})
    monkeypatch.setattr(config, "WAVEFORM_VERSAO_ALGORITMO", config.WAVEFORM_VERSAO_ALGORITMO + 1)

    resposta = client.get(URL, params={"inicio": 0, "fim": 2}).json()

    assert resposta["cache"] is False and resposta["versao"] == config.WAVEFORM_VERSAO_ALGORITMO
    assert ffmpeg_falso["ffmpeg"] == 2
    with Session(engine_teste) as session:
        assert len(session.exec(select(Waveform)).all()) == 2  # a antiga fica, só não é mais usada


def test_registro_incompleto_e_recalculado(client, ffmpeg_falso, engine_teste):
    client.get(URL, params={"inicio": 0, "fim": 2})
    with Session(engine_teste) as session:
        registro = session.exec(select(Waveform)).one()
        registro.peaks = registro.peaks[:10]  # corrompido: quantidade diz 400
        session.add(registro)
        session.commit()

    resposta = client.get(URL, params={"inicio": 0, "fim": 2}).json()

    assert resposta["cache"] is False and len(resposta["peaks"]) == N
    with Session(engine_teste) as session:
        assert len(session.exec(select(Waveform)).one().peaks) == N  # consertado no mesmo registro


def test_duas_requisicoes_ao_mesmo_tempo_nao_quebram(client, monkeypatch, engine_teste, tmp_path):
    """Enquanto esta requisição calculava, outra gravou a mesma onda: o índice único recusa a segunda gravação,
    e a resposta usa a que já estava no banco."""
    async def garantir_video(video_id):
        return tmp_path / "v.webm"

    def audio_pcm_enquanto_outra_grava(video, inicio, fim, taxa):
        with Session(engine_teste) as outra:
            outra.add(Waveform(video_id="abcdefghijk", inicio=0.0, fim=2.0, versao=config.WAVEFORM_VERSAO_ALGORITMO,
                               duracao=2.0, quantidade=N, peaks=[0.5] * N))
            outra.commit()
        return _pcm()

    monkeypatch.setattr(midia, "garantir_video", garantir_video)
    monkeypatch.setattr(midia, "audio_pcm", audio_pcm_enquanto_outra_grava)

    resposta = client.get(URL, params={"inicio": 0, "fim": 2})

    assert resposta.status_code == 200
    assert resposta.json()["peaks"] == [0.5] * N and resposta.json()["cache"] is True
    with Session(engine_teste) as session:
        assert len(session.exec(select(Waveform)).all()) == 1


# --- Erros (formato do B7) ---

def test_intervalo_invalido_400(client, ffmpeg_falso):
    resposta = client.get(URL, params={"inicio": 5, "fim": 2})

    assert resposta.status_code == 400 and resposta.json()["codigo"] == "requisicao_invalida"
    assert ffmpeg_falso["ffmpeg"] == 0


def test_video_indisponivel_502(client, monkeypatch):
    async def indisponivel(video_id):
        raise midia.VideoIndisponivel

    monkeypatch.setattr(midia, "garantir_video", indisponivel)

    resposta = client.get(URL, params={"inicio": 0, "fim": 2})
    assert resposta.status_code == 502 and resposta.json()["codigo"] == "servico_externo_indisponivel"


def test_falha_do_ffmpeg_500_com_mensagem_e_nada_gravado(client, monkeypatch, tmp_path, engine_teste):
    async def garantir_video(video_id):
        return tmp_path / "v.webm"

    def ffmpeg_quebrado(*args):
        raise subprocess.CalledProcessError(1, "ffmpeg")

    monkeypatch.setattr(midia, "garantir_video", garantir_video)
    monkeypatch.setattr(midia, "audio_pcm", ffmpeg_quebrado)

    resposta = client.get(URL, params={"inicio": 0, "fim": 2})

    assert resposta.status_code == 500
    assert resposta.json()["codigo"] == "erro_interno"
    assert resposta.json()["detail"] == "Erro ao gerar a onda da frase. O FFmpeg está instalado?"
    with Session(engine_teste) as session:
        assert session.exec(select(Waveform)).all() == []
