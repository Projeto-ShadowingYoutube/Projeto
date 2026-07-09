import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine


@pytest.fixture()
def main_module(monkeypatch, tmp_path):
    """Importa o main.py e isola o banco para cada teste."""
    Path("static").mkdir(exist_ok=True)
    Path("templates/Partials").mkdir(parents=True, exist_ok=True)

    main = importlib.import_module("main")

    test_db = tmp_path / "test_estudos.db"
    test_engine = create_engine(
        f"sqlite:///{test_db}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(test_engine)
    monkeypatch.setattr(main, "engine", test_engine)

    yield main

    test_engine.dispose()


@pytest.fixture()
def client(main_module):
    """Cliente HTTP de teste do FastAPI usando banco temporário."""
    with TestClient(main_module.app) as c:
        yield c
