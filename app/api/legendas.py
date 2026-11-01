"""Rotas das legendas e do limite de tokens por usuário."""
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter

from app import config
from app.schemas import Legendas
from app.services import legendas, youtube

logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/api", tags=["legendas"])

# Cada usuário (IP) pode carregar alguns vídeos novos por janela de tempo; vídeos na cache não gastam token.
LIMITE_TOKENS = parse(config.LIMITE_TOKENS)
limitador = FixedWindowRateLimiter(MemoryStorage())


def _ip(request: Request) -> str:
    return request.client.host if request.client else "desconhecido"


def tokens_restantes(ip: str) -> int:
    return limitador.get_window_stats(LIMITE_TOKENS, ip, "legenda").remaining


@router.get("/tokens")
def obter_tokens(request: Request):
    return {"tokens_restantes": tokens_restantes(_ip(request))}


# Rota "def" (e não "async def") de propósito: as chamadas ao YouTube são bloqueantes,
# então o FastAPI roda essa função numa thread separada, sem travar o servidor.
@router.get("/legendas", response_model=Legendas)
def obter_legendas(request: Request, url: str):
    video_id = youtube.extrair_video_id(url)
    if not video_id:
        raise HTTPException(status_code=400, detail="URL do YouTube inválida.")

    ip = _ip(request)
    dados = legendas.da_cache(video_id)
    if dados is None:
        if not limitador.hit(LIMITE_TOKENS, ip, "legenda"):
            return JSONResponse(
                status_code=429,
                content={"detail": "O limite de tokens foi atingido. Espere alguns minutos para ganhar mais.",
                         "tokens_restantes": 0},
            )
        try:
            dados = legendas.do_youtube(video_id)
        except youtube.SemLegenda:
            detalhe = "O vídeo não possui nenhuma legenda em inglês disponível."
            raise HTTPException(status_code=404, detail=detalhe) from None
        except Exception:
            logger.exception("Erro ao buscar as legendas do vídeo %s", video_id)
            raise HTTPException(status_code=500, detail="Erro ao processar legendas.") from None

    return {
        "video_id": video_id,
        "dados": legendas.frases(dados),
        "tokens_restantes": tokens_restantes(ip),
        "legenda_manual": dados["legenda_manual"],
        "titulo_video": dados["titulo_video"],
        "aviso_legenda": legendas.aviso(dados),
    }
