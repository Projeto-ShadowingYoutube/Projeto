"""Blocos R9 e R10: a tela do Reading num navegador de verdade (Chromium, via Playwright).

Opcional, como os E2E da base: E2E=1 python -m pytest tests/reading/test_reading_e2e.py
(precisa de: python -m playwright install chromium). Servidor uvicorn real com banco migrado (tem os 5 textos de
reserva da 0102). As fontes de texto ficam fora do ar e a LLM sem chave: os desafios saem da reserva, sem rede.
"""
import json
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

from app import config, db, migrar  # noqa: E402
from app.api import llm as rota_llm  # noqa: E402
from app.main import app  # noqa: E402
from app.models_reading import ReadingAttempt, ReadingChallenge, ReadingQuestion  # noqa: E402
from app.services import llm  # noqa: E402
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
    expect(aba.locator("[data-etapa=perguntas] .reading-pergunta")).to_have_count(5)
    expect(aba.locator("[data-etapa=leitura]")).to_be_hidden()
    assert aba.locator("#readingConteudo p").count() == 0  # o texto saiu da tela
    assert _estado(banco, desafio_id) == "respondendo"


def test_no_zero_a_leitura_encerra_sozinha(aba, banco, monkeypatch):
    monkeypatch.setattr(rd.rt, "limite_leitura_segundos", lambda palavras, ppm: 3)
    aba.goto(f"{aba.base}/reading")
    aba.click("#readingComecar")
    expect(aba.locator("#readingTimer")).to_be_visible()
    expect(aba.locator("[data-etapa=perguntas] .reading-pergunta")).to_have_count(5, timeout=8000)
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
    expect(aba.locator("[data-etapa=perguntas] .reading-pergunta")).to_have_count(5)
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


# --- R10: perguntas, resultado e histórico ---

def _respostas_certas(banco, desafio_id: int) -> list[str]:
    with Session(banco) as s:
        consulta = (select(ReadingQuestion).where(ReadingQuestion.desafio_id == desafio_id)
                    .order_by(ReadingQuestion.ordem))
        return [p.resposta_correta for p in s.exec(consulta).all()]


def _tentativas(banco) -> list[ReadingAttempt]:
    with Session(banco) as s:
        return list(s.exec(select(ReadingAttempt)).all())


def _ate_as_perguntas(aba, modalidade: str = "multipla_escolha") -> int:
    aba.goto(f"{aba.base}/reading")
    aba.check(f"input[name=modalidade][value='{modalidade}']")
    aba.click("#readingComecar")
    expect(aba.locator("[data-etapa=leitura]")).to_be_visible()
    aba.click("#readingTerminei")
    expect(aba.locator(".reading-pergunta")).to_have_count(5)
    return _desafio_da_url(aba)


def _marcar(aba, ordem: int, alternativa: str) -> None:
    aba.locator(f".reading-pergunta[data-ordem='{ordem}'] input[value=\"{alternativa}\"]").check()


def _erradas(aba, ordem: int, certa: str) -> str:
    valores = aba.locator(f".reading-pergunta[data-ordem='{ordem}'] input").evaluate_all("els => els.map(e => e.value)")
    return next(v for v in valores if v != certa)


def test_multipla_escolha_responder_e_ver_o_resultado(aba, banco):
    desafio_id = _ate_as_perguntas(aba)
    certas = _respostas_certas(banco, desafio_id)
    for ordem in (1, 2, 3):
        _marcar(aba, ordem, certas[ordem - 1])
    _marcar(aba, 4, _erradas(aba, 4, certas[3]))  # a 5ª fica em branco
    dialogos = []
    aba.once("dialog", lambda dialogo: (dialogos.append(dialogo.message), dialogo.accept()))

    aba.click("#readingEnviar")

    expect(aba.locator(".reading-nota")).to_have_text("Nota 6/10")
    assert dialogos == ["Há 1 pergunta sem resposta. Enviar mesmo assim?"]
    expect(aba.locator(".reading-acertos")).to_have_text("3 de 5 perguntas certas.")
    expect(aba.locator(".reading-correcao.certo")).to_have_count(3)
    expect(aba.locator(".reading-correcao.errado")).to_have_count(2)
    expect(aba.locator(".reading-correcao[data-ordem='5']")).to_contain_text("Sem resposta")
    expect(aba.locator(".reading-correcao[data-ordem='1']")).to_contain_text(f"Resposta correta: {certas[0]}")
    expect(aba.locator(".reading-correcao[data-ordem='1'] .reading-justificativa")).not_to_be_empty()
    expect(aba.locator(".reading-detalhes")).to_contain_text("Múltipla escolha")
    expect(aba.locator(".reading-detalhes")).to_contain_text("Perguntas prontas")
    aba.click(".reading-texto-resultado summary")  # o texto volta no resultado (DR26)
    expect(aba.locator(".reading-texto-resultado .reading-credito")).to_contain_text("CC BY-SA 4.0")
    [tentativa] = _tentativas(banco)
    assert tentativa.nota == 6.0 and tentativa.respostas[4] == ""

    aba.reload()  # o resultado continua no F5 (?desafio=ID)
    expect(aba.locator(".reading-nota")).to_have_text("Nota 6/10")


def test_cancelar_o_aviso_de_perguntas_em_branco_nao_envia(aba, banco):
    _ate_as_perguntas(aba)
    aba.once("dialog", lambda dialogo: dialogo.dismiss())
    aba.click("#readingEnviar")
    expect(aba.locator(".reading-pergunta")).to_have_count(5)
    expect(aba.locator("#readingEnviar")).to_be_enabled()
    assert _tentativas(banco) == []


def test_rascunho_volta_depois_do_f5(aba, banco):
    desafio_id = _ate_as_perguntas(aba, "aberta")
    aba.fill(".reading-pergunta[data-ordem='1'] textarea", "Bees make honey in the hive.")
    aba.fill(".reading-pergunta[data-ordem='3'] textarea", "Wax.")
    expect(aba.locator(".reading-pergunta[data-ordem='1'] .reading-contador")).to_have_text("28/1000")

    aba.reload()
    expect(aba.locator(".reading-pergunta")).to_have_count(5)
    assert _desafio_da_url(aba) == desafio_id
    expect(aba.locator(".reading-pergunta[data-ordem='1'] textarea")).to_have_value("Bees make honey in the hive.")
    expect(aba.locator(".reading-pergunta[data-ordem='3'] textarea")).to_have_value("Wax.")
    expect(aba.locator(".reading-pergunta[data-ordem='2'] textarea")).to_have_value("")


def _llm_falsa(monkeypatch, *respostas):
    """A LLM do servidor responde (em ordem) o texto dado ou levanta o erro; nada sai para a rede."""
    fila = list(respostas)

    def chamar(mensagens, temperatura, max_tokens):
        proxima = fila.pop(0)
        if isinstance(proxima, Exception):
            raise proxima
        return proxima

    monkeypatch.setattr(config, "LLM_CHAVE", "chave-e2e")
    monkeypatch.setattr(llm, "_chamar", chamar)


def _correcoes(*pontos, comentario="Comentário {n}.") -> str:
    return json.dumps({"correcoes": [{"ordem": n, "pontuacao": p, "comentario": comentario.format(n=n)}
                                     for n, p in enumerate(pontos, start=1)]})


def test_aberta_corrigida_pela_ia_com_credito_parcial(aba, banco, monkeypatch):
    _llm_falsa(monkeypatch, _correcoes(1, 0.5, 0, 1, 1, comentario='<img src=x onerror="window.__xss=1"> {n}'))
    _ate_as_perguntas(aba, "aberta")
    expect(aba.locator("#readingAvisoRespostas .aviso-ia")).to_contain_text("provedor externo")  # antes do envio
    for ordem in range(1, 6):
        aba.fill(f".reading-pergunta[data-ordem='{ordem}'] textarea", f"Answer {ordem}.")

    aba.click("#readingEnviar")

    expect(aba.locator(".reading-nota")).to_have_text("Nota 7/10")
    expect(aba.locator(".reading-acertos")).to_contain_text("3 de 5 perguntas certas.")
    expect(aba.locator(".reading-correcao.parcial")).to_have_count(1)
    expect(aba.locator(".reading-correcao[data-ordem='2'] .reading-correcao-titulo")).to_contain_text("½")
    expect(aba.locator(".reading-correcao[data-ordem='2']")).to_contain_text("Resposta esperada:")
    comentario = aba.locator(".reading-correcao[data-ordem='2'] .reading-comentario")
    expect(comentario).to_have_text('Comentário da correção: <img src=x onerror="window.__xss=1"> 2')  # texto, não HTML
    assert aba.locator(".reading-correcao img").count() == 0 and aba.evaluate("window.__xss") is None


def test_falha_da_ia_e_nova_correcao(aba, banco, monkeypatch):
    _llm_falsa(monkeypatch, llm.LLMIndisponivel(), _correcoes(1, 1, 1, 1, 0.5))
    desafio_id = _ate_as_perguntas(aba, "aberta")
    for ordem in range(1, 6):
        aba.fill(f".reading-pergunta[data-ordem='{ordem}'] textarea", f"Answer {ordem}.")

    aba.click("#readingEnviar")
    expect(aba.locator("#readingAvaliarDeNovo")).to_be_visible()
    expect(aba.locator("[data-etapa=resultado]")).to_contain_text("O serviço de IA está indisponível agora.")
    expect(aba.locator(".reading-correcao.pendente")).to_have_count(5)
    expect(aba.locator(".reading-correcao[data-ordem='1']")).to_contain_text("Answer 1.")  # respostas guardadas
    assert _estado(banco, desafio_id) == "erro_avaliacao"

    aba.click("#readingAvaliarDeNovo")
    expect(aba.locator(".reading-nota")).to_have_text("Nota 9/10")
    assert _estado(banco, desafio_id) == "corrigido"


def test_historico_vazio_lista_e_continuar(aba, banco):
    aba.goto(f"{aba.base}/reading")
    aba.click("#readingVerHistorico")
    expect(aba.locator("#readingHistorico .estado-vazio")).to_contain_text("Nenhum desafio ainda")
    aba.click("#readingHistorico .estado-vazio-botao.principal")  # "Começar um desafio"
    expect(aba.locator("[data-etapa=inicio]")).to_be_visible()

    feito = _ate_as_perguntas(aba)
    aba.once("dialog", lambda dialogo: dialogo.accept())
    aba.click("#readingEnviar")
    expect(aba.locator(".reading-nota")).to_be_visible()
    aba.click("[data-etapa=resultado] .reading-acoes button:has-text('NOVO DESAFIO')")
    aba.click("#readingComecar")
    expect(aba.locator("[data-etapa=leitura]")).to_be_visible()
    em_leitura = _desafio_da_url(aba)
    titulo = aba.locator("#readingTituloTexto").inner_text()

    aba.goto(f"{aba.base}/reading")
    aba.click("#readingVerHistorico")
    linhas = aba.locator(".reading-historico-linha")
    expect(linhas).to_have_count(2)
    assert [int(i) for i in linhas.evaluate_all("ls => ls.map(l => l.dataset.id)")] == [em_leitura, feito]
    expect(linhas.nth(0)).to_contain_text("Em leitura")
    expect(linhas.nth(1)).to_contain_text("0/10")

    linhas.nth(0).locator("button:has-text('Continuar')").click()  # retoma a leitura
    expect(aba.locator("#readingTituloTexto")).to_have_text(titulo)
    assert _desafio_da_url(aba) == em_leitura

    aba.goto(f"{aba.base}/reading")
    aba.click("#readingVerHistorico")
    aba.locator(".reading-historico-linha").nth(1).locator("button:has-text('Ver')").click()
    expect(aba.locator(".reading-nota")).to_have_text("Nota 0/10")


# --- Aviso de demora e sinal de carregamento ---

def test_preparacao_lenta_mostra_aviso_e_sinal(aba, monkeypatch):
    def fonte_lenta():
        time.sleep(2)
        raise rf.FonteIndisponivel("simulada")

    monkeypatch.setattr(rf, "FONTES", {"wikipedia": fonte_lenta, "gutenberg": _fora})
    aba.goto(f"{aba.base}/reading")
    expect(aba.locator("#readingCarregando")).to_be_hidden()
    aba.click("#readingComecar")
    carregando = aba.locator("#readingCarregando")
    expect(carregando).to_be_visible()
    expect(carregando).to_contain_text("Pode demorar até 1 minuto")
    expect(carregando.locator(".reading-spinner")).to_be_visible()
    expect(aba.locator("[data-etapa=leitura]")).to_be_visible()
    expect(carregando).to_be_hidden()


def test_correcao_lenta_mostra_aviso_e_sinal(aba, monkeypatch):
    def chamar_devagar(mensagens, temperatura, max_tokens):
        time.sleep(2)
        return _correcoes(1, 1, 1, 1, 1)

    monkeypatch.setattr(config, "LLM_CHAVE", "chave-e2e")
    monkeypatch.setattr(llm, "_chamar", chamar_devagar)
    _ate_as_perguntas(aba, "aberta")
    for ordem in range(1, 6):
        aba.fill(f".reading-pergunta[data-ordem='{ordem}'] textarea", f"Answer {ordem}.")
    aba.click("#readingEnviar")
    enviando = aba.locator("#readingEnviando")
    expect(enviando).to_be_visible()
    expect(enviando).to_contain_text("Corrigindo as respostas com a IA… Pode demorar até 1 minuto")
    expect(enviando.locator(".reading-spinner")).to_be_visible()
    expect(aba.locator(".reading-nota")).to_have_text("Nota 10/10")


# --- Casos de borda (R13) ---

def test_f5_durante_a_preparacao_o_desafio_aparece_no_historico(aba, banco, monkeypatch):
    """A criação termina no servidor mesmo com a página recarregada no meio: a cota já foi gasta e o desafio fica no
    histórico com "Continuar" (a URL ainda não tinha o ?desafio=ID)."""
    def fonte_lenta():
        time.sleep(2)
        raise rf.FonteIndisponivel("simulada")

    monkeypatch.setattr(rf, "FONTES", {"wikipedia": fonte_lenta, "gutenberg": _fora})
    aba.goto(f"{aba.base}/reading")
    aba.click("#readingComecar")
    expect(aba.locator("#readingCarregando")).to_be_visible()
    aba.reload()  # no meio da preparação
    expect(aba.locator("[data-etapa=inicio]")).to_be_visible()
    assert "desafio=" not in aba.url

    for _ in range(50):  # espera a criação terminar no servidor
        with Session(banco) as s:
            if s.exec(select(ReadingChallenge)).first():
                break
        time.sleep(0.1)
    aba.click("#readingVerHistorico")
    linha = aba.locator(".reading-historico-linha")
    expect(linha).to_have_count(1)
    expect(linha).to_contain_text("Em leitura")
    linha.locator("button:has-text('Continuar')").click()
    expect(aba.locator("[data-etapa=leitura]")).to_be_visible()
    expect(aba.locator("#readingConteudo p").first).to_be_visible()


def test_html_nas_perguntas_e_alternativas_aparece_como_texto(aba, banco):
    """Enunciados e alternativas (da LLM ou da reserva) com HTML: aparecem como texto, nas perguntas e no resultado."""
    maliciosa = '<img src=x onerror="window.__xss=1">'
    perguntas = [{"enunciado": f"Question {n} {maliciosa}?",
                  "alternativas": [f"<b>A{n}</b>", f"B{n} {maliciosa}", f"C{n}", f"D{n}"],
                  "resposta_correta": f"<b>A{n}</b>", "justificativa": f"Justificativa {n} {maliciosa}"}
                 for n in range(1, 6)]
    with Session(banco) as s:
        for texto in s.exec(select(rf.ReadingText)).all():
            s.delete(texto)
        s.add(rf.ReadingText(fonte="wikipedia", id_origem="xss2", titulo="Bees", url="https://en.wikipedia.org/wiki/Bee",
                             conteudo=" ".join(["bees"] * 300) + ".", palavras=300, perguntas_reserva=perguntas))
        s.commit()

    _ate_as_perguntas(aba)
    expect(aba.locator(".reading-pergunta[data-ordem='1'] legend")).to_have_text(f"1. Question 1 {maliciosa}?")
    expect(aba.locator(".reading-pergunta[data-ordem='1'] .reading-alternativa", has_text="<b>A1</b>")).to_have_count(1)
    assert aba.locator(".reading-pergunta img, .reading-pergunta b").count() == 0

    for ordem in range(1, 6):
        aba.locator(f".reading-pergunta[data-ordem='{ordem}'] input[value='<b>A{ordem}</b>']").check()
    aba.click("#readingEnviar")
    expect(aba.locator(".reading-nota")).to_have_text("Nota 10/10")  # a grafia com "<b>" é comparada como texto
    expect(aba.locator(".reading-correcao[data-ordem='1'] .reading-justificativa")).to_contain_text(maliciosa)
    assert aba.locator(".reading-correcao img, .reading-correcao b").count() == 0
    assert aba.evaluate("window.__xss") is None
