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


def test_logado_recebe_a_pagina_com_todas_as_telas(entrar_como):
    miolo = entrar_como("ana@exemplo.com").get("/writing", headers=HTMX)

    assert miolo.status_code == 200
    assert miolo.headers["cache-control"] == "no-store"
    assert 'data-pagina="writing"' in miolo.text
    for tela in ("inicio", "editor", "fim", "resultado", "rewrite"):
        assert f'data-tela="{tela}"' in miolo.text
    assert "data-res-rewrite" in miolo.text  # o caminho do resultado para o Rewrite Challenge
    assert 'data-rw-erro role="alert"' in miolo.text  # erro do envio do Rewrite na própria tela (não no modal)


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
    "/static/js/componentes/writing-destaques.js",
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


# --- W7: destaques da redação corrigida (componentes/writing-destaques.js, executado no Node.js) ---

MODULO_DESTAQUES = config.PASTA_STATIC / "js" / "componentes" / "writing-destaques.js"
# Importa o módulo REAL (não uma cópia) e devolve as partes de cada caso em JSON.
_SCRIPT_DESTAQUES = """
import { readFileSync } from "node:fs";
const { partesDoTexto } = await import(process.argv[1]);
const casos = JSON.parse(readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify(casos.map(([texto, trechos]) => partesDoTexto(texto, trechos))));
"""


def _partes_no_node(casos: list) -> list:
    resultado = subprocess.run(
        ["node", "--input-type=module", "-e", _SCRIPT_DESTAQUES, "--", MODULO_DESTAQUES.as_uri()],
        input=json.dumps(casos, ensure_ascii=False), capture_output=True, text=True, encoding="utf-8",
        timeout=30, check=False,
    )
    assert resultado.returncode == 0, resultado.stderr
    return json.loads(resultado.stdout)


def _trecho(texto: str, citacao: str, a_partir_de: int = 0) -> dict:
    """Posições como o servidor calcula (Python: caracteres Unicode)."""
    inicio = texto.index(citacao, a_partir_de)
    return {"inicio": inicio, "fim": inicio + len(citacao)}


EMOJI = "Café 😀 naïve 👍🏽 — people thinks so.\nNew line: it have problems."
CASOS_DE_DESTAQUE = {
    "emoji e acentos antes do trecho": (EMOJI, [_trecho(EMOJI, "people thinks"), _trecho(EMOJI, "it have")]),
    "sem trechos": ("Just a text.", []),
    "trecho no começo e no fim": ("bad start and bad end", [{"inicio": 0, "fim": 9}, {"inicio": 14, "fim": 21}]),
    "fora dos limites e vazio são ignorados": ("short text", [{"inicio": 6, "fim": 99}, {"inicio": 3, "fim": 3},
                                                              {"inicio": -1, "fim": 2}, {"inicio": 0, "fim": 5}]),
    "sobreposto é ignorado": ("one two three", [{"inicio": 0, "fim": 7}, {"inicio": 4, "fim": 13}]),
    "fora de ordem": ("aaa bbb ccc", [{"inicio": 8, "fim": 11}, {"inicio": 0, "fim": 3}]),
}


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js não instalado: destaques não verificados")
def test_partes_do_texto_executado_no_node():
    casos = list(CASOS_DE_DESTAQUE.values())
    resultados = dict(zip(CASOS_DE_DESTAQUE, _partes_no_node([[t, tr] for t, tr in casos]), strict=True))

    for nome, (texto, trechos) in CASOS_DE_DESTAQUE.items():
        partes = resultados[nome]
        assert "".join(p["texto"] for p in partes) == texto, nome  # nunca perde nem duplica texto
        for parte in partes:
            if parte["trecho"] is not None:  # o pedaço destacado é exatamente o que o servidor apontou
                trecho = trechos[parte["trecho"]]
                assert parte["texto"] == texto[trecho["inicio"]:trecho["fim"]], nome

    destacados = lambda nome: [p["texto"] for p in resultados[nome] if p["trecho"] is not None]  # noqa: E731
    assert destacados("emoji e acentos antes do trecho") == ["people thinks", "it have"]
    assert destacados("sem trechos") == []
    assert destacados("trecho no começo e no fim") == ["bad start", "bad end"]
    assert destacados("fora dos limites e vazio são ignorados") == ["short"]
    assert destacados("sobreposto é ignorado") == ["one two"]
    assert destacados("fora de ordem") == ["aaa", "ccc"]


# --- W9: trecho destacado dentro da frase do Rewrite (partesDaFrase, executada no Node.js) ---

_SCRIPT_FRASE = """
import { readFileSync } from "node:fs";
const { partesDaFrase } = await import(process.argv[1]);
const casos = JSON.parse(readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify(casos.map(([frase, citacao]) => partesDaFrase(frase, citacao))));
"""

CASOS_DA_FRASE = {
    "no meio": ("Many student cant pay the fees.", "student cant"),
    "no começo": ("Many student cant pay the fees.", "Many"),
    "no fim": ("Many student cant pay the fees.", "the fees."),
    "emoji e acentos antes": ("Café 😀 naïve, they gives up.", "they gives"),
    "repetida: a primeira": ("the the end", "the"),
    "ausente": ("A sentence.", "not here"),
    "citação vazia": ("A sentence.", ""),
    # Sem a proteção, o JS converteria null no texto "null" e destacaria a palavra "null" da frase.
    "citação nula": ("A null pointer.", None),
}


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js não instalado: destaque na frase não verificado")
def test_partes_da_frase_executado_no_node():
    resultado = subprocess.run(
        ["node", "--input-type=module", "-e", _SCRIPT_FRASE, "--", MODULO_DESTAQUES.as_uri()],
        input=json.dumps(list(CASOS_DA_FRASE.values()), ensure_ascii=False), capture_output=True, text=True,
        encoding="utf-8", timeout=30, check=False,
    )
    assert resultado.returncode == 0, resultado.stderr
    resultados = dict(zip(CASOS_DA_FRASE, json.loads(resultado.stdout), strict=True))

    for nome, (frase, _citacao) in CASOS_DA_FRASE.items():
        assert "".join(p["texto"] for p in resultados[nome]) == frase, nome  # nunca perde nem duplica texto

    destaque = lambda nome: [p["texto"] for p in resultados[nome] if p["destaque"]]  # noqa: E731
    assert destaque("no meio") == ["student cant"]
    assert destaque("no começo") == ["Many"] and resultados["no começo"][0]["destaque"] is True
    assert destaque("no fim") == ["the fees."] and resultados["no fim"][-1]["destaque"] is True
    assert destaque("emoji e acentos antes") == ["they gives"]
    assert resultados["repetida: a primeira"] == [{"texto": "the", "destaque": True}, {"texto": " the end",
                                                                                          "destaque": False}]
    assert resultados["ausente"] == [{"texto": "A sentence.", "destaque": False}]
    assert resultados["citação vazia"] == [{"texto": "A sentence.", "destaque": False}]
    assert resultados["citação nula"] == [{"texto": "A null pointer.", "destaque": False}]
