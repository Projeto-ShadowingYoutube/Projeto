"""Cache das legendas do último vídeo carregado.

Se o usuário pedir o mesmo vídeo de novo, as legendas vêm deste arquivo em vez do YouTube
(e nenhum token é gasto).
"""
import logging

from pydantic import BaseModel, ValidationError

from app import config

logger = logging.getLogger("uvicorn.error")


class BlocoBruto(BaseModel):
    """Bloco de legenda como veio do YouTube. A divisão em frases (frases.py) é feita a cada requisição."""
    text: str
    start: float
    duration: float


class LegendasCompletas(BaseModel):
    legenda_manual: bool
    blocos: list[BlocoBruto]
    titulo_video: str = "Vídeo do YouTube"


class UltimoVideo(BaseModel):
    video_id: str
    dados: LegendasCompletas


def salvar_na_cache(video_id: str, dados: dict) -> None:
    """Valida e salva as legendas do vídeo, sobrescrevendo o vídeo anterior."""
    try:
        conteudo = UltimoVideo(video_id=video_id, dados=dados)
        config.ARQUIVO_CACHE_LEGENDAS.parent.mkdir(parents=True, exist_ok=True)
        config.ARQUIVO_CACHE_LEGENDAS.write_text(conteudo.model_dump_json(indent=4), encoding="utf-8")
    except (OSError, ValidationError):
        logger.exception("Erro ao salvar o vídeo %s na cache", video_id)


def carregar_da_cache(video_id: str) -> dict | None:
    """Retorna os dados do vídeo se ele for o que está na cache; senão, None.

    Uma cache ilegível ou num formato antigo também retorna None, e o vídeo é buscado de novo.
    """
    try:
        conteudo = UltimoVideo.model_validate_json(config.ARQUIVO_CACHE_LEGENDAS.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValidationError):
        logger.warning("Cache ilegível ou em formato antigo; ignorando.")
        return None

    if conteudo.video_id != video_id:
        return None
    return conteudo.dados.model_dump()
