"""Ambiente do Alembic: usa a mesma URL e os mesmos modelos do app.

A URL vem de config.DATABASE_URL, a não ser que quem chamou já tenha definido "sqlalchemy.url"
(é assim que app/migrar.py e os testes apontam para um banco específico).
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine
from sqlmodel import SQLModel

import app.models  # noqa: F401  (registra as tabelas em SQLModel.metadata)
from app import config as config_app
from app.db import opcoes_de_conexao

config = context.config
if config.config_file_name and config.attributes.get("configurar_logs", True):
    # disable_existing_loggers=False: não desligar os loggers do app (uvicorn, testes).
    fileConfig(config.config_file_name, disable_existing_loggers=False)

url = config.get_main_option("sqlalchemy.url") or config_app.DATABASE_URL
eh_sqlite = url.startswith("sqlite")


def rodar_migracoes() -> None:
    engine = create_engine(url, connect_args=opcoes_de_conexao(url))
    with engine.connect() as conexao:
        context.configure(
            connection=conexao,
            target_metadata=SQLModel.metadata,
            # O SQLite não altera colunas/restrições: o Alembic recria a tabela ("batch") quando preciso.
            render_as_batch=eh_sqlite,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


rodar_migracoes()
