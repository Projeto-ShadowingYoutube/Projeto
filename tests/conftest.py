import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlmodel import Session, SQLModel, create_engine

from app import config, db, migrar
from app.main import app

# Com TEST_DATABASE_URL definida (só no terminal, nunca no .env), os testes usam esse banco (ex.: o Postgres do
# docker-compose). Sem ela, cada teste usa um SQLite temporário.
URL_BANCO_TESTE = os.environ.get("TEST_DATABASE_URL")


def _conferir_banco_de_teste(url: str) -> None:
    """Os testes apagam tabelas: recusa qualquer banco que não seja claramente de teste."""
    nome = make_url(url).database or ""
    if not nome.endswith("_teste") or url == config.DATABASE_URL:
        pytest.exit(f"TEST_DATABASE_URL precisa apontar para um banco *_teste (recebido: {nome!r}).", returncode=2)


if URL_BANCO_TESTE:
    _conferir_banco_de_teste(URL_BANCO_TESTE)


def limpar_banco(engine) -> None:
    """Apaga as tabelas dos modelos e a de versão do Alembic, deixando o banco de teste vazio."""
    SQLModel.metadata.drop_all(engine)
    with engine.begin() as conexao:
        conexao.execute(text("DROP TABLE IF EXISTS alembic_version"))


@pytest.fixture(autouse=True)
def dados_isolados(tmp_path, monkeypatch):
    """Nenhum teste encosta na pasta dados/ de verdade (vídeos, cache, modelo de fala)."""
    monkeypatch.setattr(config, "PASTA_MIDIA", tmp_path / "midia")
    monkeypatch.setattr(config, "PASTA_MODELOS", tmp_path / "modelos")
    monkeypatch.setattr(config, "ARQUIVO_CACHE_LEGENDAS", tmp_path / "ultimo_video.json")


@pytest.fixture()
def url_banco_externo_teste():
    """URL do banco de TEST_DATABASE_URL, vazio no início e no fim do teste. Sem a variável, o teste é pulado."""
    if not URL_BANCO_TESTE:
        pytest.skip("defina TEST_DATABASE_URL para rodar os testes no Postgres")
    engine = create_engine(URL_BANCO_TESTE)
    limpar_banco(engine)
    yield URL_BANCO_TESTE
    limpar_banco(engine)
    engine.dispose()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Cliente HTTP de teste usando um banco isolado e vazio para cada teste."""
    url = URL_BANCO_TESTE or f"sqlite:///{tmp_path / 'test_estudos.db'}"
    engine_teste = create_engine(url, connect_args=db.opcoes_de_conexao(url))
    if URL_BANCO_TESTE:
        limpar_banco(engine_teste)  # sobras de um teste interrompido
    # create_all deixa os testes rápidos; tests/test_migracoes.py garante que as migrações
    # produzem exatamente este mesmo esquema.
    SQLModel.metadata.create_all(engine_teste)
    # O lifespan confere a versão do banco real; no teste, ele não deve encostar nele.
    monkeypatch.setattr(migrar, "verificar_banco", lambda: None)

    def get_session_teste():
        with Session(engine_teste) as session:
            yield session

    app.dependency_overrides[db.get_session] = get_session_teste
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    if URL_BANCO_TESTE:
        limpar_banco(engine_teste)
    engine_teste.dispose()
