"""Tudo o que conversa com o YouTube: legendas, título, download do vídeo e legenda automática com tempos."""
import json
import logging
import os
import re
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

import requests
import yt_dlp
from youtube_transcript_api import CouldNotRetrieveTranscript, YouTubeTranscriptApi

logger = logging.getLogger("uvicorn.error")

TITULO_PADRAO = "Vídeo do YouTube"
PADRAO_ID_NA_URL = re.compile(r"(?:v=|/|be/)([0-9A-Za-z_-]{11})")

# VP9 + Opus (WebM) toca em qualquer Chrome/Edge; MP4 é a alternativa. 480p basta e baixa rápido.
FORMATO_VIDEO = (
    "bv*[height<=480][vcodec^=vp09]+ba[acodec=opus]"
    "/bv*[height<=480][ext=mp4]+ba[ext=m4a]"
    "/18/b[height<=480]/b"
)

# Sessão HTTP reaproveitada entre requisições (mantém os cookies do YouTube).
http_session = requests.Session()

# Re-exportada para quem trata "vídeo sem legenda" não precisar conhecer a biblioteca.
SemLegenda = CouldNotRetrieveTranscript


def url_do_video(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def extrair_video_id(url: str) -> str | None:
    encontrado = PADRAO_ID_NA_URL.search(url)
    return encontrado.group(1) if encontrado else None


def buscar_titulo(video_id: str) -> str:
    """Título pela URL oEmbed do YouTube (metadados públicos em JSON)."""
    try:
        resposta = http_session.get(
            "https://www.youtube.com/oembed",
            params={"url": url_do_video(video_id), "format": "json"},
            timeout=10,
        )
        if resposta.status_code == 200:
            return resposta.json().get("title", TITULO_PADRAO)
        logger.warning("oEmbed respondeu %s para o vídeo %s", resposta.status_code, video_id)
    except (requests.RequestException, ValueError):
        logger.exception("Erro ao buscar o título do vídeo %s", video_id)
    return TITULO_PADRAO


def baixar_legendas(video_id: str) -> tuple[list[dict], bool]:
    """(blocos brutos, legenda_manual). Prefere a legenda manual em inglês; senão, a automática.

    Lança SemLegenda se não houver nenhuma.
    """
    lista = YouTubeTranscriptApi(http_client=http_session).list(video_id)
    try:
        transcricao, manual = lista.find_manually_created_transcript(["en"]), True
    except CouldNotRetrieveTranscript:
        transcricao, manual = lista.find_generated_transcript(["en"]), False
    blocos = [{"text": b.text, "start": b.start, "duration": b.duration} for b in transcricao.fetch()]
    return blocos, manual


# --- yt-dlp ---

def _caminho_deno() -> str | None:
    """O YouTube exige um runtime JavaScript (Deno) para o yt-dlp. Procura no PATH e ao lado do Python da venv."""
    return shutil.which("deno") or shutil.which("deno", path=os.path.dirname(sys.executable))


def _opcoes_ytdlp(**extras) -> dict:
    opcoes = {"quiet": True, "noplaylist": True, **extras}
    deno = _caminho_deno()
    if deno:
        opcoes["js_runtimes"] = {"deno": {"path": deno}}
    return opcoes


def baixar_video(video_id: str, pasta: Path, ao_progredir: Callable[[float], None]) -> None:
    """Baixa o vídeo para pasta/{video_id}.{webm|mp4}, avisando o progresso (0 a 1)."""
    # Vídeo e áudio vêm em dois arquivos; o progresso soma os dois.
    partes: dict[str, tuple[int, int]] = {}

    def gancho(estado):
        total = estado.get("total_bytes") or estado.get("total_bytes_estimate")
        if not total:
            return
        partes[estado.get("filename", "")] = (estado.get("downloaded_bytes", 0), total)
        baixado = sum(b for b, _ in partes.values())
        esperado = sum(t for _, t in partes.values())
        # Sem saber o tamanho da segunda parte, a primeira conta como metade.
        fator = 1 if len(partes) > 1 else 0.5
        ao_progredir(min(0.99, baixado / esperado * fator))

    opcoes = _opcoes_ytdlp(
        format=FORMATO_VIDEO,
        merge_output_format="webm/mp4",
        outtmpl=str(pasta / f"{video_id}.%(ext)s"),
        progress_hooks=[gancho],
    )
    with yt_dlp.YoutubeDL(opcoes) as ydl:
        ydl.download([url_do_video(video_id)])


def baixar_legenda_automatica_json3(video_id: str) -> dict | None:
    """Legenda automática em json3 (traz o início de cada palavra), ou None se o vídeo não tiver."""
    with yt_dlp.YoutubeDL(_opcoes_ytdlp(skip_download=True)) as ydl:
        info = ydl.extract_info(url_do_video(video_id), download=False)
        automaticas = info.get("automatic_captions") or {}
        # "en-orig" é o reconhecimento de fala original; "en" pode ser uma tradução automática.
        formatos = automaticas.get("en-orig") or automaticas.get("en") or []
        url = next((f["url"] for f in formatos if f.get("ext") == "json3"), None)
        return json.loads(ydl.urlopen(url).read()) if url else None
