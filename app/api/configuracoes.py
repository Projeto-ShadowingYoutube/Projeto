"""Rotas das configurações de estudo do usuário logado (cada um só lê e altera as próprias)."""
from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.auth import usuario_atual
from app.db import get_session
from app.models import Usuario
from app.schemas import AlteracaoConfiguracoes, ConfiguracoesDeEstudo
from app.services import configuracoes

router = APIRouter(prefix="/api", tags=["configurações"], dependencies=[Depends(usuario_atual)])


@router.get("/configuracoes", response_model=ConfiguracoesDeEstudo)
def obter(usuario: Usuario = Depends(usuario_atual), session: Session = Depends(get_session)):
    """As configurações do usuário (os padrões, se ele nunca salvou nada)."""
    return configuracoes.obter(session, usuario.id)


@router.patch("/configuracoes", response_model=ConfiguracoesDeEstudo)
def alterar(
    corpo: AlteracaoConfiguracoes, usuario: Usuario = Depends(usuario_atual), session: Session = Depends(get_session),
):
    """Altera só os campos enviados e devolve todas as configurações."""
    return configuracoes.atualizar(session, usuario.id, corpo.model_dump(exclude_unset=True))
