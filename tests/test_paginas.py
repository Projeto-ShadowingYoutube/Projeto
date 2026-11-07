"""Páginas HTML (B6): exigem login, levam ao login com ?proximo= e protegem contra open redirect."""
from urllib.parse import urlencode

import pytest

from app.api.paginas import caminho_seguro

HTMX = {"HX-Request": "true"}
PAGINAS_PROTEGIDAS = ["/", "/inicio", "/estudo?link=abc", "/decks", "/decks/1/revisao"]


@pytest.mark.parametrize("caminho", PAGINAS_PROTEGIDAS)
def test_sem_login_abrir_a_pagina_leva_ao_login_com_proximo(client, caminho):
    resposta = client.get(caminho, follow_redirects=False)

    assert resposta.status_code == 303
    assert resposta.headers["location"] == f"/login?{urlencode({'proximo': caminho})}"


@pytest.mark.parametrize("caminho", PAGINAS_PROTEGIDAS)
def test_sem_login_navegacao_htmx_recebe_hx_redirect(client, caminho):
    resposta = client.get(caminho, headers=HTMX, follow_redirects=False)

    assert resposta.status_code == 200
    assert resposta.headers["hx-redirect"].startswith("/login?proximo=")


def test_logado_recebe_a_pagina_com_o_usuario_na_navbar(entrar_como):
    ana = entrar_como("ana@exemplo.com")

    pagina = ana.get("/decks")
    miolo = ana.get("/decks", headers=HTMX)

    assert pagina.status_code == 200
    assert "ana@exemplo.com" in pagina.text and 'id="sair"' in pagina.text
    assert 'data-pagina="decks"' in miolo.text


def test_paginas_nao_ficam_no_cache_do_navegador(client, entrar_como):
    assert client.get("/login").headers["cache-control"] == "no-store"
    assert entrar_como("ana@exemplo.com").get("/decks").headers["cache-control"] == "no-store"


def test_login_e_cadastro_abrem_sem_sessao_e_sem_navbar_de_usuario(client):
    for caminho, pagina in [("/login", "login"), ("/cadastro", "cadastro")]:
        completa = client.get(caminho)
        miolo = client.get(caminho, headers=HTMX)
        assert completa.status_code == 200
        assert 'id="sair"' not in completa.text and 'id="token-count"' not in completa.text
        assert f'data-pagina="{pagina}"' in miolo.text


def test_logado_que_abre_o_login_vai_para_o_proximo_ou_para_o_inicio(entrar_como):
    ana = entrar_como("ana@exemplo.com")

    assert ana.get("/login", follow_redirects=False).headers["location"] == "/"
    assert ana.get("/login?proximo=/decks", follow_redirects=False).headers["location"] == "/decks"
    assert ana.get("/cadastro", headers=HTMX).headers["hx-redirect"] == "/"


@pytest.mark.parametrize("proximo", ["https://malicioso.com", "//malicioso.com", "/\\malicioso.com", "decks", ""])
def test_proximo_externo_ou_invalido_vira_o_inicio(client, entrar_como, proximo):
    """Open redirect: o login nunca manda o usuário para fora do app."""
    assert caminho_seguro(proximo) == "/"
    miolo = client.get("/login", params={"proximo": proximo}, headers=HTMX)
    assert 'data-proximo="/"' in miolo.text
    ana = entrar_como("ana@exemplo.com")  # cada caso roda num banco novo
    assert ana.get("/login", params={"proximo": proximo}, follow_redirects=False).headers["location"] == "/"


def test_proximo_e_escapado_no_html(client):
    miolo = client.get("/login", params={"proximo": '/"><script>alert(1)</script>'}, headers=HTMX)

    assert "<script>alert(1)</script>" not in miolo.text
    assert "&lt;script&gt;" in miolo.text or "%3Cscript%3E" in miolo.text
