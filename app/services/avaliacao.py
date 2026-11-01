"""Avaliação da fala do usuário numa frase, no modelo das provas de "repita a frase" (PTE, Versant):

1. Palavras (completude): quais palavras da frase o usuário disse. A transcrição do navegador é casada
   com o texto; sem transcrição, o próprio servidor reconhece o áudio (Vosk, reconhecimento livre).
2. Ritmo: em que ponto da frase cada palavra começa, na fala do usuário e no original. As posições são
   relativas (0 = começo da fala, 1 = fim), então falar mais devagar como um todo não pesa aqui; o que
   conta são as pausas e o tempo dado a cada palavra. A velocidade é informada à parte.
3. Entonação: o desenho da curva de altura da voz (F0). Cada curva é medida em semitons em relação à
   mediana da própria pessoa, então voz grave ou aguda não importa, só a melodia da frase.

Não avalia a pronúncia de cada som (fonema): isso exige um modelo acústico próprio (técnica GOP).
"""
import asyncio
import tempfile
from pathlib import Path

import numpy as np

from app.services import alinhamento, karaoke, midia
from app.services.frases import peso_da_palavra

TAXA = alinhamento.TAXA_AMOSTRAGEM

# Ritmo: erro médio de posição (fração da frase) que zera a nota.
ERRO_RITMO_MAXIMO = 0.15
# Entonação: correlação entre as curvas que já vale nota máxima.
CORRELACAO_IDEAL = 0.8
PONTOS_DA_CURVA = 50
PESOS = {"palavras": 0.5, "ritmo": 0.25, "entonacao": 0.25}
# Desligada por enquanto: com microfones reais a nota de entonação saía zerada. Com False, ela não é
# calculada e a nota geral usa só palavras e ritmo (os pesos se redistribuem).
AVALIAR_ENTONACAO = False


def _limitar(valor: float) -> int:
    return round(max(0.0, min(1.0, valor)) * 100)


# --- 1. Palavras ---

def avaliar_palavras(palavras_frase: list[str], reconhecidas: list[str]) -> dict:
    pares = alinhamento.casar(palavras_frase, reconhecidas)
    ditas = [par is not None for par in pares]
    contaveis = [alinhamento.normalizar(p) != "" for p in palavras_frase]
    total = sum(contaveis) or 1
    return {
        "nota": _limitar(sum(d for d, c in zip(ditas, contaveis) if c) / total),
        "ditas": ditas,
    }


# --- 2. Ritmo ---

def avaliar_ritmo(inicios_original: list[float], inicios_usuario: list[float | None]) -> dict | None:
    """Compara o início de cada palavra (None = palavra que o usuário não disse ou não foi achada).

    Cada lista é normalizada pelo próprio trecho falado, então só a distribuição do tempo importa.
    """
    pares = [(o, u) for o, u in zip(inicios_original, inicios_usuario) if u is not None]
    if len(pares) < 3:
        return None
    original = np.array([o for o, _ in pares])
    usuario = np.array([u for _, u in pares])
    if np.ptp(original) <= 0 or np.ptp(usuario) <= 0:
        return None
    original = (original - original.min()) / np.ptp(original)
    usuario = (usuario - usuario.min()) / np.ptp(usuario)
    erros = np.abs(original - usuario)
    return {
        "nota": _limitar(1 - erros.mean() / ERRO_RITMO_MAXIMO),
        "erro_medio": round(float(erros.mean()), 3),
    }


# --- 3. Entonação ---

def curva_de_altura(pcm: np.ndarray, taxa: int = TAXA) -> np.ndarray:
    """F0 (Hz) a cada 10 ms por autocorrelação; NaN onde não há voz."""
    janela, passo = int(0.04 * taxa), int(0.01 * taxa)
    atraso_min, atraso_max = taxa // 500, taxa // 70  # vozes entre 70 e 500 Hz
    if len(pcm) < janela:
        return np.array([])
    quadros = np.lib.stride_tricks.sliding_window_view(pcm, janela)[::passo]
    energias = np.sqrt((quadros ** 2).mean(axis=1))
    limiar_energia = 0.1 * np.percentile(energias, 95)

    curva = np.full(len(quadros), np.nan)
    for i, quadro in enumerate(quadros):
        if energias[i] < limiar_energia:
            continue
        x = quadro - quadro.mean()
        espectro = np.fft.rfft(x, 2 * janela)
        auto = np.fft.irfft(espectro * np.conj(espectro))[:janela]
        if auto[0] <= 0:
            continue
        auto = auto / auto[0]
        atraso = atraso_min + int(np.argmax(auto[atraso_min:atraso_max]))
        if auto[atraso] >= 0.5:  # periodicidade clara = voz
            curva[i] = taxa / atraso
    return curva


def _semitons(curva: np.ndarray, tempos: np.ndarray, grade: np.ndarray) -> np.ndarray | None:
    """Curva em semitons (relativa à mediana da pessoa) reamostrada na grade de tempos."""
    com_voz = ~np.isnan(curva) & (tempos >= grade[0]) & (tempos <= grade[-1])
    if com_voz.sum() < 10:
        return None
    valores = 12 * np.log2(curva[com_voz] / np.median(curva[com_voz]))
    # Filtro de mediana: tira saltos de oitava isolados (erro comum da autocorrelação).
    if len(valores) >= 5:
        valores = np.median(np.lib.stride_tricks.sliding_window_view(np.pad(valores, 2, mode="edge"), 5), axis=1)
    return np.interp(grade, tempos[com_voz], valores)


def avaliar_entonacao(
    pcm_original: np.ndarray, pcm_usuario: np.ndarray, ancoras: list[tuple[float, float]] | None = None,
) -> dict | None:
    """Compara as melodias. "ancoras" = [(início no original, início na fala do usuário)] de palavras em comum:
    o tempo do usuário é levado para o do original entre uma âncora e outra (pausas e trechos mais lentos
    não desalinham as curvas). Sem âncoras, cada curva é esticada para o próprio trecho com voz.
    """
    curva_o, curva_u = curva_de_altura(pcm_original), curva_de_altura(pcm_usuario)
    tempos_o = np.arange(len(curva_o)) * 0.01 + 0.02
    tempos_u = np.arange(len(curva_u)) * 0.01 + 0.02

    ancoras = sorted(ancoras or [])
    # Âncoras precisam estar em ordem nos dois tempos (o alinhamento pode errar uma palavra ou outra).
    monotonas = []
    for original, usuario in ancoras:
        if not monotonas or (original > monotonas[-1][0] and usuario > monotonas[-1][1]):
            monotonas.append((original, usuario))
    if len(monotonas) >= 3:
        ancoras_o = np.array([o for o, _ in monotonas])
        ancoras_u = np.array([u for _, u in monotonas])
        # Fora do trecho entre a primeira e a última âncora, mantém a mesma velocidade.
        tempos_u = np.interp(tempos_u, ancoras_u, ancoras_o, left=np.nan, right=np.nan)
        grade = np.linspace(ancoras_o[0], ancoras_o[-1], PONTOS_DA_CURVA)
        tempos_u = np.where(np.isnan(tempos_u), -1.0, tempos_u)
    else:
        def esticar(curva, tempos):
            com_voz = tempos[~np.isnan(curva)]
            if len(com_voz) < 2:
                return tempos
            return (tempos - com_voz[0]) / (com_voz[-1] - com_voz[0])
        tempos_o, tempos_u = esticar(curva_o, tempos_o), esticar(curva_u, tempos_u)
        grade = np.linspace(0, 1, PONTOS_DA_CURVA)

    original = _semitons(curva_o, tempos_o, grade)
    usuario = _semitons(curva_u, tempos_u, grade)
    if original is None or usuario is None or original.std() < 0.1 or usuario.std() < 0.1:
        return None
    correlacao = float(np.corrcoef(original, usuario)[0, 1])
    return {
        "nota": _limitar(correlacao / CORRELACAO_IDEAL),
        "correlacao": round(correlacao, 3),
        "curva_original": [round(float(v), 2) for v in original],
        "curva_usuario": [round(float(v), 2) for v in usuario],
    }


# --- Tudo junto ---

def para_float(pcm: bytes) -> np.ndarray:
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768


def avaliar(
    texto: str,
    transcricao: str,
    pcm_original: bytes,
    pcm_usuario: bytes,
    tempos_original: list[list[float]],
    velocidade: float,
) -> dict:
    palavras = texto.split()
    reconhecidas = transcricao.split() or [p for p, _, _ in alinhamento.reconhecer(pcm_usuario)]
    nota_palavras = avaliar_palavras(palavras, reconhecidas)

    # Onde cada palavra começa na fala do usuário (alinhamento forçado com o Vosk).
    achadas = alinhamento.reconhecer(pcm_usuario, alinhamento.vocabulario(palavras))
    pares = alinhamento.casar(palavras, [p for p, _, _ in achadas])
    inicios_usuario = [
        achadas[j][1] if j is not None and dita else None
        for j, dita in zip(pares, nota_palavras["ditas"])
    ]
    ritmo = avaliar_ritmo([inicio for inicio, _ in tempos_original], inicios_usuario)
    entonacao = None
    if AVALIAR_ENTONACAO:
        ancoras = [(tempos_original[i][0], u) for i, u in enumerate(inicios_usuario) if u is not None]
        entonacao = avaliar_entonacao(para_float(pcm_original), para_float(pcm_usuario), ancoras)

    # Velocidade: duração da fala do usuário comparada à do original na velocidade em que ele ouviu.
    tempos_usuario = [(achadas[j][1], achadas[j][2]) for j in pares if j is not None]
    duracao_original = (tempos_original[-1][1] - tempos_original[0][0]) / velocidade if tempos_original else 0
    duracao_usuario = (tempos_usuario[-1][1] - tempos_usuario[0][0]) if len(tempos_usuario) >= 2 else 0
    razao_velocidade = round(duracao_usuario / duracao_original, 2) if duracao_original and duracao_usuario else None

    notas = {"palavras": nota_palavras["nota"], "ritmo": ritmo and ritmo["nota"],
             "entonacao": entonacao and entonacao["nota"]}
    disponiveis = {nome: nota for nome, nota in notas.items() if nota is not None}
    peso_total = sum(PESOS[nome] for nome in disponiveis)
    geral = round(sum(PESOS[nome] * nota for nome, nota in disponiveis.items()) / peso_total)

    return {
        "nota": geral,
        "palavras": {"nota": nota_palavras["nota"], "ditas": nota_palavras["ditas"],
                     "reconhecido": " ".join(reconhecidas)},
        "ritmo": ritmo,
        "entonacao": entonacao,
        "razao_velocidade": razao_velocidade,
    }


def _estimar_tempos(palavras: list[str], duracao: float) -> list[list[float]]:
    """Sem tempo medido do original: divide a duração pelo tamanho das palavras (como em frases.py)."""
    pesos = [peso_da_palavra(p) for p in palavras]
    limites = np.concatenate([[0], np.cumsum(pesos) / sum(pesos) * duracao])
    return [[float(a), float(b)] for a, b in zip(limites, limites[1:])]


async def avaliar_gravacao(
    video_id: str, inicio: float, fim: float, texto: str, transcricao: str,
    gravacao: bytes, offset: float, duracao: float, velocidade: float,
) -> dict:
    """Avalia a gravação enviada pelo navegador (só o trecho [offset, offset + duracao] é a fala)."""
    video = await midia.garantir_video(video_id)
    tempos = (await karaoke.tempos_das_palavras(video_id, inicio, fim, texto))["tempos"]

    def processar():
        with tempfile.NamedTemporaryFile(suffix=".webm") as arquivo:
            arquivo.write(gravacao)
            arquivo.flush()
            pcm_usuario = midia.audio_pcm(Path(arquivo.name), offset, offset + duracao, TAXA)
        pcm_original = midia.audio_pcm(video, inicio, fim, TAXA)
        return avaliar(
            texto, transcricao, pcm_original, pcm_usuario,
            tempos or _estimar_tempos(texto.split(), fim - inicio), velocidade,
        )

    return await asyncio.to_thread(processar)
