"""W6: avaliação na API — o envio grava o texto e corrige; falhas da LLM; "avaliar de novo"; tamanhos e tipos."""
import copy
from datetime import timedelta

import pytest
from sqlmodel import Session, select

from app.models import agora
from app.models_writing import AVALIADA, ENVIADA, ERRO_AVALIACAO, WritingAttempt, WritingFeedback
from app.services import llm
from app.services.writing_avaliacao import MAX_AVALIACOES
from app.services.writing_texto import contar_palavras

from .conftest import RESPOSTA_LLM

TEXTO = (
    "Some people thinks that technology makes our lives better. In my opinion, it have many advantages, "
    "but there are also some risks that we must consider carefully before we decide. "
    "For example, people thinks faster with computers, and they can communicate with friends everywhere. "
    "This is an important question for everyone today."
)
assert contar_palavras(TEXTO) >= 50  # o mínimo para enviar (D3); conferido pela regra do servidor, não de cabeça


def _resposta(*citacoes: str) -> dict:
    resposta = copy.deepcopy(RESPOSTA_LLM)
    resposta["trechos"] = [{
        "categoria": "gramatica", "citacao": c, "gravidade": 2, "explicacao": "Concordância.",
        "sugestao": "Corrected.", "instrucao_reescrita": "Revise a concordância.",
    } for c in citacoes]
    return resposta


@pytest.fixture()
def ana(entrar_como, temas):
    return entrar_como("ana@exemplo.com")


@pytest.fixture()
def redacao(ana) -> dict:
    """Uma redação em rascunho da Ana (a criação não chama a LLM)."""
    resposta = ana.post("/api/writing/challenges", json={"categoria": "ielts_opiniao"})
    assert resposta.status_code == 201
    return resposta.json()


def _enviar(cliente, redacao_id: int, texto: str = TEXTO):
    return cliente.post(f"/api/writing/attempts/{redacao_id}/submissao", json={"texto": texto})


def _avaliar(cliente, redacao_id: int):
    return cliente.post(f"/api/writing/attempts/{redacao_id}/avaliacao")


def _no_banco(engine, redacao_id: int) -> tuple[WritingAttempt, list[WritingFeedback]]:
    with Session(engine) as session:
        tentativa = session.get(WritingAttempt, redacao_id)
        feedbacks = session.exec(select(WritingFeedback).where(WritingFeedback.attempt_id == redacao_id)).all()
        session.expunge_all()
        return tentativa, list(feedbacks)


def _cota_writing(cliente) -> int:
    return cliente.get("/api/llm/situacao").json()["cotas"]["writing"]["restantes"]


# --- Envio corrige ---

def test_envio_corrige_e_grava_o_feedback(ana, redacao, llm_falsa, engine_teste):
    llm_falsa.responder(_resposta("people thinks", "it have", "citação que não existe"))

    resposta = _enviar(ana, redacao["id"])

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["estado"] == AVALIADA and corpo["avaliacoes_restantes"] == MAX_AVALIACOES - 1
    feedback = corpo["feedback"]
    assert feedback["nota_geral"] == 7.4 and feedback["notas"]["coerencia"]["nota"] == 8
    assert feedback["resumo"] == "Boa redação." and feedback["versao_prompt"] == 1 and feedback["modelo"]
    assert [t["citacao"] for t in feedback["trechos"]] == ["people thinks", "it have"]  # a inexistente caiu
    for trecho in feedback["trechos"]:
        assert TEXTO[trecho["inicio"]:trecho["fim"]] == trecho["citacao"]
    tentativa, feedbacks = _no_banco(engine_teste, redacao["id"])
    assert tentativa.estado == AVALIADA and tentativa.texto == TEXTO and tentativa.avaliacoes_tentadas == 1
    assert len(feedbacks) == 1 and feedbacks[0].nota_geral == 7.4
    assert len(llm_falsa.chamadas) == 1


def test_redacao_nova_tem_tres_avaliacoes_e_nenhum_feedback(redacao):
    assert redacao["avaliacoes_restantes"] == MAX_AVALIACOES and redacao["feedback"] is None


def test_get_e_lista_mostram_o_resultado(ana, redacao, llm_falsa):
    llm_falsa.responder(_resposta("it have"))
    _enviar(ana, redacao["id"])

    lida = ana.get(f"/api/writing/attempts/{redacao['id']}").json()
    lista = ana.get("/api/writing/attempts").json()

    assert lida["feedback"]["trechos"][0]["citacao"] == "it have"
    assert lista[0]["nota_geral"] == 7.4


def test_lista_sem_avaliacao_tem_nota_nula(ana, redacao):
    assert ana.get("/api/writing/attempts").json()[0]["nota_geral"] is None


# --- Falhas da LLM: a redação nunca se perde ---

@pytest.mark.parametrize("falha, status, codigo, trecho_da_mensagem", [
    (llm.LLMTempoEsgotado(), 504, "llm_tempo_esgotado", "A correção demorou demais."),
    (llm.LLMIndisponivel(), 502, "llm_indisponivel", "indisponível"),
    (llm.LLMIndisponivel("O serviço de IA atingiu o limite de uso. Tente de novo em alguns minutos."), 502,
     "llm_indisponivel", "limite de uso"),
])
def test_falha_da_llm_deixa_erro_avaliacao_com_o_texto_salvo(
    ana, redacao, llm_falsa, engine_teste, falha, status, codigo, trecho_da_mensagem,
):
    llm_falsa.falhar(falha)

    resposta = _enviar(ana, redacao["id"])

    assert resposta.status_code == status
    assert resposta.json()["codigo"] == codigo
    assert trecho_da_mensagem in resposta.json()["detail"]
    assert "A sua redação foi salva" in resposta.json()["detail"]
    tentativa, feedbacks = _no_banco(engine_teste, redacao["id"])
    assert tentativa.estado == ERRO_AVALIACAO and tentativa.texto == TEXTO
    assert tentativa.avaliacoes_tentadas == 1 and feedbacks == []


def test_resposta_invalida_duas_vezes_deixa_erro_avaliacao(ana, redacao, llm_falsa, engine_teste):
    llm_falsa.responder("não é JSON").responder({"categorias": {}})

    resposta = _enviar(ana, redacao["id"])

    assert resposta.status_code == 502 and resposta.json()["codigo"] == "llm_resposta_invalida"
    tentativa, feedbacks = _no_banco(engine_teste, redacao["id"])
    assert tentativa.estado == ERRO_AVALIACAO and feedbacks == [] and tentativa.avaliacoes_tentadas == 1


def test_sem_llm_configurada_nao_gasta_tentativa(ana, redacao, engine_teste):
    """D16. Sem llm_falsa, a fixture automática llm_desligada deixa o servidor sem chave."""
    resposta = _enviar(ana, redacao["id"])

    assert resposta.status_code == 503 and resposta.json()["codigo"] == "llm_nao_configurada"
    assert "A sua redação foi salva" in resposta.json()["detail"]
    tentativa, _ = _no_banco(engine_teste, redacao["id"])
    assert tentativa.estado == ERRO_AVALIACAO and tentativa.texto == TEXTO and tentativa.avaliacoes_tentadas == 0


def test_texto_e_tentativa_ficam_gravados_antes_da_chamada_a_llm(ana, redacao, llm_falsa, engine_teste):
    """Se algo inesperado acontecer DURANTE a chamada, o texto e a tentativa já estão no banco. (O middleware da base,
    app/erros.py, transforma o erro inesperado num 500 genérico, com a stack só no log.)"""
    llm_falsa.falhar(RuntimeError("o servidor caiu no meio da correção"))

    resposta = _enviar(ana, redacao["id"])

    assert resposta.status_code == 500 and resposta.json()["codigo"] == "erro_interno"
    tentativa, feedbacks = _no_banco(engine_teste, redacao["id"])
    assert tentativa.estado == ENVIADA and tentativa.texto == TEXTO
    assert tentativa.avaliacoes_tentadas == 1 and feedbacks == []


# --- Avaliar de novo ---

def test_avaliar_de_novo_depois_da_falha_sem_gastar_cota(ana, redacao, llm_falsa, engine_teste):
    llm_falsa.falhar(llm.LLMTempoEsgotado()).responder(_resposta("it have"))
    _enviar(ana, redacao["id"])
    cota_antes = _cota_writing(ana)

    resposta = _avaliar(ana, redacao["id"])

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["estado"] == AVALIADA and resposta.json()["avaliacoes_restantes"] == 1
    assert resposta.json()["feedback"]["trechos"][0]["citacao"] == "it have"
    assert _cota_writing(ana) == cota_antes
    tentativa, feedbacks = _no_banco(engine_teste, redacao["id"])
    assert tentativa.avaliacoes_tentadas == 2 and len(feedbacks) == 1


def test_redacao_enviada_sem_feedback_pode_ser_avaliada(ana, redacao, llm_falsa, engine_teste):
    """O servidor caiu durante a correção: a redação ficou "enviada" e não deve ficar presa."""
    llm_falsa.falhar(RuntimeError("queda")).responder(RESPOSTA_LLM)
    assert _enviar(ana, redacao["id"]).status_code == 500

    resposta = _avaliar(ana, redacao["id"])

    assert resposta.status_code == 200 and resposta.json()["estado"] == AVALIADA


def test_no_maximo_tres_tentativas_de_avaliacao(ana, redacao, llm_falsa, engine_teste):
    for _ in range(MAX_AVALIACOES):
        llm_falsa.falhar(llm.LLMIndisponivel())
    _enviar(ana, redacao["id"])
    _avaliar(ana, redacao["id"])
    _avaliar(ana, redacao["id"])

    resposta = _avaliar(ana, redacao["id"])

    assert resposta.status_code == 409 and resposta.json()["codigo"] == "limite_de_avaliacoes"
    assert len(llm_falsa.chamadas) == MAX_AVALIACOES  # a 4ª nem chega à LLM
    assert _no_banco(engine_teste, redacao["id"])[0].avaliacoes_tentadas == MAX_AVALIACOES


def test_avaliar_de_novo_recusa_redacao_ja_avaliada(ana, redacao, llm_corrige):
    _enviar(ana, redacao["id"])
    resposta = _avaliar(ana, redacao["id"])
    assert resposta.status_code == 409 and resposta.json()["codigo"] == "redacao_ja_avaliada"


def test_avaliar_de_novo_recusa_rascunho(ana, redacao, llm_corrige):
    resposta = _avaliar(ana, redacao["id"])
    assert resposta.status_code == 409 and resposta.json()["codigo"] == "redacao_nao_enviada"
    assert llm_corrige.chamadas == []


def test_duplo_clique_vira_409_e_nao_duplica_o_feedback(ana, redacao, llm_falsa, engine_teste):
    """Simula a corrida: outra requisição gravou o feedback enquanto esta esperava a LLM (UNIQUE attempt_id)."""
    llm_falsa.falhar(llm.LLMTempoEsgotado()).responder(RESPOSTA_LLM)
    _enviar(ana, redacao["id"])  # fica em erro_avaliacao
    with Session(engine_teste) as session:
        session.add(WritingFeedback(
            attempt_id=redacao["id"], notas={}, nota_geral=5.0, resumo="Da outra requisição.", trechos=[],
            modelo="m", versao_prompt=1,
        ))
        session.commit()

    resposta = _avaliar(ana, redacao["id"])

    assert resposta.status_code == 409 and resposta.json()["codigo"] == "redacao_ja_avaliada"
    _, feedbacks = _no_banco(engine_teste, redacao["id"])
    assert [f.resumo for f in feedbacks] == ["Da outra requisição."]


# --- Isolamento ---

def test_outra_conta_nao_avalia_nem_ve_o_feedback(ana, redacao, entrar_como, llm_corrige):
    _enviar(ana, redacao["id"])
    bruno = entrar_como("bruno@exemplo.com")

    for resposta in (_avaliar(bruno, redacao["id"]), bruno.get(f"/api/writing/attempts/{redacao['id']}")):
        assert resposta.status_code == 404
        assert resposta.json() == {"detail": "Redação não encontrada.", "codigo": "nao_encontrado"}


# --- Tamanhos e tipos de redação (fluxo completo) ---

LONGA = ("Technology changes how people live and work. " * 222).strip()  # ~9990 caracteres
TIPOS = {
    "exatamente 50 palavras": (" ".join(["word"] * 49) + " ending", "ending"),
    "perto do limite de 10.000 caracteres": (LONGA, "how people live"),
    "acentos e emoji": (("Café 😀 é ótimo, naïve façade — people thinks so. " * 7).strip(), "people thinks"),
    "tags HTML e caracteres especiais": (
        ('<script>alert("x")</script> & <b>bold</b> it have many "quotes" and 50% {braces}. ' * 6).strip(),
        "it have",
    ),
}
for _texto, _ in TIPOS.values():
    assert 50 <= contar_palavras(_texto) and len(_texto) <= 10_000  # todos enviáveis (D3), conferido pela regra


@pytest.mark.parametrize("texto, citacao", TIPOS.values(), ids=TIPOS.keys())
def test_tamanhos_e_tipos_de_redacao(ana, redacao, llm_falsa, engine_teste, texto, citacao):
    llm_falsa.responder(_resposta(citacao))

    resposta = _enviar(ana, redacao["id"], texto)

    assert resposta.status_code == 200, resposta.text
    [trecho] = resposta.json()["feedback"]["trechos"]
    assert texto[trecho["inicio"]:trecho["fim"]] == citacao
    assert f"<redacao>\n{texto}\n</redacao>" in llm_falsa.chamadas[0][1]["content"]  # a redação chegou inteira
    assert _no_banco(engine_teste, redacao["id"])[0].texto == texto


def test_envio_depois_do_prazo_corrige_o_ultimo_autosave(ana, redacao, llm_falsa, engine_teste):
    """D2 + W6: o que vai para a LLM é o texto que foi de fato enviado (o último autosave)."""
    ana.patch(f"/api/writing/attempts/{redacao['id']}", json={"texto": TEXTO})
    with Session(engine_teste) as session:
        tentativa = session.get(WritingAttempt, redacao["id"])
        tentativa.prazo = agora() - timedelta(minutes=5)
        session.add(tentativa)
        session.commit()
    llm_falsa.responder(RESPOSTA_LLM)

    resposta = _enviar(ana, redacao["id"], "outro texto que chegou atrasado " * 10)

    assert resposta.status_code == 200 and resposta.json()["usou_ultimo_salvamento"] is True
    assert f"<redacao>\n{TEXTO}\n</redacao>" in llm_falsa.chamadas[0][1]["content"]
