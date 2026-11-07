"""Rotas das legendas e do limite de tokens de cada usuário (documentado no README, seção "Tokens").

Cada conta pode carregar alguns vídeos NOVOS por janela de tempo (config.LIMITE_TOKENS, hoje 5 a cada 5 minutos).
- Gasta 1 token: buscar as legendas de um vídeo no YouTube (inclusive se o vídeo não tiver legenda: a consulta ao
  YouTube aconteceu, e é ela que o limite protege).
- Não gasta: vídeo que está na cache, URL inválida, revisar Decks, rever frases.
- O limite é da conta (chave "usuario:<id>"), não do IP: pessoas na mesma rede não dividem tokens.
- Algoritmo: janela fixa (FixedWindowRateLimiter, da biblioteca limits). Os tokens da janela voltam todos juntos
  quando ela termina. Fica em memória: zera ao reiniciar o servidor e exige um único processo (pendência no plano).
- Acabou: 429 com codigo "limite_de_tokens", o tempo até a renovação (tentar_novamente_em) e o header Retry-After.
  O limite é só informado, nunca contornado.
"""
import logging
import math
import time

from fastapi import APIRouter, Depends, HTTPException
from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter

from app import config
from app.api.auth import usuario_atual
from app.erros import ErroDaApi
from app.models import Usuario
from app.schemas import Legendas, Tokens
from app.services import legendas, youtube

logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/api", tags=["legendas"], dependencies=[Depends(usuario_atual)])

LIMITE_TOKENS = parse(config.LIMITE_TOKENS)
limitador = FixedWindowRateLimiter(MemoryStorage())
ESPACO = "legenda"


def _chave(usuario: Usuario) -> str:
    return f"usuario:{usuario.id}"


def situacao_dos_tokens(chave: str) -> dict:
    """{tokens_restantes, limite, renova_em}. renova_em: segundos até a janela recomeçar, ou None se nenhum token
    foi gasto (nada a renovar)."""
    janela = limitador.get_window_stats(LIMITE_TOKENS, chave, ESPACO)
    algum_gasto = janela.remaining < LIMITE_TOKENS.amount
    renova_em = max(1, math.ceil(janela.reset_time - time.time())) if algum_gasto else None
    return {"tokens_restantes": janela.remaining, "limite": LIMITE_TOKENS.amount, "renova_em": renova_em}


def tempo_legivel(segundos: int) -> str:
    """252 → "4 min 12 s"; 45 → "45 s"; 120 → "2 min"."""
    minutos, resto = divmod(segundos, 60)
    if not minutos:
        return f"{resto} s"
    return f"{minutos} min {resto} s" if resto else f"{minutos} min"


@router.get("/tokens", response_model=Tokens)
def obter_tokens(usuario: Usuario = Depends(usuario_atual)):
    return situacao_dos_tokens(_chave(usuario))


# Rota "def" (e não "async def") de propósito: as chamadas ao YouTube são bloqueantes,
# então o FastAPI roda essa função numa thread separada, sem travar o servidor.
@router.get("/legendas", response_model=Legendas)
def obter_legendas(url: str, usuario: Usuario = Depends(usuario_atual)):
    video_id = youtube.extrair_video_id(url)
    if not video_id:
        raise HTTPException(status_code=400, detail="URL do YouTube inválida.")

    chave = _chave(usuario)
    dados = legendas.da_cache(video_id)
    if dados is None:
        if not limitador.hit(LIMITE_TOKENS, chave, ESPACO):
            espera = situacao_dos_tokens(chave)["renova_em"] or 1
            raise ErroDaApi(
                429,
                f"Seus tokens acabaram. Novos tokens em {tempo_legivel(espera)}. "
                "Enquanto isso, você pode revisar seus Decks (a revisão não gasta tokens).",
                codigo="limite_de_tokens",
                headers={"Retry-After": str(espera)},  # padrão HTTP: segundos até poder tentar de novo
                tokens_restantes=0, limite=LIMITE_TOKENS.amount, tentar_novamente_em=espera,
            )
        try:
            dados = legendas.do_youtube(video_id)
        except youtube.SemLegenda:
            detalhe = "O vídeo não possui nenhuma legenda em inglês disponível."
            raise HTTPException(status_code=404, detail=detalhe) from None
        except Exception:
            logger.exception("Erro ao buscar as legendas do vídeo %s", video_id)
            raise HTTPException(status_code=500, detail="Erro ao processar legendas.") from None

    situacao = situacao_dos_tokens(chave)
    return {
        "video_id": video_id,
        "dados": legendas.frases(dados),
        "tokens_restantes": situacao["tokens_restantes"],
        "renova_em": situacao["renova_em"],
        "legenda_manual": dados["legenda_manual"],
        "titulo_video": dados["titulo_video"],
        "aviso_legenda": legendas.aviso(dados),
    }
