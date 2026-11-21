"""Reading Challenge (Membro 1): limpeza, seleção do trecho e tempo de leitura dos textos.

Só funções puras (sem rede, banco ou FastAPI): as fontes (Wikipedia, Gutenberg) buscam o texto bruto e chamam:

    secoes = limpar_wikipedia(bruto)            # ou limpar_gutenberg(bruto)
    if eh_inadequado(titulo, " ".join(...)):    # lista, desambiguação ou tema sensível → outro artigo
        ...
    trecho = selecionar_trecho(secoes)          # None → outro artigo
    limite = limite_leitura_segundos(contar_palavras(trecho), ppm)

Um texto limpo é uma lista de seções, e cada seção é uma lista de parágrafos. A primeira seção é a introdução.
O trecho é sempre feito de parágrafos INTEIROS de UMA seção (decisão DR9): nunca há corte no meio de um parágrafo.
"""
import html
import re

# --- Constantes da feature ---

VELOCIDADES_PPM = (150, 200, 250)  # palavras por minuto que o usuário pode escolher (DR4)
PPM_PADRAO = 200
PALAVRAS_MIN = 250  # tamanho do trecho (DR5)
PALAVRAS_MAX = 600
ARREDONDAMENTO_SEGUNDOS = 5  # o tempo limite é arredondado para cima em múltiplos de 5 s (DR10)

# Parágrafo de verdade: termina em pontuação de fim de frase e tem um mínimo de palavras. O resto (itens de lista,
# legendas, títulos soltos) é descartado.
PALAVRAS_MIN_PARAGRAFO = 8
_FIM_DE_FRASE = re.compile(r"[.!?][\"'”’)]*$")

# Seções da Wikipedia a partir das quais não há mais texto corrido.
SECOES_FINAIS = {
    "see also", "references", "external links", "notes", "further reading", "bibliography", "sources",
    "citations", "footnotes", "works cited", "explanatory notes",
}

# Filtro simples de temas sensíveis (por início de palavra: "therapist" não casa com "rape").
# Não é infalível: ajuste esta lista se um texto ruim passar ou um texto bom for barrado.
_TERMOS_SENSIVEIS = re.compile(
    r"\b(?:rape[ds]?|raping|porn\w*|sexual\w*|suicid\w*|murder\w*|massacre\w*|genocid\w*|terroris\w*|tortur\w*|"
    r"beheading\w*|lynching\w*|pedophil\w*|paedophil\w*|overdos\w*)\b",
    re.IGNORECASE,
)
_PREFIXOS_DE_LISTA = ("list of", "lists of", "index of", "outline of", "timeline of", "glossary of")

_PALAVRA = re.compile(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*")
_REFERENCIA = re.compile(
    r"\[(?:\d+|[a-z]|note \d+|nb \d+|citation needed|clarification needed|who\?|when\?|according to whom\?)\]",
    re.IGNORECASE,
)
_TAG_HTML = re.compile(r"<[^>]+>")
_TITULO_WIKIPEDIA = re.compile(r"^=+\s*(.*?)\s*=+$")

_INICIO_GUTENBERG = re.compile(r"\*\*\*\s*START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*", re.IGNORECASE)
_FIM_GUTENBERG = re.compile(r"\*\*\*\s*END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK", re.IGNORECASE)
_TITULO_CAPITULO = re.compile(r"^(?:chapter|book|part|volume|letter)\b", re.IGNORECASE)
_ILUSTRACAO = re.compile(r"\[(?:illustration|transcriber'?s? note)[^\]]*\]", re.IGNORECASE | re.DOTALL)


# --- Limpeza ---

def normalizar(texto: str) -> str:
    """Limpeza comum a todas as fontes: entidades e tags HTML, referências [1], espaços repetidos.
    Mantém as quebras de linha (elas separam parágrafos e títulos)."""
    texto = html.unescape(_TAG_HTML.sub("", texto))
    texto = _REFERENCIA.sub("", texto)
    linhas = (re.sub(r"[ \t ]+", " ", linha).strip() for linha in texto.splitlines())
    texto = "\n".join(linhas)
    texto = re.sub(r" +([.,;:!?])", r"\1", texto)  # "honey [1]." virou "honey ." → "honey."
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


def eh_paragrafo(linha: str) -> bool:
    return bool(_FIM_DE_FRASE.search(linha)) and contar_palavras(linha) >= PALAVRAS_MIN_PARAGRAFO


def limpar_wikipedia(bruto: str) -> list[list[str]]:
    """Texto da Wikipedia (prop=extracts&explaintext=1) → seções com parágrafos.
    Os títulos "== Seção ==" separam as seções; o texto acaba na primeira seção final (References, See also...)."""
    secoes: list[list[str]] = [[]]
    for linha in normalizar(bruto).splitlines():
        titulo = _TITULO_WIKIPEDIA.match(linha)
        if titulo:
            if titulo.group(1).strip().lower() in SECOES_FINAIS:
                break
            secoes.append([])
        elif eh_paragrafo(linha):
            secoes[-1].append(linha)
    return [secao for secao in secoes if secao]


def limpar_gutenberg(bruto: str) -> list[list[str]]:
    """Livro do Project Gutenberg (texto puro) → seções (capítulos) com parágrafos.
    Fica só com o miolo entre as marcas START/END, junta as linhas quebradas em ~70 colunas e usa os títulos de
    capítulo para separar as seções."""
    inicio = _INICIO_GUTENBERG.search(bruto)
    if inicio:
        bruto = bruto[inicio.end():]
    fim = _FIM_GUTENBERG.search(bruto)
    if fim:
        bruto = bruto[:fim.start()]
    bruto = _ILUSTRACAO.sub("", bruto)

    secoes: list[list[str]] = [[]]
    for bloco in re.split(r"\n\s*\n", normalizar(bruto)):
        paragrafo = " ".join(bloco.split())
        if not paragrafo:
            continue
        letras = re.sub(r"[^A-Za-z]", "", paragrafo)
        if _TITULO_CAPITULO.match(paragrafo) or (letras and letras.isupper()):
            secoes.append([])
        elif eh_paragrafo(paragrafo):
            secoes[-1].append(paragrafo)
    return [secao for secao in secoes if secao]


# --- Conteúdo inadequado ---

def eh_inadequado(titulo: str, texto: str) -> bool:
    """Listas, desambiguações e textos com temas sensíveis não viram desafio."""
    titulo_minusculo = titulo.strip().lower()
    if titulo_minusculo.startswith(_PREFIXOS_DE_LISTA) or "(disambiguation)" in titulo_minusculo:
        return True
    if "may refer to" in texto.lower():
        return True
    return bool(_TERMOS_SENSIVEIS.search(titulo) or _TERMOS_SENSIVEIS.search(texto))


# --- Seleção do trecho (DR9: parágrafos inteiros de uma seção) ---

def selecionar_trecho(secoes: list[list[str]], minimo: int = PALAVRAS_MIN, maximo: int = PALAVRAS_MAX) -> str | None:
    """Escolhe o trecho de leitura, só com parágrafos inteiros e de uma só seção.

    1. A introdução tem prioridade: parágrafos desde o início, enquanto couberem no máximo.
    2. Se ela não chegar ao mínimo, o maior bloco contínuo de parágrafos de uma seção qualquer entre mínimo e máximo.
    3. Nada cabe → None (a fonte tenta outro artigo).
    """
    if not secoes:
        return None

    introducao = _prefixo_que_cabe(secoes[0], maximo)
    if contar_palavras("\n\n".join(introducao)) >= minimo:
        return "\n\n".join(introducao)

    melhor: list[str] = []
    melhor_palavras = 0
    for secao in secoes:
        tamanhos = [contar_palavras(p) for p in secao]
        for inicio in range(len(secao)):
            total = 0
            for fim in range(inicio, len(secao)):
                total += tamanhos[fim]
                if total > maximo:
                    break
                if total >= minimo and total > melhor_palavras:
                    melhor, melhor_palavras = secao[inicio:fim + 1], total
    return "\n\n".join(melhor) if melhor else None


def _prefixo_que_cabe(paragrafos: list[str], maximo: int) -> list[str]:
    escolhidos, total = [], 0
    for paragrafo in paragrafos:
        total += contar_palavras(paragrafo)
        if total > maximo:
            break
        escolhidos.append(paragrafo)
    return escolhidos


# --- Contagem de palavras e tempo ---

def contar_palavras(texto: str) -> int:
    """Palavras do texto. Contrações ("don't") e palavras com hífen ("well-known") contam como uma."""
    return len(_PALAVRA.findall(texto))


def limite_leitura_segundos(palavras: int, ppm: int) -> int:
    """Tempo de leitura: palavras ÷ ppm × 60, arredondado para cima em múltiplos de 5 s (DR10).
    Ex.: 300 palavras a 200 ppm = 90 s; 301 palavras = 90,3 s → 95 s."""
    if ppm not in VELOCIDADES_PPM:
        raise ValueError(f"velocidade inválida: {ppm} (use uma de {VELOCIDADES_PPM})")
    if palavras <= 0:
        raise ValueError("o texto precisa ter ao menos uma palavra")
    # Conta só com inteiros (divisão com teto): sem erro de arredondamento de float nos limites exatos.
    blocos = -(-palavras * 60 // (ppm * ARREDONDAMENTO_SEGUNDOS))
    return blocos * ARREDONDAMENTO_SEGUNDOS
