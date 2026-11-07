"""Rotas que entregam as páginas HTML.

A navegação é feita pelo HTMX, que pede só o miolo da página (header "HX-Request").
Quando a URL é aberta direto no navegador (F5, link colado), entregamos o base.html,
que então carrega o miolo pela mesma URL.

Todas as páginas exigem login, menos /login e /cadastro. Sem sessão, quem abre uma página vai para
/login?proximo=<página>, e depois de entrar volta para ela.
"""
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app import config
from app.api.auth import usuario_opcional
from app.db import get_session
from app.models import Usuario
from app.services import configuracoes

router = APIRouter(default_response_class=HTMLResponse, include_in_schema=False)
templates = Jinja2Templates(directory=config.PASTA_TEMPLATES)

# Páginas dependem de quem está logado: o navegador não deve guardá-las (nem mostrar uma cópia com
# o botão "voltar" depois do logout).
SEM_CACHE = {"Cache-Control": "no-store"}


def _eh_navegacao_htmx(request: Request) -> bool:
    return "HX-Request" in request.headers and "HX-History-Restore-Request" not in request.headers


def caminho_seguro(proximo: str | None) -> str:
    """Só aceita caminhos deste site ("/decks"); qualquer outra coisa vira "/".
    Sem isso, /login?proximo=https://site-falso levaria o usuário para fora do app depois do login
    (falha conhecida como open redirect). "//site" e "/\\site" também apontam para outros sites."""
    if proximo and proximo.startswith("/") and not proximo.startswith("//") and "\\" not in proximo:
        return proximo
    return "/"


def _redirecionar(request: Request, destino: str) -> Response:
    if "HX-Request" in request.headers:
        # O HTMX não segue um 303 trocando a página inteira; com este header, ele faz a navegação completa.
        return Response(headers={"HX-Redirect": destino, **SEM_CACHE})
    return RedirectResponse(destino, status_code=303, headers=SEM_CACHE)


def _renderizar(request: Request, template: str, usuario: Usuario | None, **contexto):
    if not _eh_navegacao_htmx(request):
        caminho = request.url.path if request.url.path != "/" else "/inicio"
        if request.url.query:
            caminho += f"?{request.url.query}"
        return templates.TemplateResponse(
            request, "base.html", {"pagina": caminho, "usuario": usuario}, headers=SEM_CACHE,
        )
    return templates.TemplateResponse(request, f"paginas/{template}", contexto, headers=SEM_CACHE)


def _pagina_protegida(request: Request, usuario: Usuario | None, template: str, **contexto):
    if usuario is None:
        aqui = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        return _redirecionar(request, f"/login?{urlencode({'proximo': aqui})}")
    return _renderizar(request, template, usuario, **contexto)


def _pagina_de_entrada(request: Request, usuario: Usuario | None, template: str, proximo: str | None):
    destino = caminho_seguro(proximo)
    if usuario is not None:  # já está logado: não faz sentido mostrar o login
        return _redirecionar(request, destino)
    return _renderizar(request, template, usuario, proximo=destino)


@router.get("/")
@router.get("/inicio")
def inicio(request: Request, usuario: Usuario | None = Depends(usuario_opcional)):
    return _pagina_protegida(request, usuario, "inicio.html")


def _preferencias_do_player(session: Session, usuario: Usuario | None) -> dict:
    """Velocidade e volume salvos do usuário, entregues já no HTML: o vídeo começa neles (sem passar por 1x/100%)."""
    if usuario is None:
        return dict(configuracoes.PADROES)
    return configuracoes.obter(session, usuario.id)


@router.get("/estudo")
def estudo(
    request: Request, link: str = "", usuario: Usuario | None = Depends(usuario_opcional),
    session: Session = Depends(get_session),
):
    return _pagina_protegida(request, usuario, "estudo.html", link=link, **_preferencias_do_player(session, usuario))


@router.get("/decks")
def decks(request: Request, usuario: Usuario | None = Depends(usuario_opcional)):
    return _pagina_protegida(request, usuario, "decks.html")


@router.get("/decks/{deck_id}/revisao")
def revisao(
    request: Request, deck_id: int, usuario: Usuario | None = Depends(usuario_opcional),
    session: Session = Depends(get_session),
):
    return _pagina_protegida(
        request, usuario, "revisao.html", deck_id=deck_id, **_preferencias_do_player(session, usuario),
    )


@router.get("/login")
def login(request: Request, proximo: str | None = None, usuario: Usuario | None = Depends(usuario_opcional)):
    return _pagina_de_entrada(request, usuario, "login.html", proximo)


@router.get("/cadastro")
def cadastro(request: Request, proximo: str | None = None, usuario: Usuario | None = Depends(usuario_opcional)):
    return _pagina_de_entrada(request, usuario, "cadastro.html", proximo)
