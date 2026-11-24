"""Bloco R9: a tela de início e leitura num navegador de verdade (Chromium, via Playwright).

Opcional, como os E2E da base: E2E=1 python -m pytest tests/reading/test_reading_e2e.py
(precisa de: python -m playwright install chromium). Servidor uvicorn real com banco migrado (tem os 5 textos de
reserva da 0102). As fontes de texto ficam fora do ar e a LLM sem chave: os desafios saem da reserva, sem rede.
"""
import os
import re
import socket
import threading
import time

import pytest

if not os.environ.get("E2E"):
    pytest.skip("testes de navegador desligados (defina E2E=1)", allow_module_level=True)

pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402
from limits.storage import MemoryStorage  # noqa: E402
from limits.strategies import FixedWindowRateLimiter  # noqa: E402
from playwright.sync_api import expect, sync_playwright  # noqa: E402
from sqlmodel import Session, create_engine, select  # noqa: E402

from app import db, migrar  # noqa: E402
from app.api import llm as rota_llm  # noqa: E402
from app.main import app  # noqa: E402
from app.models_reading import ReadingChallenge  # noqa: E402
from app.services import reading_desafios as rd  # noqa: E402
from app.services import reading_fontes as rf  # noqa: E402

SENHA = "senha-forte-123"
TITULOS_RESERVA = ["Honey bee", "Coffee", "Volcano", "Moon", "Penguin"]


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _fora():
    raise rf.FonteIndisponivel("simulada")


@pytest.fixture()
def banco(tmp_path):
    url = f"sqlite:///{tmp_path / 'e2e.db'}"
    migrar.migrar(url)
    engine = create_engine(url, connect_args=db.opcoes_de_conexao(url))
    yield engine
    engine.dispose()


@pytest.fixture()
def servidor(banco, monkeypatch):
    def sessao():
        with Session(banco) as session:
            yield session

    monkeypatch.setattr(migrar, "verificar_banco", lambda: None)
    app.dependency_overrides[db.get_session] = sessao
    monkeypatch.setattr(rf, "FONTES", {"wikipedia": _fora, "gutenberg": _fora})
    monkeypatch.setattr(rota_llm, "limitador", FixedWindowRateLimiter(MemoryStorage()))

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


@pytest.fixture()
def aba(servidor):
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        contexto = navegador.new_context()
        pagina = contexto.new_page()
        erros_js = []
        pagina.on("pageerror", lambda erro: erros_js.append(str(erro)))
        pagina.goto(f"{servidor}/cadastro")
        expect(pagina.locator("button[type=submit]")).to_be_enabled()
        pagina.fill("#email", "ana@exemplo.com")
        pagina.fill("#senha", SENHA)
        pagina.fill("#confirmacao", SENHA)
        pagina.click("button[type=submit]")
        expect(pagina.locator(".nav-usuario")).to_have_text("ana@exemplo.com")
        pagina.base = servidor
        yield pagina
        assert erros_js == [], erros_js  # nenhum erro de JavaScript em nenhum teste
        navegador.close()


def _desafio_da_url(aba) -> int:
    return int(re.search(r"[?&]desafio=(\d+)", aba.url).group(1))


def _estado(banco, desafio_id: int) -> str:
    with Session(banco) as s:
        return s.get(ReadingChallenge, desafio_id).estado


def _segundos(aba) -> int:
    minutos, segundos = aba.locator("#readingTimer").inner_text().split(":")
    return int(minutos) * 60 + int(segundos)


def test_inicio_leitura_f5_e_terminei(aba, banco):
    aba.click("button.nav-btn[hx-get='/reading']")
    expect(aba.locator(".aviso-ia")).to_contain_text("provedor externo de inteligência artificial")
    expect(aba.locator("#readingCota")).to_contain_text("10 de 10")
    expect(aba.locator("#readingCota")).to_contain_text("perguntas prontas")  # LLM sem chave (DR17)

    aba.check("input[name=ppm][value='250']")
    aba.click("#readingComecar")
    expect(aba.locator("[data-etapa=leitura]")).to_be_visible()
    titulo = aba.locator("#readingTituloTexto").inner_text()
    assert titulo in TITULOS_RESERVA
    assert aba.locator("#readingConteudo p").count() >= 1
    expect(aba.locator("#readingCredito")).to_contain_text("CC BY-SA 4.0")
    assert aba.locator("#readingCredito a").get_attribute("href").startswith("https://en.wikipedia.org/wiki/")
    desafio_id = _desafio_da_url(aba)
    expect(aba.locator("#readingCota")).to_be_hidden()
    antes = _segundos(aba)
    assert 0 < antes <= 145  # o maior texto de reserva (588 palavras) a 250 ppm dá 145 s

    aba.wait_for_timeout(1500)
    aba.reload()  # F5: volta ao mesmo texto, com o tempo do servidor
    expect(aba.locator("#readingTituloTexto")).to_have_text(titulo)
    assert _desafio_da_url(aba) == desafio_id and _segundos(aba) < antes

    aba.click("#readingTerminei")
    expect(aba.locator("[data-etapa=perguntas]")).to_contain_text("Leitura encerrada")
    expect(aba.locator("[data-etapa=leitura]")).to_be_hidden()
    assert aba.locator("#readingConteudo p").count() == 0  # o texto saiu da tela
    assert _estado(banco, desafio_id) == "respondendo"


def test_no_zero_a_leitura_encerra_sozinha(aba, banco, monkeypatch):
    monkeypatch.setattr(rd.rt, "limite_leitura_segundos", lambda palavras, ppm: 3)
    aba.goto(f"{aba.base}/reading")
    aba.click("#readingComecar")
    expect(aba.locator("#readingTimer")).to_be_visible()
    expect(aba.locator("[data-etapa=perguntas]")).to_contain_text("Leitura encerrada", timeout=8000)
    assert _estado(banco, _desafio_da_url(aba)) == "respondendo"


def test_voltar_depois_do_prazo_nao_mostra_o_texto(aba, banco, monkeypatch):
    """Saiu da página no meio da leitura e voltou depois do prazo: vai direto às perguntas (DR24)."""
    monkeypatch.setattr(rd.rt, "limite_leitura_segundos", lambda palavras, ppm: 2)
    aba.goto(f"{aba.base}/reading")
    aba.click("#readingComecar")
    expect(aba.locator("[data-etapa=leitura]")).to_be_visible()
    desafio_id = _desafio_da_url(aba)
    aba.goto(f"{aba.base}/decks")  # sai antes do zero: o timer da página é cancelado
    aba.wait_for_timeout(2000 + 5000 + 500)  # prazo + tolerância
    assert _estado(banco, desafio_id) == "lendo"

    aba.goto(f"{aba.base}/reading?desafio={desafio_id}")
    expect(aba.locator("[data-etapa=perguntas]")).to_contain_text("Leitura encerrada")
    assert aba.locator("#readingConteudo p").count() == 0
    assert _estado(banco, desafio_id) == "respondendo"


def test_cota_esgotada_desativa_o_botao(aba):
    for _ in range(10):
        assert aba.request.post(f"{aba.base}/api/reading/challenges", data={"modalidade": "aberta"}).status == 201
    aba.goto(f"{aba.base}/reading")
    expect(aba.locator("#readingCota")).to_contain_text("0 de 10")
    expect(aba.locator("#readingCota")).to_contain_text("Novos desafios em")
    expect(aba.locator("#readingComecar")).to_be_disabled()


def test_erro_da_api_aparece_em_portugues(aba, banco):
    """Sem texto nenhum (fonte fora e sem reserva): a mensagem do servidor aparece na tela."""
    with Session(banco) as s:
        for texto in s.exec(select(rf.ReadingText)).all():
            s.delete(texto)
        s.commit()
    aba.goto(f"{aba.base}/reading")
    aba.click("#readingComecar")
    expect(aba.locator("#readingErroInicio")).to_have_text(
        "Não foi possível obter um texto agora. Tente de novo em instantes.")
    expect(aba.locator("#readingComecar")).to_be_enabled()
    expect(aba.locator("#readingCota")).to_contain_text("9 de 10")  # a cota foi gasta (achado do R5)


def test_conteudo_do_texto_nao_vira_html(aba, banco):
    """Um texto com HTML no título e no conteúdo aparece como texto: nada é executado (XSS).
    Ele é o único texto de reserva do banco (com a LLM sem chave, o desafio sempre sai da reserva, DR17)."""
    perguntas = [{"enunciado": f"Question number {n}?", "alternativas": [f"A{n}", f"B{n}", f"C{n}", f"D{n}"],
                  "resposta_correta": f"A{n}", "justificativa": f"O texto diz \"A{n}\"."} for n in range(1, 6)]
    conteudo = " ".join(["bees"] * 300) + ' <img src=x onerror="window.__xss=1"> <script>window.__xss=2</script>.'
    with Session(banco) as s:
        for texto in s.exec(select(rf.ReadingText)).all():
            s.delete(texto)
        s.add(rf.ReadingText(fonte="wikipedia", id_origem="xss", titulo='<b onclick="x()">Bees</b>',
                             url="javascript:window.__xss=3", conteudo=conteudo, palavras=306,
                             perguntas_reserva=perguntas))
        s.commit()
    aba.goto(f"{aba.base}/reading")
    aba.click("#readingComecar")
    expect(aba.locator("#readingTituloTexto")).to_have_text('<b onclick="x()">Bees</b>')
    expect(aba.locator("#readingConteudo")).to_contain_text("<script>window.__xss=2</script>")
    assert aba.locator("#readingConteudo img, #readingConteudo script, #readingTituloTexto b").count() == 0
    assert aba.locator("#readingCredito a").count() == 0  # URL que não é https não vira link
    assert aba.evaluate("window.__xss") is None
