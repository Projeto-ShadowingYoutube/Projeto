"""Vídeos baixados e o áudio de cada frase.

O vídeo é baixado uma única vez, em segundo plano (a página acompanha o progresso). O áudio de cada
frase é recortado dele com o FFmpeg. Só os vídeos usados mais recentemente ficam guardados.
"""
import asyncio
import logging
import os
import subprocess
import tempfile
from pathlib import Path

from app import config
from app.services import youtube

logger = logging.getLogger("uvicorn.error")

TIPOS_DE_VIDEO = {".webm": "video/webm", ".mp4": "video/mp4", ".mkv": "video/x-matroska"}

# Downloads em andamento: video_id → tarefa. O progresso (0 a 1) é atualizado pela thread do yt-dlp.
_downloads: dict[str, asyncio.Task] = {}
_progresso: dict[str, float] = {}


class VideoIndisponivel(Exception):
    """O vídeo não pôde ser baixado do YouTube."""


def pasta() -> Path:
    # Lida a cada uso (e não guardada numa constante) para os testes poderem trocar a pasta.
    config.PASTA_MIDIA.mkdir(parents=True, exist_ok=True)
    return config.PASTA_MIDIA


def arquivo_do_video(video_id: str) -> Path | None:
    """O vídeo já baixado (a extensão depende do formato escolhido), ou None."""
    for extensao in TIPOS_DE_VIDEO:
        caminho = pasta() / f"{video_id}{extensao}"
        if caminho.exists():
            return caminho
    return None


def tipo_do_video(caminho: Path) -> str:
    return TIPOS_DE_VIDEO[caminho.suffix]


def progresso(video_id: str) -> float:
    return _progresso.get(video_id, 0.0)


def _limpar_antigos() -> None:
    """Apaga os vídeos usados há mais tempo, junto com os arquivos derivados deles (áudios, tempos)."""
    videos = sorted(
        (p for p in pasta().iterdir() if p.suffix in TIPOS_DE_VIDEO),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for antigo in videos[config.MAX_VIDEOS_GUARDADOS:]:
        for arquivo in pasta().glob(f"{antigo.stem}*"):
            arquivo.unlink(missing_ok=True)


async def _executar_download(video_id: str) -> None:
    logger.info("Baixando o vídeo %s...", video_id)
    try:
        await asyncio.to_thread(
            youtube.baixar_video, video_id, pasta(), lambda valor: _progresso.__setitem__(video_id, valor),
        )
        await asyncio.to_thread(_limpar_antigos)
    finally:
        _progresso.pop(video_id, None)


def iniciar_download(video_id: str) -> asyncio.Task:
    """Começa o download e devolve a tarefa. Baixa de novo se ainda não começou, se o anterior falhou, ou se ele
    terminou mas o arquivo não existe mais (a limpeza de _limpar_antigos o apagou). Um download em andamento nunca
    é duplicado."""
    tarefa = _downloads.get(video_id)
    terminou_sem_arquivo = tarefa is not None and tarefa.done() and arquivo_do_video(video_id) is None
    if tarefa is None or (tarefa.done() and tarefa.exception()) or terminou_sem_arquivo:
        _progresso[video_id] = 0.0
        tarefa = asyncio.create_task(_executar_download(video_id))
        _downloads[video_id] = tarefa
    return tarefa


def download_falhou(video_id: str) -> bool:
    tarefa = _downloads.get(video_id)
    return bool(tarefa and tarefa.done() and tarefa.exception())


async def garantir_video(video_id: str) -> Path:
    """Espera o vídeo estar baixado e devolve o arquivo. Lança VideoIndisponivel se não der."""
    caminho = arquivo_do_video(video_id)
    if not caminho:
        try:
            await asyncio.shield(iniciar_download(video_id))
        except Exception as erro:
            logger.exception("Erro ao baixar o vídeo %s", video_id)
            raise VideoIndisponivel from erro
        caminho = arquivo_do_video(video_id)
        if not caminho:
            raise VideoIndisponivel
    caminho.touch()  # marca como usado recentemente (ver _limpar_antigos)
    return caminho


def _ffmpeg(origem: Path, inicio: float, fim: float, *formato_saida: str, saida: str) -> bytes:
    return subprocess.run(
        ["ffmpeg", "-y", "-ss", str(inicio), "-i", str(origem), "-t", str(fim - inicio), "-vn",
         *formato_saida, saida],
        check=True, capture_output=True,
    ).stdout


async def audio_da_frase(video_id: str, inicio: float, fim: float) -> Path:
    """WAV do trecho, gerado uma vez e guardado ao lado do vídeo."""
    destino = pasta() / f"{video_id}_{inicio:.2f}_{fim:.2f}.wav"
    if destino.exists():
        return destino

    video = await garantir_video(video_id)

    def cortar():
        # Escreve num arquivo temporário e só depois renomeia: assim, duas requisições da mesma frase
        # nunca leem um WAV pela metade.
        descritor, temporario = tempfile.mkstemp(suffix=".wav", dir=destino.parent)
        os.close(descritor)
        try:
            _ffmpeg(video, inicio, fim, "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "1", saida=temporario)
            os.replace(temporario, destino)
        finally:
            if os.path.exists(temporario):
                os.remove(temporario)

    await asyncio.to_thread(cortar)
    return destino


def audio_pcm(video: Path, inicio: float, fim: float, taxa: int) -> bytes:
    """O trecho como áudio PCM 16 bits mono (para o reconhecedor de fala)."""
    return _ffmpeg(video, inicio, fim, "-ac", "1", "-ar", str(taxa), "-f", "s16le", saida="-")
