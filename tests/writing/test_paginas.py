"""W4: página /writing (login, encaixes na navbar/CSS/JS) e paridade da contagem de palavras entre JS e Python."""
import json
import re
import shutil
import subprocess
from urllib.parse import urlencode

import pytest

from app import config
from app.services import writing_texto
from app.services.writing_texto import contar_palavras

HTMX = {"HX-Request": "true"}
JS_DA_PAGINA = config.PASTA_STATIC / "js" / "paginas" / "writing.js"

# A expressão da tela (writing.js) e a do servidor (writing_texto.py) descrevem a mesma regra em sintaxes diferentes.
REGEX_JS = r"/[\p{L}\p{N}]+(?:['’-][\p{L}\p{N}]+)*/gu"
REGEX_PYTHON = r"[^\W_]+(?:['’\-][^\W_]+)*"


def test_sem_login_abrir_a_pagina_leva_ao_login(client):
    resposta = client.get("/writing", follow_redirects=False)
    assert resposta.status_code == 303
    assert resposta.headers["location"] == f"/login?{urlencode({'proximo': '/writing'})}"


def test_sem_login_navegacao_htmx_recebe_hx_redirect(client):
    resposta = client.get("/writing", headers=HTMX, follow_redirects=False)
    assert resposta.headers["hx-redirect"].startswith("/login?proximo=")


def test_logado_recebe_a_pagina_com_as_tres_telas(entrar_como):
    miolo = entrar_como("ana@exemplo.com").get("/writing", headers=HTMX)

    assert miolo.status_code == 200
    assert miolo.headers["cache-control"] == "no-store"
    assert 'data-pagina="writing"' in miolo.text
    for tela in ("inicio", "editor", "fim"):
        assert f'data-tela="{tela}"' in miolo.text


def test_recarregar_com_a_redacao_na_url_entrega_a_pagina(entrar_como):
    """F5 em /writing?redacao=7: o base.html carrega o miolo pela mesma URL (com a consulta); o JS reabre a redação."""
    pagina = entrar_como("ana@exemplo.com").get("/writing?redacao=7")
    assert pagina.status_code == 200
    assert 'hx-get="/writing?redacao=7"' in pagina.text


def test_base_html_carrega_o_css_do_writing(entrar_como):
    """Encaixe de CSS do base.html. Não há botão na navbar (D13): o acesso é pela URL /writing, e a interface inicial
    que levará aos desafios fica com o tech lead."""
    pagina = entrar_como("ana@exemplo.com").get("/decks").text
    assert '<link rel="stylesheet" href="/static/css/writing.css">' in pagina


@pytest.mark.parametrize("arquivo", [
    "/static/js/paginas/writing.js", "/static/js/nucleo/api-writing.js", "/static/css/writing.css",
])
def test_arquivos_estaticos_sao_servidos(client, arquivo):
    assert client.get(arquivo).status_code == 200


def test_main_js_importa_a_pagina(client):
    """Encaixe do main.js: sem este import, a página carrega mas o JS dela nunca roda."""
    main_js = client.get("/static/js/main.js").text
    assert re.search(r'^import "\./paginas/writing\.js";\r?$', main_js, re.MULTILINE)  # o arquivo usa \r\n


def test_contagem_de_palavras_usa_a_mesma_regra_no_js_e_no_python():
    """Se alguém mudar a regra de um lado e esquecer o outro, a tela e o resultado deixam de bater."""
    js = JS_DA_PAGINA.read_text(encoding="utf-8")
    assert f"const PALAVRA = {REGEX_JS};" in js
    assert writing_texto._PALAVRA.pattern == REGEX_PYTHON
    assert 'normalize("NFC")' in js  # a normalização também precisa existir nos dois lados


# Roda a contarPalavras REAL do writing.js (extraída do arquivo) e devolve as contagens em JSON.
_SCRIPT_NODE = r"""
const fs = require("node:fs");
const fonte = fs.readFileSync(process.argv[1], "utf8");
const regex = fonte.match(/^const PALAVRA = (.*);\r?$/m)[1];
const funcao = fonte.match(/export function contarPalavras[\s\S]*?\n}/)[0].replace("export ", "");
const contar = new Function(`const PALAVRA = ${regex};\n${funcao}\nreturn contarPalavras;`)();
const textos = JSON.parse(fs.readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify(textos.map(contar)));
"""

TEXTOS_DE_PARIDADE = [
    "I don't agree.", "I don’t agree.", "a well-known fact", "In 2024, 60% agreed", "word — word", "word - word",
    "word,word", "café naïve", "naïve", "snake_case", "'quoted' -dash- end-", "First line.\nSecond.\n\nThird.",
    "", "   \n\t ", "!!! ... ---", "São Paulo é ótima", "e-mail, rock'n'roll, 3.5 million",
    "über-cool ñandú 東京 مرحبا",
]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js não instalado: paridade JS × Python não verificada")
def test_contagem_do_js_da_o_mesmo_resultado_que_a_do_python():
    """Executa o JS de verdade (Node.js), não só compara o texto das expressões."""
    resultado = subprocess.run(
        ["node", "-e", _SCRIPT_NODE, str(JS_DA_PAGINA)], input=json.dumps(TEXTOS_DE_PARIDADE, ensure_ascii=False),
        capture_output=True, text=True, encoding="utf-8", timeout=30, check=True,
    )
    assert json.loads(resultado.stdout) == [contar_palavras(texto) for texto in TEXTOS_DE_PARIDADE]
