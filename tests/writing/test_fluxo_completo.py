"""W10: teste de integração da sequência completa do Writing, pela API, com a LLM simulada.

criar (gasta 1 da cota) → autosave → recarregar → enviar → correção gravada → Rewrite rodada 1 → rodada 2 → concluído
e, no banco, a prova de que nada foi sobrescrito: o texto original, 1 feedback e uma linha por reescrita.
"""
import copy

import pytest
from sqlmodel import Session, select

from app.models_writing import AVALIADA, WritingAttempt, WritingFeedback, WritingRewrite
from app.services import llm
from app.services.writing_llm import VERSAO_PROMPT, VERSAO_PROMPT_REWRITE

from .conftest import RESPOSTA_LLM
from .test_rewrite import CITACOES, FRASE_1, FRASE_2, FRASE_3, TEXTO

RASCUNHO_PARCIAL = TEXTO[:120]  # um pedaço, como se a pessoa ainda estivesse escrevendo


def _correcao() -> dict:
    resposta = copy.deepcopy(RESPOSTA_LLM)
    resposta["trechos"] = []
    for citacao, categoria, gravidade in CITACOES:
        resposta["trechos"].append({
            "categoria": categoria, "citacao": citacao, "gravidade": gravidade, "explicacao": f"Erro em '{citacao}'.",
            "sugestao": "Corrected.", "instrucao_reescrita": f"Revise '{citacao}'.",
        })
    return resposta


def _veredito(*pares) -> dict:
    return {"avaliacoes": [{"indice": i, "melhorou": m, "nota": 8 if m else 3, "comentario": "ok"} for i, m in pares]}


def _cota(cliente) -> int:
    return cliente.get("/api/llm/situacao").json()["cotas"]["writing"]["restantes"]


@pytest.fixture()
def ana(entrar_como, temas):
    return entrar_como("ana@exemplo.com")


def test_sequencia_completa_do_writing(ana, llm_falsa, engine_teste):
    # 1. Criar o desafio: gasta 1 da cota e abre o rascunho com o prazo do tema.
    cota_inicial = _cota(ana)
    redacao = ana.post("/api/writing/challenges", json={"categoria": "ielts_opiniao"}).json()
    rid = redacao["id"]
    assert redacao["estado"] == "rascunho" and redacao["segundos_restantes"] > 0
    assert _cota(ana) == cota_inicial - 1

    # 2. Autosave de um rascunho parcial, e depois do texto inteiro; recarregar traz o último salvo.
    assert ana.patch(f"/api/writing/attempts/{rid}", json={"texto": RASCUNHO_PARCIAL}).status_code == 200
    salvo = ana.patch(f"/api/writing/attempts/{rid}", json={"texto": TEXTO}).json()
    assert salvo["palavras"] > 50
    assert ana.get(f"/api/writing/attempts/{rid}").json()["texto"] == TEXTO

    # 3. Enviar: o texto é congelado e corrigido (uma chamada à LLM).
    llm_falsa.responder(_correcao())
    enviada = ana.post(f"/api/writing/attempts/{rid}/submissao", json={"texto": TEXTO}).json()
    assert enviada["estado"] == AVALIADA and enviada["feedback"]["nota_geral"] == 7.4
    assert len(enviada["feedback"]["trechos"]) == len(CITACOES)
    assert ana.patch(f"/api/writing/attempts/{rid}", json={"texto": "mudar depois"}).status_code == 409
    assert ana.get("/api/writing/attempts").json()[0]["nota_geral"] == 7.4

    # 4. Rewrite, rodada 1: as 3 frases escolhidas; 1 melhora, 2 não.
    desafio = ana.get(f"/api/writing/attempts/{rid}/rewrite").json()
    assert [p["frase"] for p in desafio["problemas"]] == [FRASE_1, FRASE_2, FRASE_3]
    llm_falsa.responder(_veredito((0, True), (2, False), (3, False)))
    rodada_1 = ana.post(f"/api/writing/attempts/{rid}/rewrite", json={"reescritas": [
        {"indice": 0, "texto": "Many students can't pay the fees, so they give up their dreams."},
        {"indice": 2, "texto": "Firstly, free education give opportunities."},
        {"indice": 3, "texto": "If the government pay, the country will be more develop."},
    ]}).json()
    assert rodada_1["rodada_atual"] == 2 and [p["indice"] for p in rodada_1["problemas"]] == [2, 3]

    # 5. Rodada 2: só as 2 que não melhoraram; depois disso, concluído.
    llm_falsa.responder(_veredito((2, True), (3, False)))
    final = ana.post(f"/api/writing/attempts/{rid}/rewrite", json={"reescritas": [
        {"indice": 2, "texto": "Firstly, free education gives everyone equal opportunities."},
        {"indice": 3, "texto": "If the government pays, the country will be more developed."},
    ]}).json()
    assert final["concluido"] is True and final["problemas"] == []
    assert [(h["rodada"], h["indice"], h["avaliacao"]["melhorou"]) for h in final["historico"]] == [
        (1, 0, True), (1, 2, False), (1, 3, False), (2, 2, True), (2, 3, False),
    ]

    # 6. O histórico original → feedback → reescritas no banco: nada sobrescrito.
    with Session(engine_teste) as session:
        tentativa = session.get(WritingAttempt, rid)
        feedbacks = session.exec(select(WritingFeedback).where(WritingFeedback.attempt_id == rid)).all()
        reescritas = session.exec(select(WritingRewrite).where(WritingRewrite.feedback_id == feedbacks[0].id)).all()
        assert tentativa.texto == TEXTO and tentativa.estado == AVALIADA and tentativa.avaliacoes_tentadas == 1
        assert len(feedbacks) == 1 and feedbacks[0].versao_prompt == VERSAO_PROMPT and feedbacks[0].modelo
        assert len(reescritas) == 5
        assert {r.versao_prompt for r in reescritas} == {VERSAO_PROMPT_REWRITE}
        assert {r.trecho_original for r in reescritas if r.indice_trecho == 3} == {FRASE_3}  # a frase original, sempre

    # 7. Chamadas à LLM: 1 correção + 2 rodadas. A cota só contou a criação.
    assert len(llm_falsa.chamadas) == 3
    assert _cota(ana) == cota_inicial - 1


def test_sequencia_com_falha_na_correcao_e_avaliar_de_novo(ana, llm_falsa, engine_teste):
    """A correção falha (timeout), a redação fica salva, "avaliar de novo" funciona e o Rewrite segue normalmente."""
    rid = ana.post("/api/writing/challenges", json={}).json()["id"]
    llm_falsa.falhar(llm.LLMTempoEsgotado()).responder(_correcao())

    falha = ana.post(f"/api/writing/attempts/{rid}/submissao", json={"texto": TEXTO})
    assert falha.status_code == 504
    assert ana.get(f"/api/writing/attempts/{rid}").json()["estado"] == "erro_avaliacao"
    assert ana.get(f"/api/writing/attempts/{rid}/rewrite").json()["codigo"] == "redacao_nao_avaliada"

    corrigida = ana.post(f"/api/writing/attempts/{rid}/avaliacao").json()
    assert corrigida["estado"] == AVALIADA and corrigida["avaliacoes_restantes"] == 1

    llm_falsa.responder(_veredito((0, True), (2, True), (3, True)))
    desafio = ana.post(f"/api/writing/attempts/{rid}/rewrite", json={"reescritas": [
        {"indice": i, "texto": f"Reescrita {i}."} for i in (0, 2, 3)
    ]}).json()
    assert desafio["concluido"] is True
    with Session(engine_teste) as session:
        assert session.get(WritingAttempt, rid).texto == TEXTO
