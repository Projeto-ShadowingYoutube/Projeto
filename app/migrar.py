"""Atualiza o esquema do banco com segurança. Uso: python -m app.migrar

O esquema do banco é versionado pelo Alembic (pasta migrations/). Este comando:
1. Descobre o estado do banco: novo (vazio), legado (tabelas criadas antes do Alembic, sem versão) ou versionado.
2. Se houver algo a mudar num SQLite com dados, faz um backup antes, na pasta backup/ ao lado do
   arquivo do banco (para o banco padrão: dados/backup/).
3. Banco legado: confere se o esquema é exatamente o do baseline e só o marca como versão 0001
   ("stamp"), sem tocar nos dados. Se o esquema for diferente, para sem alterar nada.
4. Aplica as migrações pendentes ("upgrade head").

O app não migra sozinho ao subir: ele só confere a versão (verificar_banco) e, se o banco estiver
desatualizado, recusa subir e manda rodar este comando.
"""
import logging
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url

from app import config
from app.db import opcoes_de_conexao

ARQUIVO_ALEMBIC = config.RAIZ_PROJETO / "alembic.ini"
REVISAO_BASELINE = "0001"
TABELA_VERSAO = "alembic_version"


class BancoDesatualizado(RuntimeError):
    """O banco não está na versão que o app precisa."""


class BancoIncompativel(RuntimeError):
    """Um banco legado com esquema diferente do baseline: não dá para marcá-lo com segurança."""


def config_alembic(url: str) -> Config:
    cfg = Config(str(ARQUIVO_ALEMBIC))
    # O ConfigParser trata "%" como variável; senhas na URL podem ter "%" (caracteres escapados).
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    # Os logs do Alembic ficam com quem chamou (o main abaixo, o uvicorn ou o pytest).
    cfg.attributes["configurar_logs"] = False
    return cfg


def revisao_mais_recente() -> str:
    return ScriptDirectory.from_config(config_alembic("")).get_current_head()


def _arquivo_sqlite(url: str) -> Path | None:
    """O arquivo do banco, se for SQLite em arquivo; None para outros bancos."""
    endereco = make_url(url)
    if endereco.get_backend_name() != "sqlite" or endereco.database in (None, "", ":memory:"):
        return None
    return Path(endereco.database)


def _estado(url: str) -> tuple[str | None, set[str]]:
    """(revisão gravada no banco ou None, nomes das tabelas)."""
    engine = create_engine(url, connect_args=opcoes_de_conexao(url))
    try:
        with engine.connect() as conexao:
            return MigrationContext.configure(conexao).get_current_revision(), set(inspect(conexao).get_table_names())
    finally:
        engine.dispose()


def _assinatura(url: str) -> dict[str, tuple[frozenset, frozenset]]:
    """Tabelas → (colunas, índices). Basta para reconhecer o esquema do baseline."""
    engine = create_engine(url, connect_args=opcoes_de_conexao(url))
    try:
        inspetor = inspect(engine)
        return {
            tabela: (
                frozenset(coluna["name"] for coluna in inspetor.get_columns(tabela)),
                frozenset(indice["name"] for indice in inspetor.get_indexes(tabela)),
            )
            for tabela in inspetor.get_table_names()
            if tabela != TABELA_VERSAO
        }
    finally:
        engine.dispose()


def _assinatura_do_baseline() -> dict[str, tuple[frozenset, frozenset]]:
    """Cria um SQLite temporário só com o baseline e lê o esquema dele."""
    with tempfile.TemporaryDirectory() as pasta:
        url = f"sqlite:///{Path(pasta) / 'baseline.db'}"
        command.upgrade(config_alembic(url), REVISAO_BASELINE)
        return _assinatura(url)


def fazer_backup(arquivo: Path, pasta: Path) -> Path:
    """Cópia consistente do SQLite (a API de backup do sqlite3 funciona mesmo com o banco aberto)."""
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{arquivo.stem}-{datetime.now():%Y%m%d-%H%M%S-%f}.db"
    origem, copia = sqlite3.connect(arquivo), sqlite3.connect(destino)
    try:
        origem.backup(copia)
    finally:
        origem.close()
        copia.close()
    return destino


def migrar(url: str | None = None, pasta_backup: Path | None = None) -> list[str]:
    """Leva o banco até a versão mais recente. Devolve o que foi feito, em mensagens legíveis."""
    url = url or config.DATABASE_URL
    mais_recente = revisao_mais_recente()

    arquivo = _arquivo_sqlite(url)
    if arquivo:
        arquivo.parent.mkdir(parents=True, exist_ok=True)

    atual, tabelas = _estado(url)
    if atual == mais_recente:
        return [f"O banco já está atualizado (versão {atual}). Nada a fazer."]

    mensagens = []
    tem_dados = bool(tabelas - {TABELA_VERSAO})
    if tem_dados and arquivo:
        mensagens.append(f"Backup criado: {fazer_backup(arquivo, pasta_backup or arquivo.parent / 'backup')}")
    elif tem_dados:
        mensagens.append("Atenção: o backup automático só existe para SQLite. Faça o backup deste banco antes.")

    cfg = config_alembic(url)
    if atual is None and tem_dados:
        esperado, encontrado = _assinatura_do_baseline(), _assinatura(url)
        if encontrado != esperado:
            raise BancoIncompativel(
                "O banco tem tabelas, mas o esquema não é o do baseline; nada foi alterado. "
                f"Esperado: {sorted(esperado)}. Encontrado: {sorted(encontrado)}."
            )
        command.stamp(cfg, REVISAO_BASELINE)
        mensagens.append(f"Banco criado antes do Alembic: marcado como versão {REVISAO_BASELINE} (dados intactos).")

    command.upgrade(cfg, "head")
    mensagens.append(f"Banco na versão {mais_recente}.")
    return mensagens


def verificar_banco(url: str | None = None) -> None:
    """Chamada ao subir o app: falha logo, com a instrução, se o banco não estiver na versão certa."""
    url = url or config.DATABASE_URL
    instrucao = "Rode: python -m app.migrar (veja o README)."
    arquivo = _arquivo_sqlite(url)
    if arquivo and not arquivo.exists():
        raise BancoDesatualizado(f"O banco ainda não foi criado ({arquivo}). {instrucao}")

    atual, _ = _estado(url)
    mais_recente = revisao_mais_recente()
    if atual != mais_recente:
        raise BancoDesatualizado(
            f"O banco está na versão {atual or 'nenhuma (anterior ao Alembic)'}, "
            f"mas o app precisa da versão {mais_recente}. {instrucao}"
        )


def main() -> None:
    # Só avisos e erros do Alembic; o resumo do que foi feito vem das mensagens abaixo.
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    try:
        for mensagem in migrar():
            print(mensagem)
    except BancoIncompativel as erro:
        print(f"ERRO: {erro}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
