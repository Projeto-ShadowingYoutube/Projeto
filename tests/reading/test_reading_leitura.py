"""Bloco R6: leitura com o tempo validado no servidor (texto só dentro do prazo; encerrar libera as perguntas).

O relógio é falso (rd.agora): nenhum teste espera o tempo passar. Os desafios saem da reserva (fonte fora do ar e
sem LLM): 450 palavras a 200 ppm = limite de 135 s.
"""
from datetime import datetime, timedelta

import pytest
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter
from sqlmodel import Session, select

from app.api import llm as rota_llm
from app.models import Usuario
from app.models_reading import ReadingChallenge, ReadingQuestion, ReadingText
from app.services import reading_desafios as rd
from app.services import reading_fontes as rf

URL = "/api/reading/challenges"
INICIO = datetime(2026, 11, 22, 10, 0, 0)
LIMITE = 135
CONTEUDO = " ".join(["honey"] * 450)


def _mc(n: int) -> dict:
    return {"enunciado": f"What does the text say about item {n}?",
            "alternativas": [f"Right {n}", f"Wrong A {n}", f"Wrong B {n}", f"Wrong C {n}"],
            "resposta_correta": f"Right {n}", "justificativa": f"Segredo da justificativa {n}."}


class Relogio:
    def __init__(self):
        self.agora = INICIO

    def __call__(self) -> datetime:
        return self.agora

    def avancar(self, segundos: float) -> None:
        self.agora += timedelta(seconds=segundos)


@pytest.fixture()
def relogio(monkeypatch):
    falso = Relogio()
    monkeypatch.setattr(rd, "agora", falso)
    return falso


@pytest.fixture(autouse=True)
def ambiente(monkeypatch, engine_teste):
    """Cota nova, fonte fora do ar e um texto de reserva: o desafio sai sem rede e sem LLM."""
    monkeypatch.setattr(rota_llm, "limitador", FixedWindowRateLimiter(MemoryStorage()))

    def fora():
        raise rf.FonteIndisponivel("simulada")

    monkeypatch.setattr(rf, "FONTES", {"wikipedia": fora, "gutenberg": fora})
    with Session(engine_teste) as s:
        s.add(ReadingText(fonte="wikipedia", id_origem="reserva", titulo="Honey bee", url="https://x/Honey_bee",
                          conteudo=CONTEUDO, palavras=450, perguntas_reserva=[_mc(n) for n in range(1, 6)]))
        s.commit()


def _criar(cliente, modalidade: str = "multipla_escolha") -> int:
    resposta = cliente.post(URL, json={"modalidade": modalidade})
    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["limite_segundos"] == LIMITE
    return resposta.json()["id"]


def _no_banco(engine, desafio_id: int) -> ReadingChallenge:
    with Session(engine) as s:
        return s.get(ReadingChallenge, desafio_id)


# --- Texto só dentro do prazo ---

def test_texto_dentro_do_prazo(entrar_como, relogio):
    ana = entrar_como("ana@exemplo.com")
    desafio_id = _criar(ana)
    relogio.avancar(35)

    resposta = ana.get(f"{URL}/{desafio_id}/texto")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["conteudo"] == CONTEUDO and corpo["titulo"] == "Honey bee"
    assert corpo["segundos_restantes"] == LIMITE - 35
    assert "CC BY-SA 4.0" in corpo["credito"]


@pytest.mark.parametrize("passados, disponivel", [
    (LIMITE, True),
    (LIMITE + 5, True),   # DR22: 5 s de tolerância para a latência da rede (valor fixo: não lê a constante)
    (LIMITE + 6, False),
    (3600, False),
])
def test_texto_bloqueado_depois_do_prazo_e_da_tolerancia(entrar_como, relogio, passados, disponivel):
    ana = entrar_como("ana@exemplo.com")
    desafio_id = _criar(ana)
    relogio.avancar(passados)

    resposta = ana.get(f"{URL}/{desafio_id}/texto")
    if disponivel:
        assert resposta.status_code == 200 and resposta.json()["segundos_restantes"] == 0
    else:
        assert resposta.status_code == 409
        assert resposta.json() == {"detail": "O tempo de leitura deste desafio acabou.", "codigo": "leitura_encerrada"}


def test_texto_bloqueado_depois_de_encerrar(entrar_como, relogio):
    ana = entrar_como("ana@exemplo.com")
    desafio_id = _criar(ana)
    relogio.avancar(10)
    ana.post(f"{URL}/{desafio_id}/encerrar-leitura")
    assert ana.get(f"{URL}/{desafio_id}/texto").status_code == 409


# --- Encerrar a leitura ---

def test_encerrar_antes_do_prazo_grava_o_horario_real(entrar_como, relogio, engine_teste):
    ana = entrar_como("ana@exemplo.com")
    desafio_id = _criar(ana)
    relogio.avancar(40)

    resposta = ana.post(f"{URL}/{desafio_id}/encerrar-leitura")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["estado"] == "respondendo" and corpo["segundos_restantes"] == 0
    assert corpo["leitura_encerrada_em"] == (INICIO + timedelta(seconds=40)).isoformat()
    desafio = _no_banco(engine_teste, desafio_id)
    assert desafio.estado == "respondendo" and desafio.leitura_encerrada_em == INICIO + timedelta(seconds=40)


def test_encerrar_depois_do_prazo_grava_o_fim_do_prazo(entrar_como, relogio, engine_teste):
    """Aba fechada e volta depois: as perguntas continuam disponíveis, e a leitura conta como o limite."""
    ana = entrar_como("ana@exemplo.com")
    desafio_id = _criar(ana)
    relogio.avancar(1000)

    corpo = ana.post(f"{URL}/{desafio_id}/encerrar-leitura").json()
    assert len(corpo["perguntas"]) == 5
    assert _no_banco(engine_teste, desafio_id).leitura_encerrada_em == INICIO + timedelta(seconds=LIMITE)


def test_perguntas_sem_resposta_e_sem_justificativa(entrar_como, relogio):
    ana = entrar_como("ana@exemplo.com")
    resposta = ana.post(f"{URL}/{_criar(ana)}/encerrar-leitura")

    perguntas = resposta.json()["perguntas"]
    assert [p["ordem"] for p in perguntas] == [1, 2, 3, 4, 5]
    assert all(set(p) == {"ordem", "tipo", "enunciado", "alternativas"} for p in perguntas)
    assert all(p["tipo"] == "multipla_escolha" and len(p["alternativas"]) == 4 for p in perguntas)
    assert "resposta_correta" not in resposta.text and "Segredo da justificativa" not in resposta.text


def test_perguntas_abertas_sem_alternativas(entrar_como, relogio):
    ana = entrar_como("ana@exemplo.com")
    perguntas = ana.post(f"{URL}/{_criar(ana, 'aberta')}/encerrar-leitura").json()["perguntas"]
    assert all(p["tipo"] == "aberta" and p["alternativas"] == [] for p in perguntas)
    assert "Right 1" not in str(perguntas)  # na aberta, a resposta esperada não pode vazar pelas alternativas


def test_encerrar_e_idempotente(entrar_como, relogio, engine_teste):
    """F5 ou clique duplo: mesmas perguntas, e o horário gravado não muda."""
    ana = entrar_como("ana@exemplo.com")
    desafio_id = _criar(ana)
    relogio.avancar(40)
    primeira = ana.post(f"{URL}/{desafio_id}/encerrar-leitura").json()
    relogio.avancar(20)
    segunda = ana.post(f"{URL}/{desafio_id}/encerrar-leitura")

    assert segunda.status_code == 200 and segunda.json() == primeira
    assert _no_banco(engine_teste, desafio_id).leitura_encerrada_em == INICIO + timedelta(seconds=40)


def test_duas_requisicoes_simultaneas_gravam_so_o_primeiro_horario(engine_teste, relogio):
    """Duas sessões leram o desafio em "lendo"; a segunda a encerrar não sobrescreve o horário da primeira."""
    with Session(engine_teste) as s:
        usuario = Usuario(email="ana@exemplo.com", senha_hash="x")
        s.add(usuario)
        s.commit()
        desafio, _ = rd.criar_desafio(s, usuario.id, fonte="wikipedia", modalidade="aberta", ppm=200)
        desafio_id = desafio.id

    with Session(engine_teste) as primeira, Session(engine_teste) as segunda:
        na_primeira, na_segunda = primeira.get(ReadingChallenge, desafio_id), segunda.get(ReadingChallenge, desafio_id)
        rd.encerrar_leitura(primeira, na_primeira, INICIO + timedelta(seconds=10))
        rd.encerrar_leitura(segunda, na_segunda, INICIO + timedelta(seconds=50))
        assert na_segunda.leitura_encerrada_em == INICIO + timedelta(seconds=10)  # releu o que a primeira gravou
    assert _no_banco(engine_teste, desafio_id).leitura_encerrada_em == INICIO + timedelta(seconds=10)


# --- Resumo ---

def test_resumo_mostra_os_segundos_restantes(entrar_como, relogio):
    ana = entrar_como("ana@exemplo.com")
    desafio_id = _criar(ana)

    relogio.avancar(35)
    assert ana.get(f"{URL}/{desafio_id}").json()["segundos_restantes"] == LIMITE - 35
    relogio.avancar(200)
    assert ana.get(f"{URL}/{desafio_id}").json()["segundos_restantes"] == 0


def test_resumo_depois_de_encerrar(entrar_como, relogio):
    ana = entrar_como("ana@exemplo.com")
    desafio_id = _criar(ana)
    ana.post(f"{URL}/{desafio_id}/encerrar-leitura")
    resumo = ana.get(f"{URL}/{desafio_id}").json()
    assert resumo["estado"] == "respondendo" and resumo["segundos_restantes"] == 0


# --- Isolamento ---

@pytest.mark.parametrize("metodo, sufixo", [("get", "/texto"), ("post", "/encerrar-leitura")])
def test_rotas_da_leitura_de_outra_conta_respondem_404(entrar_como, relogio, engine_teste, metodo, sufixo):
    ana, bruno = entrar_como("ana@exemplo.com"), entrar_como("bruno@exemplo.com")
    desafio_id = _criar(ana)

    de_outro = getattr(bruno, metodo)(f"{URL}/{desafio_id}{sufixo}")
    inexistente = getattr(bruno, metodo)(f"{URL}/999999{sufixo}")
    assert de_outro.status_code == inexistente.status_code == 404
    assert de_outro.json() == inexistente.json()
    assert _no_banco(engine_teste, desafio_id).estado == "lendo"  # o Bruno não encerrou a leitura da Ana


# --- Regras de tempo (funções puras) ---

def _desafio(estado: str = "lendo") -> ReadingChallenge:
    return ReadingChallenge(usuario_id=1, texto_id=1, modalidade="aberta", ppm=200, limite_segundos=LIMITE,
                            estado=estado, iniciado_em=INICIO)


@pytest.mark.parametrize("passados, restantes", [(0, 135), (0.5, 135), (1, 134), (134.2, 1), (135, 0), (500, 0)])
def test_segundos_restantes_arredonda_para_cima(passados, restantes):
    assert rd.segundos_restantes(_desafio(), INICIO + timedelta(seconds=passados)) == restantes


def test_segundos_restantes_fora_da_leitura():
    assert rd.segundos_restantes(_desafio("respondendo"), INICIO) == 0


def test_leitura_disponivel_so_em_lendo():
    assert rd.leitura_disponivel(_desafio(), INICIO)
    assert not rd.leitura_disponivel(_desafio("respondendo"), INICIO)


def test_perguntas_saem_na_ordem_mesmo_gravadas_fora_de_ordem(engine_teste):
    with Session(engine_teste) as s:
        usuario = Usuario(email="ana@exemplo.com", senha_hash="x")
        s.add(usuario)
        s.commit()
        texto = s.exec(select(ReadingText)).first()
        desafio = ReadingChallenge(usuario_id=usuario.id, texto_id=texto.id, modalidade="aberta", ppm=200,
                                   limite_segundos=LIMITE)
        s.add(desafio)
        s.commit()
        for ordem in (3, 1, 5, 2, 4):
            s.add(ReadingQuestion(desafio_id=desafio.id, ordem=ordem, tipo="aberta", enunciado=f"Q{ordem}?",
                                  resposta_correta="A.", justificativa="J."))
        s.commit()
        assert [p.ordem for p in rd.perguntas_do_desafio(s, desafio)] == [1, 2, 3, 4, 5]
