"""Regras de texto do Writing Challenge (Membro 3, W2).

contar_palavras é a contagem que vale (validação e nota). O contador da tela (static/js/paginas/writing.js) usa a
MESMA regra, para os números da tela e do resultado baterem:
    Python: [^\\W_]+(?:['’\\-][^\\W_]+)*           (letras ou números; [^\\W_] = \\w sem o "_")
    JS:     /[\\p{L}\\p{N}]+(?:['’-][\\p{L}\\p{N}]+)*/gu
Uma palavra é uma sequência de letras ou números, com apóstrofo ou hífen só NO MEIO ("don't", "well-known").
Pontuação, travessões e hífens soltos não contam. O texto é normalizado (NFC) antes, nos dois lados: assim um
acento digitado como letra + acento combinado conta igual a um acento pronto.
"""
import re
import unicodedata

_PALAVRA = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*")


def contar_palavras(texto: str) -> int:
    return len(_PALAVRA.findall(unicodedata.normalize("NFC", texto)))
