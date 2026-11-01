"""Tempo de cada palavra de uma frase, escolhendo a melhor fonte disponível (ver alinhamento.py).

1. Legenda automática do YouTube (buscada uma vez por vídeo e guardada ao lado dele).
2. Alinhamento do áudio da frase com o Vosk.
3. Nenhuma: a página mantém a estimativa pelo tamanho das palavras (frases.py).
"""
import asyncio
import json
import logging

from app.services import alinhamento, midia, youtube

logger = logging.getLogger("uvicorn.error")

MAX_RESULTADOS_EM_MEMORIA = 500

_cadeados: dict[str, asyncio.Lock] = {}
_resultados: dict[tuple, dict] = {}


async def palavras_da_legenda_automatica(video_id: str) -> list:
    """[(palavra, início, fim)] do vídeo inteiro; lista vazia se ele não tiver legenda automática."""
    arquivo = midia.pasta() / f"{video_id}.palavras.json"
    async with _cadeados.setdefault(video_id, asyncio.Lock()):
        if arquivo.exists():
            return json.loads(arquivo.read_text())
        try:
            dados = await asyncio.to_thread(youtube.baixar_legenda_automatica_json3, video_id)
        except Exception:
            # Falha de rede não é salva: na próxima frase tenta de novo.
            logger.exception("Erro ao buscar a legenda automática do vídeo %s", video_id)
            return []
        palavras = alinhamento.palavras_do_json3(dados) if dados else []
        arquivo.write_text(json.dumps(palavras))
        return palavras


async def _calcular(video_id: str, inicio: float, fim: float, texto: str) -> dict:
    palavras = texto.split()
    tempos, cobertura = alinhamento.tempos_pela_legenda_automatica(
        await palavras_da_legenda_automatica(video_id), palavras, inicio, fim,
    )
    if cobertura >= alinhamento.COBERTURA_MINIMA:
        return {"tempos": tempos, "fonte": "youtube"}

    try:
        video = await midia.garantir_video(video_id)
        tempos, cobertura = await asyncio.to_thread(alinhamento.tempos_pelo_audio, video, palavras, inicio, fim)
    except Exception:
        logger.exception("Erro ao alinhar o áudio do vídeo %s", video_id)
        cobertura = 0
    if cobertura >= alinhamento.COBERTURA_MINIMA:
        return {"tempos": tempos, "fonte": "audio"}

    return {"tempos": None, "fonte": "estimativa"}


async def tempos_das_palavras(video_id: str, inicio: float, fim: float, texto: str) -> dict:
    """{"tempos": [[início, fim], ...] ou None, "fonte": "youtube" | "audio" | "estimativa"}."""
    chave = (video_id, round(inicio, 2), round(fim, 2), texto)
    if chave in _resultados:
        return _resultados[chave]
    resultado = await _calcular(video_id, inicio, fim, texto)
    if resultado["tempos"]:  # a estimativa não é guardada: a falha pode ter sido passageira
        if len(_resultados) >= MAX_RESULTADOS_EM_MEMORIA:
            _resultados.pop(next(iter(_resultados)))
        _resultados[chave] = resultado
    return resultado
