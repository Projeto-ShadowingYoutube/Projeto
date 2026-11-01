"""Tempo de cada palavra de uma frase, para o modo karaokê.

Duas fontes, nesta ordem:

1. Legenda automática do YouTube (formato json3): o reconhecimento de fala do YouTube marca o início de
   cada palavra. Vale até para vídeos com legenda manual, porque quase todo vídeo em inglês também tem
   a automática. O texto dela é casado com o texto da frase (as palavras podem diferir um pouco).
2. Alinhamento do próprio áudio com o texto (Vosk): o reconhecedor procura só as palavras da frase no
   áudio e devolve onde cada uma começa e termina. Usado quando não há legenda automática ou ela não
   bate com o texto (ex.: o vídeo não é em inglês e o "en" é uma tradução).

As palavras que nenhuma fonte encontrou (números, nomes próprios...) têm o tempo distribuído entre as
vizinhas. Se nada funcionar, fica a estimativa de frases.py.
"""
import json
import logging
import re
import threading
import zipfile
from difflib import SequenceMatcher
from pathlib import Path

import requests

from app import config
from app.services.frases import peso_da_palavra
from app.services.midia import audio_pcm

logger = logging.getLogger("uvicorn.error")

COBERTURA_MINIMA = 0.6   # fração das palavras da frase que a fonte precisa ter encontrado
MARGEM = 0.5             # segundos: palavras da legenda automática um pouco fora da frase também contam

MODELO_VOSK = "vosk-model-small-en-us-0.15"
URL_MODELO_VOSK = f"https://alphacephei.com/vosk/models/{MODELO_VOSK}.zip"
TAXA_AMOSTRAGEM = 16000


def normalizar(palavra: str) -> str:
    """Forma usada para comparar palavras: "It's" e "its" casam."""
    return re.sub(r"[^a-z0-9]", "", palavra.lower())


def vocabulario(palavras: list[str]) -> list[str]:
    """Palavras no formato do modelo do Vosk (minúsculas, com apóstrofo; "root-of-it-all" vira 4)."""
    palavras_do_modelo = set()
    for palavra in palavras:
        for parte in re.split(r"[-—–/]", palavra.lower().replace("’", "'")):
            parte = re.sub(r"[^a-z0-9']", "", parte).strip("'")
            if parte:
                palavras_do_modelo.add(parte)
    return sorted(palavras_do_modelo)


# --- Alinhamento das palavras de referência (com tempo) ao texto da frase ---

def casar(palavras_frase: list[str], outras: list[str]) -> list[int | None]:
    """Para cada palavra da frase, o índice da palavra correspondente em "outras" (ou None).

    Usa a maior sequência em comum, então palavras repetidas casam na ordem certa.
    """
    frase = [normalizar(p) for p in palavras_frase]
    pares: list[int | None] = [None] * len(frase)
    for bloco in SequenceMatcher(None, frase, [normalizar(p) for p in outras], autojunk=False).get_matching_blocks():
        for k in range(bloco.size):
            if frase[bloco.a + k]:
                pares[bloco.a + k] = bloco.b + k
    return pares


def alinhar(palavras_frase: list[str], referencia: list[tuple[str, float, float]], duracao: float):
    """Casa as palavras da frase com as da referência ([(palavra, início, fim)], tempos relativos à frase).

    Devolve ([início, fim] por palavra, cobertura) ou (None, 0) se nada casou.
    """
    pares = casar(palavras_frase, [p for p, _, _ in referencia])
    tempos = [list(referencia[j][1:]) if j is not None else None for j in pares]
    casadas = sum(j is not None for j in pares)
    if not casadas:
        return None, 0.0
    return _preencher(palavras_frase, tempos, duracao), casadas / len(palavras_frase)


def _preencher(palavras: list[str], tempos: list, duracao: float) -> list[list[float]]:
    """Dá tempo às palavras sem par (dividindo o espaço entre as vizinhas) e garante a ordem."""
    resultado = [list(t) if t else None for t in tempos]
    i = 0
    while i < len(resultado):
        if resultado[i] is not None:
            i += 1
            continue
        j = i
        while j < len(resultado) and resultado[j] is None:
            j += 1
        inicio = resultado[i - 1][1] if i > 0 else 0.0
        fim = resultado[j][0] if j < len(resultado) else duracao
        fim = max(fim, inicio)
        pesos = [peso_da_palavra(p) for p in palavras[i:j]]
        cursor = inicio
        for k, peso in enumerate(pesos):
            proximo = cursor + (fim - inicio) * peso / sum(pesos)
            resultado[i + k] = [cursor, proximo]
            cursor = proximo
        i = j

    # Inícios em ordem crescente e dentro da frase; cada palavra fica destacada até a seguinte começar.
    anterior = 0.0
    for t in resultado:
        t[0] = anterior = min(max(t[0], anterior), duracao)
    for atual, proxima in zip(resultado, resultado[1:]):
        atual[1] = proxima[0]
    ultima = resultado[-1]
    ultima[1] = min(duracao, max(ultima[1], ultima[0] + 0.3))
    return [[round(a, 3), round(b, 3)] for a, b in resultado]


# --- Fonte 1: legenda automática do YouTube ---

def palavras_do_json3(dados: dict) -> list[tuple[str, float, float]]:
    """[(palavra, início, fim)] em segundos absolutos do vídeo. O fim é o início da palavra seguinte."""
    inicios = []
    for evento in dados.get("events", []):
        base = evento.get("tStartMs", 0)
        fim_evento = base + evento.get("dDurationMs", 0)
        for segmento in evento.get("segs") or []:
            texto = segmento.get("utf8", "").strip()
            if not texto or texto.startswith("["):
                continue
            inicios.append([texto, (base + segmento.get("tOffsetMs", 0)) / 1000, fim_evento / 1000])
    for atual, proxima in zip(inicios, inicios[1:]):
        atual[2] = min(atual[2], proxima[1]) if proxima[1] > atual[1] else atual[2]
    return [(p, i, f) for p, i, f in inicios]


def tempos_pela_legenda_automatica(palavras_youtube, palavras_frase, inicio, fim):
    referencia = [
        (p, i - inicio, f - inicio)
        for p, i, f in palavras_youtube
        if inicio - MARGEM <= i <= fim + MARGEM
    ]
    if not referencia:
        return None, 0.0
    return alinhar(palavras_frase, referencia, fim - inicio)


# --- Fonte 2: alinhamento do áudio com o Vosk ---

_modelo = None
_modelo_cadeado = threading.Lock()


def _carregar_modelo():
    """Baixa (na primeira vez, ~40 MB) e carrega o modelo de inglês do Vosk. None se não der."""
    global _modelo
    with _modelo_cadeado:
        if _modelo is None:
            try:
                import vosk
                vosk.SetLogLevel(-1)
                pasta = config.PASTA_MODELOS / MODELO_VOSK
                if not pasta.exists():
                    _baixar_modelo()
                _modelo = vosk.Model(str(pasta))
            except Exception:
                logger.exception("Modelo do Vosk indisponível; o karaokê usa só a legenda automática.")
                _modelo = False
    return _modelo or None


def _baixar_modelo():
    logger.info("Baixando o modelo de fala do Vosk (%s)...", MODELO_VOSK)
    config.PASTA_MODELOS.mkdir(parents=True, exist_ok=True)
    zip_temporario = config.PASTA_MODELOS / f"{MODELO_VOSK}.zip.part"
    with requests.get(URL_MODELO_VOSK, stream=True, timeout=30) as resposta:
        resposta.raise_for_status()
        with open(zip_temporario, "wb") as arquivo:
            for pedaco in resposta.iter_content(1 << 20):
                arquivo.write(pedaco)
    with zipfile.ZipFile(zip_temporario) as pacote:
        pacote.extractall(config.PASTA_MODELOS)
    zip_temporario.unlink()


def reconhecer(pcm: bytes, vocabulario: list[str] | None = None) -> list[tuple[str, float, float]]:
    """[(palavra, início, fim)] reconhecidas num áudio PCM 16 bits mono 16 kHz.

    Com vocabulário, o reconhecimento fica restrito a essas palavras: na prática, um alinhamento forçado.
    Sem vocabulário, é um reconhecimento livre. Lista vazia se o modelo não estiver disponível.
    """
    modelo = _carregar_modelo()
    if modelo is None:
        return []
    import vosk

    if vocabulario:
        reconhecedor = vosk.KaldiRecognizer(modelo, TAXA_AMOSTRAGEM, json.dumps(vocabulario + ["[unk]"]))
    else:
        reconhecedor = vosk.KaldiRecognizer(modelo, TAXA_AMOSTRAGEM)
    reconhecedor.SetWords(True)
    resultados = []
    for i in range(0, len(pcm), 8000):
        if reconhecedor.AcceptWaveform(pcm[i:i + 8000]):
            resultados.append(json.loads(reconhecedor.Result()))
    resultados.append(json.loads(reconhecedor.FinalResult()))
    return [
        (palavra["word"], palavra["start"], palavra["end"])
        for resultado in resultados
        for palavra in resultado.get("result", [])
        if palavra["word"] != "[unk]"
    ]


def tempos_do_pcm(pcm: bytes, palavras_frase: list[str], duracao: float):
    """([início, fim] de cada palavra da frase no áudio, cobertura). (None, 0) se nada casou."""
    referencia = reconhecer(pcm, vocabulario(palavras_frase))
    if not referencia:
        return None, 0.0
    return alinhar(palavras_frase, referencia, duracao)


def tempos_pelo_audio(video: Path, palavras_frase: list[str], inicio: float, fim: float):
    return tempos_do_pcm(audio_pcm(video, inicio, fim, TAXA_AMOSTRAGEM), palavras_frase, fim - inicio)
