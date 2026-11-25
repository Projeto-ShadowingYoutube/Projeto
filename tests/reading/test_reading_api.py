"""Bloco R5: criação do desafio (POST /api/reading/challenges) e o resumo (GET /api/reading/challenges/{id}).

Integração FastAPI + serviços + banco: a fonte de texto é falsa (rf.FONTES) e a LLM é a llm_falsa.
"""
import pytest
from sqlmodel import Session, select

from app import config
from app.models import Usuario
from app.models_reading import ReadingChallenge, ReadingQuestion, ReadingText
from app.services import llm
from app.services import reading_desafios as rd
from app.services import reading_fontes as rf
from app.services import reading_llm as rl

URL = "/api/reading/challenges"
INTRO = " ".join(["bees"] * 300) + "."  # 300 palavras: limite de 90 s a 200 ppm


def _mc(n: int) -> dict:
    return {"enunciado": f"What does the text say about item {n}?",
            "alternativas": [f"Right {n}", f"Wrong A {n}", f"Wrong B {n}", f"Wrong C {n}"],
            "resposta_correta": f"Right {n}", "justificativa": f"O texto diz \"item {n}\"."}


RESPOSTA_MC = {"perguntas": [{"tipo": "multipla_escolha", **_mc(n)} for n in range(1, 6)]}
PERGUNTAS_PRONTAS = [_mc(n) for n in range(1, 6)]


pytestmark = pytest.mark.usefixtures("cota_nova")  # tests/reading/conftest.py


class FonteFalsa:
    """Substitui as fontes do R3 (rf.FONTES): devolve um artigo bom, ou simula a fonte fora do ar."""

    def __init__(self):
        self.fora = False
        self.chamadas = []

    def buscar(self, fonte: str):
        def _buscar():
            self.chamadas.append(fonte)
            if self.fora:
                raise rf.FonteIndisponivel("simulada")
            return rf.TextoBruto(fonte=fonte, id_origem=str(len(self.chamadas)), titulo=f"Bees ({fonte})",
                                 url=f"https://exemplo.org/{fonte}", secoes=[[INTRO]])
        return _buscar


@pytest.fixture()
def fonte(monkeypatch):
    falsa = FonteFalsa()
    monkeypatch.setattr(rf, "FONTES", {"wikipedia": falsa.buscar("wikipedia"), "gutenberg": falsa.buscar("gutenberg")})
    return falsa


def _reserva(engine, palavras: int = 450) -> ReadingText:
    with Session(engine) as s:
        texto = ReadingText(fonte="wikipedia", id_origem="reserva", titulo="Honey bee", url="https://x/Honey_bee",
                            conteudo=" ".join(["honey"] * palavras), palavras=palavras,
                            perguntas_reserva=PERGUNTAS_PRONTAS)
        s.add(texto)
        s.commit()
        s.refresh(texto)
        return texto


def _desafios(engine) -> list[ReadingChallenge]:
    with Session(engine) as s:
        return list(s.exec(select(ReadingChallenge)).all())


def _perguntas(engine) -> list[ReadingQuestion]:
    with Session(engine) as s:
        return list(s.exec(select(ReadingQuestion).order_by(ReadingQuestion.ordem)).all())


# --- Criação ---

def test_cria_o_desafio_com_texto_e_cinco_perguntas(entrar_como, fonte, llm_falsa, engine_teste):
    ana = entrar_como("ana@exemplo.com")
    llm_falsa.responder(RESPOSTA_MC)

    resposta = ana.post(URL, json={"modalidade": "multipla_escolha"})

    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    assert corpo["estado"] == "lendo" and corpo["modalidade"] == "multipla_escolha"
    assert corpo["ppm"] == 200 and corpo["limite_segundos"] == 90 and corpo["usou_reserva"] is False
    assert corpo["texto"]["titulo"] == "Bees (wikipedia)" and corpo["texto"]["palavras"] == 300
    assert corpo["texto"]["conteudo"] == INTRO
    assert "CC BY-SA 4.0" in corpo["texto"]["credito"]

    [desafio] = _desafios(engine_teste)
    assert desafio.id == corpo["id"] and desafio.usuario_id == ana.get("/api/auth/me").json()["id"]
    assert desafio.modelo_llm == config.LLM_MODELO
    perguntas = _perguntas(engine_teste)
    assert [p.ordem for p in perguntas] == [1, 2, 3, 4, 5]
    assert all(p.desafio_id == desafio.id for p in perguntas)
    assert [p.enunciado for p in perguntas] == [p["enunciado"] for p in RESPOSTA_MC["perguntas"]]
    assert sorted(perguntas[0].alternativas) == sorted(RESPOSTA_MC["perguntas"][0]["alternativas"])


def test_a_resposta_nao_revela_as_perguntas(entrar_como, fonte, llm_falsa):
    """As perguntas só saem do servidor quando a leitura termina (R6)."""
    llm_falsa.responder(RESPOSTA_MC)
    resposta = entrar_como("ana@exemplo.com").post(URL, json={"modalidade": "multipla_escolha"})
    assert "perguntas" not in resposta.json()
    for segredo in ("Right 1", "Wrong A 1", "item 1", "resposta_correta", "justificativa"):
        assert segredo not in resposta.text


def test_valores_padrao_e_escolhas(entrar_como, fonte, llm_falsa):
    ana = entrar_como("ana@exemplo.com")
    llm_falsa.responder(RESPOSTA_MC)
    padrao = ana.post(URL, json={"modalidade": "multipla_escolha"}).json()
    assert (padrao["ppm"], padrao["texto"]["fonte"]) == (200, "wikipedia")

    llm_falsa.responder({"perguntas": [{"tipo": "aberta", "enunciado": f"Why item {n}?", "resposta_correta": "Yes.",
                                        "justificativa": "O texto diz \"yes\"."} for n in range(1, 6)]})
    escolhido = ana.post(URL, json={"modalidade": "aberta", "fonte": "gutenberg", "ppm": 150}).json()
    assert escolhido["modalidade"] == "aberta" and escolhido["ppm"] == 150
    assert escolhido["limite_segundos"] == 120  # 300 palavras a 150 ppm
    assert escolhido["texto"]["fonte"] == "gutenberg" and "domínio público" in escolhido["texto"]["credito"]
    assert fonte.chamadas == ["wikipedia", "gutenberg"]


@pytest.mark.parametrize("corpo", [
    {},
    {"modalidade": "verdadeiro_falso"},
    {"modalidade": "aberta", "ppm": 180},
    {"modalidade": "aberta", "ppm": "200"},
    {"modalidade": "aberta", "fonte": "youtube"},
    {"modalidade": "aberta", "limite_segundos": 9999},  # campo extra: o cliente não escolhe o próprio tempo
])
def test_corpo_invalido(entrar_como, fonte, engine_teste, corpo):
    resposta = entrar_como("ana@exemplo.com").post(URL, json=corpo)
    assert resposta.status_code == 422 and resposta.json()["codigo"] == "dados_invalidos"
    assert fonte.chamadas == [] and _desafios(engine_teste) == []


def test_sem_login_responde_401(client, fonte):
    assert client.post(URL, json={"modalidade": "aberta"}).status_code == 401
    assert fonte.chamadas == []


def test_cota_de_dez_desafios_por_dia(entrar_como, fonte, engine_teste):
    """Fonte fora + reserva no banco: os desafios saem sem chamar a LLM."""
    _reserva(engine_teste)
    fonte.fora = True
    ana, bruno = entrar_como("ana@exemplo.com"), entrar_como("bruno@exemplo.com")
    for _ in range(10):
        assert ana.post(URL, json={"modalidade": "aberta"}).status_code == 201

    resposta = ana.post(URL, json={"modalidade": "aberta"})
    assert resposta.status_code == 429 and resposta.json()["codigo"] == "limite_de_desafios"
    assert len(_desafios(engine_teste)) == 10
    assert bruno.post(URL, json={"modalidade": "aberta"}).status_code == 201  # a cota é por conta


def test_sem_texto_nenhum_responde_502(entrar_como, fonte, engine_teste):
    fonte.fora = True
    resposta = entrar_como("ana@exemplo.com").post(URL, json={"modalidade": "aberta"})
    assert resposta.status_code == 502
    assert resposta.json()["codigo"] == "texto_indisponivel" and resposta.json()["detail"]
    assert _desafios(engine_teste) == []


def test_llm_fora_usa_o_texto_de_reserva(entrar_como, fonte, llm_falsa, engine_teste):
    reserva = _reserva(engine_teste, palavras=450)
    llm_falsa.falhar(llm.LLMIndisponivel())

    corpo = entrar_como("ana@exemplo.com").post(URL, json={"modalidade": "multipla_escolha"}).json()

    assert corpo["usou_reserva"] is True and corpo["texto"]["titulo"] == "Honey bee"
    assert corpo["limite_segundos"] == 135  # calculado com o texto de reserva (450 palavras), não com o original
    [desafio] = _desafios(engine_teste)
    assert desafio.texto_id == reserva.id and desafio.modelo_llm is None and desafio.usou_reserva is True
    assert [p.resposta_correta for p in _perguntas(engine_teste)] == [p["resposta_correta"] for p in PERGUNTAS_PRONTAS]


def test_llm_fora_e_sem_reserva_responde_o_erro_padrao(entrar_como, fonte, llm_falsa, engine_teste):
    llm_falsa.falhar(llm.LLMTempoEsgotado())
    resposta = entrar_como("ana@exemplo.com").post(URL, json={"modalidade": "multipla_escolha"})
    assert resposta.status_code == 504 and resposta.json()["codigo"] == "llm_tempo_esgotado"
    assert _desafios(engine_teste) == [] and _perguntas(engine_teste) == []


def test_desafios_simultaneos_sao_permitidos(entrar_como, fonte, engine_teste):
    _reserva(engine_teste)
    fonte.fora = True
    ana = entrar_como("ana@exemplo.com")
    ids = {ana.post(URL, json={"modalidade": "aberta"}).json()["id"] for _ in range(2)}
    assert len(ids) == 2


# --- Regras do serviço ---

def test_relogio_da_leitura_comeca_depois_da_geracao(engine_teste, fonte, monkeypatch):
    """A espera pela fonte e pela LLM não conta como tempo de leitura."""
    _reserva(engine_teste)
    eventos = []
    original = rl.perguntas_para_o_desafio
    real_agora = rd.agora

    def perguntas(*args, **kwargs):
        eventos.append("perguntas")
        return original(*args, **kwargs)

    def relogio():
        eventos.append("relogio")
        return real_agora()

    monkeypatch.setattr(rd.rl, "perguntas_para_o_desafio", perguntas)
    monkeypatch.setattr(rd, "agora", relogio)
    fonte.fora = True
    with Session(engine_teste) as s:
        rd.criar_desafio(s, usuario_id=_usuario(s), fonte="wikipedia", modalidade="aberta", ppm=200)
    assert eventos == ["perguntas", "relogio"]


def test_falha_ao_gravar_as_perguntas_nao_deixa_desafio_pela_metade(engine_teste, fonte, monkeypatch):
    _reserva(engine_teste)
    fonte.fora = True

    def pergunta_que_falha(**kwargs):
        raise RuntimeError("falha simulada")

    monkeypatch.setattr(rd, "ReadingQuestion", pergunta_que_falha)
    with Session(engine_teste) as s:
        usuario_id = _usuario(s)
        with pytest.raises(RuntimeError):
            rd.criar_desafio(s, usuario_id=usuario_id, fonte="wikipedia", modalidade="aberta", ppm=200)
    assert _desafios(engine_teste) == []


def test_ppm_invalido_e_recusado_antes_de_buscar_o_texto(engine_teste, fonte):
    with Session(engine_teste) as s, pytest.raises(ValueError):
        rd.criar_desafio(s, usuario_id=1, fonte="wikipedia", modalidade="aberta", ppm=180)
    assert fonte.chamadas == []


def _usuario(session) -> int:
    usuario = Usuario(email="servico@exemplo.com", senha_hash="x")
    session.add(usuario)
    session.commit()
    return usuario.id


# --- Resumo e isolamento ---

def test_resumo_do_proprio_desafio(entrar_como, fonte, engine_teste):
    _reserva(engine_teste)
    fonte.fora = True
    ana = entrar_como("ana@exemplo.com")
    criado = ana.post(URL, json={"modalidade": "aberta"}).json()

    resumo = ana.get(f"{URL}/{criado['id']}")
    assert resumo.status_code == 200
    assert resumo.json() == {k: criado[k] for k in resumo.json()}
    assert "texto" not in resumo.json() and "perguntas" not in resumo.json()
    assert resumo.json()["leitura_encerrada_em"] is None


def test_desafio_de_outra_conta_responde_404_igual_a_inexistente(entrar_como, fonte, engine_teste):
    _reserva(engine_teste)
    fonte.fora = True
    ana, bruno = entrar_como("ana@exemplo.com"), entrar_como("bruno@exemplo.com")
    id_da_ana = ana.post(URL, json={"modalidade": "aberta"}).json()["id"]

    de_outro = bruno.get(f"{URL}/{id_da_ana}")
    inexistente = bruno.get(f"{URL}/999999")
    assert de_outro.status_code == inexistente.status_code == 404
    assert de_outro.json() == inexistente.json() == {"detail": "Desafio não encontrado.", "codigo": "nao_encontrado"}
