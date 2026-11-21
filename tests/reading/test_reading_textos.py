"""Bloco R2: limpeza dos textos, seleção do trecho (só parágrafos inteiros) e tempo de leitura.

Tudo com strings fixas: nenhuma rede, nenhum banco.
"""
import pytest

from app.services import reading_textos as rt


def paragrafo(palavras: int, palavra: str = "bees") -> str:
    """Um parágrafo com exatamente `palavras` palavras, terminado em ponto final."""
    return " ".join([palavra] * palavras) + "."


# --- normalizar ---

def test_normalizar_remove_referencias_html_e_espacos():
    bruto = "Bees  make <b>honey</b>[1] and wax[citation needed]. They &amp; ants are insects [a]."
    assert rt.normalizar(bruto) == "Bees make honey and wax. They & ants are insects."


def test_normalizar_mantem_as_quebras_de_paragrafo():
    assert rt.normalizar("Primeira linha.\n\n\n\nSegunda linha.") == "Primeira linha.\n\nSegunda linha."


# --- limpar_wikipedia ---

WIKIPEDIA = """The honey bee is a eusocial flying insect within the genus Apis of the bee clade.[1]
It is known for the construction of perennial colonial nests from wax by its workers.

== Etymology ==
The genus name Apis is Latin for bee, and it has been used since ancient times by writers.

== Species ==
Western honey bee
Eastern honey bee
Giant honey bee

=== Behaviour ===
Honey bees communicate the location of food through a movement called the waggle dance.

== See also ==
Beekeeping practices around the world are described in many different articles and books.

== References ==
Smith, J. (2001). Bees and their world. Oxford University Press, United Kingdom, page 12.
"""


def test_wikipedia_separa_as_secoes_pelos_titulos():
    secoes = rt.limpar_wikipedia(WIKIPEDIA)
    assert len(secoes) == 3  # introdução, Etymology, Behaviour (Species só tinha lista e some)
    assert secoes[0][0].startswith("The honey bee is a eusocial")
    assert len(secoes[0]) == 2
    assert secoes[1] == ["The genus name Apis is Latin for bee, and it has been used since ancient times by writers."]
    assert secoes[2][0].startswith("Honey bees communicate")


def test_wikipedia_remove_listas_referencias_e_secoes_finais():
    texto = "\n".join(p for secao in rt.limpar_wikipedia(WIKIPEDIA) for p in secao)
    assert "Western honey bee" not in texto  # item de lista
    assert "[1]" not in texto
    assert "Beekeeping" not in texto  # "See also" em diante fica de fora
    assert "Oxford" not in texto


def test_wikipedia_vazio():
    assert rt.limpar_wikipedia("") == []
    assert rt.limpar_wikipedia("== References ==\nSmith, J. (2001). A long reference line that ends in a dot.") == []


# --- limpar_gutenberg ---

GUTENBERG = """The Project Gutenberg eBook of Bees, by Someone

This eBook is for the use of anyone anywhere in the United States and most other parts.

*** START OF THE PROJECT GUTENBERG EBOOK BEES ***

CHAPTER I

The bees woke up early in the morning, as they
always did, and flew out of the hive to look for
the first flowers of the season.

[Illustration: A bee on a flower]

They came back at noon, tired but happy, carrying
pollen on their legs and nectar in their stomachs.

CHAPTER II. THE QUEEN

The queen stayed inside the hive all day long and laid
hundreds of eggs in the small wax cells of the comb.

*** END OF THE PROJECT GUTENBERG EBOOK BEES ***

This file should be named bees.txt and is released under the Project Gutenberg License.
"""


def test_gutenberg_fica_so_com_o_miolo_e_junta_as_linhas():
    secoes = rt.limpar_gutenberg(GUTENBERG)
    assert secoes == [
        [
            "The bees woke up early in the morning, as they always did, and flew out of the hive to look for "
            "the first flowers of the season.",
            "They came back at noon, tired but happy, carrying pollen on their legs and nectar in their stomachs.",
        ],
        ["The queen stayed inside the hive all day long and laid hundreds of eggs in the small wax cells of the comb."],
    ]


def test_gutenberg_remove_cabecalho_rodape_e_ilustracoes():
    texto = " ".join(p for secao in rt.limpar_gutenberg(GUTENBERG) for p in secao)
    assert "eBook" not in texto and "License" not in texto
    assert "Illustration" not in texto
    assert "CHAPTER" not in texto


LIVRO_COM_PREFACIO = """*** START OF THE PROJECT GUTENBERG EBOOK BEES ***

CONTENTS

CHAPTER I. The Hive
CHAPTER II. The Queen

PREFACE

This little book was written for children who like to watch the bees in the garden.

CHAPTER I. THE HIVE

The bees woke up early in the morning and flew out of the hive to look for flowers.

CHAPTER II. THE QUEEN

The queen stayed inside the hive all day long and laid hundreds of eggs in the cells.

*** END OF THE PROJECT GUTENBERG EBOOK BEES ***
"""


def test_gutenberg_descarta_sumario_e_prefacio_e_comeca_no_capitulo_1():
    """DR13: o capítulo 1 fica em primeiro (e ganha a prioridade da "introdução" no selecionar_trecho)."""
    secoes = rt.limpar_gutenberg(LIVRO_COM_PREFACIO)
    assert secoes == [
        ["The bees woke up early in the morning and flew out of the hive to look for flowers."],
        ["The queen stayed inside the hive all day long and laid hundreds of eggs in the cells."],
    ]


def test_gutenberg_sem_capitulos_mantem_todas_as_secoes():
    livro = ("INTRODUCTION\n\nThe bees woke up early in the morning and flew out of the hive.\n\n"
             "THE QUEEN\n\nThe queen stayed inside the hive all day long and laid many eggs.")
    assert len(rt.limpar_gutenberg(livro)) == 2


def test_gutenberg_sem_marcas_usa_o_texto_inteiro():
    secoes = rt.limpar_gutenberg("The bees flew out of the hive to look for flowers in the field.")
    assert secoes == [["The bees flew out of the hive to look for flowers in the field."]]


# --- eh_inadequado ---

@pytest.mark.parametrize("titulo, texto", [
    ("List of bee species", "Bees are insects that live in colonies."),
    ("Mercury (disambiguation)", "Mercury is a planet."),
    ("Mercury", "Mercury may refer to: a planet, an element or a god."),
    ("Some battle", "The massacre happened in the village."),
    ("Some person", "He was convicted of murder in 1902."),
])
def test_inadequados_sao_recusados(titulo, texto):
    assert rt.eh_inadequado(titulo, texto)


def test_texto_normal_passa_e_o_filtro_respeita_o_inicio_das_palavras():
    # "rapes" e "porn" aparecem dentro de outras palavras; só o início de palavra conta.
    assert not rt.eh_inadequado("Honey bee", "Bees visit grapes and drapes near the hive, and also popcorn.")


# --- selecionar_trecho (DR9) ---

def test_introducao_que_cabe_e_usada():
    intro = [paragrafo(150), paragrafo(150)]
    assert rt.selecionar_trecho([intro]) == "\n\n".join(intro)


def test_introducao_tem_prioridade_sobre_secao_maior():
    intro = [paragrafo(300, "intro")]
    outra = [paragrafo(550, "outra")]
    assert rt.selecionar_trecho([intro, outra]) == intro[0]


def test_introducao_curta_usa_o_maior_bloco_de_outra_secao():
    intro = [paragrafo(100, "intro")]
    secao_b = [paragrafo(260, "b")]
    secao_c = [paragrafo(200, "c"), paragrafo(200, "c"), paragrafo(300, "c")]
    # Blocos válidos: B = 260; em C, 200+200 = 400 e 200+300 = 500 (os três juntos passam de 600). O maior é 500.
    assert rt.selecionar_trecho([intro, secao_b, secao_c]) == "\n\n".join(secao_c[1:])


def test_introducao_longa_leva_so_os_paragrafos_que_cabem():
    intro = [paragrafo(250, "a"), paragrafo(250, "b"), paragrafo(250, "c")]
    assert rt.selecionar_trecho([intro]) == "\n\n".join(intro[:2])  # 500; o 3º passaria de 600


def test_bloco_nunca_atravessa_duas_secoes():
    """Cada seção tem 200 palavras: juntas dariam 400, mas misturariam assuntos."""
    assert rt.selecionar_trecho([[paragrafo(100)], [paragrafo(200)], [paragrafo(200)]]) is None


def test_paragrafo_gigante_nao_e_cortado():
    assert rt.selecionar_trecho([[paragrafo(700)]]) is None


@pytest.mark.parametrize("palavras, aceito", [(249, False), (250, True), (600, True), (601, False)])
def test_limites_do_tamanho(palavras, aceito):
    trecho = rt.selecionar_trecho([[paragrafo(palavras)]])
    assert (trecho is not None) is aceito
    if aceito:
        assert rt.contar_palavras(trecho) == palavras


def test_sem_secoes():
    assert rt.selecionar_trecho([]) is None


@pytest.mark.parametrize("secoes", [
    [[paragrafo(120, "a"), paragrafo(90, "b"), paragrafo(200, "c"), paragrafo(260, "d")]],
    [[paragrafo(40, "x")], [paragrafo(310, "y"), paragrafo(330, "z")], [paragrafo(80, "w"), paragrafo(240, "v")]],
    [[paragrafo(590, "a"), paragrafo(20, "b")]],
])
def test_todo_paragrafo_do_trecho_existe_inteiro_numa_unica_secao(secoes):
    trecho = rt.selecionar_trecho(secoes)
    assert trecho is not None
    partes = trecho.split("\n\n")
    assert any(all(p in secao for p in partes) for secao in secoes)
    assert rt.PALAVRAS_MIN <= rt.contar_palavras(trecho) <= rt.PALAVRAS_MAX


def test_do_texto_bruto_ao_trecho():
    """Wikipedia limpa → trecho: o fluxo que as fontes vão usar no R3."""
    bruto = "Intro sentence with enough words to be a real paragraph here.\n\n== History ==\n" + "\n".join(
        paragrafo(100, "history") for _ in range(4))
    trecho = rt.selecionar_trecho(rt.limpar_wikipedia(bruto))
    assert rt.contar_palavras(trecho) == 400 and "Intro" not in trecho


# --- contar_palavras ---

@pytest.mark.parametrize("texto, esperado", [
    ("Bees make honey.", 3),
    ("Don't touch the well-known hive, it’s 2 meters tall!", 9),
    ("  ", 0),
    ("— , . !", 0),
])
def test_contar_palavras(texto, esperado):
    assert rt.contar_palavras(texto) == esperado


# --- limite_leitura_segundos (DR10: múltiplos de 5 s, para cima) ---

@pytest.mark.parametrize("palavras, ppm, segundos", [
    (300, 200, 90),   # exato
    (301, 200, 95),   # 90,3 s → 95
    (250, 250, 60),
    (600, 150, 240),
    (1, 150, 5),      # 0,4 s → 5
    (550, 200, 165),  # exato: 165
    (551, 200, 170),
])
def test_limite_de_leitura(palavras, ppm, segundos):
    assert rt.limite_leitura_segundos(palavras, ppm) == segundos


@pytest.mark.parametrize("palavras, ppm", [(300, 180), (300, 0), (0, 200), (-5, 200)])
def test_limite_com_valores_invalidos(palavras, ppm):
    with pytest.raises(ValueError):
        rt.limite_leitura_segundos(palavras, ppm)
