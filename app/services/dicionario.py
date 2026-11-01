"""Dicionário do popup de palavras (a rota está em app/api/dicionario.py).

1. O spaCy analisa a frase inteira para achar a forma base (is → be) e a classe gramatical da palavra
   naquele contexto ("light" em "a light bag" é adjetivo).
2. As definições vêm do Wiktionary (cobre até preposições e artigos, como "for").
   A pronúncia (IPA/áudio) vem da dictionaryapi.dev, quando disponível.
3. O resultado fica salvo no SQLite.
"""
import json
import logging
import re
import threading
from datetime import timedelta
from html.parser import HTMLParser
from urllib.parse import quote

import requests
from sqlmodel import Session

from app.models import EntradaDicionario, agora

logger = logging.getLogger("uvicorn.error")

http_session = requests.Session()
# A Wikimedia pede que todo cliente se identifique pelo User-Agent.
http_session.headers["User-Agent"] = "ShadowingApp/1.0 (projeto academico de pratica de ingles)"

URL_WIKTIONARY = "https://en.wiktionary.org/api/rest_v1/page/definition/{}"
URL_PRONUNCIA = "https://api.dictionaryapi.dev/api/v2/entries/en/{}"
VALIDADE_PALAVRA_NAO_ENCONTRADA = timedelta(days=7)
# Limites para o popup ser curto: a classe da frase vem com 2 definições; uma segunda entrada da mesma
# classe (ex: "light" = claro / leve) e uma classe diferente vêm com 1 cada. Só a 1ª definição tem exemplo.
MAX_DEFINICOES_CONTEXTO = 2
MAX_ENTRADAS_CONTEXTO = 2
MAX_OUTRAS_CLASSES = 1
LIMITE_DEFINICAO = 90
LIMITE_EXEMPLO = 90

# Definições que só remetem a outra palavra ("past participle of rin", "plural of ...") não ajudam no popup.
DEFINICAO_REMISSIVA = re.compile(
    r"^(plural|(simple )?past( tense)?|past participle|present participle|third-person singular[\w\s-]*"
    r"|(alternative|obsolete|archaic|nonstandard|dated) (form|spelling)|misspelling|eye dialect spelling"
    r"|comparative( form)?|superlative( form)?) of\b",
    re.IGNORECASE,
)

# Classe gramatical do spaCy (Universal POS) → nome usado pelo Wiktionary.
CLASSES_SPACY = {
    "ADJ": "Adjective", "ADP": "Preposition", "ADV": "Adverb", "AUX": "Verb", "VERB": "Verb",
    "CCONJ": "Conjunction", "SCONJ": "Conjunction", "DET": "Determiner", "INTJ": "Interjection",
    "NOUN": "Noun", "PROPN": "Proper noun", "NUM": "Numeral", "PART": "Particle", "PRON": "Pronoun",
}
# Classes equivalentes: o Wiktionary chama "the" de "Article", mas o spaCy de determinante.
CLASSES_EQUIVALENTES = {"Determiner": {"Determiner", "Article"}}

_nlp = None
_nlp_carregado = False
_nlp_cadeado = threading.Lock()


def _carregar_nlp():
    """Carrega o modelo do spaCy uma única vez. Sem ele, o dicionário funciona, só que sem contexto."""
    global _nlp, _nlp_carregado
    with _nlp_cadeado:
        if not _nlp_carregado:
            try:
                import spacy
                _nlp = spacy.load("en_core_web_sm", disable=["ner", "parser"])
            except (ImportError, OSError):
                logger.warning("Modelo en_core_web_sm do spaCy indisponível; o dicionário vai funcionar sem contexto.")
            _nlp_carregado = True
    return _nlp


def normalizar(palavra: str) -> str:
    palavra = palavra.replace("’", "'").replace("‘", "'")
    return re.sub(r"[^A-Za-z'-]", "", palavra).strip("'-")


def analisar_no_contexto(palavra: str, frase: str | None, indice: int | None) -> tuple[str, str | None]:
    """Devolve (forma base, classe no padrão do Wiktionary) da palavra clicada dentro da frase."""
    nlp = _carregar_nlp()
    if nlp is None:
        return palavra.lower(), None

    texto, inicio, fim = palavra, 0, len(palavra)
    if frase and indice is not None:
        # O front-end separa a frase por espaços; acha onde está a palavra de número "indice".
        posicoes = list(re.finditer(r"\S+", frase))
        if indice < len(posicoes):
            texto, inicio, fim = frase, posicoes[indice].start(), posicoes[indice].end()

    for token in nlp(texto):
        if inicio <= token.idx < fim and token.is_alpha:
            # Nomes próprios e o pronome "I" mantêm a maiúscula (no Wiktionary, "i" é a letra).
            lema = token.lemma_ if token.pos_ == "PROPN" or token.lemma_ == "I" else token.lemma_.lower()
            return lema, CLASSES_SPACY.get(token.pos_)
    return palavra.lower(), None


class _ExtratorDeTexto(HTMLParser):
    def __init__(self):
        super().__init__()
        self.partes = []

    def handle_data(self, data):
        self.partes.append(data)


def html_para_texto(html: str) -> str:
    extrator = _ExtratorDeTexto()
    extrator.feed(html)
    return " ".join("".join(extrator.partes).split())


def buscar_definicoes(palavra: str) -> list | None:
    """Busca no Wiktionary. Devolve [{classe, definicoes: [{definicao, exemplo}]}] ou None."""
    for titulo in dict.fromkeys([palavra, palavra.lower(), palavra.capitalize()]):
        resposta = http_session.get(URL_WIKTIONARY.format(quote(titulo)), timeout=10)
        if resposta.status_code == 404:
            continue
        resposta.raise_for_status()

        classes = []
        for entrada in resposta.json().get("en", []):
            if entrada.get("language") != "English":
                continue
            definicoes = []
            for item in entrada.get("definitions", []):
                definicao = html_para_texto(item.get("definition", ""))
                # Sub-sentidos do Wiktionary costumam repetir o texto do sentido principal.
                if not definicao or any(definicao in d["definicao"] for d in definicoes):
                    continue
                exemplos = item.get("examples") or []
                exemplo = html_para_texto(exemplos[0]) if exemplos else None
                definicoes.append({"definicao": definicao, "exemplo": exemplo})
            if definicoes:
                classes.append({"classe": entrada["partOfSpeech"], "definicoes": definicoes})
        if classes:
            return classes
    return None


def buscar_pronuncia(palavra: str) -> dict:
    """IPA e áudio da dictionaryapi.dev. É opcional: qualquer falha devolve vazio."""
    try:
        resposta = http_session.get(URL_PRONUNCIA.format(quote(palavra)), timeout=5)
        if resposta.status_code != 200:
            return {}
        foneticas = [f for entrada in resposta.json() for f in entrada.get("phonetics", [])]
        return {
            "fonetica": next((f["text"] for f in foneticas if f.get("text")), None),
            "audio": next((f["audio"] for f in foneticas if f.get("audio")), None),
        }
    except (requests.RequestException, ValueError):
        return {}


class DicionarioIndisponivel(Exception):
    """O Wiktionary não respondeu."""


def consultar(session: Session, lema: str) -> dict | None:
    """Definições + pronúncia do lema, usando o cache do banco."""
    em_cache = session.get(EntradaDicionario, lema)
    if em_cache:
        dados = json.loads(em_cache.dados)
        nao_encontrada_expirou = dados is None and agora() - em_cache.data_consulta > VALIDADE_PALAVRA_NAO_ENCONTRADA
        if not nao_encontrada_expirou:
            return dados

    try:
        classes = buscar_definicoes(lema)
    except requests.RequestException as erro:
        logger.exception("Erro ao consultar o Wiktionary para '%s'", lema)
        raise DicionarioIndisponivel from erro

    dados = {"classes": classes, **buscar_pronuncia(lema)} if classes else None
    session.merge(EntradaDicionario(palavra=lema, dados=json.dumps(dados, ensure_ascii=False)))
    session.commit()
    return dados


def _encurtar(texto: str, limite: int) -> str:
    """Corta no limite sem quebrar palavra."""
    if len(texto) <= limite:
        return texto
    return texto[:limite].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def resumir_definicao(definicao: str) -> str:
    """Encurta as definições do Wiktionary, que costumam empilhar frases e sinônimos.

    "To move swiftly. To move forward quickly upon two feet..." → "To move swiftly."
    """
    texto = re.split(r"(?<=\.)\s+(?=[A-Z])", definicao)[0]
    if len(texto) > LIMITE_DEFINICAO:
        texto = re.sub(r"\s*\([^()]*\)", "", texto)  # tira explicações entre parênteses
    if len(texto) > LIMITE_DEFINICAO:
        partes = texto.split("; ")
        texto = partes[0]
        for parte in partes[1:]:
            if len(texto) + 2 + len(parte) > LIMITE_DEFINICAO:
                break
            texto += "; " + parte
    return _encurtar(texto, LIMITE_DEFINICAO)


def _sem_remissivas(classes: list) -> list:
    filtradas = [
        {**c, "definicoes": [d for d in c["definicoes"] if not DEFINICAO_REMISSIVA.match(d["definicao"])]}
        for c in classes
    ]
    filtradas = [c for c in filtradas if c["definicoes"]]
    # Se a palavra só tem definições remissivas, é melhor mostrá-las do que nada.
    return filtradas or classes


def _ordenar_por_contexto(classes: list, classe_no_contexto: str | None) -> list:
    """Coloca primeiro a classe gramatical que a palavra tem na frase e deixa a resposta curta.

    Uma palavra pode ter várias entradas da mesma classe (ex: "light" adjetivo = claro / leve);
    a segunda aparece com uma definição só.
    """
    classes = _sem_remissivas(classes)
    aceitas = CLASSES_EQUIVALENTES.get(classe_no_contexto, {classe_no_contexto}) if classe_no_contexto else set()
    do_contexto = ([c for c in classes if c["classe"] in aceitas] or classes[:1])[:MAX_ENTRADAS_CONTEXTO]
    outras = [c for c in classes if c not in do_contexto and c["classe"] not in aceitas][:MAX_OUTRAS_CLASSES]

    resultado = []
    for posicao, classe in enumerate(do_contexto + outras):
        limite = MAX_DEFINICOES_CONTEXTO if posicao == 0 else 1
        definicoes = []
        for indice, item in enumerate(classe["definicoes"][:limite]):
            exemplo = item["exemplo"] if posicao == 0 and indice == 0 else None
            definicoes.append({
                "definicao": resumir_definicao(item["definicao"]),
                "exemplo": exemplo if exemplo and len(exemplo) <= LIMITE_EXEMPLO else None,
            })
        resultado.append({**classe, "definicoes": definicoes, "do_contexto": classe["classe"] in aceitas})
    return resultado


def buscar(session: Session, palavra: str, frase: str | None, indice: int | None) -> dict | None:
    """Verbete da palavra clicada, já ordenado pelo contexto da frase; None se não existir.

    Lança ValueError se a palavra não tiver letras e DicionarioIndisponivel se o Wiktionary falhar.
    """
    limpa = normalizar(palavra)
    if not limpa:
        raise ValueError("Palavra inválida.")

    lema, classe = analisar_no_contexto(limpa, frase, indice)
    dados = consultar(session, lema)
    if dados is None and lema != limpa.lower():
        lema, dados = limpa.lower(), consultar(session, limpa.lower())
    if dados is None:
        return None

    return {
        "palavra": limpa,
        "lema": lema,
        "classe_no_contexto": classe,
        "fonetica": dados.get("fonetica"),
        "audio": dados.get("audio"),
        "classes": _ordenar_por_contexto(dados["classes"], classe),
        "fonte": "Wiktionary",
    }
