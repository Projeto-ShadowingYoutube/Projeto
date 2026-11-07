"""Testes de ponta a ponta num navegador de verdade (Chromium, via Playwright).

Opcionais, porque são lentos e exigem o Chromium e o FFmpeg instalados. Para rodar:
    pip install -r requirements-dev.txt && python -m playwright install chromium
    E2E=1 pytest tests/test_e2e_navegador.py        (PowerShell: $env:E2E="1"; pytest ...)

O app roda num servidor uvicorn real, com um banco SQLite temporário criado pelas migrações. O vídeo do YouTube é
trocado por um WebM de 3 segundos gerado pelo FFmpeg (sem rede, sem gastar tokens). O karaokê é desligado, para o
teste não depender do YouTube nem do modelo de fala.
"""
import http.server
import os
import re
import shutil
import socket
import subprocess
import threading
import time

import pytest

if not os.environ.get("E2E"):
    pytest.skip("testes de navegador desligados (defina E2E=1)", allow_module_level=True)

playwright_sync = pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402
from limits import parse  # noqa: E402
from limits.storage import MemoryStorage  # noqa: E402
from limits.strategies import FixedWindowRateLimiter  # noqa: E402
from playwright.sync_api import expect, sync_playwright  # noqa: E402
from sqlmodel import Session, create_engine  # noqa: E402

from app import config, db, migrar  # noqa: E402
from app.api import legendas as rota_legendas  # noqa: E402
from app.main import app  # noqa: E402
from app.services import karaoke, midia, youtube  # noqa: E402

VIDEO_ID = "abcdefghijk"
SENHA = "senha-forte-123"


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def video_falso(tmp_path_factory):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg não encontrado")
    arquivo = tmp_path_factory.mktemp("video") / f"{VIDEO_ID}.webm"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
         "-f", "lavfi", "-i", "color=c=black:s=64x64:d=3", "-shortest", "-c:v", "libvpx-vp9", "-c:a", "libopus",
         str(arquivo)],
        check=True,
    )
    return arquivo


@pytest.fixture()
def servidor(tmp_path, monkeypatch, video_falso):
    """URL de um servidor real do app, com banco próprio (migrado) e o vídeo falso já "baixado"."""
    url_banco = f"sqlite:///{tmp_path / 'e2e.db'}"
    migrar.migrar(url_banco)
    engine = create_engine(url_banco, connect_args=db.opcoes_de_conexao(url_banco))

    def sessao():
        with Session(engine) as session:
            yield session

    monkeypatch.setattr(migrar, "verificar_banco", lambda: None)
    app.dependency_overrides[db.get_session] = sessao
    config.PASTA_MIDIA.mkdir(parents=True, exist_ok=True)
    shutil.copy(video_falso, config.PASTA_MIDIA)  # o Player acha o vídeo "já baixado" e não chama o YouTube

    async def sem_karaoke(*_):
        return {"tempos": None, "fonte": "estimativa"}

    monkeypatch.setattr(karaoke, "_calcular", sem_karaoke)

    # YouTube simulado: qualquer vídeo tem a legenda "Hello world." (0 a 2.5 s) e "baixa" o WebM falso.
    monkeypatch.setattr(youtube, "baixar_legendas", lambda video_id: (
        [{"text": "Hello world.", "start": 0.0, "duration": 2.5}], True, "en",
    ))
    monkeypatch.setattr(youtube, "buscar_titulo", lambda video_id: "Vídeo simulado")
    monkeypatch.setattr(youtube, "baixar_video", lambda video_id, pasta, ao_progredir: shutil.copy(
        video_falso, pasta / f"{video_id}.webm",
    ))
    # Estado em memória do processo, zerado a cada teste (como um servidor recém-iniciado): o registro de downloads
    # lembra vídeos "já baixados" em pastas de testes anteriores, que não existem mais.
    monkeypatch.setattr(midia, "_downloads", {})
    monkeypatch.setattr(midia, "_progresso", {})
    # Tokens: limitador novo a cada teste (o do app é global ao processo).
    monkeypatch.setattr(rota_legendas, "limitador", FixedWindowRateLimiter(MemoryStorage()))

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
def navegador():
    with sync_playwright() as p:
        chromium = p.chromium.launch()
        yield chromium
        chromium.close()


def _nova_aba(navegador):
    contexto = navegador.new_context()
    aba = contexto.new_page()
    aba.on("dialog", lambda dialogo: dialogo.accept())  # confirm() e alert() do app
    return contexto, aba


def _formulario_pronto(aba):
    """Espera o JS da tela de login/cadastro assumir o formulário (o botão nasce desabilitado e só habilita no fim
    da inicialização). Digitar antes disso compete com a inicialização da página, que pode mexer no foco."""
    expect(aba.locator("button[type=submit]")).to_be_enabled()


def _cadastrar(aba, base, email):
    aba.goto(f"{base}/cadastro")
    _formulario_pronto(aba)
    aba.fill("#email", email)
    aba.fill("#senha", SENHA)
    aba.fill("#confirmacao", SENHA)
    aba.click("button[type=submit]")
    expect(aba.locator(".nav-usuario")).to_have_text(email)


def _criar_deck_pela_tela(aba, nome):
    aba.click("#btnCriarDeckRevisao")
    aba.fill("#novoNomeDeckInput", nome)
    aba.click("#btnConfirmarCriarDeck")
    expect(aba.locator(".dashboard-tr-deck .td-deck-name", has_text=nome)).to_be_visible()


def _salvar_card(aba, base, deck_id, texto):
    """O mesmo POST que o botão "Salvar card" da página de estudo faz (aquela página precisa do YouTube)."""
    corpo = {"video_id": VIDEO_ID, "texto_legenda": texto, "start_time": 0.0, "end_time": 2.5}
    resposta = aba.request.post(f"{base}/api/decks/{deck_id}/cards", data=corpo)
    assert resposta.status == 201


def _iniciar_estudos(aba):
    """Como o usuário: o botão "Iniciar Estudos" tira a proteção do player (o navegador só toca som após um clique)."""
    expect(aba.locator("#protecaoButton")).to_be_enabled(timeout=15000)
    aba.click("#protecaoButton")


def _linha(aba, nome):
    return aba.locator(".dashboard-tr-deck", has=aba.locator(".td-deck-name", has_text=nome))


def test_fluxo_completo_login_decks_revisao_e_logout(servidor, navegador):
    contexto, aba = _nova_aba(navegador)

    # Sem login, a página pedida leva ao login (guardando para onde voltar).
    aba.goto(f"{servidor}/decks")
    expect(aba).to_have_url(f"{servidor}/login?proximo=%2Fdecks")
    expect(aba.locator(".nav-usuario")).to_have_count(0)

    # Cadastro: senhas diferentes mostram o erro na tela; depois, a conta é criada e o usuário volta para /decks.
    aba.click("text=Criar conta")
    expect(aba).to_have_url(f"{servidor}/cadastro?proximo=/decks")
    _formulario_pronto(aba)
    aba.fill("#email", "ana@exemplo.com")
    aba.fill("#senha", SENHA)
    aba.fill("#confirmacao", "outra-senha-123")
    aba.click("button[type=submit]")
    expect(aba.locator(".auth-erro")).to_have_text("As senhas não conferem.")
    aba.fill("#confirmacao", SENHA)
    aba.click("button[type=submit]")
    expect(aba).to_have_url(f"{servidor}/decks")
    expect(aba.locator(".nav-usuario")).to_have_text("ana@exemplo.com")
    expect(aba.locator(".dashboard-aviso")).to_contain_text("Você ainda não tem Decks")

    # Agosto: criar Deck pelo modal, salvar Card, revisar com "Fácil".
    _criar_deck_pela_tela(aba, "Inglês")
    deck_id = int(_linha(aba, "Inglês").get_attribute("data-id"))
    _salvar_card(aba, servidor, deck_id, "Hello from the browser")
    aba.reload()
    expect(_linha(aba, "Inglês").locator(".td-novos")).to_have_text("1")

    _linha(aba, "Inglês").dblclick()
    expect(aba).to_have_url(f"{servidor}/decks/{deck_id}/revisao")
    expect(aba.locator("#legenda")).to_contain_text("Hello from the browser")
    _iniciar_estudos(aba)
    aba.click("#facil")
    expect(aba).to_have_url(f"{servidor}/decks")  # "revisão finalizada" (alert aceito) → volta ao dashboard
    expect(_linha(aba, "Inglês").locator(".td-novos")).to_have_text("0")
    expect(_linha(aba, "Inglês").locator(".td-qtd-total")).to_have_text("1")

    # Agosto: excluir um Card na revisão.
    _salvar_card(aba, servidor, deck_id, "Card para apagar")
    aba.goto(f"{servidor}/decks/{deck_id}/revisao")
    expect(aba.locator("#legenda")).to_contain_text("Card para apagar")
    _iniciar_estudos(aba)
    aba.click("#delete")
    expect(aba).to_have_url(f"{servidor}/decks")
    expect(_linha(aba, "Inglês").locator(".td-qtd-total")).to_have_text("1")

    # Sair: volta ao login, e o botão "voltar" do navegador não reabre o dashboard.
    aba.click("#sair")
    expect(aba).to_have_url(f"{servidor}/login")
    aba.go_back()
    expect(aba).to_have_url(f"{servidor}/login?proximo=%2Fdecks")
    expect(aba.locator(".dashboard-tr-deck")).to_have_count(0)

    # Login com senha errada: mensagem na tela, sem sair da página. Com a certa, volta para /decks.
    _formulario_pronto(aba)
    aba.fill("#email", "ana@exemplo.com")
    aba.fill("#senha", "senha-errada-1")
    aba.click("button[type=submit]")
    expect(aba.locator(".auth-erro")).to_have_text("E-mail ou senha incorretos.")
    aba.fill("#senha", SENHA)
    aba.click("button[type=submit]")
    expect(aba).to_have_url(f"{servidor}/decks")
    expect(_linha(aba, "Inglês")).to_be_visible()
    contexto.close()


def test_outra_conta_nao_ve_nem_abre_os_decks_da_primeira(servidor, navegador):
    contexto_ana, ana = _nova_aba(navegador)
    _cadastrar(ana, servidor, "ana@exemplo.com")
    ana.goto(f"{servidor}/decks")
    _criar_deck_pela_tela(ana, "Deck da Ana")
    deck_da_ana = _linha(ana, "Deck da Ana").get_attribute("data-id")

    contexto_bruno, bruno = _nova_aba(navegador)
    _cadastrar(bruno, servidor, "bruno@exemplo.com")
    bruno.goto(f"{servidor}/decks")
    expect(bruno.locator(".dashboard-aviso")).to_contain_text("Você ainda não tem Decks")

    bruno.goto(f"{servidor}/decks/{deck_da_ana}/revisao")
    expect(bruno.locator("#erro")).to_have_text("Deck não encontrado.")
    contexto_ana.close()
    contexto_bruno.close()


def test_sessao_que_expira_no_meio_do_uso_leva_ao_login_e_volta(servidor, navegador):
    contexto, aba = _nova_aba(navegador)
    _cadastrar(aba, servidor, "ana@exemplo.com")
    aba.goto(f"{servidor}/decks")
    expect(aba.locator(".dashboard-aviso")).to_be_visible()  # página carregada antes de "expirar" a sessão

    contexto.clear_cookies()  # a sessão "expira" com a página aberta
    aba.click("#btnCriarDeckRevisao")
    aba.fill("#novoNomeDeckInput", "Não vai ser criado")
    aba.click("#btnConfirmarCriarDeck")

    expect(aba).to_have_url(f"{servidor}/login?proximo=%2Fdecks")
    contexto.close()


def test_outro_site_nao_consegue_deslogar_o_usuario(servidor, navegador, tmp_path):
    """CSRF de verdade: uma página em outra origem (outra porta: para o SameSite é o mesmo "site", então o cookie
    VAI junto) manda um POST /api/auth/logout com os cookies da vítima. É uma "requisição simples" (sem corpo), que
    o navegador envia sem pedir permissão (CORS). Quem barra é a verificação de Origin."""
    contexto, aba = _nova_aba(navegador)
    _cadastrar(aba, servidor, "ana@exemplo.com")

    (tmp_path / "malicioso.html").write_text("<html><body>site malicioso</body></html>", encoding="utf-8")
    porta = _porta_livre()
    manipulador = lambda *a: http.server.SimpleHTTPRequestHandler(*a, directory=str(tmp_path))  # noqa: E731
    site_malicioso = http.server.ThreadingHTTPServer(("127.0.0.1", porta), manipulador)
    threading.Thread(target=site_malicioso.serve_forever, daemon=True).start()
    try:
        aba.goto(f"http://127.0.0.1:{porta}/malicioso.html")
        aba.evaluate(
            'url => fetch(url, {method: "POST", credentials: "include", mode: "no-cors"})',
            f"{servidor}/api/auth/logout",
        )
    finally:
        site_malicioso.shutdown()

    aba.goto(f"{servidor}/decks")
    expect(aba).to_have_url(f"{servidor}/decks")  # continua logada
    expect(aba.locator(".nav-usuario")).to_have_text("ana@exemplo.com")
    contexto.close()


def _mover_slider(aba, valor):
    """Como arrastar o slider: muda o valor e dispara o evento "input" (o mesmo que o navegador dispara)."""
    aba.eval_on_selector(
        "#velocidade", "(s, v) => { s.value = v; s.dispatchEvent(new Event('input', {bubbles: true})); }", str(valor),
    )


def _eh_salvamento(requisicao):
    return requisicao.method == "PATCH" and "/api/configuracoes" in requisicao.url


def _esperar_velocidade_salva(aba, base, esperada, limite_s=5):
    """Consulta a API até a velocidade salva ser a esperada (sem depender de um tempo fixo)."""
    fim = time.monotonic() + limite_s
    while (atual := aba.request.get(f"{base}/api/configuracoes").json()["velocidade"]) != esperada:
        assert time.monotonic() < fim, f"velocidade salva continua {atual}, esperada {esperada}"
        aba.wait_for_timeout(100)


def _velocidade_do_video(aba):
    return aba.eval_on_selector("#player video", "v => v.playbackRate")


def test_velocidade_funciona_como_antes_e_fica_salva_na_conta(servidor, navegador):
    contexto, aba = _nova_aba(navegador)
    _cadastrar(aba, servidor, "ana@exemplo.com")
    aba.goto(f"{servidor}/decks")
    _criar_deck_pela_tela(aba, "Velocidade")
    deck_id = int(_linha(aba, "Velocidade").get_attribute("data-id"))
    _salvar_card(aba, servidor, deck_id, "Speed test")  # frase de 2.5 s
    salvamentos = []
    aba.on("request", lambda r: salvamentos.append(r) if _eh_salvamento(r) else None)

    # Primeira vez: 1x, como sempre.
    aba.goto(f"{servidor}/decks/{deck_id}/revisao")
    _iniciar_estudos(aba)
    expect(aba.locator("#velocidadeValor")).to_have_text("1.00x")
    expect(aba.locator("#timerTexto")).to_have_text("0.0s / 2.5s")
    assert _velocidade_do_video(aba) == 1

    # Comportamento existente: arrastar o slider muda o vídeo, o rótulo e o timer na hora.
    with aba.expect_response(lambda r: _eh_salvamento(r.request)) as salvo:
        for valor in (0.95, 0.9, 0.85, 0.8, 0.75):  # vários passos seguidos, como um arraste
            _mover_slider(aba, valor)
        expect(aba.locator("#velocidadeValor")).to_have_text("0.75x")
        assert _velocidade_do_video(aba) == 0.75
        expect(aba.locator("#timerTexto")).to_have_text("0.0s / 3.3s")  # 2.5 s a 0.75x
    assert salvo.value.json()["velocidade"] == 0.75
    aba.wait_for_timeout(700)
    assert len(salvamentos) == 1  # um arraste inteiro = um salvamento (o último valor)

    # Novo: recarregar a página mantém a velocidade (vídeo, slider, rótulo e timer do gravador).
    aba.reload()
    expect(aba.locator("#velocidadeValor")).to_have_text("0.75x")
    expect(aba.locator("#timerTexto")).to_have_text("0.0s / 3.3s")
    _iniciar_estudos(aba)
    assert aba.eval_on_selector("#velocidade", "s => s.value") == "0.75"
    assert _velocidade_do_video(aba) == 0.75

    # Comportamento existente: duplo clique volta para 1x (e isso também fica salvo).
    with aba.expect_response(lambda r: _eh_salvamento(r.request)):
        aba.dblclick("#velocidade")
    expect(aba.locator("#velocidadeValor")).to_have_text("1.00x")
    assert _velocidade_do_video(aba) == 1
    assert aba.request.get(f"{servidor}/api/configuracoes").json()["velocidade"] == 1.0

    # Sair da página logo depois de mexer (antes do atraso de 500 ms) não perde a mudança.
    _mover_slider(aba, 1.25)
    aba.click(".nav-btn:has-text('Revisar')")
    expect(aba.locator(".dashboard-tr-deck")).to_have_count(1)
    _esperar_velocidade_salva(aba, servidor, 1.25)
    contexto.close()


def _barra_do_player_numa_linha(aba):
    """Pedido do usuário (B9.2): a barra do player cabe numa linha só em 1280 px. Compara o centro vertical dos
    PRÓPRIOS controles (um grupo que quebra por dentro continua centralizado). O mais largo é o do estudo, que tem
    Anterior / Próxima / contador; na revisão esses botões não existem."""
    aba.set_viewport_size({"width": 1280, "height": 900})
    centros = aba.evaluate("""() => ['#pausar', '.controle-velocidade', '#mudo'].map(s => {
        const r = document.querySelector(s).getBoundingClientRect(); return Math.round(r.top + r.height / 2); })""")
    assert max(centros) - min(centros) <= 3, f"barra do player quebrou em mais de uma linha: centros {centros}"


def _estudar(aba, base, numero):
    aba.goto(f"{base}/estudo?link=https://youtu.be/video{numero:06d}")


def test_estudo_abre_na_velocidade_salva_e_avisa_quando_os_tokens_acabam(servidor, navegador, monkeypatch):
    monkeypatch.setattr(rota_legendas, "LIMITE_TOKENS", parse("2/5 minute"))
    contexto, aba = _nova_aba(navegador)
    _cadastrar(aba, servidor, "ana@exemplo.com")
    assert aba.request.patch(f"{servidor}/api/configuracoes", data={"velocidade": 0.75}).ok

    # 1º vídeo: legenda, velocidade salva (B8) e 1 token gasto.
    _estudar(aba, servidor, 1)
    expect(aba.locator("#textologs")).to_contain_text("Vídeo simulado")
    expect(aba.locator("#avisoUltimoToken")).to_be_hidden()
    expect(aba.locator("#token-count")).to_have_text("1")
    aba.click("#botaoContinuar")
    expect(aba.locator("#legenda")).to_contain_text("Hello world.")
    _barra_do_player_numa_linha(aba)  # o estudo tem a barra mais larga (Anterior / Próxima / contador)
    expect(aba.locator("#velocidadeValor")).to_have_text("0.75x")
    _iniciar_estudos(aba)
    assert _velocidade_do_video(aba) == 0.75
    botao_tokens = aba.locator("#token-count").locator("xpath=..")
    expect(botao_tokens).to_have_attribute("title", re.compile(r"Tokens renovam em \d:\d\d"))

    # 2º vídeo: o último token. Aviso no modal da legenda e contador vermelho.
    _estudar(aba, servidor, 2)
    expect(aba.locator("#avisoUltimoToken")).to_be_visible()
    expect(aba.locator("#avisoUltimoToken")).to_contain_text("Este foi seu último token. Novos tokens em ")
    expect(aba.locator("#token-count")).to_have_text("0")
    expect(aba.locator("#token-count")).to_have_class(re.compile("token-low"))

    # 3º vídeo: sem tokens. Mensagem específica com contagem (e não o modal de erro genérico).
    _estudar(aba, servidor, 3)
    expect(aba.locator("#modalSemTokens")).to_be_visible()
    expect(aba.locator("#contagemTokens")).to_have_text(re.compile(r"^[0-5]:\d\d$"))
    expect(aba.locator("#erroModal")).to_be_hidden()
    expect(aba.locator("#semTokensTentar")).to_be_hidden()  # só aparece quando renovar: nada de contornar
    aba.click("#semTokensDecks")
    expect(aba).to_have_url(f"{servidor}/decks")
    contexto.close()


def test_quando_os_tokens_renovam_da_para_carregar_o_video(servidor, navegador, monkeypatch):
    monkeypatch.setattr(rota_legendas, "LIMITE_TOKENS", parse("1/6 second"))  # janela curta, só para o teste
    contexto, aba = _nova_aba(navegador)
    _cadastrar(aba, servidor, "ana@exemplo.com")
    assert aba.request.get(f"{servidor}/api/legendas", params={"url": "https://youtu.be/video000001"}).ok

    _estudar(aba, servidor, 2)
    expect(aba.locator("#modalSemTokens")).to_be_visible()
    expect(aba.locator("#semTokensTentar")).to_be_visible(timeout=10000)  # contagem chegou a zero
    expect(aba.locator("#contagemTokens")).to_contain_text("renovados")
    aba.click("#semTokensTentar")
    expect(aba.locator("#textologs")).to_contain_text("Vídeo simulado")  # agora carregou, com token novo
    contexto.close()


def _progresso_da_onda(aba):
    """Largura da parte "já tocada" (cor de progresso) desenhada pelo WaveSurfer, em % (fica no shadow DOM dele)."""
    return aba.evaluate("""() => {
        const raiz = document.querySelector('#waveform > div')?.shadowRoot;
        const progresso = raiz?.querySelector('[part~="progress"]') || raiz?.querySelector('.progress');
        return progresso ? parseFloat(progresso.style.width) : null;
    }""")


def test_onda_vem_pronta_do_servidor_e_clicar_nela_leva_o_video_ao_ponto(servidor, navegador):
    contexto, aba = _nova_aba(navegador)
    pedidos = []
    aba.on("request", lambda r: pedidos.append(r.url.replace(servidor, "")) if "/api/videos/" in r.url else None)
    _cadastrar(aba, servidor, "ana@exemplo.com")

    with aba.expect_response(lambda r: "/waveform?" in r.url) as primeira:
        _estudar(aba, servidor, 1)
    onda = primeira.value.json()  # lido agora: o navegador descarta o corpo quando a página recarrega
    assert onda["cache"] is False and len(onda["peaks"]) == 400
    aba.click("#botaoContinuar")
    _iniciar_estudos(aba)
    expect(aba.locator("#waveform > div")).to_be_attached()  # o WaveSurfer desenhou
    expect(aba.locator(".waveform-falha")).to_have_count(0)
    assert not any("/audio?" in pedido for pedido in pedidos)  # o navegador não baixa mais o WAV

    # Comportamento existente (mesmo resultado da referência de antes do B9): clicar a 60% da onda leva o vídeo a
    # 60% da frase (2.5 s → 1.5 s), move o cursor vermelho e pinta o progresso da onda até ali.
    aba.click("#pausar")
    caixa = aba.locator("#waveformContainer").bounding_box()
    aba.mouse.click(caixa["x"] + caixa["width"] * 0.6, caixa["y"] + caixa["height"] / 2)
    assert abs(aba.eval_on_selector("#player video", "v => v.currentTime") - 1.5) < 0.05
    expect(aba.locator("#waveCursor")).to_have_attribute("style", re.compile(r"left: 60%"))
    progresso = _progresso_da_onda(aba)
    assert progresso is not None and abs(progresso - 60) < 2, progresso

    # Arrastar o cursor (comportamento existente) também leva o vídeo junto.
    aba.mouse.move(caixa["x"] + caixa["width"] * 0.6, caixa["y"] + caixa["height"] / 2)
    aba.mouse.down()
    aba.mouse.move(caixa["x"] + caixa["width"] * 0.2, caixa["y"] + caixa["height"] / 2, steps=5)
    aba.mouse.up()
    assert abs(aba.eval_on_selector("#player video", "v => v.currentTime") - 0.5) < 0.05

    # Segunda visita à mesma frase: a onda vem do banco (sem FFmpeg).
    with aba.expect_response(lambda r: "/waveform?" in r.url) as segunda:
        aba.reload()
    assert segunda.value.json()["cache"] is True
    assert segunda.value.json()["peaks"] == onda["peaks"]
    contexto.close()


def _mover_volume(aba, valor):
    aba.eval_on_selector(
        "#volume", "(s, v) => { s.value = v; s.dispatchEvent(new Event('input', {bubbles: true})); }", str(valor),
    )


def _volume_do_video(aba):
    return round(aba.eval_on_selector("#player video", "v => v.volume"), 2)


def _icone_do_volume(aba):
    return aba.eval_on_selector("#mudo i", "i => i.className")


def _aparencia(aba, seletor):
    """Tamanho e estilo de um elemento, para comparar o visual dos controles. Espera as fontes carregarem: os ícones
    são da fonte Font Awesome (CDN), e antes dela chegar o navegador mostra um caractere provisório mais estreito."""
    aba.evaluate("() => document.fonts.ready.then(() => true)")
    return aba.eval_on_selector(seletor, """e => { const r = e.getBoundingClientRect(), c = getComputedStyle(e);
        return {largura: Math.round(r.width), altura: Math.round(r.height), fonte: c.fontSize, cor: c.color,
                fundo: c.backgroundColor, opacidade: c.opacity}; }""")


def test_controle_de_volume_ao_lado_da_velocidade_e_salvo_na_conta(servidor, navegador):
    contexto, aba = _nova_aba(navegador)
    _cadastrar(aba, servidor, "ana@exemplo.com")
    aba.goto(f"{servidor}/decks")
    _criar_deck_pela_tela(aba, "Volume")
    deck_id = int(_linha(aba, "Volume").get_attribute("data-id"))
    _salvar_card(aba, servidor, deck_id, "Volume test")
    aba.goto(f"{servidor}/decks/{deck_id}/revisao")

    # Fica na barra do player, logo depois da velocidade, e travado até "Iniciar Estudos" (como a velocidade).
    assert aba.eval_on_selector(".grupo-ajustes", "g => [...g.children].map(c => c.className)") == [
        "controle-velocidade", "controle-volume",
    ]
    # Na barra fica só o alto-falante; o slider aparece numa caixa acima ao passar o mouse (verificado mais abaixo).
    _barra_do_player_numa_linha(aba)
    expect(aba.locator(".volume-flutuante")).to_be_hidden()
    expect(aba.locator("#volume")).to_be_disabled()
    expect(aba.locator("#mudo")).to_be_disabled()
    # Mesmo visual da velocidade (pedido do usuário): ícone, barra e valor iguais, travado ou liberado.
    for _ in ("travado", "liberado"):
        assert _aparencia(aba, "#mudo") == _aparencia(aba, ".controle-velocidade > i")
        assert _aparencia(aba, "#volume") == _aparencia(aba, "#velocidade")
        assert _aparencia(aba, "#volumeValor") == _aparencia(aba, "#velocidadeValor")
        if _ == "travado":
            _iniciar_estudos(aba)
    # Depois de "Iniciar Estudos" (antes, a proteção do player cobre a barra): a caixa aparece ao passar o mouse.
    aba.hover("#mudo")
    expect(aba.locator(".volume-flutuante")).to_be_visible()
    caixa, painel = aba.locator(".volume-flutuante").bounding_box(), aba.locator("#painelPrincipal").bounding_box()
    assert painel["x"] <= caixa["x"] and caixa["x"] + caixa["width"] <= painel["x"] + painel["width"]
    aba.mouse.move(0, 0)
    expect(aba.locator(".volume-flutuante")).to_be_hidden()
    expect(aba.locator("#volume")).to_be_enabled()
    expect(aba.locator("#volumeValor")).to_have_text("100%")
    assert _volume_do_video(aba) == 1 and _icone_do_volume(aba) == "fa fa-volume-up"

    # Arrastar muda o volume do vídeo na hora (rótulo e ícone acompanham) e salva na conta.
    with aba.expect_response(lambda r: _eh_salvamento(r.request)) as salvo:
        _mover_volume(aba, 0.3)
        expect(aba.locator("#volumeValor")).to_have_text("30%")
        assert _volume_do_video(aba) == 0.3 and _icone_do_volume(aba) == "fa fa-volume-down"
    assert salvo.value.json() == {"velocidade": 1.0, "volume": 0.3}

    # Clique no alto-falante: mudo; outro clique: volta para onde estava.
    aba.click("#mudo")
    expect(aba.locator("#volumeValor")).to_have_text("0%")
    assert _volume_do_video(aba) == 0 and _icone_do_volume(aba) == "fa fa-volume-off"
    expect(aba.locator("#mudo")).to_have_attribute("title", "Ativar o som")
    aba.click("#mudo")
    expect(aba.locator("#volumeValor")).to_have_text("30%")
    assert _volume_do_video(aba) == 0.3

    # Duplo clique no controle volta para 100% (como a velocidade volta para 1x).
    aba.hover("#mudo")
    aba.dblclick("#volume")
    expect(aba.locator("#volumeValor")).to_have_text("100%")
    assert _volume_do_video(aba) == 1

    # Mexer em velocidade e volume em seguida: um único salvamento com os dois.
    with aba.expect_response(lambda r: _eh_salvamento(r.request) and "volume" in (r.request.post_data or "")) as junto:
        _mover_slider(aba, 0.9)
        _mover_volume(aba, 0.6)
    assert junto.value.json() == {"velocidade": 0.9, "volume": 0.6}

    # Recarregar: o volume salvo volta (vídeo, controle e rótulo), junto com a velocidade.
    aba.reload()
    expect(aba.locator("#volumeValor")).to_have_text("60%")
    expect(aba.locator("#velocidadeValor")).to_have_text("0.90x")
    _iniciar_estudos(aba)
    assert _volume_do_video(aba) == 0.6 and _velocidade_do_video(aba) == 0.9
    contexto.close()


def test_video_sem_legenda_manual_mostra_a_tela_de_aviso(servidor, navegador, monkeypatch):
    """B10: só legenda automática (en-US) → tela de aviso própria; com manual → o modal de sempre."""
    def legendas(video_id):
        automatica = video_id.startswith("autom")
        blocos = [{"text": "Hello world.", "start": 0.0, "duration": 2.5}]
        return blocos, not automatica, "en-US" if automatica else "en"

    monkeypatch.setattr(youtube, "baixar_legendas", legendas)
    contexto, aba = _nova_aba(navegador)
    _cadastrar(aba, servidor, "ana@exemplo.com")

    # Sem legenda manual: a tela de aviso, com o idioma e o título; "Estudar mesmo assim" segue para o estudo.
    aba.goto(f"{servidor}/estudo?link=https://youtu.be/autom000001")
    expect(aba.locator("#modalLegendaAutomatica")).to_be_visible()
    expect(aba.locator("#modalLegendaTitulo")).to_be_hidden()
    expect(aba.locator("#idiomaLegendaAutomatica")).to_have_text("en-US")
    expect(aba.locator("#tituloLegendaAutomatica")).to_have_text("Vídeo simulado")
    aba.click("#estudarMesmoAssim")
    expect(aba.locator("#modalLegendaAutomatica")).to_be_hidden()
    expect(aba.locator("#legenda")).to_contain_text("Hello world.")
    _iniciar_estudos(aba)

    # "Escolher outro vídeo" volta para o início.
    aba.goto(f"{servidor}/estudo?link=https://youtu.be/autom000002")
    expect(aba.locator("#modalLegendaAutomatica")).to_be_visible()
    aba.click("#escolherOutroVideo")
    expect(aba).to_have_url(f"{servidor}/")
    expect(aba.locator(".url-input")).to_be_visible()

    # Com legenda manual: o modal de sempre (tipo e título), sem a tela de aviso.
    _estudar(aba, servidor, 1)
    expect(aba.locator("#modalLegendaTitulo")).to_be_visible()
    expect(aba.locator("#textologs")).to_contain_text("MANUAL (en)")
    expect(aba.locator("#modalLegendaAutomatica")).to_be_hidden()
    contexto.close()


def test_estados_vazios_explicam_e_oferecem_a_proxima_acao(servidor, navegador):
    """B12: dashboard sem Decks, modal de salvar Card sem Decks / filtro sem resultado, revisão de Deck vazio e de
    Deck em dia."""
    contexto, aba = _nova_aba(navegador)
    _cadastrar(aba, servidor, "ana@exemplo.com")

    # Dashboard de conta nova: motivo + "Estudar um vídeo" (vai ao início) + "Criar Deck" (abre o modal de sempre).
    aba.goto(f"{servidor}/decks")
    vazio = aba.locator(".dashboard-aviso .estado-vazio")
    expect(vazio).to_contain_text("Você ainda não tem Decks")
    expect(vazio).to_contain_text("marcador")
    vazio.get_by_role("button", name="Estudar um vídeo").click()
    expect(aba).to_have_url(f"{servidor}/")
    aba.goto(f"{servidor}/decks")
    aba.locator(".dashboard-aviso").get_by_role("button", name="Criar Deck").click()
    expect(aba.locator("#subModalCriarDeck")).to_be_visible()
    aba.click("#btnCancelarSubModal")

    # Modal "Salvar Card" no estudo: sem Decks, e filtro sem resultado.
    _estudar(aba, servidor, 1)
    aba.click("#botaoContinuar")
    aba.click("#salvar")
    expect(aba.locator("#listaDecks")).to_contain_text("Você ainda não tem Decks")
    aba.click("#btnCriarDeckModal")
    aba.fill("#novoNomeDeckInput", "Inglês")
    aba.click("#btnConfirmarCriarDeck")
    expect(aba.locator("#listaDecks .modal-deck-item", has_text="Inglês")).to_be_visible()
    aba.fill("#filtroInput", "xyz")
    expect(aba.locator("#listaDecks .sem-resultado")).to_have_text("Nenhum Deck com “xyz”.")
    aba.fill("#filtroInput", "ing")
    expect(aba.locator("#listaDecks .sem-resultado")).to_have_count(0)
    aba.click("#btnCancelarRodape")

    # Revisão de um Deck sem Cards.
    aba.goto(f"{servidor}/decks")
    deck_id = int(_linha(aba, "Inglês").get_attribute("data-id"))
    aba.goto(f"{servidor}/decks/{deck_id}/revisao")
    expect(aba.locator("#revisaoVazia")).to_be_visible()
    expect(aba.locator("#revisaoVazia")).to_contain_text("Este Deck ainda não tem Cards")

    # Revisão de um Deck todo revisado: "Tudo revisado" com a data da próxima ("Fácil" = 7 dias, no 1º Card).
    _salvar_card(aba, servidor, deck_id, "Review me")
    card_id = aba.request.get(f"{servidor}/api/decks/{deck_id}/revisao").json()[0]["id"]
    assert aba.request.post(f"{servidor}/api/cards/{card_id}/avaliacao", data={"dificuldade": "facil"}).ok
    aba.goto(f"{servidor}/decks/{deck_id}/revisao")
    expect(aba.locator("#revisaoVazia")).to_contain_text("Tudo revisado!")
    proxima = re.compile(r"Próxima revisão deste Deck: em 7 dias \(\d\d/\d\d\)")
    expect(aba.locator("#revisaoVazia")).to_contain_text(proxima)
    aba.locator("#revisaoVazia").get_by_role("button", name="Voltar aos Decks").click()
    expect(aba).to_have_url(f"{servidor}/decks")
    contexto.close()


def test_roteiro_integrado_de_outubro(servidor, navegador, monkeypatch):
    """Out-12: os blocos de outubro juntos, como um usuário usaria. Legenda automática (B10) → onda pronta do
    servidor (B9) → velocidade e volume salvos (B8, B9.2) → salvar Card no Deck (agosto) → revisar na velocidade e
    no volume salvos → "Fácil" → revisão em dia (B12). Tokens (B11) e erros (B7) aparecem ao longo do caminho."""
    def legendas(video_id):
        return [{"text": "Hello world.", "start": 0.0, "duration": 2.5}], False, "en-US"

    monkeypatch.setattr(youtube, "baixar_legendas", legendas)
    contexto, aba = _nova_aba(navegador)
    _cadastrar(aba, servidor, "ana@exemplo.com")

    with aba.expect_response(lambda r: "/waveform?" in r.url) as onda:
        aba.goto(f"{servidor}/estudo?link=https://youtu.be/autom000001")
    expect(aba.locator("#modalLegendaAutomatica")).to_be_visible()
    expect(aba.locator("#token-count")).to_have_text("4")
    aba.click("#estudarMesmoAssim")
    assert onda.value.json()["cache"] is False and len(onda.value.json()["peaks"]) == 400
    _iniciar_estudos(aba)

    with aba.expect_response(lambda r: _eh_salvamento(r.request) and "volume" in (r.request.post_data or "")):
        _mover_slider(aba, 0.8)
        _mover_volume(aba, 0.5)

    aba.click("#salvar")
    aba.click("#btnCriarDeckModal")
    aba.fill("#novoNomeDeckInput", "Outubro")
    aba.click("#btnConfirmarCriarDeck")
    aba.locator("#listaDecks .modal-deck-item", has_text="Outubro").click()
    aba.click("#btnSalvar")
    expect(aba.locator("#salvar")).to_have_class(re.compile("salvo"))

    aba.click(".nav-btn:has-text('Revisar')")
    expect(_linha(aba, "Outubro").locator(".td-novos")).to_have_text("1")
    _linha(aba, "Outubro").dblclick()
    expect(aba.locator("#legenda")).to_contain_text("Hello world.")
    expect(aba.locator("#velocidadeValor")).to_have_text("0.80x")
    expect(aba.locator("#volumeValor")).to_have_text("50%")
    _iniciar_estudos(aba)
    assert _velocidade_do_video(aba) == 0.8 and _volume_do_video(aba) == 0.5
    aba.click("#facil")
    expect(aba).to_have_url(f"{servidor}/decks")
    _linha(aba, "Outubro").dblclick()
    expect(aba.locator("#revisaoVazia")).to_contain_text("Tudo revisado!")
    contexto.close()


def test_sessao_que_vence_no_estudo_leva_ao_login_pela_onda(servidor, navegador, monkeypatch):
    """B13: a onda é buscada fora das chamadas comuns da página; com a sessão vencida, ir para a próxima frase pede
    a onda dela, recebe 401 e leva ao login (antes, só mostraria "onda indisponível")."""
    monkeypatch.setattr(youtube, "baixar_legendas", lambda video_id: ([
        {"text": "Hello world.", "start": 0.0, "duration": 1.2},
        {"text": "Second line here.", "start": 1.3, "duration": 1.2},
    ], True, "en"))
    contexto, aba = _nova_aba(navegador)
    _cadastrar(aba, servidor, "ana@exemplo.com")
    _estudar(aba, servidor, 1)
    aba.click("#botaoContinuar")
    expect(aba.locator("#contadorFrase")).to_have_text("1 / 2")
    _iniciar_estudos(aba)

    # Isola a onda: o karaokê da nova frase também consulta a API (e já levava ao login antes do B13). Aqui ele é
    # respondido pelo próprio navegador, então só a busca da onda chega ao servidor sem sessão.
    aba.route("**/palavras?**", lambda rota: rota.fulfill(json={"tempos": None, "fonte": "estimativa"}))
    contexto.clear_cookies()  # a sessão vence com a página aberta
    aba.click("#proximo")

    expect(aba).to_have_url(re.compile(re.escape(f"{servidor}/login?proximo=") + r"%2Festudo"))
    contexto.close()
