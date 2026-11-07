"""Rota do dicionário do popup de palavras (a lógica está em app/services/dicionario.py)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.api.auth import usuario_atual
from app.db import get_session
from app.services import dicionario

# Exige login (B13): estas rotas são as mais caras do servidor (YouTube, FFmpeg, Vosk, Wiktionary).
router = APIRouter(prefix="/api", tags=["dicionário"], dependencies=[Depends(usuario_atual)])


# "def" de propósito: as consultas externas e o spaCy são bloqueantes (o FastAPI roda numa thread).
@router.get("/dicionario")
def consultar(
    palavra: str = Query(min_length=1, max_length=60),
    frase: str | None = Query(default=None, max_length=1000),
    indice: int | None = Query(default=None, ge=0),
    session: Session = Depends(get_session),
):
    try:
        verbete = dicionario.buscar(session, palavra, frase, indice)
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from None
    except dicionario.DicionarioIndisponivel:
        raise HTTPException(status_code=502, detail="O dicionário está indisponível no momento.") from None
    if verbete is None:
        raise HTTPException(status_code=404, detail="Palavra não encontrada.")
    return verbete
