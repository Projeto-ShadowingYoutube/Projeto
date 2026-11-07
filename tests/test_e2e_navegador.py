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
from playwright.sync_api import expect, sync_playwright  # noqa: E402
from sqlmodel import Session, create_engine  # noqa: E402

from app import config, db, migrar  # noqa: E402
from app.main import app  # noqa: E402
from app.services import karaoke  # noqa: E402

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
    expect(aba.locator(".dashboard-aviso")).to_contain_text("Nenhum deck cadastrado")

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
    expect(bruno.locator(".dashboard-aviso")).to_contain_text("Nenhum deck cadastrado")

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
