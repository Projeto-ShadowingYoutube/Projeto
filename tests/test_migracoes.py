import os
import sqlite3
import subprocess
import sys

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlmodel import SQLModel

import app.models  # noqa: F401  (registra as tabelas em SQLModel.metadata)
from app import config, migrar
from app.main import app


@pytest.fixture()
def banco(tmp_path):
    """(url, arquivo) de um SQLite temporário que ainda não existe."""
    arquivo = tmp_path / "estudos.db"
    return f"sqlite:///{arquivo}", arquivo


def _criar_banco_legado(url, arquivo, com_decks=False):
    """Um banco como os criados antes do Alembic: tabelas do baseline, com dados, e sem versão.
    Por padrão, só com dados sem dono (cache do dicionário); com_decks=True inclui Decks e Cards antigos."""
    command.upgrade(migrar.config_alembic(url), migrar.REVISAO_BASELINE)
    with sqlite3.connect(arquivo) as conexao:
        conexao.execute("DROP TABLE alembic_version")
        conexao.execute("INSERT INTO entradadicionario VALUES ('hello', '{}', '2026-01-01')")
        if com_decks:
            conexao.execute("INSERT INTO deck (id, nome) VALUES (1, 'Meu deck')")
            conexao.execute(
                "INSERT INTO card (id, texto_legenda, video_id, start_time, end_time, data_criacao,"
                " data_proxima_revisao, revisao, deck_id)"
                " VALUES (1, 'Hello', 'abcdefghijk', 0, 2, '2026-01-01', '2026-01-02', 3, 1)"
            )
    conexao.close()


def _linhas(arquivo, consulta):
    conexao = sqlite3.connect(arquivo)
    try:
        return conexao.execute(consulta).fetchall()
    finally:
        conexao.close()


def test_migracoes_produzem_o_mesmo_esquema_dos_modelos(banco, tmp_path):
    """Se alguém mudar um modelo e esquecer a migração, este teste falha."""
    url, _ = banco
    migrar.migrar(url, tmp_path / "backup")

    engine = create_engine(url)
    with engine.connect() as conexao:
        diferencas = compare_metadata(MigrationContext.configure(conexao), SQLModel.metadata)
    engine.dispose()
    assert diferencas == []


def test_banco_novo_e_criado_sem_backup(banco, tmp_path):
    url, _ = banco

    mensagens = migrar.migrar(url, tmp_path / "backup")

    assert not (tmp_path / "backup").exists()
    assert mensagens[-1] == f"Banco na versão {migrar.revisao_mais_recente()}."
    migrar.verificar_banco(url)  # não lança


def test_banco_legado_e_marcado_sem_perder_dados(banco, tmp_path):
    url, arquivo = banco
    _criar_banco_legado(url, arquivo)

    mensagens = migrar.migrar(url)  # sem pasta: o backup vai para backup/ ao lado do arquivo do banco

    assert any("marcado como versão 0001" in m for m in mensagens)
    assert _linhas(arquivo, "SELECT palavra FROM entradadicionario") == [("hello",)]
    backups = list((tmp_path / "backup").glob("estudos-*.db"))
    assert len(backups) == 1
    assert _linhas(backups[0], "SELECT palavra FROM entradadicionario") == [("hello",)]
    migrar.verificar_banco(url)


def test_banco_legado_com_decks_sem_dono_e_recusado_sem_inventar_dono(banco, tmp_path):
    """Decisão D3: Decks antigos não têm dono, e a migração 0003 não escolhe um. Nada se perde."""
    url, arquivo = banco
    _criar_banco_legado(url, arquivo, com_decks=True)

    with pytest.raises(migrar.BancoIncompativel, match="sem dono"):
        migrar.migrar(url)

    assert _linhas(arquivo, "SELECT id, nome FROM deck") == [(1, "Meu deck")]
    assert _linhas(arquivo, "SELECT texto_legenda, revisao FROM card") == [("Hello", 3)]
    colunas_deck = {coluna for (_, coluna, *_resto) in _linhas(arquivo, "PRAGMA table_info(deck)")}
    assert "usuario_id" not in colunas_deck
    assert len(list((tmp_path / "backup").glob("estudos-*.db"))) == 1
    with pytest.raises(migrar.BancoDesatualizado):
        migrar.verificar_banco(url)  # o app continua recusando subir


def test_banco_legado_com_esquema_diferente_e_recusado_sem_alteracoes(banco, tmp_path):
    url, arquivo = banco
    with sqlite3.connect(arquivo) as conexao:
        conexao.execute("CREATE TABLE deck (id INTEGER PRIMARY KEY, outro TEXT)")
    conexao.close()

    with pytest.raises(migrar.BancoIncompativel):
        migrar.migrar(url, tmp_path / "backup")

    tabelas = {nome for (nome,) in _linhas(arquivo, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert tabelas == {"deck"}


def test_banco_atualizado_nao_faz_nada_nem_backup(banco, tmp_path):
    url, _ = banco
    migrar.migrar(url, tmp_path / "backup")

    mensagens = migrar.migrar(url, tmp_path / "backup")

    assert "Nada a fazer" in mensagens[0]
    assert not (tmp_path / "backup").exists()


def test_verificar_recusa_banco_inexistente_e_banco_legado(banco):
    url, arquivo = banco
    with pytest.raises(migrar.BancoDesatualizado, match="ainda não foi criado"):
        migrar.verificar_banco(url)

    _criar_banco_legado(url, arquivo)
    with pytest.raises(migrar.BancoDesatualizado, match="python -m app.migrar"):
        migrar.verificar_banco(url)


def test_app_nao_sobe_com_banco_desatualizado(banco, monkeypatch):
    url, _ = banco
    monkeypatch.setattr(config, "DATABASE_URL", url)

    with pytest.raises(migrar.BancoDesatualizado), TestClient(app):
        pass


def test_migracoes_no_banco_externo_sobem_descem_e_batem_com_os_modelos(url_banco_externo_teste):
    """Roda no Postgres (TEST_DATABASE_URL). Prova também que o downgrade de cada migração funciona."""
    url = url_banco_externo_teste
    cfg = migrar.config_alembic(url)

    mensagens = migrar.migrar(url)
    assert mensagens[-1] == f"Banco na versão {migrar.revisao_mais_recente()}."
    migrar.verificar_banco(url)
    engine = create_engine(url)
    with engine.connect() as conexao:
        assert compare_metadata(MigrationContext.configure(conexao), SQLModel.metadata) == []

    command.downgrade(cfg, "base")
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}

    command.upgrade(cfg, "head")
    assert {"deck", "card", "entradadicionario"} <= set(inspect(engine).get_table_names())
    engine.dispose()


def test_comando_mostra_erro_de_migracao_sem_traceback(banco):
    """Roda "python -m app.migrar" de verdade: o erro de uma migração deve sair como mensagem, não traceback."""
    url, arquivo = banco
    _criar_banco_legado(url, arquivo, com_decks=True)

    resultado = subprocess.run(
        [sys.executable, "-m", "app.migrar"], cwd=config.RAIZ_PROJETO, capture_output=True, text=True,
        env={**os.environ, "DATABASE_URL": url, "PYTHONIOENCODING": "utf-8"}, encoding="utf-8",
    )

    assert resultado.returncode == 1
    assert resultado.stderr.startswith("ERRO: Existem 1 Deck(s)")
    assert "Traceback" not in resultado.stderr
