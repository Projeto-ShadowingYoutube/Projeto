"""Bloco R1: modelos do Reading Challenge e a migração 0101.

Confere o que o banco garante sozinho (unicidade, JSON, valores padrão) e que a migração cria e remove as tabelas
com todas as FKs e UNIQUEs nomeadas. A equivalência modelos x migrações fica no tests/test_migracoes.py.
"""
import subprocess
import sys
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app import migrar
from app.models import Usuario
from app.models_reading import ReadingAttempt, ReadingChallenge, ReadingQuestion, ReadingText

TABELAS_READING = {"readingtext", "readingchallenge", "readingquestion", "readingattempt"}

FKS_ESPERADAS = {
    "readingchallenge": {"fk_readingchallenge_usuario_id_usuario", "fk_readingchallenge_texto_id_readingtext"},
    "readingquestion": {"fk_readingquestion_desafio_id_readingchallenge"},
    "readingattempt": {"fk_readingattempt_usuario_id_usuario", "fk_readingattempt_desafio_id_readingchallenge"},
}
UNIQUES_ESPERADOS = {
    "readingtext": {"uq_readingtext_fonte_origem"},
    "readingquestion": {"uq_readingquestion_desafio_ordem"},
    "readingattempt": {"uq_readingattempt_desafio"},
}


# --- Auxiliares: um usuário, um texto e um desafio mínimos ---

def _usuario(session: Session, email: str = "ana@exemplo.com") -> Usuario:
    usuario = Usuario(email=email, senha_hash="hash-qualquer")
    session.add(usuario)
    session.commit()
    session.refresh(usuario)
    return usuario


def _texto(session: Session, id_origem: str = "123", **extras) -> ReadingText:
    texto = ReadingText(fonte="wikipedia", id_origem=id_origem, titulo="Honey bee", conteudo="Bees make honey.",
                        palavras=3, **extras)
    session.add(texto)
    session.commit()
    session.refresh(texto)
    return texto


def _desafio(session: Session) -> ReadingChallenge:
    usuario = _usuario(session)
    texto = _texto(session)
    desafio = ReadingChallenge(usuario_id=usuario.id, texto_id=texto.id, modalidade="multipla_escolha", ppm=200,
                               limite_segundos=60)
    session.add(desafio)
    session.commit()
    session.refresh(desafio)
    return desafio


def _pergunta(desafio_id: int, ordem: int = 1) -> ReadingQuestion:
    return ReadingQuestion(desafio_id=desafio_id, ordem=ordem, tipo="multipla_escolha", enunciado="What do bees make?",
                           alternativas=["Honey", "Milk", "Wax paper", "Silk"], resposta_correta="Honey",
                           justificativa="Bees make honey.")


def _tentativa(usuario_id: int, desafio_id: int) -> ReadingAttempt:
    return ReadingAttempt(usuario_id=usuario_id, desafio_id=desafio_id, modalidade="multipla_escolha",
                          respostas=["Honey"] * 5, tempo_leitura_segundos=40, tempo_resposta_segundos=90)


# --- Modelos ---

def test_importar_app_models_registra_as_tabelas_do_reading():
    """O Alembic (migrations/env.py) importa só app.models: sem o import no ponto de encaixe, ele não enxergaria as
    tabelas. Roda num processo novo, porque aqui este arquivo já importou app.models_reading e mascararia a falta."""
    codigo = ("import app.models; from sqlmodel import SQLModel; "
              "print(','.join(sorted(t for t in SQLModel.metadata.tables if t.startswith('reading'))))")
    saida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, check=True,
                           cwd=Path(__file__).resolve().parents[2])
    assert set(saida.stdout.strip().split(",")) == TABELAS_READING


def test_grava_e_le_todos_os_modelos_com_json(engine_teste):
    perguntas_reserva = [{"enunciado": "Q?", "alternativas": ["a", "b", "c", "d"], "resposta_correta": "a"}]
    with Session(engine_teste) as session:
        desafio = _desafio(session)
        _texto(session, id_origem="reserva-1", perguntas_reserva=perguntas_reserva)
        session.add(_pergunta(desafio.id))
        tentativa = _tentativa(desafio.usuario_id, desafio.id)
        tentativa.avaliacao = [{"ordem": 1, "correta": True, "comentario": "Isso."}]
        session.add(tentativa)
        session.commit()
        ids = desafio.id, desafio.usuario_id

    with Session(engine_teste) as session:  # sessão nova: lê do banco, não da memória
        pergunta = session.exec(select(ReadingQuestion)).one()
        assert pergunta.alternativas == ["Honey", "Milk", "Wax paper", "Silk"]
        tentativa = session.exec(select(ReadingAttempt)).one()
        assert (tentativa.desafio_id, tentativa.usuario_id) == ids
        assert tentativa.respostas == ["Honey"] * 5
        assert tentativa.avaliacao == [{"ordem": 1, "correta": True, "comentario": "Isso."}]
        reserva = session.exec(select(ReadingText).where(ReadingText.id_origem == "reserva-1")).one()
        assert reserva.perguntas_reserva == perguntas_reserva


def test_valores_padrao(engine_teste):
    with Session(engine_teste) as session:
        desafio = _desafio(session)
        session.add(ReadingQuestion(desafio_id=desafio.id, ordem=5, tipo="aberta", enunciado="Why?",
                                    resposta_correta="Because.", justificativa="..."))
        session.add(_tentativa(desafio.usuario_id, desafio.id))
        session.commit()

        assert desafio.estado == "lendo"
        assert desafio.usou_reserva is False
        assert desafio.iniciado_em is not None
        assert desafio.leitura_encerrada_em is None
        assert session.exec(select(ReadingText)).one().perguntas_reserva is None
        assert session.exec(select(ReadingQuestion)).one().alternativas == []  # pergunta aberta: sem alternativas
        tentativa = session.exec(select(ReadingAttempt)).one()
        assert tentativa.avaliacao == [] and tentativa.nota is None and tentativa.avaliado_em is None


def test_texto_sem_perguntas_de_reserva_grava_null_do_sql(engine_teste):
    """O filtro "é texto de reserva?" usa IS NULL: o None não pode virar o texto JSON 'null'."""
    with Session(engine_teste) as session:
        _texto(session, id_origem="comum")
        _texto(session, id_origem="reserva", perguntas_reserva=[{"enunciado": "Q?"}])
        comuns = session.exec(select(ReadingText).where(ReadingText.perguntas_reserva.is_(None))).all()
        assert [t.id_origem for t in comuns] == ["comum"]


def test_o_mesmo_artigo_nao_e_gravado_duas_vezes(engine_teste):
    with Session(engine_teste) as session:
        _texto(session, id_origem="123")
        with pytest.raises(IntegrityError):
            _texto(session, id_origem="123")


def test_textos_diferentes_da_mesma_fonte_convivem(engine_teste):
    with Session(engine_teste) as session:
        _texto(session, id_origem="123")
        _texto(session, id_origem="456")
        assert len(session.exec(select(ReadingText)).all()) == 2


def test_um_desafio_nao_tem_duas_perguntas_na_mesma_ordem(engine_teste):
    with Session(engine_teste) as session:
        desafio = _desafio(session)
        session.add(_pergunta(desafio.id, ordem=1))
        session.commit()
        session.add(_pergunta(desafio.id, ordem=1))
        with pytest.raises(IntegrityError):
            session.commit()


def test_um_desafio_tem_cinco_perguntas_em_ordens_diferentes(engine_teste):
    with Session(engine_teste) as session:
        desafio = _desafio(session)
        session.add_all(_pergunta(desafio.id, ordem) for ordem in range(1, 6))
        session.commit()
        assert len(session.exec(select(ReadingQuestion).where(ReadingQuestion.desafio_id == desafio.id)).all()) == 5


def test_um_desafio_aceita_no_maximo_uma_tentativa(engine_teste):
    """Garantido pelo banco: nem duas requisições simultâneas conseguem enviar respostas duas vezes."""
    with Session(engine_teste) as session:
        desafio = _desafio(session)
        session.add(_tentativa(desafio.usuario_id, desafio.id))
        session.commit()
        session.add(_tentativa(desafio.usuario_id, desafio.id))
        with pytest.raises(IntegrityError):
            session.commit()


# --- Migração 0101 ---

def _esquema_reading(url: str) -> dict:
    """{tabela: (nomes das FKs, nomes dos UNIQUEs)} das tabelas do Reading existentes no banco."""
    engine = create_engine(url)
    try:
        inspetor = inspect(engine)
        return {
            tabela: ({fk["name"] for fk in inspetor.get_foreign_keys(tabela)},
                     {uq["name"] for uq in inspetor.get_unique_constraints(tabela)})
            for tabela in set(inspetor.get_table_names()) & TABELAS_READING
        }
    finally:
        engine.dispose()


def test_migracao_cria_as_tabelas_com_restricoes_nomeadas(tmp_path):
    url = f"sqlite:///{tmp_path / 'estudos.db'}"
    migrar.migrar(url, tmp_path / "backup")

    esquema = _esquema_reading(url)
    assert set(esquema) == TABELAS_READING
    for tabela in TABELAS_READING:
        fks, uniques = esquema[tabela]
        assert fks == FKS_ESPERADAS.get(tabela, set()), tabela
        assert uniques == UNIQUES_ESPERADOS.get(tabela, set()), tabela


def test_migracao_desfaz_e_refaz(tmp_path):
    """Downgrade para a 0006 remove só as tabelas do Reading; o upgrade volta a criá-las."""
    url = f"sqlite:///{tmp_path / 'estudos.db'}"
    migrar.migrar(url, tmp_path / "backup")
    cfg = migrar.config_alembic(url)

    command.downgrade(cfg, "0006")
    assert _esquema_reading(url) == {}
    engine = create_engine(url)
    assert "usuario" in inspect(engine).get_table_names()  # a base continua lá
    engine.dispose()

    command.upgrade(cfg, "head")
    assert set(_esquema_reading(url)) == TABELAS_READING
