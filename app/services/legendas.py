"""Legendas de um vídeo: da cache (sem custo) ou do YouTube, já divididas em frases."""
from types import SimpleNamespace

from app.services import youtube
from app.services.cache_legendas import carregar_da_cache, salvar_na_cache
from app.services.frases import segmentar_frases


def da_cache(video_id: str) -> dict | None:
    """As legendas do vídeo, se ele for o que está na cache."""
    dados = carregar_da_cache(video_id)
    if dados and dados.get("titulo_video", youtube.TITULO_PADRAO) == youtube.TITULO_PADRAO:
        # Caches antigas não guardavam o título.
        dados["titulo_video"] = youtube.buscar_titulo(video_id)
        salvar_na_cache(video_id, dados)
    return dados


def do_youtube(video_id: str) -> dict:
    """Baixa as legendas e guarda na cache. Lança youtube.SemLegenda se o vídeo não tiver legenda em inglês."""
    blocos, manual = youtube.baixar_legendas(video_id)
    dados = {"blocos": blocos, "legenda_manual": manual, "titulo_video": youtube.buscar_titulo(video_id)}
    salvar_na_cache(video_id, dados)
    return dados


def frases(dados: dict) -> list[dict]:
    return segmentar_frases(SimpleNamespace(**bloco) for bloco in dados["blocos"])


def aviso(dados: dict) -> str:
    tipo = "MANUAL" if dados["legenda_manual"] else "AUTOMÁTICA - Erros de transcrição são possíveis nesse caso."
    return f"Tipo de legenda: {tipo} | Título: {dados['titulo_video']}"
