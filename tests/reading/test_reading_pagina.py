"""Bloco R9: página /reading (rota, template, pontos de encaixe, arquivos estáticos e segurança do JS).

O comportamento da tela (timer, F5, encerrar) está no teste de navegador test_reading_e2e.py (E2E=1).
"""
import re
from pathlib import Path

import pytest
from fastapi.routing import APIRoute

from app.main import app

HTMX = {"HX-Request": "true"}
RAIZ = Path(__file__).resolve().parents[2]
JS_DO_READING = [RAIZ / "app/static/js/paginas/reading.js", RAIZ / "app/static/js/nucleo/api-reading.js"]


def test_sem_login_vai_para_o_login_e_volta(client):
    resposta = client.get("/reading", follow_redirects=False)
    assert resposta.status_code == 303 and resposta.headers["location"] == "/login?proximo=%2Freading"
    htmx = client.get("/reading", headers=HTMX, follow_redirects=False)
    assert htmx.headers["HX-Redirect"] == "/login?proximo=%2Freading"


def test_carregamento_completo_tem_o_botao_e_o_css(entrar_como):
    html = entrar_como("ana@exemplo.com").get("/reading").text
    assert '<link rel="stylesheet" href="/static/css/reading.css">' in html
    assert 'hx-get="/reading" hx-target="main" hx-push-url="true">📖' in html
    assert '<main class="content" hx-get="/reading"' in html  # o base.html carrega o miolo pela mesma URL


def test_o_desafio_da_url_e_mantido_no_f5(entrar_como):
    html = entrar_como("ana@exemplo.com").get("/reading?desafio=5").text
    assert 'hx-get="/reading?desafio=5"' in html


def test_navegacao_htmx_entrega_o_miolo(entrar_como):
    resposta = entrar_como("ana@exemplo.com").get("/reading", headers=HTMX)
    assert resposta.status_code == 200 and resposta.headers["cache-control"] == "no-store"
    html = resposta.text
    assert 'data-pagina="reading"' in html and "<html" not in html
    for etapa in ("inicio", "leitura", "perguntas"):
        assert f'data-etapa="{etapa}"' in html
    # Padrões (DR1, DR4): Wikipedia e 200 ppm já marcados; as 3 velocidades.
    assert re.search(r'value="wikipedia" checked', html) and re.search(r'value="200" checked', html)
    assert all(f'value="{ppm}"' in html for ppm in (150, 200, 250))
    assert 'id="readingAviso"' in html  # o aviso de IA entra antes do botão de começar
    assert html.index('id="readingAviso"') < html.index('id="readingComecar"')


@pytest.mark.parametrize("arquivo", ["/static/js/paginas/reading.js", "/static/js/nucleo/api-reading.js",
                                     "/static/css/reading.css"])
def test_arquivos_estaticos(client, arquivo):
    assert client.get(arquivo).status_code == 200


def test_main_js_importa_a_pagina():
    main = (RAIZ / "app/static/js/main.js").read_text(encoding="utf-8")
    assert re.search(r'^import "\./paginas/reading\.js";$', main, re.MULTILINE)


@pytest.mark.parametrize("arquivo", JS_DO_READING, ids=lambda p: p.name)
def test_js_nunca_monta_html_com_texto(arquivo):
    """Conteúdo da API (texto da Wikipedia, LLM, respostas) só entra por textContent: sem brecha para XSS."""
    codigo = arquivo.read_text(encoding="utf-8")
    for proibido in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert proibido not in codigo, f"{proibido} em {arquivo.name}"


def test_cliente_usa_as_rotas_que_existem():
    """Cada rota do api-reading.js existe na API (um erro de digitação no front apareceria só no navegador)."""
    caminhos = {r.path for r in app.routes if isinstance(r, APIRoute)}
    cliente = (RAIZ / "app/static/js/nucleo/api-reading.js").read_text(encoding="utf-8")
    assert '"/api/reading/challenges"' in cliente and "/api/reading/challenges" in caminhos
    sufixos = re.findall(r"\$\{BASE\}/\$\{id\}(/[\w-]+)?`", cliente)
    assert len(sufixos) == 6  # resumo, texto, encerrar-leitura, respostas, resultado, avaliar
    for sufixo in sufixos:
        assert f"/api/reading/challenges/{{desafio_id}}{sufixo}" in caminhos, sufixo
