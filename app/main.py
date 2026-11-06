"""Ponto de entrada do app: cria o FastAPI e junta as rotas de cada módulo.

Para rodar: uvicorn app.main:app --reload
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import config, migrar
from app.api import avaliacoes, decks, dicionario, legendas, paginas, videos


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Não cria nem altera tabelas: só confere se o banco está na versão das migrações (senão, não sobe).
    migrar.verificar_banco()
    yield


def criar_app() -> FastAPI:
    app = FastAPI(title="Shadowing", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=config.PASTA_STATIC), name="static")
    for modulo in (paginas, legendas, videos, avaliacoes, decks, dicionario):
        app.include_router(modulo.router)
    return app


app = criar_app()
