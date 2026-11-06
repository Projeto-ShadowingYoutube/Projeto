import pytest
from pydantic import ValidationError

from app import config
from app.db import opcoes_de_conexao


def test_sem_configuracao_usa_o_sqlite_local(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    configuracoes = config.Configuracoes(_env_file=None)

    assert configuracoes.database_url == f"sqlite:///{config.ARQUIVO_BANCO}"


def test_variavel_de_ambiente_define_o_banco(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:s@localhost:5432/teste")

    assert config.Configuracoes(_env_file=None).database_url == "postgresql+psycopg://u:s@localhost:5432/teste"


def test_arquivo_env_define_o_banco(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    arquivo = tmp_path / ".env"
    arquivo.write_text("DATABASE_URL=sqlite:///outro.db\n", encoding="utf-8")

    assert config.Configuracoes(_env_file=arquivo).database_url == "sqlite:///outro.db"


def test_variavel_de_ambiente_tem_prioridade_sobre_o_env(tmp_path, monkeypatch):
    arquivo = tmp_path / ".env"
    arquivo.write_text("DATABASE_URL=sqlite:///do_arquivo.db\n", encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///do_ambiente.db")

    assert config.Configuracoes(_env_file=arquivo).database_url == "sqlite:///do_ambiente.db"


def test_opcao_de_thread_so_vale_para_sqlite():
    assert opcoes_de_conexao("sqlite:///qualquer.db") == {"check_same_thread": False}
    assert opcoes_de_conexao("postgresql+psycopg://u:s@localhost/db") == {}


def test_ambiente_padrao_e_desenvolvimento_e_so_aceita_valores_conhecidos(monkeypatch):
    monkeypatch.delenv("AMBIENTE", raising=False)
    assert config.Configuracoes(_env_file=None).ambiente == "desenvolvimento"

    monkeypatch.setenv("AMBIENTE", "producao")
    assert config.Configuracoes(_env_file=None).ambiente == "producao"

    monkeypatch.setenv("AMBIENTE", "prod")  # erro de digitação não pode virar "desenvolvimento" em silêncio
    with pytest.raises(ValidationError):
        config.Configuracoes(_env_file=None)
