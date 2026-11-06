"""Conexão com o banco que guarda os Decks, os Cards e a cache do dicionário.

O endereço vem de config.DATABASE_URL (variável de ambiente ou .env); o padrão é o SQLite em dados/.
As tabelas são criadas e alteradas pelas migrações (python -m app.migrar), não por aqui.
"""
from sqlalchemy.engine import make_url
from sqlmodel import Session, create_engine

from app import config


def opcoes_de_conexao(url: str) -> dict:
    """Opções específicas do driver. O SQLite precisa liberar o uso da conexão em outras threads
    (o FastAPI roda as rotas "def" numa thread); os outros bancos não aceitam essa opção."""
    if make_url(url).get_backend_name() == "sqlite":
        return {"check_same_thread": False}
    return {}


engine = create_engine(config.DATABASE_URL, connect_args=opcoes_de_conexao(config.DATABASE_URL))


def get_session():
    """Dependência do FastAPI: abre uma sessão por requisição e fecha ao final."""
    with Session(engine) as session:
        yield session
