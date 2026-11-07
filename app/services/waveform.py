"""Onda (waveform) de cada frase: peaks calculados uma vez no servidor e guardados no banco como JSON.

Antes (até o B8), o navegador baixava o WAV inteiro do trecho (~88 KB por segundo) só para desenhar a onda, e
recalculava tudo a cada visita. Agora:
1. Procura a onda do trecho no banco (chave: vídeo, início, fim e versão do algoritmo).
2. Achou e está íntegra → devolve (sem vídeo, sem FFmpeg).
3. Não achou → extrai o áudio do trecho (FFmpeg, a 8 kHz), calcula os peaks com numpy e grava.

Peaks: o trecho é dividido em N blocos iguais (config.WAVEFORM_QUANTIDADE_PEAKS); cada peak é o maior volume
absoluto do bloco, normalizado de 0 a 1 pelo maior do trecho (silêncio: tudo 0). ~3 KB de JSON por frase.

Compatibilidade do cache: a versão do algoritmo (config.WAVEFORM_VERSAO_ALGORITMO) faz parte da chave. Mudou o
cálculo? Aumente a versão: os registros antigos simplesmente deixam de ser encontrados e cada onda é recalculada.
"""
import asyncio
import logging

import numpy as np
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app import config
from app.models import Waveform
from app.services import midia

logger = logging.getLogger("uvicorn.error")


def calcular_peaks(pcm: bytes, quantidade: int) -> list[float]:
    """PCM 16 bits mono → `quantidade` peaks entre 0 e 1 (3 casas decimais)."""
    amostras = np.abs(np.frombuffer(pcm, dtype="<i2").astype(np.float32))
    blocos = np.array_split(amostras, quantidade)  # trecho curtíssimo: alguns blocos vazios (= 0)
    peaks = np.array([bloco.max() if bloco.size else 0.0 for bloco in blocos])
    maior = peaks.max() if peaks.size else 0.0
    if maior > 0:
        peaks = peaks / maior
    return [round(float(peak), 3) for peak in peaks]


def _buscar(session: Session, video_id: str, inicio: float, fim: float) -> Waveform | None:
    consulta = select(Waveform).where(
        Waveform.video_id == video_id, Waveform.inicio == inicio, Waveform.fim == fim,
        Waveform.versao == config.WAVEFORM_VERSAO_ALGORITMO,
    )
    return session.exec(consulta).first()


def _integra(registro: Waveform) -> bool:
    return isinstance(registro.peaks, list) and registro.quantidade == len(registro.peaks) > 0


def _resposta(registro: Waveform, cache: bool) -> dict:
    return {
        "video_id": registro.video_id, "inicio": registro.inicio, "fim": registro.fim, "duracao": registro.duracao,
        "versao": registro.versao, "peaks": registro.peaks, "cache": cache,
    }


async def obter(session: Session, video_id: str, inicio: float, fim: float) -> dict:
    """A onda do trecho: do banco, se já existe; senão, calcula e grava. Lança midia.VideoIndisponivel se o
    vídeo não puder ser baixado, e OSError/CalledProcessError se o FFmpeg falhar."""
    inicio, fim = round(inicio, 2), round(fim, 2)
    registro = _buscar(session, video_id, inicio, fim)
    if registro is not None and _integra(registro):
        return _resposta(registro, cache=True)

    video = await midia.garantir_video(video_id)
    pcm = await asyncio.to_thread(midia.audio_pcm, video, inicio, fim, config.WAVEFORM_TAXA_AMOSTRAGEM)
    peaks = calcular_peaks(pcm, config.WAVEFORM_QUANTIDADE_PEAKS)

    if registro is None:
        registro = Waveform(
            video_id=video_id, inicio=inicio, fim=fim, versao=config.WAVEFORM_VERSAO_ALGORITMO,
            duracao=round(fim - inicio, 2), quantidade=len(peaks), peaks=peaks,
        )
    else:  # existia, mas incompleto/corrompido: recalculado no mesmo registro
        logger.warning("Waveform %s %.2f-%.2f inválida no banco; recalculando.", video_id, inicio, fim)
        registro.peaks, registro.quantidade = peaks, len(peaks)
    session.add(registro)
    try:
        session.commit()
    except IntegrityError:
        # Outra requisição da mesma frase gravou antes (índice único): usa a dela.
        session.rollback()
        return _resposta(_buscar(session, video_id, inicio, fim), cache=True)
    session.refresh(registro)
    return _resposta(registro, cache=False)
