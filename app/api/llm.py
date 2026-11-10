"""Regras comuns dos desafios com IA: cota diária por conta e aviso de privacidade (README, seção "LLM").

Base protegida (ver CLAUDE.md): os Membros 1 a 3 usam, não alteram.

- Cota: cada conta pode INICIAR config.LIMITE_DESAFIOS_LLM desafios por dia (hoje 10) em CADA feature (reading,
  writing e speaking têm cotas separadas). Coloque a dependência só na rota que CRIA o desafio:

      @router.post("/challenges", dependencies=[Depends(exigir_cota("reading"))])

  Acabou: 429 com codigo "limite_de_desafios", desafios_restantes, limite, tentar_novamente_em e header Retry-After.
  Mesmo algoritmo dos tokens de legenda (api/legendas.py): janela fixa de 24 h que começa no primeiro desafio,
  em memória (zera ao reiniciar o servidor; exige um único processo, pendência do B16).
- GET /api/llm/situacao: se a IA está configurada, o aviso de privacidade e as cotas, para a interface mostrar.
"""
import math
import time
from typing import Literal, get_args

from fastapi import APIRouter, Depends
from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter

from app import config
from app.api.auth import usuario_atual
from app.erros import ErroDaApi
from app.models import Usuario
from app.schemas import SituacaoLLM
from app.services import llm

router = APIRouter(prefix="/api/llm", tags=["llm"], dependencies=[Depends(usuario_atual)])

Feature = Literal["reading", "writing", "speaking"]
FEATURES: tuple[str, ...] = get_args(Feature)

LIMITE_DESAFIOS = parse(config.LIMITE_DESAFIOS_LLM)
limitador = FixedWindowRateLimiter(MemoryStorage())

AVISO_PRIVACIDADE = (
    "Para gerar e corrigir os desafios, o seu texto (ou a transcrição da sua fala) é enviado a um provedor "
    "externo de inteligência artificial. Não inclua dados pessoais."
)


def _chave(usuario: Usuario) -> str:
    return f"usuario:{usuario.id}"


def situacao_da_cota(usuario: Usuario, feature: str) -> dict:
    """{restantes, limite, renova_em} da conta nesta feature."""
    janela = limitador.get_window_stats(LIMITE_DESAFIOS, _chave(usuario), feature)
    algum_feito = janela.remaining < LIMITE_DESAFIOS.amount
    renova_em = max(1, math.ceil(janela.reset_time - time.time())) if algum_feito else None
    return {"restantes": janela.remaining, "limite": LIMITE_DESAFIOS.amount, "renova_em": renova_em}


def exigir_cota(feature: Feature):
    """Dependência que gasta 1 desafio da cota diária da feature, ou responde 429 se ela acabou."""
    if feature not in FEATURES:
        raise ValueError(f"feature desconhecida: {feature!r} (use uma de {FEATURES})")

    def gastar_um_desafio(usuario: Usuario = Depends(usuario_atual)) -> None:
        if limitador.hit(LIMITE_DESAFIOS, _chave(usuario), feature):
            return
        situacao = situacao_da_cota(usuario, feature)
        espera = situacao["renova_em"] or 1
        horas, resto = divmod(espera, 3600)
        quando = f"{horas} h {resto // 60} min" if horas else f"{max(1, resto // 60)} min"
        raise ErroDaApi(
            429,
            f"Você já fez os {situacao['limite']} desafios de hoje nesta atividade. Novos desafios em {quando}.",
            codigo="limite_de_desafios",
            headers={"Retry-After": str(espera)},
            desafios_restantes=0,
            limite=situacao["limite"],
            tentar_novamente_em=espera,
        )

    return gastar_um_desafio


@router.get("/situacao", response_model=SituacaoLLM)
def obter_situacao(usuario: Usuario = Depends(usuario_atual)):
    return {
        "configurada": llm.configurada(),
        "aviso": AVISO_PRIVACIDADE,
        "cotas": {feature: situacao_da_cota(usuario, feature) for feature in FEATURES},
    }
