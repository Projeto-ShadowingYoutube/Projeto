"""Transforma os blocos de legenda do YouTube em frases boas para shadowing.

Os blocos do YouTube são cortados pela tela (largura da legenda), não pelo sentido: metade deles termina
no meio de uma sentença, e as legendas automáticas nem têm pontuação. Aqui os blocos são reagrupados:

- uma frase termina numa pontuação final (. ? !) ou numa pausa na fala;
- frases curtas demais são juntadas à seguinte (nenhum texto é descartado);
- frases longas demais são quebradas, de preferência numa vírgula.

Para o modo karaokê, cada frase também traz o tempo estimado de cada palavra. A legenda do YouTube só
diz quando cada bloco começa e termina; dentro do bloco, o tempo é dividido entre as palavras
proporcionalmente ao tamanho delas (palavras longas demoram mais para ser ditas, e uma pontuação
no fim da palavra indica uma pequena pausa).
"""
import re
from dataclasses import dataclass

DURACAO_MINIMA = 1.0   # segundos: frases menores que isso são juntadas à seguinte
DURACAO_MAXIMA = 8.0   # segundos: acima disso a frase é quebrada
PAUSA_MINIMA = 0.6     # segundos de silêncio entre blocos que indicam fim de frase

# Trechos que não são fala: [Music], [Applause], ♪, e o ">>" que marca troca de falante.
RUIDO = re.compile(r"\[[^\]]*\]|♪+|>>")
FIM_DE_SENTENCA = re.compile(r"[.?!…][\"'”’)\]]*$")
FIM_DE_ORACAO = re.compile(r"[,;:—–][\"'”’]*$")
PESO_BASE_PALAVRA = 2    # "letras" extras de cada palavra (até "a" leva algum tempo)
PESO_PONTUACAO = 3       # pausa depois de vírgula, ponto etc.


@dataclass
class Trecho:
    texto: str
    inicio: float
    fim: float


def _limpar(texto: str) -> str:
    return " ".join(RUIDO.sub(" ", texto).split())


def _normalizar(blocos) -> list[Trecho]:
    """Limpa o texto, junta repetições seguidas e elimina a sobreposição de tempo entre blocos."""
    trechos: list[Trecho] = []
    for bloco in blocos:
        texto = _limpar(bloco.text)
        if not texto:
            continue
        fim = bloco.start + bloco.duration
        if trechos and texto == trechos[-1].texto:
            trechos[-1].fim = max(trechos[-1].fim, fim)
            continue
        trechos.append(Trecho(texto, bloco.start, fim))

    # Nas legendas automáticas um bloco costuma terminar depois do início do próximo;
    # sem esse ajuste, o loop do vídeo tocaria um pedaço da frase seguinte.
    for atual, proximo in zip(trechos, trechos[1:]):
        if proximo.inicio > atual.inicio:
            atual.fim = min(atual.fim, proximo.inicio)
    return trechos


def peso_da_palavra(palavra: str) -> float:
    """Quanto tempo relativo a palavra leva para ser dita."""
    letras = sum(c.isalnum() for c in palavra)
    pausa = PESO_PONTUACAO if re.search(r"[,.;:?!…—]$", palavra) else 0
    return letras + PESO_BASE_PALAVRA + pausa


def tempos_das_palavras(trechos: list[Trecho]) -> list[list[float]]:
    """[início, fim] de cada palavra da frase, em segundos desde o início da frase."""
    origem = trechos[0].inicio
    tempos = []
    for trecho in trechos:
        palavras = trecho.texto.split()
        pesos = [peso_da_palavra(p) for p in palavras]
        duracao = trecho.fim - trecho.inicio
        cursor = trecho.inicio
        for peso in pesos:
            fim = cursor + duracao * peso / sum(pesos)
            tempos.append([round(cursor - origem, 3), round(fim - origem, 3)])
            cursor = fim
    return tempos


def _duracao(trechos: list[Trecho]) -> float:
    return trechos[-1].fim - trechos[0].inicio


def _ponto_de_corte(trechos: list[Trecho]) -> int:
    """Quantos trechos manter ao quebrar uma frase longa: até a última vírgula, ou todos se não houver."""
    for i in range(len(trechos) - 1, 0, -1):
        if FIM_DE_ORACAO.search(trechos[i - 1].texto) and _duracao(trechos[:i]) >= DURACAO_MINIMA:
            return i
    return len(trechos)


def segmentar_frases(blocos) -> list[dict]:
    """Recebe os blocos brutos (com .text, .start e .duration) e devolve a lista de frases."""
    trechos = _normalizar(blocos)
    grupos: list[list[Trecho]] = []
    atual: list[Trecho] = []

    for i, trecho in enumerate(trechos):
        while atual and trecho.fim - atual[0].inicio > DURACAO_MAXIMA:
            corte = _ponto_de_corte(atual)
            grupos.append(atual[:corte])
            atual = atual[corte:]

        atual.append(trecho)
        proximo = trechos[i + 1] if i + 1 < len(trechos) else None
        pausa = proximo.inicio - trecho.fim if proximo else float("inf")
        if _duracao(atual) >= DURACAO_MINIMA and (FIM_DE_SENTENCA.search(trecho.texto) or pausa >= PAUSA_MINIMA):
            grupos.append(atual)
            atual = []

    if atual:
        # Sobra curta no fim do vídeo: junta à frase anterior, se couber.
        if grupos and _duracao(atual) < DURACAO_MINIMA and atual[-1].fim - grupos[-1][0].inicio <= DURACAO_MAXIMA:
            grupos[-1].extend(atual)
        else:
            grupos.append(atual)

    return [
        {
            "id_do_bloco": indice,
            "texto_limpo": " ".join(t.texto for t in grupo),
            "tempo_inicio": grupo[0].inicio,
            "tempo_fim": grupo[-1].fim,
            # Alinhado com texto_limpo.split(): um [início, fim] por palavra.
            "tempos_palavras": tempos_das_palavras(grupo),
        }
        for indice, grupo in enumerate(grupos)
    ]
