"""Bloco R3: fontes de texto (Wikipedia, Gutenberg), artigos salvos, textos de reserva e a migração 0102.

Nenhum teste acessa a rede: a sessão HTTP do serviço é trocada por uma falsa, que devolve respostas prontas e
registra cada chamada (para conferir tentativas, parâmetros e timeouts).
"""
import pytest
import requests
from alembic import command
from sqlalchemy import create_engine, text
from sqlmodel import Session, select

from app import migrar
from app.models import Usuario
from app.models_reading import ReadingChallenge, ReadingText
from app.services import reading_fontes as rf
from app.services import reading_textos as rt


def paragrafo(palavras: int, palavra: str = "bees") -> str:
    return " ".join([palavra] * palavras) + "."


# --- HTTP falso ---

class RespostaFalsa:
    def __init__(self, status: int = 200, json=None, pedacos: list[bytes] | None = None,
                 tipo: str = "text/plain; charset=utf-8"):
        self.status_code = status
        self.headers = {"content-type": tipo} if tipo else {}
        self._json = json
        self._pedacos = pedacos or []
        self.pedacos_lidos = 0
        self.fechada = False

    def json(self):
        if self._json is None:
            raise ValueError("não é JSON")
        return self._json

    def iter_content(self, chunk_size):
        for pedaco in self._pedacos:
            self.pedacos_lidos += 1
            yield pedaco

    def close(self):
        self.fechada = True


class SessaoFalsa:
    """Devolve (ou levanta) as respostas da fila, na ordem, e registra (url, parâmetros) de cada chamada."""

    def __init__(self):
        self.respostas: list = []
        self.chamadas: list[tuple[str, dict]] = []

    def get(self, url, **parametros):
        self.chamadas.append((url, parametros))
        resposta = self.respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


@pytest.fixture()
def http(monkeypatch):
    falsa = SessaoFalsa()
    monkeypatch.setattr(rf, "http_session", falsa)
    return falsa


@pytest.fixture()
def session(engine_teste):
    with Session(engine_teste) as s:
        yield s


def artigo(pageid: int, titulo: str, extract: str) -> RespostaFalsa:
    return RespostaFalsa(json={"query": {"pages": [{
        "pageid": pageid, "title": titulo, "extract": extract,
        "fullurl": f"https://en.wikipedia.org/wiki/{titulo.replace(' ', '_')}",
    }]}})


BOM = paragrafo(150, "bees") + "\n" + paragrafo(150, "honey")  # introdução de 300 palavras
CURTO = paragrafo(100)


def _salvar(session, fonte="wikipedia", id_origem="999", perguntas=None) -> ReadingText:
    texto = ReadingText(fonte=fonte, id_origem=id_origem, titulo=f"Salvo {id_origem}", conteudo=paragrafo(300),
                        palavras=300, perguntas_reserva=perguntas)
    session.add(texto)
    session.commit()
    session.refresh(texto)
    return texto


PERGUNTAS = [{"enunciado": "Q?", "alternativas": ["a", "b", "c", "d"], "resposta_correta": "a",
              "justificativa": "..."}] * 5


# --- Wikipedia ---

def test_artigo_bom_e_gravado_e_devolvido(http, session):
    http.respostas = [artigo(1, "Honey bee", BOM)]
    texto = rf.obter_texto(session, "wikipedia")

    assert (texto.fonte, texto.id_origem, texto.titulo) == ("wikipedia", "1", "Honey bee")
    assert texto.url == "https://en.wikipedia.org/wiki/Honey_bee"
    assert texto.palavras == 300 and texto.perguntas_reserva is None
    assert session.exec(select(ReadingText)).all() == [texto]

    url, parametros = http.chamadas[0]
    assert url == rf.URL_WIKIPEDIA
    assert parametros["timeout"] == rf.TIMEOUT_API


def test_wikipedia_sorteia_entre_os_good_articles(http):
    """R3b (DR37): o sorteio de qualquer artigo trazia quase sempre artigos curtos demais."""
    http.respostas = [artigo(1, "Honey bee", BOM)]
    rf.buscar_wikipedia()
    [(url, parametros)] = http.chamadas
    p = parametros["params"]
    assert url == rf.URL_WIKIPEDIA
    assert (p["generator"], p["gsrsearch"], p["gsrsort"]) == ("search", "incategory:Good_articles", "random")
    assert p["gsrlimit"] == 1 and p["gsrnamespace"] == 0  # um artigo por chamada, só do espaço dos artigos
    assert p["prop"] == "extracts|info" and p["explaintext"] == 1 and p["inprop"] == "url"
    assert "grnnamespace" not in p and "grnlimit" not in p


def test_limite_de_uso_da_wikipedia_nao_e_repetido(http, session):
    """429 (limite da API, com Retry-After): não insiste; usa um artigo salvo (e depois a reserva)."""
    limite = _artigo_com_status(429)
    limite.headers = {"Retry-After": "5"}
    http.respostas = [limite]
    salvo = _salvar(session, id_origem="salvo")
    assert rf.obter_texto(session, "wikipedia").id == salvo.id
    assert len(http.chamadas) == 1


def test_artigos_curtos_ou_inadequados_sao_pulados(http, session):
    http.respostas = [artigo(1, "Curto", CURTO), artigo(2, "List of bees", BOM), artigo(3, "Honey bee", BOM)]
    texto = rf.obter_texto(session, "wikipedia")
    assert texto.id_origem == "3"
    assert len(http.chamadas) == 3
    assert session.exec(select(ReadingText)).all() == [texto]  # os descartados não são gravados


def test_no_maximo_tres_tentativas_e_depois_a_reserva(http, session):
    reserva = _salvar(session, id_origem="reserva", perguntas=PERGUNTAS)
    http.respostas = [artigo(1, "A", CURTO), artigo(2, "B", CURTO), artigo(3, "C", CURTO), artigo(4, "Bom", BOM)]
    assert rf.obter_texto(session, "wikipedia").id == reserva.id
    assert len(http.chamadas) == 3


@pytest.mark.parametrize("falha", [requests.ConnectionError("sem rede"), requests.Timeout("demorou")])
def test_rede_fora_nao_repete_e_usa_um_artigo_salvo(http, session, falha):
    salvo = _salvar(session, id_origem="salvo")
    _salvar(session, id_origem="reserva", perguntas=PERGUNTAS)
    http.respostas = [falha, artigo(2, "Bom", BOM)]
    assert rf.obter_texto(session, "wikipedia").id == salvo.id  # o salvo vem antes da reserva
    assert len(http.chamadas) == 1


def test_sem_artigo_salvo_usa_a_reserva(http, session):
    reserva = _salvar(session, id_origem="reserva", perguntas=PERGUNTAS)
    _salvar(session, fonte="gutenberg", id_origem="84")  # de outra fonte: não serve como "salvo"
    http.respostas = [requests.ConnectionError()]
    assert rf.obter_texto(session, "wikipedia").id == reserva.id


def test_sem_nada_no_banco_texto_indisponivel(http, session):
    http.respostas = [requests.ConnectionError()]
    with pytest.raises(rf.TextoIndisponivel):
        rf.obter_texto(session, "wikipedia")


def _artigo_com_status(status: int) -> RespostaFalsa:
    """Status de erro com um corpo VÁLIDO: só a conferência do status pode recusar a resposta."""
    resposta = artigo(1, "Honey bee", BOM)
    resposta.status_code = status
    return resposta


@pytest.mark.parametrize("resposta", [
    _artigo_com_status(503),
    _artigo_com_status(429),
    _artigo_com_status(404),
    RespostaFalsa(json=None),            # corpo que não é JSON
    RespostaFalsa(json={"query": {}}),   # JSON sem as páginas
    RespostaFalsa(json={"query": {"pages": []}}),
])
def test_respostas_ruins_da_wikipedia_viram_fonte_indisponivel(http, resposta):
    http.respostas = [resposta]
    with pytest.raises(rf.FonteIndisponivel):
        rf.buscar_wikipedia()


def test_o_mesmo_artigo_e_reaproveitado(http, session):
    http.respostas = [artigo(7, "Honey bee", BOM), artigo(7, "Honey bee", BOM)]
    primeiro = rf.obter_texto(session, "wikipedia")
    segundo = rf.obter_texto(session, "wikipedia")
    assert primeiro.id == segundo.id
    assert len(session.exec(select(ReadingText)).all()) == 1


def test_artigo_ja_gravado_e_reaproveitado_sem_tentar_gravar_de_novo(http, session, monkeypatch):
    """A consulta antes do INSERT evita o erro de UNIQUE e o rollback no caso comum (artigo sorteado de novo)."""
    ja_gravado = _salvar(session, id_origem="7")
    rollbacks = []
    monkeypatch.setattr(session, "rollback", lambda: rollbacks.append(1))
    http.respostas = [artigo(7, "Honey bee", BOM)]
    assert rf.obter_texto(session, "wikipedia").id == ja_gravado.id
    assert rollbacks == []


def test_corrida_entre_dois_desafios_usa_o_texto_ja_gravado(http, session, monkeypatch):
    """Outro desafio grava o mesmo artigo entre a consulta e o commit: o UNIQUE barra, e o serviço usa o dele."""
    ja_gravado = _salvar(session, id_origem="7")
    buscar_de_verdade = rf._buscar_gravado
    consultas = []

    def nao_viu_na_primeira_vez(s, bruto):
        consultas.append(bruto.id_origem)
        return None if len(consultas) == 1 else buscar_de_verdade(s, bruto)

    monkeypatch.setattr(rf, "_buscar_gravado", nao_viu_na_primeira_vez)
    http.respostas = [artigo(7, "Honey bee", BOM)]
    assert rf.obter_texto(session, "wikipedia").id == ja_gravado.id
    assert len(consultas) == 2


def test_fonte_desconhecida(session):
    with pytest.raises(ValueError):
        rf.obter_texto(session, "jornal")


def test_user_agent_identificado():
    assert rf.http_session.headers["User-Agent"].startswith("ShadowingApp/")


# --- Gutenberg ---

LIVRO = ("*** START OF THE PROJECT GUTENBERG EBOOK BEES ***\n\nPREFACE\n\n"
         + paragrafo(300, "prefacio") + "\n\nCHAPTER I\n\n" + paragrafo(150, "um") + "\n\n" + paragrafo(150, "um")
         + "\n\nCHAPTER II\n\n" + paragrafo(500, "dois") + "\n\n*** END OF THE PROJECT GUTENBERG EBOOK BEES ***\n")

GUTENDEX = {"results": [{
    "id": 84, "title": "Bees", "copyright": False,
    "formats": {"application/zip": "https://www.gutenberg.org/cache/84.zip",
                "text/plain; charset=us-ascii": "https://www.gutenberg.org/ebooks/84.txt.utf-8"},
}]}


def test_gutenberg_usa_o_capitulo_1(http, session):
    livro = RespostaFalsa(pedacos=[LIVRO.encode()[:500], LIVRO.encode()[500:]])
    http.respostas = [RespostaFalsa(json=GUTENDEX), livro]
    texto = rf.obter_texto(session, "gutenberg")

    assert (texto.fonte, texto.id_origem, texto.titulo) == ("gutenberg", "84", "Bees")
    assert texto.url == "https://www.gutenberg.org/ebooks/84"
    assert texto.conteudo.startswith("um um") and "prefacio" not in texto.conteudo and texto.palavras == 300

    (url_lista, lista), (url_livro, baixar) = http.chamadas
    assert url_lista == rf.URL_GUTENDEX
    # R13b: só languages=en (com qualquer outro filtro o Gutendex pode passar de 30 s) e timeout curto
    assert lista["params"] == {"languages": "en"} and lista["timeout"] == rf.TIMEOUT_GUTENDEX == 5
    # O .txt vem do espelho oficial (o www.gutenberg.org recusa downloads automáticos), e não da URL do Gutendex
    assert url_livro == "https://gutenberg.pglaf.org/cache/epub/84/pg84.txt"
    assert baixar["stream"] is True and baixar["timeout"] == rf.TIMEOUT_LIVRO
    assert livro.fechada


def test_livro_sem_texto_puro_e_pulado(http):
    """Só livros com text/plain (e não só .zip) entram no sorteio; o download sai do espelho com o id do escolhido."""
    lista = {"results": [{"id": 1, "title": "Só zip", "copyright": False,
                          "formats": {"application/zip": "https://x/1.zip"}},
                         GUTENDEX["results"][0]]}
    http.respostas = [RespostaFalsa(json=lista), RespostaFalsa(pedacos=[LIVRO.encode()])]
    assert rf.buscar_gutenberg().id_origem == "84"
    assert http.chamadas[1][0] == rf.URL_TEXTO_GUTENBERG.format(id=84)


@pytest.mark.parametrize("titulo, serve", [
    ("Chambers's Twentieth Century Dictionary (part 1 of 4: A-D)", False),
    ("The Complete Works of William Shakespeare", False),
    ("The Works of William Shakespeare [Cambridge Edition] [Vol. 5 of 9]", False),
    ("Encyclopaedia Britannica, Volume 1", False),
    ("Roget's Thesaurus of English Words and Phrases", False),
    ("Pride and Prejudice", True),
    ("The Adventures of Tom Sawyer, Complete", True),
    ("Indexed Tales of the Sea", True),  # "index" só como palavra inteira
])
def test_obras_de_consulta_ficam_fora_do_sorteio(http, titulo, serve):
    livro = {"id": 7, "title": titulo, "copyright": False, "formats": {"text/plain; charset=utf-8": "https://x/7.txt"}}
    http.respostas = [RespostaFalsa(json={"results": [livro]}), RespostaFalsa(pedacos=[LIVRO.encode()])]
    if serve:
        assert rf.buscar_gutenberg().titulo == titulo
    else:  # o único livro da lista foi filtrado: o sorteio sai do catálogo (R13b)
        assert rf.buscar_gutenberg().titulo in dict(rf.CATALOGO_GUTENBERG).values()


@pytest.mark.parametrize("tipo", ["text/html; charset=utf-8", "application/octet-stream", ""])
def test_espelho_que_nao_devolve_texto_puro_e_fonte_indisponivel(http, tipo):
    """R13: uma página HTML com status 200 (manutenção, bloqueio) não pode virar o trecho do desafio."""
    pagina = RespostaFalsa(pedacos=[b"<html><body><p>Site under maintenance. Please come back later.</p>"], tipo=tipo)
    http.respostas = [RespostaFalsa(json=GUTENDEX), pagina]
    with pytest.raises(rf.FonteIndisponivel, match="texto puro"):
        rf.buscar_gutenberg()
    assert pagina.fechada and pagina.pedacos_lidos == 0  # nem chegou a ler o corpo


def test_espelho_fora_do_ar_e_fonte_indisponivel(http):
    http.respostas = [RespostaFalsa(json=GUTENDEX), RespostaFalsa(status=503)]
    with pytest.raises(rf.FonteIndisponivel):
        rf.buscar_gutenberg()


def test_gutenberg_le_no_maximo_o_limite_de_bytes(http, monkeypatch):
    monkeypatch.setattr(rf, "LIMITE_BYTES_LIVRO", 1000)
    livro = RespostaFalsa(pedacos=[b"x" * 300] * 10)  # 3.000 bytes no total
    http.respostas = [RespostaFalsa(json=GUTENDEX), livro]
    rf.buscar_gutenberg()
    assert livro.pedacos_lidos == 4  # 300, 600, 900, 1.200 ≥ 1.000: para aí
    assert livro.fechada


# --- Catálogo de reserva do Gutenberg (R13b) ---

def _livro_do_catalogo(http) -> tuple[str, str]:
    """(título escolhido, URL baixada) de um sorteio que deveria ter saído do catálogo."""
    texto = rf.buscar_gutenberg()
    url_baixada = http.chamadas[-1][0]
    catalogo = dict(rf.CATALOGO_GUTENBERG)
    assert int(texto.id_origem) in catalogo and texto.titulo == catalogo[int(texto.id_origem)]
    assert url_baixada == rf.URL_TEXTO_GUTENBERG.format(id=texto.id_origem)
    return texto.titulo, url_baixada


@pytest.mark.parametrize("falha", [
    requests.Timeout("lento"),                               # o caso real de 25/11/2026 (mais de 30 s)
    requests.ConnectionError("fora do ar"),
    RespostaFalsa(status=503, json={"results": []}),
    RespostaFalsa(json=None),                                # não é JSON
    RespostaFalsa(json={"outra": "coisa"}),                  # sem "results"
    RespostaFalsa(json={"results": [{"titulo": "sem id"}]}),
])
def test_gutendex_com_falha_sorteia_do_catalogo(http, falha):
    http.respostas = [falha, RespostaFalsa(pedacos=[LIVRO.encode()])]
    _livro_do_catalogo(http)
    assert len(http.chamadas) == 2  # uma tentativa no Gutendex (sem repetir) e o download


@pytest.mark.parametrize("lista", [
    {"results": []},
    {"results": [{"id": 1, "title": "Só zip", "copyright": False, "formats": {"application/zip": "https://x/1.zip"}}]},
])
def test_gutendex_sem_livro_utilizavel_sorteia_do_catalogo(http, lista):
    http.respostas = [RespostaFalsa(json=lista), RespostaFalsa(pedacos=[LIVRO.encode()])]
    _livro_do_catalogo(http)


@pytest.mark.parametrize("copyright_", [True, None])
def test_livro_com_direitos_autorais_fica_fora(http, copyright_):
    """O domínio público é conferido no código (o filtro copyright=false do Gutendex deixava a consulta lenta)."""
    livro = {**GUTENDEX["results"][0], "copyright": copyright_}
    http.respostas = [RespostaFalsa(json={"results": [livro]}), RespostaFalsa(pedacos=[LIVRO.encode()])]
    titulo, _ = _livro_do_catalogo(http)
    assert titulo != "Bees"


def test_catalogo_so_tem_livros_utilizaveis():
    ids = [id_livro for id_livro, _ in rf.CATALOGO_GUTENBERG]
    assert len(ids) == len(set(ids)) >= 20
    for id_livro, titulo in rf.CATALOGO_GUTENBERG:
        assert isinstance(id_livro, int) and id_livro > 0 and titulo.strip()
        assert not rf._NAO_E_LEITURA.search(titulo), titulo


def test_livro_cortado_no_limite_nao_deixa_paragrafo_pela_metade(http, monkeypatch):
    """O corte cai no meio do 2º parágrafo, logo depois de um ponto: o pedaço não pode virar parágrafo."""
    inteiro = "First full paragraph of the book, long enough to count.\r\n\r\nSecond paragraph. It goes on and on"
    monkeypatch.setattr(rf, "LIMITE_BYTES_LIVRO", len(inteiro.encode()) - 15)  # corta em "Second paragraph. It"
    http.respostas = [RespostaFalsa(pedacos=[inteiro.encode()])]
    assert rf._baixar_texto("https://espelho/1.txt") == "First full paragraph of the book, long enough to count."


def test_livro_inteiro_abaixo_do_limite_vem_completo(http):
    livro = "Para um.\r\n\r\nPara dois, ainda sem ponto"
    http.respostas = [RespostaFalsa(pedacos=[livro.encode()])]
    assert rf._baixar_texto("https://espelho/1.txt") == livro.replace("\r\n", "\n")  # não cortou: nada some


def test_download_lento_demais_e_fonte_indisponivel(http, monkeypatch):
    """O timeout de leitura vale por pedaço: um espelho lento poderia levar minutos (medido: 3 MB em 150 s)."""
    tempos = iter([0, 10, 20, 30])
    monkeypatch.setattr(rf, "_relogio", lambda: next(tempos))
    livro = RespostaFalsa(pedacos=[b"x" * 100] * 10)
    http.respostas = [livro]
    with pytest.raises(rf.FonteIndisponivel, match="lento demais"):
        rf._baixar_texto("https://espelho/1.txt")
    assert livro.pedacos_lidos == 3 and livro.fechada


def test_falha_no_download_do_livro(http):
    class QuebraNoMeio(RespostaFalsa):
        def iter_content(self, chunk_size):
            yield b"comeco"
            raise requests.ConnectionError("caiu")

    livro = QuebraNoMeio()
    http.respostas = [RespostaFalsa(json=GUTENDEX), livro]
    with pytest.raises(rf.FonteIndisponivel):
        rf.buscar_gutenberg()
    assert livro.fechada


# --- Crédito ---

def test_credito_de_cada_fonte():
    wikipedia = ReadingText(fonte="wikipedia", id_origem="1", titulo="Moon", url="https://en.wikipedia.org/wiki/Moon",
                            conteudo="", palavras=0)
    assert "Wikipedia" in rf.credito(wikipedia) and "CC BY-SA 4.0" in rf.credito(wikipedia)
    assert "\"Moon\"" in rf.credito(wikipedia) and "https://en.wikipedia.org/wiki/Moon" in rf.credito(wikipedia)
    gutenberg = ReadingText(fonte="gutenberg", id_origem="84", titulo="Bees", url="https://www.gutenberg.org/ebooks/84",
                            conteudo="", palavras=0)
    assert "domínio público" in rf.credito(gutenberg) and "\"Bees\"" in rf.credito(gutenberg)


# --- Migração 0102 (textos de reserva) ---

@pytest.fixture()
def banco_migrado(tmp_path):
    url = f"sqlite:///{tmp_path / 'estudos.db'}"
    migrar.migrar(url, tmp_path / "backup")
    engine = create_engine(url)
    yield url, engine
    engine.dispose()


def _reservas(engine) -> list[ReadingText]:
    with Session(engine) as s:
        return list(s.exec(select(ReadingText).where(ReadingText.perguntas_reserva.is_not(None))).all())


def test_migracao_insere_cinco_textos_de_reserva_validos(banco_migrado):
    _, engine = banco_migrado
    reservas = _reservas(engine)
    assert len(reservas) == 5
    for texto in reservas:
        assert texto.fonte == "wikipedia" and texto.url.startswith("https://en.wikipedia.org/wiki/")
        assert rt.PALAVRAS_MIN <= texto.palavras <= rt.PALAVRAS_MAX
        assert rt.contar_palavras(texto.conteudo) == texto.palavras
        assert not rt.eh_inadequado(texto.titulo, texto.conteudo)
        assert len(texto.perguntas_reserva) == 5
        for pergunta in texto.perguntas_reserva:
            assert pergunta["enunciado"].strip() and pergunta["justificativa"].strip()
            assert len(pergunta["alternativas"]) == 4 == len(set(pergunta["alternativas"]))
            assert pergunta["resposta_correta"] in pergunta["alternativas"]


def test_reserva_do_banco_migrado_e_encontrada(banco_migrado):
    _, engine = banco_migrado
    with Session(engine) as s:
        assert rf.texto_de_reserva(s).perguntas_reserva
        assert rf.texto_salvo(s, "wikipedia") is None  # a reserva não conta como "artigo salvo"


def test_downgrade_preserva_o_historico_dos_textos_ja_usados(banco_migrado):
    url, engine = banco_migrado
    usado = _reservas(engine)[0]
    with Session(engine) as s:
        usuario = Usuario(email="ana@exemplo.com", senha_hash="x")
        s.add(usuario)
        s.commit()
        s.add(ReadingChallenge(usuario_id=usuario.id, texto_id=usado.id, modalidade="multipla_escolha", ppm=200,
                               limite_segundos=90))
        s.commit()

    cfg = migrar.config_alembic(url)
    command.downgrade(cfg, "0101")
    with engine.connect() as conexao:
        linhas = conexao.execute(text("SELECT id, perguntas_reserva IS NULL FROM readingtext")).all()
    assert linhas == [(usado.id, 1)]  # só o texto usado ficou, como texto comum (NULL do SQL)

    command.upgrade(cfg, "head")
    assert len(_reservas(engine)) == 4  # os outros quatro voltam; o usado não é duplicado
