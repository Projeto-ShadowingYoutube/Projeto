"""Reading Challenge (Membro 1): de onde vêm os textos (Wikipedia, Project Gutenberg e a reserva do banco).

Cada fonte é uma função sem parâmetros que devolve um TextoBruto (mesma interface: trocar ou somar fontes não muda
a rota). A limpeza e a seleção do trecho são as funções puras de reading_textos.py.

    texto = obter_texto(session, "wikipedia")   # ReadingText já gravado, pronto para o desafio

Ordem (decisões DR1, DR12):
1. Até TENTATIVAS_BUSCA artigos da fonte: os curtos, longos demais (sem bloco válido) ou inadequados são pulados.
   Falha de rede, timeout ou limite de uso (429) não é repetida (cada nova tentativa esperaria o timeout de novo, ou
   insistiria no limite). Na Wikipedia, o sorteio é entre os "Good articles" (R3b).
2. Não deu: um artigo da mesma fonte já salvo no banco (a LLM gera as perguntas normalmente).
3. Nenhum salvo: um texto de reserva (migração 0102), que já tem as perguntas prontas.
4. Nem reserva (banco sem a 0102): TextoIndisponivel, que a rota transforma num 502.

Padrão de app/services/dicionario.py: requests.Session reaproveitada, User-Agent identificado (a Wikimedia exige) e
timeout em toda chamada.
"""
import logging
import random
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

import requests
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models_reading import ReadingText
from app.services import reading_textos as rt

logger = logging.getLogger("uvicorn.error")

TENTATIVAS_BUSCA = 3
TIMEOUT_API = 10    # segundos (Wikipedia)
# O Gutendex é instável: a mesma consulta já respondeu em 0,5 s e, no dia seguinte, passou de 30 s (25/11/2026).
# Com timeout curto, a espera é pequena e o sorteio segue pelo CATALOGO_GUTENBERG (R13b).
TIMEOUT_GUTENDEX = 5
TIMEOUT_LIVRO = 20  # o .txt de um livro é maior
# O trecho sai do começo do capítulo 1 (nos livros medidos, nos primeiros 4 KB) e o espelho entrega ≈ 27 KB/s:
# 150 KB levam uns 5 s. Um livro cujo capítulo 1 não cabe (sumário enorme) é descartado e outro é sorteado (R12b).
LIMITE_BYTES_LIVRO = 150 * 1024
TEMPO_MAX_LIVRO = 25  # segundos para o download inteiro (o TIMEOUT_LIVRO vale para cada leitura, não para o total)

URL_WIKIPEDIA = "https://en.wikipedia.org/w/api.php"
# Sorteio entre os "Good articles" (≈ 40 mil artigos revisados, longos e bem escritos): o sorteio de qualquer artigo
# trazia quase sempre artigos curtos demais para um trecho de 250–600 palavras (bloco R3b, decisão DR37).
CATEGORIA_WIKIPEDIA = "Good_articles"
URL_GUTENDEX = "https://gutendex.com/books/"
URL_LIVRO_GUTENBERG = "https://www.gutenberg.org/ebooks/{id}"  # página do livro (crédito, para pessoas)
# O .txt vem de um espelho oficial (PGLAF, a fundação do Project Gutenberg): o www.gutenberg.org recusa downloads
# automáticos (503) e a política de robôs deles pede espelhos. O caminho cache/epub é o mesmo para todo livro (R12b).
URL_TEXTO_GUTENBERG = "https://gutenberg.pglaf.org/cache/epub/{id}/pg{id}.txt"

# Crédito exigido pela licença de cada fonte (a tela mostra junto do texto).
CREDITOS = {
    "wikipedia": "Texto: Wikipedia, artigo \"{titulo}\" ({url}). Licença CC BY-SA 4.0 "
                 "(https://creativecommons.org/licenses/by-sa/4.0/). Trecho selecionado do artigo.",
    "gutenberg": "Texto: Project Gutenberg, \"{titulo}\" ({url}). Obra em domínio público nos EUA. "
                 "Trecho selecionado do livro.",
}

http_session = requests.Session()
# A Wikimedia pede que todo cliente se identifique pelo User-Agent (o mesmo de app/services/dicionario.py).
http_session.headers["User-Agent"] = "ShadowingApp/1.0 (projeto academico de pratica de ingles)"

# Obras de consulta e coletâneas não servem como texto de leitura (entre os mais baixados há um dicionário e as
# obras completas de Shakespeare, que começam por um sumário enorme). Filtradas pelo título, antes do sorteio (R12b).
_NAO_E_LEITURA = re.compile(r"\b(?:dictionar|encyclop|thesaurus|glossar|index\b|(?:complete )?works of)", re.IGNORECASE)

_sorteio = random.Random()
_relogio = time.monotonic  # trocado nos testes


class FonteIndisponivel(Exception):
    """A fonte não respondeu (rede, timeout, status de erro) ou respondeu fora do formato esperado."""


class TextoIndisponivel(Exception):
    """Não há texto nenhum: a fonte falhou, não há artigo salvo e não há textos de reserva no banco."""


@dataclass
class TextoBruto:
    """O que uma fonte devolve: o texto já limpo, separado em seções com parágrafos."""
    fonte: str
    id_origem: str
    titulo: str
    url: str | None
    secoes: list[list[str]]


# --- Fontes ---

def buscar_wikipedia() -> TextoBruto:
    """Um artigo da Wikipedia em inglês sorteado entre os da CATEGORIA_WIKIPEDIA, numa única chamada (texto e URL).

    A busca (CirrusSearch) com gsrsort=random devolve um artigo diferente a cada chamada; gsrnamespace=0 deixa só
    artigos (sem páginas de usuário, discussão etc.)."""
    parametros = {
        "action": "query", "format": "json", "formatversion": 2,
        "generator": "search", "gsrsearch": f"incategory:{CATEGORIA_WIKIPEDIA}", "gsrsort": "random",
        "gsrlimit": 1, "gsrnamespace": 0,
        "prop": "extracts|info", "explaintext": 1, "exlimit": 1, "inprop": "url",
    }
    resposta = _get(URL_WIKIPEDIA, params=parametros, timeout=TIMEOUT_API)
    try:
        pagina = resposta.json()["query"]["pages"][0]
        return TextoBruto(fonte="wikipedia", id_origem=str(pagina["pageid"]), titulo=pagina["title"],
                          url=pagina.get("fullurl"), secoes=rt.limpar_wikipedia(pagina.get("extract") or ""))
    except (ValueError, KeyError, IndexError, TypeError) as erro:
        raise FonteIndisponivel("a Wikipedia respondeu fora do formato esperado") from erro


def buscar_gutenberg() -> TextoBruto:
    """Um livro em inglês e em domínio público do Project Gutenberg, sorteado entre os mais baixados.

    A lista vem do Gutendex; se ele falhar (timeout, erro, formato) ou não sobrar livro, vem do CATALOGO_GUTENBERG
    (R13b). O .txt é sempre baixado do espelho oficial."""
    try:
        livros = _livros_do_gutendex()
    except FonteIndisponivel as erro:
        logger.warning("Reading: Gutendex indisponível (%s); sorteando do catálogo", erro)
        livros = []
    id_livro, titulo = _sorteio.choice(livros or CATALOGO_GUTENBERG)
    bruto = _baixar_texto(URL_TEXTO_GUTENBERG.format(id=id_livro))
    return TextoBruto(fonte="gutenberg", id_origem=str(id_livro), titulo=titulo,
                      url=URL_LIVRO_GUTENBERG.format(id=id_livro), secoes=rt.limpar_gutenberg(bruto))


# Reserva do Gutenberg quando o Gutendex falha (R13b, DR47): os livros de domínio público (copyright=false) da 1ª
# página do Gutendex em 25/11/2026, menos as obras de consulta, todos conferidos no espelho (.txt com status 200).
CATALOGO_GUTENBERG: tuple[tuple[int, str], ...] = (
    (1342, "Pride and Prejudice"),
    (84, "Frankenstein; or, The modern Prometheus"),
    (2701, "Moby Dick; Or, The Whale"),
    (11, "Alice's Adventures in Wonderland"),
    (1661, "The Adventures of Sherlock Holmes"),
    (1513, "Romeo and Juliet"),
    (345, "Dracula"),
    (43, "The strange case of Dr. Jekyll and Mr. Hyde"),
    (145, "Middlemarch"),
    (67979, "The Blue Castle: a novel"),
    (2554, "Crime and Punishment"),
    (1260, "Jane Eyre: An Autobiography"),
    (2680, "Meditations"),
    (1184, "The Count of Monte Cristo"),
    (2641, "A Room with a View"),
    (174, "The Picture of Dorian Gray"),
    (37106, "Little Women; Or, Meg, Jo, Beth, and Amy"),
    (98, "A Tale of Two Cities"),
    (64317, "The Great Gatsby"),
    (65238, "The Secret of Chimneys"),
    (2600, "War and Peace"),
    (1952, "The Yellow Wallpaper"),
    (1259, "Twenty years after"),
    (1727, "The Odyssey: Rendered into English prose for the use of those who cannot read the original"),
    (1232, "The Prince"),
    (394, "Cranford"),
    (2160, "The Expedition of Humphry Clinker"),
    (16389, "The Enchanted April"),
)


FONTES: dict[str, Callable[[], TextoBruto]] = {"wikipedia": buscar_wikipedia, "gutenberg": buscar_gutenberg}


def _livros_do_gutendex() -> list[tuple[int, str]]:
    """(id, título) dos livros de domínio público, com .txt e que não são obras de consulta, da 1ª página.

    Só languages=en: com qualquer outro filtro (copyright, mime_type, page) a consulta pode passar de 30 s; o domínio
    público (copyright=false) e o formato .txt são conferidos aqui."""
    resposta = _get(URL_GUTENDEX, params={"languages": "en"}, timeout=TIMEOUT_GUTENDEX)
    try:
        return [(int(livro["id"]), livro["title"]) for livro in resposta.json()["results"]
                if livro.get("copyright") is False and _url_do_texto(livro)
                and not _NAO_E_LEITURA.search(livro["title"])]
    except (ValueError, KeyError, TypeError, AttributeError) as erro:
        raise FonteIndisponivel("o Gutendex respondeu fora do formato esperado") from erro


# --- Obter o texto do desafio ---

def obter_texto(session: Session, fonte: str, tentativas: int = TENTATIVAS_BUSCA) -> ReadingText:
    """Texto pronto para um desafio, na ordem descrita no topo do módulo."""
    if fonte not in FONTES:
        raise ValueError(f"fonte desconhecida: {fonte!r} (use uma de {tuple(FONTES)})")
    buscar = FONTES[fonte]

    for tentativa in range(1, tentativas + 1):
        try:
            bruto = buscar()
        except FonteIndisponivel as erro:
            logger.warning("Reading: %s indisponível (%s); usando um texto salvo", fonte, erro)
            break
        trecho = rt.selecionar_trecho(bruto.secoes)
        if trecho is None or rt.eh_inadequado(bruto.titulo, trecho):
            logger.info("Reading: %s \"%s\" descartado (tentativa %d de %d)", fonte, bruto.titulo, tentativa,
                        tentativas)
            continue
        return _gravar(session, bruto, trecho)

    texto = texto_salvo(session, fonte) or texto_de_reserva(session)
    if texto is None:
        raise TextoIndisponivel()
    return texto


def texto_salvo(session: Session, fonte: str) -> ReadingText | None:
    """Um artigo da fonte já salvo por um desafio anterior (sem os textos de reserva), sorteado."""
    consulta = (select(ReadingText)
                .where(ReadingText.fonte == fonte, ReadingText.perguntas_reserva.is_(None))
                .order_by(func.random()).limit(1))
    return session.exec(consulta).first()


def texto_de_reserva(session: Session) -> ReadingText | None:
    """Um dos textos de reserva (com perguntas prontas), sorteado. Também usado quando a LLM falha (R4)."""
    consulta = (select(ReadingText).where(ReadingText.perguntas_reserva.is_not(None))
                .order_by(func.random()).limit(1))
    return session.exec(consulta).first()


def credito(texto: ReadingText) -> str:
    """Crédito e licença do texto, para mostrar na tela (exigência da CC BY-SA da Wikipedia)."""
    return CREDITOS[texto.fonte].format(titulo=texto.titulo, url=texto.url or "")


# --- Internos ---

def _gravar(session: Session, bruto: TextoBruto, trecho: str) -> ReadingText:
    """Grava o texto, ou devolve o já gravado (o mesmo artigo é compartilhado por todos os usuários)."""
    existente = _buscar_gravado(session, bruto)
    if existente:
        return existente
    texto = ReadingText(fonte=bruto.fonte, id_origem=bruto.id_origem, titulo=bruto.titulo, url=bruto.url,
                        conteudo=trecho, palavras=rt.contar_palavras(trecho))
    session.add(texto)
    try:
        session.commit()
    except IntegrityError:
        # Outro desafio gravou o mesmo artigo entre a consulta e o commit (UNIQUE fonte + id_origem): usa o dele.
        session.rollback()
        return _buscar_gravado(session, bruto)
    session.refresh(texto)
    return texto


def _buscar_gravado(session: Session, bruto: TextoBruto) -> ReadingText | None:
    consulta = select(ReadingText).where(ReadingText.fonte == bruto.fonte, ReadingText.id_origem == bruto.id_origem)
    return session.exec(consulta).first()


def _get(url: str, **parametros) -> requests.Response:
    try:
        resposta = http_session.get(url, **parametros)
    except requests.RequestException as erro:
        raise FonteIndisponivel(f"falha de conexão ({type(erro).__name__})") from erro
    if resposta.status_code >= 400:
        raise FonteIndisponivel(f"status {resposta.status_code}")
    return resposta


def _url_do_texto(livro: dict) -> str | None:
    """O livro tem texto puro? (O Gutendex lista vários formatos; o .zip não serve.) O download usa o espelho."""
    for tipo, url in (livro.get("formats") or {}).items():
        if tipo.startswith("text/plain") and not url.endswith(".zip"):
            return url
    return None


def _baixar_texto(url: str) -> str:
    """Baixa o .txt do livro: só text/plain, no máximo LIMITE_BYTES_LIVRO e TEMPO_MAX_LIVRO segundos (R12b, R13).

    Se o arquivo foi cortado no limite, descarta o que vem depois da última linha em branco: o corte cai no meio de
    um parágrafo, e um pedaço que terminasse num ponto passaria por parágrafo inteiro."""
    resposta = _get(url, timeout=TIMEOUT_LIVRO, stream=True)
    tipo = resposta.headers.get("content-type", "")
    if not tipo.startswith("text/plain"):
        # Ex.: página HTML de manutenção ou de bloqueio com status 200; tratada como livro, as tags virariam o trecho.
        resposta.close()
        raise FonteIndisponivel(f"o espelho não devolveu texto puro (content-type {tipo or 'ausente'!r})")
    partes, total, cortado = [], 0, False
    inicio = _relogio()
    try:
        for pedaco in resposta.iter_content(chunk_size=16 * 1024):
            partes.append(pedaco)
            total += len(pedaco)
            if total >= LIMITE_BYTES_LIVRO:
                cortado = True
                break
            if _relogio() - inicio > TEMPO_MAX_LIVRO:
                raise FonteIndisponivel(f"download do livro lento demais (mais de {TEMPO_MAX_LIVRO} s)")
    except requests.RequestException as erro:
        raise FonteIndisponivel(f"falha ao baixar o livro ({type(erro).__name__})") from erro
    finally:
        resposta.close()
    texto = b"".join(partes)[:LIMITE_BYTES_LIVRO].decode("utf-8", errors="replace").replace("\r\n", "\n")
    if cortado:
        texto = texto[:max(texto.rfind("\n\n"), 0)]
    return texto
