"""W1: modelos do Writing Challenge e migração 0301 (esquema)."""
from datetime import timedelta

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, select

from app import migrar
from app.models import Usuario, agora
from app.models_writing import (
    ESTADOS,
    RASCUNHO,
    WritingAttempt,
    WritingFeedback,
    WritingPrompt,
    WritingRewrite,
)

TABELAS_WRITING = {"writingprompt", "writingattempt", "writingfeedback", "writingrewrite"}

NOTAS = {
    "gramatica": {"nota": 7, "comentario": "Concordância verbal com alguns deslizes."},
    "vocabulario": {"nota": 8, "comentario": "Vocabulário variado."},
}
TRECHOS = [{
    "categoria": "gramatica", "citacao": "people thinks", "inicio": 10, "fim": 23, "gravidade": 3,
    "explicacao": "Sujeito plural pede verbo sem -s.", "sugestao": "people think",
    "instrucao_reescrita": "Corrija a concordância entre sujeito e verbo.",
}]


@pytest.fixture()
def session(engine_teste):
    with Session(engine_teste) as s:
        yield s


def _salvar(session, objeto):
    session.add(objeto)
    session.commit()
    session.refresh(objeto)
    return objeto


@pytest.fixture()
def tentativa(session):
    usuario = _salvar(session, Usuario(email="ana@exemplo.com", senha_hash="hash"))
    tema = _salvar(session, WritingPrompt(
        categoria="ielts_opiniao", enunciado="Some people think... Do you agree?",
        tempo_limite_segundos=2400, palavras_minimas=250,
    ))
    prazo = agora() + timedelta(minutes=40)
    return _salvar(session, WritingAttempt(usuario_id=usuario.id, prompt_id=tema.id, prazo=prazo))


def _feedback(attempt_id: int) -> WritingFeedback:
    return WritingFeedback(
        attempt_id=attempt_id, notas=NOTAS, nota_geral=7.5, resumo="Bom texto.", trechos=TRECHOS,
        modelo="gemini-flash-latest", versao_prompt=1,
    )


def _rewrite(feedback_id: int, rodada: int = 1, indice: int = 0) -> WritingRewrite:
    return WritingRewrite(
        feedback_id=feedback_id, rodada=rodada, indice_trecho=indice, trecho_original="people thinks",
        instrucao="Corrija a concordância.", reescrita="people think",
        avaliacao={"melhorou": True, "nota": 9, "comentario": "Corrigido."}, modelo="gemini-flash-latest",
        versao_prompt=1,
    )


def test_encaixe_registra_as_tabelas_no_metadata():
    """O import no fim de app/models.py (ponto de encaixe) é o que faz o Alembic e os testes enxergarem as tabelas."""
    assert TABELAS_WRITING <= set(SQLModel.metadata.tables)


def test_tentativa_nasce_como_rascunho_vazio(tentativa):
    assert tentativa.estado == RASCUNHO
    assert tentativa.estado in ESTADOS
    assert tentativa.texto == ""
    assert tentativa.palavras == 0
    assert tentativa.avaliacoes_tentadas == 0
    assert tentativa.salva_em is None and tentativa.enviada_em is None
    assert tentativa.prazo > tentativa.iniciada_em


def test_tema_nasce_ativo(session, tentativa):
    tema = session.get(WritingPrompt, tentativa.prompt_id)
    assert tema.ativo is True


def test_feedback_guarda_notas_e_trechos_em_json(session, tentativa, engine_teste):
    feedback = _salvar(session, _feedback(tentativa.id))

    with Session(engine_teste) as outra:  # lido do banco, não do objeto em memória
        lido = outra.get(WritingFeedback, feedback.id)
        assert lido.notas == NOTAS
        assert lido.trechos == TRECHOS
        assert lido.modelo == "gemini-flash-latest" and lido.versao_prompt == 1
        assert lido.criado_em is not None


def test_banco_recusa_segundo_feedback_para_a_mesma_tentativa(session, tentativa):
    _salvar(session, _feedback(tentativa.id))

    session.add(_feedback(tentativa.id))
    with pytest.raises(IntegrityError):
        session.commit()


def test_banco_recusa_reescrita_repetida_na_mesma_rodada_e_trecho(session, tentativa):
    feedback = _salvar(session, _feedback(tentativa.id))
    _salvar(session, _rewrite(feedback.id, rodada=1, indice=0))

    session.add(_rewrite(feedback.id, rodada=1, indice=0))
    with pytest.raises(IntegrityError):
        session.commit()


def test_reescritas_em_outra_rodada_ou_trecho_viram_linhas_novas(session, tentativa):
    feedback = _salvar(session, _feedback(tentativa.id))
    for rodada, indice in [(1, 0), (1, 1), (2, 0)]:
        _salvar(session, _rewrite(feedback.id, rodada=rodada, indice=indice))

    linhas = session.exec(select(WritingRewrite).where(WritingRewrite.feedback_id == feedback.id)).all()
    assert len(linhas) == 3


def test_migracao_0301_sobe_e_desce_sem_tocar_nas_tabelas_da_base(tmp_path):
    url = f"sqlite:///{tmp_path / 'estudos.db'}"
    cfg = migrar.config_alembic(url)
    engine = create_engine(url)

    command.upgrade(cfg, "0006")
    tabelas_da_base = set(inspect(engine).get_table_names())

    command.upgrade(cfg, "0301")
    inspetor = inspect(engine)
    assert TABELAS_WRITING <= set(inspetor.get_table_names())
    nomes_das_fks = {fk["name"] for tabela in TABELAS_WRITING for fk in inspetor.get_foreign_keys(tabela)}
    assert nomes_das_fks == {
        "fk_writingattempt_usuario_id_usuario", "fk_writingattempt_prompt_id_writingprompt",
        "fk_writingfeedback_attempt_id_writingattempt", "fk_writingrewrite_feedback_id_writingfeedback",
    }

    command.downgrade(cfg, "0006")
    assert set(inspect(engine).get_table_names()) == tabelas_da_base
    engine.dispose()
