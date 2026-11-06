"""Rotas de conta (cadastro, login, logout, /me) e a dependência usuario_atual, que protege as outras rotas.

Uso numa rota protegida:  def rota(usuario: Usuario = Depends(usuario_atual)): ...
Sem sessão válida, a rota nem chega a rodar: a resposta é 401.
"""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import APIKeyCookie
from sqlmodel import Session

from app import config
from app.db import get_session
from app.models import Usuario
from app.schemas import Credenciais, NovoUsuario, UsuarioPublico
from app.services import auth

router = APIRouter(prefix="/api/auth", tags=["autenticação"])

# Lê o cookie de sessão (e documenta a autenticação no /docs). auto_error=False: quem decide o erro somos nós.
cookie_sessao = APIKeyCookie(name=config.COOKIE_SESSAO, auto_error=False)


def _opcoes_do_cookie() -> dict:
    # HttpOnly: o JavaScript da página não lê o token (um XSS não o rouba).
    # SameSite=Lax: o navegador não manda o cookie em POSTs vindos de outros sites (defesa contra CSRF).
    # Secure (produção): o cookie só trafega por HTTPS.
    return {"httponly": True, "samesite": "lax", "secure": config.AMBIENTE == "producao", "path": "/"}


def _gravar_cookie(resposta: Response, token: str) -> None:
    resposta.set_cookie(
        config.COOKIE_SESSAO, token, max_age=config.DURACAO_SESSAO_DIAS * 24 * 60 * 60, **_opcoes_do_cookie(),
    )


def usuario_atual(token: str | None = Depends(cookie_sessao), session: Session = Depends(get_session)) -> Usuario:
    """Dependência: o usuário dono da sessão do cookie. Sem sessão válida, responde 401."""
    usuario = auth.usuario_da_sessao(session, token) if token else None
    if usuario is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Faça login para continuar.")
    return usuario


@router.post("/cadastro", response_model=UsuarioPublico, status_code=status.HTTP_201_CREATED)
def cadastrar(corpo: NovoUsuario, resposta: Response, session: Session = Depends(get_session)):
    """Cria a conta e já entra nela."""
    try:
        usuario = auth.cadastrar(session, corpo.email, corpo.senha)
    except auth.EmailJaCadastrado:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Este e-mail já está cadastrado.") from None
    _gravar_cookie(resposta, auth.criar_sessao(session, usuario))
    return usuario


@router.post("/login", response_model=UsuarioPublico)
def entrar(corpo: Credenciais, resposta: Response, session: Session = Depends(get_session)):
    usuario = auth.autenticar(session, corpo.email, corpo.senha)
    if usuario is None:
        # Mesma mensagem para e-mail inexistente e senha errada: não revela quais e-mails têm conta.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="E-mail ou senha incorretos.")
    _gravar_cookie(resposta, auth.criar_sessao(session, usuario))
    return usuario


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def sair(token: str | None = Depends(cookie_sessao), session: Session = Depends(get_session)):
    """Encerra a sessão no servidor e apaga o cookie. Sem sessão, não faz nada (e não é erro)."""
    if token:
        auth.encerrar_sessao(session, token)
    resposta = Response(status_code=status.HTTP_204_NO_CONTENT)
    resposta.delete_cookie(config.COOKIE_SESSAO, **_opcoes_do_cookie())
    return resposta


@router.get("/me", response_model=UsuarioPublico)
def quem_sou_eu(usuario: Usuario = Depends(usuario_atual)):
    return usuario
