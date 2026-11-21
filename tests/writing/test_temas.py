"""W2: categorias, sorteio do tema e migração de dados 0302 (temas iniciais)."""
import importlib
from datetime import timedelta

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlmodel import Session

from app import migrar
from app.models import agora
from app.services.writing_temas import CATEGORIAS, sortear_tema

from .conftest import criar_tema

migracao_0302 = importlib.import_module("migrations.versions.0302_writing_temas_iniciais")


# --- Categorias ---

def test_seis_categorias_com_nome_tempo_e_minimo():
    assert len(CATEGORIAS) == 6
    assert CATEGORIAS["ielts_opiniao"].nome == "Opinião"
    assert CATEGORIAS["ielts_discussao"].nome == "Discussão de dois lados"
    for categoria in CATEGORIAS.values():
        assert categoria.nome and categoria.prova
        assert categoria.tempo_limite_segundos > 0 and categoria.palavras_minimas > 0


# --- Sorteio ---

def test_sorteio_respeita_a_categoria(engine_teste, temas):
    with Session(engine_teste) as session:
        for _ in range(20):
            assert sortear_tema(session, "toefl_discussao_academica").id == temas["toefl"].id


def test_tema_inativo_nunca_e_sorteado(engine_teste, temas):
    with Session(engine_teste) as session:
        sorteados = {sortear_tema(session, "ielts_opiniao").id for _ in range(200)}
        sorteados |= {sortear_tema(session).id for _ in range(200)}
    assert temas["inativo"].id not in sorteados


def test_sorteio_varia_entre_os_temas(engine_teste, temas):
    """Com 2 temas ativos na categoria, 200 sorteios trazem os dois (chance de falhar: 1 em 2^199)."""
    with Session(engine_teste) as session:
        sorteados = {sortear_tema(session, "ielts_opiniao").id for _ in range(200)}
    assert sorteados == {temas["opiniao_1"].id, temas["opiniao_2"].id}


def test_surpresa_alcanca_categorias_diferentes(engine_teste, temas):
    with Session(engine_teste) as session:
        categorias = {sortear_tema(session).categoria for _ in range(200)}
    assert categorias == {"ielts_opiniao", "toefl_discussao_academica"}


def test_sem_tema_ativo_devolve_none(engine_teste):
    with Session(engine_teste) as session:
        assert sortear_tema(session) is None
        criar_tema(session, "ielts_vantagens", "Retired topic.", ativo=False)
        assert sortear_tema(session, "ielts_vantagens") is None
        assert sortear_tema(session) is None


def test_categoria_desconhecida_e_recusada(engine_teste):
    with Session(engine_teste) as session, pytest.raises(ValueError, match="categoria desconhecida"):
        sortear_tema(session, "nao_existe")


# --- Migração 0302 (dados) ---

def test_temas_da_0302_batem_com_as_categorias_do_servico():
    """A 0302 tem os dados congelados; este teste garante que ela e writing_temas.CATEGORIAS não divergem."""
    assert set(migracao_0302.TEMAS) == set(CATEGORIAS)
    for categoria, (tempo, minimo) in migracao_0302.FORMATOS.items():
        assert (tempo, minimo) == (CATEGORIAS[categoria].tempo_limite_segundos, CATEGORIAS[categoria].palavras_minimas)
    for enunciados in migracao_0302.TEMAS.values():
        assert len(enunciados) == 4
        assert len(set(enunciados)) == 4


@pytest.fixture()
def banco_0302(tmp_path):
    url = f"sqlite:///{tmp_path / 'estudos.db'}"
    cfg = migrar.config_alembic(url)
    command.upgrade(cfg, "0302")
    engine = create_engine(url)
    yield cfg, engine
    engine.dispose()


def _contar(engine, consulta: str) -> int:
    with engine.connect() as conexao:
        return conexao.execute(text(consulta)).scalar()


def test_0302_insere_24_temas_ativos_4_por_categoria(banco_0302):
    _, engine = banco_0302
    assert _contar(engine, "SELECT COUNT(*) FROM writingprompt WHERE ativo") == 24
    with engine.connect() as conexao:
        consulta = text("SELECT categoria, COUNT(*) FROM writingprompt GROUP BY categoria")
        por_categoria = dict(conexao.execute(consulta).all())  # cada linha se comporta como uma tupla
    assert por_categoria == {categoria: 4 for categoria in CATEGORIAS}


def test_0302_desce_apagando_so_os_seus_temas(banco_0302):
    cfg, engine = banco_0302
    with engine.begin() as conexao:  # um tema criado depois (ex.: por um administrador) não é da 0302
        conexao.execute(text(
            "INSERT INTO writingprompt (categoria, enunciado, tempo_limite_segundos, palavras_minimas, ativo) "
            "VALUES ('ielts_opiniao', 'Tema extra.', 2400, 250, 1)"
        ))

    command.downgrade(cfg, "0301")

    with engine.connect() as conexao:
        assert conexao.execute(text("SELECT enunciado FROM writingprompt")).scalars().all() == ["Tema extra."]


def test_0302_recusa_descer_com_tema_em_uso_sem_apagar_nada(banco_0302):
    cfg, engine = banco_0302
    with engine.begin() as conexao:
        # Datas como texto ISO (o formato que o SQLAlchemy grava): o adaptador automático de datetime do sqlite3
        # está descontinuado desde o Python 3.12.
        conexao.execute(text("INSERT INTO usuario (email, senha_hash, data_criacao) VALUES ('a@x.com', 'h', :d)"),
                        {"d": agora().isoformat(" ")})
        conexao.execute(text(
            "INSERT INTO writingattempt (usuario_id, prompt_id, texto, estado, palavras, iniciada_em, prazo, "
            "avaliacoes_tentadas) VALUES (1, 1, '', 'rascunho', 0, :inicio, :prazo, 0)"
        ), {"inicio": agora().isoformat(" "), "prazo": (agora() + timedelta(minutes=40)).isoformat(" ")})

    with pytest.raises(migrar.BancoIncompativel, match="redação"):
        command.downgrade(cfg, "0301")

    assert _contar(engine, "SELECT COUNT(*) FROM writingprompt") == 24
    assert _contar(engine, "SELECT COUNT(*) FROM writingattempt") == 1
