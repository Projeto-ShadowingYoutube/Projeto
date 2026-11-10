"""Serviço compartilhado de LLM (app/services/llm.py), cota diária de desafios e aviso (app/api/llm.py).

Nada sai para a rede: a sessão HTTP do serviço é substituída por um provedor falso que registra cada requisição.
O fim do arquivo mostra o uso da fixture llm_falsa, que é a forma de testar as features (Reading, Writing, Speaking).
"""
import logging
from types import SimpleNamespace

import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter
from pydantic import BaseModel, Field

from app import config, erros
from app.api import llm as rota_llm
from app.erros import ErroDaApi
from app.services import llm

CHAVE = "chave-secreta-123"


class Correcao(BaseModel):
    nota: int = Field(ge=0, le=10)
    comentario: str


class RespostaHTTP:
    def __init__(self, status=200, corpo=None, texto=None):
        self.status_code = status
        self._corpo = corpo
        self.text = texto if texto is not None else str(corpo)

    def json(self):
        if self._corpo is None:
            raise ValueError("sem JSON")
        return self._corpo


def conteudo(texto):
    """Corpo de uma resposta de /chat/completions com `texto` como resposta do modelo."""
    return RespostaHTTP(200, {"choices": [{"message": {"content": texto}}], "usage": {"total_tokens": 42}})


@pytest.fixture()
def provedor(monkeypatch):
    """LLM configurada, com um provedor falso: provedor.respostas (fila) e provedor.pedidos (o que foi enviado)."""
    monkeypatch.setattr(config, "LLM_CHAVE", CHAVE)
    monkeypatch.setattr(config, "LLM_BASE_URL", "https://provedor.exemplo/v1/")
    monkeypatch.setattr(config, "LLM_MODELO", "modelo-x")
    monkeypatch.setattr(config, "LLM_MODO_JSON", True)
    falso = SimpleNamespace(respostas=[], pedidos=[])

    def post(url, json=None, headers=None, timeout=None):
        falso.pedidos.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        proxima = falso.respostas.pop(0)
        if isinstance(proxima, Exception):
            raise proxima
        return proxima

    monkeypatch.setattr(llm._sessao, "post", post)
    return falso


def gerar():
    return llm.gerar_json(sistema="Corrija a redação.", usuario="I has a dog.", modelo=Correcao)


# --- Configuração ---

def test_sem_chave_nao_chama_o_provedor(provedor, monkeypatch):
    monkeypatch.setattr(config, "LLM_CHAVE", "")

    assert llm.configurada() is False
    with pytest.raises(llm.LLMNaoConfigurada):
        gerar()
    assert provedor.pedidos == []


def test_modelo_em_uso(provedor):
    assert llm.modelo_em_uso() == "modelo-x"


# --- Caminho feliz ---

def test_resposta_valida_vira_objeto_validado(provedor):
    provedor.respostas.append(conteudo('{"nota": 7, "comentario": "Use have."}'))

    resultado = gerar()

    assert resultado == Correcao(nota=7, comentario="Use have.")
    pedido = provedor.pedidos[0]
    assert pedido["url"] == "https://provedor.exemplo/v1/chat/completions"
    assert pedido["headers"]["Authorization"] == f"Bearer {CHAVE}"
    assert pedido["json"]["model"] == "modelo-x"
    assert pedido["json"]["response_format"] == {"type": "json_object"}
    assert pedido["timeout"] == (llm.TIMEOUT_CONEXAO, config.LLM_TIMEOUT_SEGUNDOS)
    sistema, usuario = pedido["json"]["messages"]
    assert sistema["role"] == "system" and "Corrija a redação." in sistema["content"]
    assert '"nota"' in sistema["content"]  # o schema vai junto das instruções
    assert usuario == {"role": "user", "content": "I has a dog."}


def test_aceita_bloco_de_codigo_e_texto_em_volta(provedor):
    provedor.respostas.append(conteudo('Claro! ```json\n{"nota": 9, "comentario": "ok"}\n```'))

    assert gerar().nota == 9


def test_modo_json_desligado_nao_envia_response_format(provedor, monkeypatch):
    monkeypatch.setattr(config, "LLM_MODO_JSON", False)
    provedor.respostas.append(conteudo('{"nota": 1, "comentario": "x"}'))

    gerar()

    assert "response_format" not in provedor.pedidos[0]["json"]


# --- Resposta fora do formato: uma nova tentativa ---

def test_resposta_invalida_tem_uma_nova_tentativa_com_os_problemas(provedor):
    provedor.respostas += [conteudo('{"nota": 15}'), conteudo('{"nota": 8, "comentario": "ok"}')]

    assert gerar().nota == 8
    assert len(provedor.pedidos) == 2
    correcao = provedor.pedidos[1]["json"]["messages"]
    assert correcao[-2] == {"role": "assistant", "content": '{"nota": 15}'}
    assert "nota" in correcao[-1]["content"] and "comentario" in correcao[-1]["content"]


def test_duas_respostas_invalidas_viram_erro(provedor):
    provedor.respostas += [conteudo("não sei"), conteudo('{"nota": "dez"}')]

    with pytest.raises(llm.LLMRespostaInvalida):
        gerar()
    assert len(provedor.pedidos) == 2


@pytest.mark.parametrize("resposta", [
    RespostaHTTP(200, {"sem": "choices"}),
    RespostaHTTP(200, None, texto="<html>"),
    RespostaHTTP(200, {"choices": [{"message": {"content": "  "}}]}),
])
def test_resposta_do_provedor_sem_o_formato_da_api(provedor, resposta):
    provedor.respostas.append(resposta)

    with pytest.raises(llm.LLMRespostaInvalida):
        gerar()


# --- Falhas do provedor: sem nova tentativa ---

def test_timeout_vira_tempo_esgotado_sem_repetir(provedor):
    provedor.respostas.append(requests.ReadTimeout())

    with pytest.raises(llm.LLMTempoEsgotado):
        gerar()
    assert len(provedor.pedidos) == 1


def test_falha_de_conexao_vira_indisponivel(provedor):
    provedor.respostas.append(requests.ConnectionError())

    with pytest.raises(llm.LLMIndisponivel):
        gerar()


def test_limite_do_provedor_429(provedor):
    provedor.respostas.append(RespostaHTTP(429, {"error": "quota"}))

    with pytest.raises(llm.LLMIndisponivel, match="limite de uso"):
        gerar()


@pytest.mark.parametrize("status", [400, 401, 403, 500, 503])
def test_outros_erros_do_provedor_viram_indisponivel(provedor, status):
    provedor.respostas.append(RespostaHTTP(status, {"error": "x"}))

    with pytest.raises(llm.LLMIndisponivel):
        gerar()


def test_a_chave_nunca_vai_para_o_log(provedor, caplog):
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    provedor.respostas += [RespostaHTTP(401, {"error": "bad key"}), RespostaHTTP(500, {"error": "x"}),
                           RespostaHTTP(429, {"error": "q"}), requests.ReadTimeout(), requests.ConnectionError(),
                           RespostaHTTP(200, {"sem": "choices"}),
                           conteudo("lixo"), conteudo("lixo"), conteudo('{"nota": 1, "comentario": "x"}')]

    for _ in range(7):
        with pytest.raises(llm.ErroLLM):
            gerar()
    gerar()

    assert caplog.records  # houve registros (senão o teste não provaria nada)
    assert CHAVE not in caplog.text


# --- Erros no formato padrão da API ---

@pytest.mark.parametrize("erro, status, codigo", [
    (llm.LLMNaoConfigurada(), 503, "llm_nao_configurada"),
    (llm.LLMIndisponivel(), 502, "llm_indisponivel"),
    (llm.LLMTempoEsgotado(), 504, "llm_tempo_esgotado"),
    (llm.LLMRespostaInvalida(), 502, "llm_resposta_invalida"),
    (llm.LLMTempoEsgotado("A correção demorou. A sua redação foi salva."), 504, "llm_tempo_esgotado"),
])
def test_erros_da_llm_viram_o_formato_padrao(erro, status, codigo):
    app = FastAPI()
    erros.registrar(app)

    @app.get("/x")
    def rota():
        raise erro

    resposta = TestClient(app).get("/x")

    assert resposta.status_code == status
    assert resposta.json() == {"detail": erro.mensagem, "codigo": codigo}


# --- Cota diária de desafios (app/api/llm.py) ---

@pytest.fixture()
def cota_nova(monkeypatch):
    monkeypatch.setattr(rota_llm, "limitador", FixedWindowRateLimiter(MemoryStorage()))


def test_cota_de_10_desafios_por_dia_por_feature_e_por_conta(cota_nova):
    ana, bruno = SimpleNamespace(id=1), SimpleNamespace(id=2)
    gastar_reading = rota_llm.exigir_cota("reading")

    for _ in range(10):
        gastar_reading(usuario=ana)
    with pytest.raises(ErroDaApi) as excecao:
        gastar_reading(usuario=ana)

    erro = excecao.value
    assert erro.status_code == 429 and erro.codigo == "limite_de_desafios"
    assert erro.extras["desafios_restantes"] == 0 and erro.extras["limite"] == 10
    assert 0 < erro.extras["tentar_novamente_em"] <= 24 * 3600
    assert erro.headers["Retry-After"] == str(erro.extras["tentar_novamente_em"])
    # As outras features e as outras contas não foram afetadas.
    rota_llm.exigir_cota("writing")(usuario=ana)
    gastar_reading(usuario=bruno)


def test_feature_desconhecida_e_erro_de_programacao():
    with pytest.raises(ValueError):
        rota_llm.exigir_cota("listening")


def test_situacao_mostra_aviso_configuracao_e_cotas(entrar_como, cota_nova):
    ana = entrar_como("ana@exemplo.com")

    corpo = ana.get("/api/llm/situacao").json()

    assert corpo["configurada"] is False  # nos testes, a LLM real fica sempre desligada
    assert "provedor externo de inteligência artificial" in corpo["aviso"]
    assert corpo["cotas"] == {f: {"restantes": 10, "limite": 10, "renova_em": None}
                              for f in ("reading", "writing", "speaking")}


def test_situacao_reflete_o_que_foi_gasto(entrar_como, cota_nova, llm_falsa):
    ana = entrar_como("ana@exemplo.com")
    id_da_ana = ana.get("/api/auth/me").json()["id"]
    rota_llm.exigir_cota("speaking")(usuario=SimpleNamespace(id=id_da_ana))

    corpo = ana.get("/api/llm/situacao").json()

    assert corpo["configurada"] is True
    assert corpo["cotas"]["speaking"]["restantes"] == 9 and corpo["cotas"]["speaking"]["renova_em"] > 0
    assert corpo["cotas"]["reading"]["restantes"] == 10


# --- A fixture llm_falsa (é assim que as features testam o uso da LLM) ---

def test_llm_falsa_passa_pela_validacao_real(llm_falsa):
    llm_falsa.responder({"nota": 15}).responder(Correcao(nota=6, comentario="ok"))

    assert gerar().nota == 6
    assert len(llm_falsa.chamadas) == 2  # a 1ª resposta era inválida (nota > 10): houve nova tentativa


def test_llm_falsa_simula_falhas(llm_falsa):
    llm_falsa.falhar(llm.LLMTempoEsgotado())

    with pytest.raises(llm.LLMTempoEsgotado):
        gerar()


def test_sem_llm_falsa_nenhum_teste_alcanca_a_rede(monkeypatch):
    """A fixture automática llm_desligada: mesmo com chave, a chamada real reprova o teste."""
    monkeypatch.setattr(config, "LLM_CHAVE", "chave-qualquer")

    with pytest.raises(AssertionError, match="llm_falsa"):
        gerar()
