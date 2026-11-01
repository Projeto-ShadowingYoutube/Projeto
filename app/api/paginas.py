"""Rotas que entregam as páginas HTML.

A navegação é feita pelo HTMX, que pede só o miolo da página (header "HX-Request").
Quando a URL é aberta direto no navegador (F5, link colado), entregamos o base.html,
que então carrega o miolo pela mesma URL.
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app import config

router = APIRouter(default_response_class=HTMLResponse, include_in_schema=False)
templates = Jinja2Templates(directory=config.PASTA_TEMPLATES)


def _renderizar(request: Request, template: str, **contexto):
    eh_navegacao_htmx = "HX-Request" in request.headers and "HX-History-Restore-Request" not in request.headers
    if not eh_navegacao_htmx:
        caminho = request.url.path if request.url.path != "/" else "/inicio"
        if request.url.query:
            caminho += f"?{request.url.query}"
        return templates.TemplateResponse(request, "base.html", {"pagina": caminho})
    return templates.TemplateResponse(request, f"paginas/{template}", contexto)


@router.get("/")
@router.get("/inicio")
def inicio(request: Request):
    return _renderizar(request, "inicio.html")


@router.get("/estudo")
def estudo(request: Request, link: str = ""):
    return _renderizar(request, "estudo.html", link=link)


@router.get("/decks")
def decks(request: Request):
    return _renderizar(request, "decks.html")


@router.get("/decks/{deck_id}/revisao")
def revisao(request: Request, deck_id: int):
    return _renderizar(request, "revisao.html", deck_id=deck_id)
