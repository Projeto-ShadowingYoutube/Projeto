"""W2: contagem de palavras (a regra que vale no servidor; o contador da tela usa a mesma)."""
import pytest

from app.services.writing_texto import contar_palavras


@pytest.mark.parametrize("texto, esperado", [
    ("I don't agree.", 3),               # apóstrofo no meio une
    ("I don’t agree.", 3),               # apóstrofo tipográfico também
    ("a well-known fact", 3),            # hífen no meio une
    ("In 2024, 60% agreed", 4),          # números contam; "%" e "," não
    ("word — word", 2),                  # travessão não é palavra
    ("word - word", 2),                  # hífen solto não é palavra
    ("word,word", 2),                    # vírgula sem espaço separa (split() contaria 1)
    ("café naïve", 2),                   # acentos fazem parte da palavra
    ("naïve", 1),                  # acento combinado (i + ¨) NO MEIO: sem NFC partiria em 2 palavras
    ("snake_case", 2),                   # "_" não é letra
    ("'quoted' -dash- end-", 3),         # apóstrofo/hífen nas pontas não colam
    ("First line.\nSecond line.\n\nThird.", 5),
    ("", 0),
    ("   \n\t ", 0),
    ("!!! ... ---", 0),
])
def test_conta_palavras(texto, esperado):
    assert contar_palavras(texto) == esperado


def test_texto_longo():
    assert contar_palavras("Education matters. " * 500) == 1000
