"""Rotas do Reading Challenge (Membro 1). Rotas finas: as regras ficam em app/services/reading_*.py.

Todas exigem login (dependência no router). Cada usuário só enxerga os próprios desafios: um desafio de outra
conta responde 404, igual a um inexistente (padrão _deck de app/api/decks.py).

A rota que cria o desafio gasta 1 da cota diária (exigir_cota("reading")) e é "def": a busca do texto e a LLM
bloqueiam, e o FastAPI a roda numa thread à parte.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.auth import usuario_atual
from app.api.llm import exigir_cota
from app.db import get_session
from app.erros import ErroDaApi
from app.models import Usuario
from app.models_reading import ReadingChallenge, ReadingText
from app.schemas_reading import DesafioCriado, NovoDesafio, ResumoDesafio
from app.services import reading_desafios as rd
from app.services import reading_fontes as rf

router = APIRouter(prefix="/api/reading", tags=["reading"], dependencies=[Depends(usuario_atual)])


def _desafio(
    desafio_id: int, usuario: Usuario = Depends(usuario_atual), session: Session = Depends(get_session),
) -> ReadingChallenge:
    desafio = session.get(ReadingChallenge, desafio_id)
    if not desafio or desafio.usuario_id != usuario.id:
        raise HTTPException(status_code=404, detail="Desafio não encontrado.")
    return desafio


@router.post("/challenges", response_model=DesafioCriado, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(exigir_cota("reading"))])
def criar_desafio(corpo: NovoDesafio, usuario: Usuario = Depends(usuario_atual),
                  session: Session = Depends(get_session)):
    try:
        desafio, texto = rd.criar_desafio(session, usuario.id, fonte=corpo.fonte, modalidade=corpo.modalidade,
                                          ppm=corpo.ppm)
    except rf.TextoIndisponivel:
        raise ErroDaApi(502, "Não foi possível obter um texto agora. Tente de novo em instantes.",
                        codigo="texto_indisponivel") from None
    return _criado(desafio, texto)


@router.get("/challenges/{desafio_id}", response_model=ResumoDesafio)
def obter_desafio(desafio: ReadingChallenge = Depends(_desafio)):
    return desafio


def _criado(desafio: ReadingChallenge, texto: ReadingText) -> dict:
    return {
        **ResumoDesafio.model_validate(desafio).model_dump(),
        "texto": {"titulo": texto.titulo, "conteudo": texto.conteudo, "palavras": texto.palavras,
                  "fonte": texto.fonte, "url": texto.url, "credito": rf.credito(texto)},
    }
