"""Rota da avaliação da fala do usuário (a lógica está em app/services/avaliacao.py)."""
import logging
import subprocess

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app import config
from app.schemas import ResultadoAvaliacao
from app.services import avaliacao, midia

logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/api", tags=["avaliação"])

TAMANHO_MAXIMO_GRAVACAO = 10 * 1024 * 1024  # bytes


@router.post("/avaliacoes", response_model=ResultadoAvaliacao)
async def avaliar_fala(
    gravacao: UploadFile = File(description="Áudio gravado pelo navegador (WebM/Opus)"),
    video_id: str = Form(pattern=config.PADRAO_VIDEO_ID),
    inicio: float = Form(ge=0),
    fim: float = Form(gt=0),
    texto: str = Form(min_length=1, max_length=1000),
    transcricao: str = Form(default="", max_length=2000),
    offset: float = Form(default=0, ge=0, description="Segundos da gravação antes de a fala começar"),
    duracao: float = Form(gt=0, le=config.DURACAO_MAXIMA_TRECHO, description="Duração da fala, em segundos"),
    velocidade: float = Form(default=1, gt=0, le=2, description="Velocidade em que o vídeo estava tocando"),
):
    if fim <= inicio or fim - inicio > config.DURACAO_MAXIMA_TRECHO:
        raise HTTPException(status_code=400, detail="Intervalo inválido.")
    dados = await gravacao.read(TAMANHO_MAXIMO_GRAVACAO + 1)
    if len(dados) > TAMANHO_MAXIMO_GRAVACAO:
        raise HTTPException(status_code=413, detail="Gravação grande demais.")

    try:
        return await avaliacao.avaliar_gravacao(
            video_id, inicio, fim, texto, transcricao, dados, offset, duracao, velocidade,
        )
    except midia.VideoIndisponivel:
        raise HTTPException(status_code=502, detail="Não foi possível baixar o vídeo do YouTube.") from None
    except subprocess.CalledProcessError:
        logger.exception("Erro ao converter a gravação do usuário")
        raise HTTPException(status_code=400, detail="Não foi possível ler a gravação enviada.") from None
