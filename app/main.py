"""Ponto de entrada do app: cria o FastAPI e junta as rotas de cada módulo.

Para rodar: uvicorn app.main:app --reload
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import config, erros, migrar, seguranca
from app.api import auth, avaliacoes, configuracoes, decks, dicionario, legendas, llm, paginas, videos


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Não cria nem altera tabelas: só confere se o banco está na versão das migrações (senão, não sobe).
    migrar.verificar_banco()
    yield


def _rotas_das_features() -> list:
    """Pontos de encaixe das features novas (ver CLAUDE.md, "Pontos de encaixe").

    Cada membro altera SÓ o próprio bloco, sem mexer nos outros nem nas linhas em branco entre eles: assim o merge
    das três branches não tem conflito. Exemplo (o Membro 1 acrescenta as duas linhas logo abaixo do comentário dele):
        from app.api import reading
        rotas += [reading.router, reading.paginas]
    """
    rotas = []

    # Membro 1 (Reading)

    # Membro 2 (Speaking)

    # Membro 3 (Writing)

    return rotas


def criar_app() -> FastAPI:
    app = FastAPI(title="Shadowing", lifespan=lifespan)
    app.middleware("http")(seguranca.verificar_origem)  # CSRF: recusa POST/PATCH/DELETE vindos de outros sites
    # Por último: o middleware adicionado por último é o mais externo, e assim captura erros inesperados de tudo,
    # inclusive dos middlewares acima. Todo erro da API sai como {"detail", "codigo", ...} (ver app/erros.py).
    erros.registrar(app)
    app.mount("/static", StaticFiles(directory=config.PASTA_STATIC), name="static")
    for modulo in (paginas, auth, configuracoes, legendas, videos, avaliacoes, decks, dicionario, llm):
        app.include_router(modulo.router)
    for rota in _rotas_das_features():
        app.include_router(rota)
    return app


app = criar_app()
