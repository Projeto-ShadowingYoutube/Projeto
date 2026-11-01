"""Conexão com o banco SQLite que guarda os Decks, os Cards e a cache do dicionário."""
from sqlmodel import Session, SQLModel, create_engine

from app import config

engine = create_engine(f"sqlite:///{config.ARQUIVO_BANCO}", connect_args={"check_same_thread": False})


def criar_db_e_tabelas():
    """Cria o arquivo do banco e as tabelas, caso ainda não existam."""
    config.ARQUIVO_BANCO.parent.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)


def get_session():
    """Dependência do FastAPI: abre uma sessão por requisição e fecha ao final."""
    with Session(engine) as session:
        yield session
