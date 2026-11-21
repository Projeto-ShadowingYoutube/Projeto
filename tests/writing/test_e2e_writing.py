"""Testes de ponta a ponta do Writing num navegador de verdade (Chromium, via Playwright). Membro 3, W10 (D29).

Opcionais (como os da base, tests/test_e2e_navegador.py): lentos e exigem o Chromium e internet (o base.html carrega
o HTMX de um CDN). Para rodar:
    python -m playwright install chromium        (uma vez, ~150 MB)
    PowerShell:  $env:E2E="1"; python -m pytest tests/writing/test_e2e_writing.py --no-cov
    bash:        E2E=1 python -m pytest tests/writing/test_e2e_writing.py --no-cov

O app roda num servidor uvicorn real (num thread deste processo), com um banco SQLite temporário criado pelas
migrações (que já trazem os 24 temas da 0302). A LLM é a simulada (llm_falsa): nada sai para a rede além do CDN.
"""
import copy
import os
import socket
import threading
import time

import pytest

if not os.environ.get("E2E"):
    pytest.skip("testes de navegador desligados (defina E2E=1)", allow_module_level=True)

pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402
from playwright.sync_api import expect, sync_playwright  # noqa: E402
from sqlmodel import Session, create_engine  # noqa: E402

from app import db, migrar  # noqa: E402
from app.main import app  # noqa: E402

from .conftest import RESPOSTA_LLM  # noqa: E402
from .test_rewrite import CITACOES, TEXTO  # noqa: E402

SENHA = "senha-forte-123"


def _correcao() -> dict:
    resposta = copy.deepcopy(RESPOSTA_LLM)
    resposta["trechos"] = [{
        "categoria": categoria, "citacao": citacao, "gravidade": gravidade, "explicacao": f"Erro em '{citacao}'.",
        "sugestao": "Corrected version.", "instrucao_reescrita": f"Revise '{citacao}'.",
    } for citacao, categoria, gravidade in CITACOES]
    return resposta


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def servidor(tmp_path, monkeypatch):
    url_banco = f"sqlite:///{tmp_path / 'e2e.db'}"
    migrar.migrar(url_banco)  # esquema + os 24 temas da 0302
    engine = create_engine(url_banco, connect_args=db.opcoes_de_conexao(url_banco))

    def sessao():
        with Session(engine) as session:
            yield session

    monkeypatch.setattr(migrar, "verificar_banco", lambda: None)
    app.dependency_overrides[db.get_session] = sessao
    porta = _porta_livre()
    servidor = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=porta, log_level="warning"))
    thread = threading.Thread(target=servidor.run, daemon=True)
    thread.start()
    while not servidor.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{porta}"
    servidor.should_exit = True
    thread.join(5)
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture()
def aba(servidor):
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        contexto = navegador.new_context()
        pagina = contexto.new_page()
        pagina.on("dialog", lambda dialogo: dialogo.accept())  # o confirm() do envio (D11)
        erros = []
        pagina.on("pageerror", lambda erro: erros.append(str(erro)))  # erro de JS = teste reprovado
        pagina.goto(f"{servidor}/cadastro")
        expect(pagina.locator("button[type=submit]")).to_be_enabled()
        pagina.fill("#email", "ana@exemplo.com")
        pagina.fill("#senha", SENHA)
        pagina.fill("#confirmacao", SENHA)
        pagina.click("button[type=submit]")
        expect(pagina.locator(".nav-usuario")).to_have_text("ana@exemplo.com")
        yield pagina
        assert erros == [], f"erros de JavaScript na página: {erros}"
        navegador.close()


def _abrir_editor(aba, servidor):
    aba.goto(f"{servidor}/writing")
    aba.locator(".writing-categoria-botao", has_text="Opinião").click()
    expect(aba.locator("[data-tela=editor]")).to_be_visible()


def test_escrever_autosave_e_recarregar_traz_o_texto(aba, servidor):
    """O teste sugerido pelo guia: digitar, esperar o autosave, recarregar e ver o texto voltar."""
    _abrir_editor(aba, servidor)
    expect(aba.locator("[data-timer]")).to_have_text("40:00")  # Opinião: 40 min, a partir do relógio do servidor
    aba.fill("[data-texto]", "I don't agree, it's well-known.")
    expect(aba.locator("[data-contador]")).to_have_text("5 palavras")  # mesma regra do servidor
    expect(aba.locator("[data-salvo]")).to_contain_text("Salvo às", timeout=10000)  # 3 s depois de parar

    aba.reload()

    expect(aba.locator("[data-tela=editor]")).to_be_visible()
    expect(aba.locator("[data-texto]")).to_have_value("I don't agree, it's well-known.")
    assert "redacao=" in aba.url


def test_enviar_mostra_o_resultado_com_os_trechos(aba, servidor, llm_falsa):
    llm_falsa.responder(_correcao())
    _abrir_editor(aba, servidor)
    aba.fill("[data-texto]", TEXTO)
    expect(aba.locator("[data-enviar]")).to_be_enabled()

    aba.click("[data-enviar]")

    expect(aba.locator("[data-tela=resultado]")).to_be_visible(timeout=15000)
    expect(aba.locator("[data-res-nota]")).to_have_text("7,4")
    expect(aba.locator(".writing-nota")).to_have_count(5)
    marcas = aba.locator("[data-res-texto] .writing-marca")
    expect(marcas).to_have_count(len(CITACOES))
    expect(marcas.first).to_have_text("Many student cant")  # o destaque cai exatamente no trecho
    marcas.first.click()
    expect(aba.locator("[data-res-trecho]")).to_contain_text("O que fazer:")
    expect(aba.locator(".writing-trecho-sugestao")).to_be_hidden()  # D18
    aba.get_by_role("button", name="Ver sugestão").click()
    expect(aba.locator(".writing-trecho-sugestao")).to_contain_text("Corrected version.")


def test_rewrite_compara_e_mostra_o_veredito(aba, servidor, llm_falsa):
    llm_falsa.responder(_correcao())
    llm_falsa.responder({"avaliacoes": [
        {"indice": 0, "melhorou": True, "nota": 9, "comentario": "Corrigiu o plural."},
        {"indice": 2, "melhorou": True, "nota": 8, "comentario": "Concordância certa."},
        {"indice": 3, "melhorou": False, "nota": 4, "comentario": "Ainda falta."},
    ]})
    _abrir_editor(aba, servidor)
    aba.fill("[data-texto]", TEXTO)
    aba.click("[data-enviar]")
    expect(aba.locator("[data-res-rewrite]")).to_be_visible(timeout=15000)

    aba.click("[data-res-rewrite]")

    expect(aba.locator("[data-rw-rodada]")).to_have_text("Rodada 1 de 2")
    campos = aba.locator(".writing-rw-texto")
    expect(campos).to_have_count(3)
    expect(aba.locator("[data-rw-enviar]")).to_be_disabled()  # D26: nada alterado ainda
    campos.nth(0).fill("Many students can't pay the high fees, so they give up their dreams.")
    campos.nth(1).fill("Firstly, free education gives equal opportunities.")
    campos.nth(2).fill("If the government pays, the country will be more develop.")
    expect(aba.locator("[data-rw-enviar]")).to_be_enabled()
    aba.click("[data-rw-enviar]")

    expect(aba.locator("[data-rw-rodada]")).to_have_text("Rodada 2 de 2", timeout=15000)
    expect(aba.locator(".writing-rw-item")).to_have_count(3)
    expect(aba.locator(".writing-veredito.melhorou")).to_have_count(2)
    expect(aba.locator(".writing-rw-comparacao del").first).to_be_visible()  # o que saiu, riscado
    expect(aba.locator(".writing-rw-comparacao ins").first).to_be_visible()  # o que entrou, destacado
    expect(campos).to_have_count(1)  # rodada 2: só a que não melhorou (D21)
    expect(campos.first).to_have_value("If the government pays, the country will be more develop.")  # D25

    aba.reload()  # F5 volta ao Rewrite (&rewrite=1)
    expect(aba.locator("[data-rw-rodada]")).to_have_text("Rodada 2 de 2")
