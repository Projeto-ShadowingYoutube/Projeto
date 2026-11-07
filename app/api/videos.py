"""Rotas do vídeo baixado: progresso do download, o arquivo, a onda (waveform) e o áudio de uma frase e o tempo
das palavras."""
import logging
import subprocess

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import FileResponse
from sqlmodel import Session

from app import config
from app.api.auth import usuario_atual
from app.db import get_session
from app.schemas import StatusVideo, TemposPalavras, WaveformDoTrecho
from app.services import karaoke, midia, waveform

logger = logging.getLogger("uvicorn.error")
# Exige login (B13): estas rotas são as mais caras do servidor (YouTube, FFmpeg, Vosk, Wiktionary).
router = APIRouter(prefix="/api/videos/{video_id}", tags=["vídeos"], dependencies=[Depends(usuario_atual)])

VideoId = Path(pattern=config.PADRAO_VIDEO_ID)


def _validar_trecho(inicio: float, fim: float) -> None:
    if fim <= inicio or fim - inicio > config.DURACAO_MAXIMA_TRECHO:
        raise HTTPException(status_code=400, detail="Intervalo inválido.")


@router.get("/status", response_model=StatusVideo)
async def status_do_video(video_id: str = VideoId):
    """Começa o download, se preciso, e informa o progresso. A página consulta até ficar pronto."""
    if midia.arquivo_do_video(video_id):
        return {"pronto": True, "progresso": 1.0}
    midia.iniciar_download(video_id)
    if midia.download_falhou(video_id):
        raise HTTPException(status_code=502, detail="Não foi possível baixar o vídeo do YouTube.")
    return {"pronto": False, "progresso": round(midia.progresso(video_id), 3)}


@router.get("", response_class=FileResponse)
async def obter_video(video_id: str = VideoId):
    """O arquivo do vídeo (aceita Range, para o navegador pular para qualquer ponto)."""
    caminho = midia.arquivo_do_video(video_id)
    if not caminho:
        raise HTTPException(status_code=404, detail="O vídeo ainda não foi baixado.")
    return FileResponse(caminho, media_type=midia.tipo_do_video(caminho))


@router.get("/waveform", response_model=WaveformDoTrecho)
async def onda_do_trecho(
    video_id: str = VideoId, inicio: float = Query(ge=0), fim: float = Query(gt=0),
    session: Session = Depends(get_session),
):
    """Peaks (0 a 1) para desenhar a onda da frase. Calculados uma vez e guardados no banco (services/waveform.py):
    da segunda vez em diante, vêm prontos, sem FFmpeg e sem precisar do vídeo."""
    _validar_trecho(inicio, fim)
    try:
        return await waveform.obter(session, video_id, inicio, fim)
    except midia.VideoIndisponivel:
        raise HTTPException(status_code=502, detail="Não foi possível baixar o vídeo do YouTube.") from None
    except (OSError, subprocess.CalledProcessError):
        logger.exception("Erro ao calcular a onda do vídeo %s", video_id)
        raise HTTPException(status_code=500, detail="Erro ao gerar a onda da frase. O FFmpeg está instalado?") from None


@router.get("/audio", response_class=FileResponse)
async def obter_audio(video_id: str = VideoId, inicio: float = Query(ge=0), fim: float = Query(gt=0)):
    """WAV de uma frase. Desde o B9 a onda usa /waveform; esta rota ficou sem uso interno (candidata a remoção)."""
    _validar_trecho(inicio, fim)
    try:
        audio = await midia.audio_da_frase(video_id, inicio, fim)
    except midia.VideoIndisponivel:
        raise HTTPException(status_code=502, detail="Não foi possível baixar o vídeo do YouTube.") from None
    except (OSError, subprocess.CalledProcessError):
        logger.exception("Erro ao recortar o áudio do vídeo %s", video_id)
        detalhe = "Erro ao gerar o áudio da frase. O FFmpeg está instalado?"
        raise HTTPException(status_code=500, detail=detalhe) from None
    return FileResponse(audio, media_type="audio/wav")


@router.get("/palavras", response_model=TemposPalavras)
async def tempos_das_palavras(
    video_id: str = VideoId,
    inicio: float = Query(ge=0),
    fim: float = Query(gt=0),
    texto: str = Query(min_length=1, max_length=1000),
):
    """Tempo de cada palavra da frase, para o modo karaokê."""
    _validar_trecho(inicio, fim)
    return await karaoke.tempos_das_palavras(video_id, inicio, fim, texto)
