"""Proteção contra CSRF pela verificação do cabeçalho Origin.

CSRF: um site malicioso faz o navegador da vítima enviar um POST para o nosso app; como o navegador anexa os
cookies, o pedido chegaria autenticado. São duas barreiras:
1. O cookie de sessão é SameSite=Lax (api/auth.py): o navegador não o envia em POSTs vindos de outros sites.
2. Este middleware: em métodos que alteram dados, se o navegador informar uma origem (Origin) que não é a do
   próprio app, a requisição é recusada com 403, antes de chegar a qualquer rota.

Requisições sem Origin (curl, scripts, testes) passam: elas não carregam os cookies de uma vítima. Navegadores
modernos sempre enviam Origin em POST/PUT/PATCH/DELETE vindos de outro site.
"""
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse

METODOS_QUE_ALTERAM = {"POST", "PUT", "PATCH", "DELETE"}


def mesma_origem(origem: str, request: Request) -> bool:
    """A origem informada pelo navegador aponta para este mesmo app (mesmo host e porta)?
    "null" (páginas em sandbox, arquivos locais, alguns redirecionamentos) nunca é aceito."""
    if origem == "null":
        return False
    return urlsplit(origem).netloc.lower() == request.headers.get("host", "").lower()


async def verificar_origem(request: Request, call_next):
    origem = request.headers.get("origin")
    if request.method in METODOS_QUE_ALTERAM and origem is not None and not mesma_origem(origem, request):
        return JSONResponse(status_code=403, content={"detail": "Requisição bloqueada: origem não permitida."})
    return await call_next(request)
