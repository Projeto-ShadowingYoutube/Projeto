import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app import config, db, migrar
from app.main import app


@pytest.fixture(autouse=True)
def dados_isolados(tmp_path, monkeypatch):
    """Nenhum teste encosta na pasta dados/ de verdade (vídeos, cache, modelo de fala)."""
    monkeypatch.setattr(config, "PASTA_MIDIA", tmp_path / "midia")
    monkeypatch.setattr(config, "PASTA_MODELOS", tmp_path / "modelos")
    monkeypatch.setattr(config, "ARQUIVO_CACHE_LEGENDAS", tmp_path / "ultimo_video.json")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Cliente HTTP de teste usando um banco temporário e isolado para cada teste."""
    engine_teste = create_engine(
        f"sqlite:///{tmp_path / 'test_estudos.db'}",
        connect_args={"check_same_thread": False},
    )
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
    engine_teste.dispose()
