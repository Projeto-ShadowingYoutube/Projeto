"""Bloco R7: envio das respostas, correção da múltipla escolha e o resultado.

Relógio falso (rd.agora). Os desafios saem da reserva (fonte fora e sem LLM): 450 palavras a 200 ppm = 135 s; a
resposta certa da pergunta n é "Right n".
"""
from datetime import datetime, timedelta

import pytest
from sqlmodel import Session, select

from app.models import Usuario
from app.models_reading import ReadingAttempt, ReadingChallenge, ReadingQuestion
from app.services import reading_correcao as rc
from app.services import reading_desafios as rd

URL = "/api/reading/challenges"
INICIO = datetime(2026, 11, 22, 10, 0, 0)
CERTAS = [f"Right {n}" for n in range(1, 6)]



pytestmark = pytest.mark.usefixtures("ambiente")  # tests/reading/conftest.py



def _pronto(cliente, relogio, modalidade: str = "multipla_escolha", leitura: int = 40) -> int:
    """Cria o desafio, lê por `leitura` segundos e encerra a leitura. Devolve o id."""
    desafio_id = cliente.post(URL, json={"modalidade": modalidade}).json()["id"]
    relogio.avancar(leitura)
    assert cliente.post(f"{URL}/{desafio_id}/encerrar-leitura").status_code == 200
    return desafio_id


def _enviar(cliente, desafio_id: int, respostas: list[str]):
    return cliente.post(f"{URL}/{desafio_id}/respostas", json={"respostas": respostas})


def _tentativas(engine) -> list[ReadingAttempt]:
    with Session(engine) as s:
        return list(s.exec(select(ReadingAttempt)).all())


def _estado(engine, desafio_id: int) -> str:
    with Session(engine) as s:
        return s.get(ReadingChallenge, desafio_id).estado


# --- Múltipla escolha ---

def test_todas_certas_nota_dez_e_resultado_completo(entrar_como, relogio):
    ana = entrar_como("ana@exemplo.com")
    desafio_id = _pronto(ana, relogio, leitura=40)
    relogio.avancar(60)

    resposta = _enviar(ana, desafio_id, CERTAS)

    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    assert corpo["estado"] == "corrigido" and corpo["modalidade"] == "multipla_escolha"
    assert (corpo["acertos"], corpo["nota"]) == (5, 10.0)
    assert (corpo["tempo_leitura_segundos"], corpo["tempo_resposta_segundos"]) == (40, 60)
    assert corpo["avaliado_em"] == corpo["enviado_em"] == (INICIO + timedelta(seconds=100)).isoformat()
    assert [p["ordem"] for p in corpo["perguntas"]] == [1, 2, 3, 4, 5]
    primeira = corpo["perguntas"][0]
    assert primeira["resposta"] == "Right 1" and primeira["correta"] is True
    assert primeira["resposta_correta"] == "Right 1" and primeira["justificativa"] == 'O texto diz "item 1".'
    assert len(primeira["alternativas"]) == 4 and primeira["comentario"] is None
    assert corpo["texto"]["titulo"] == "Honey bee" and "CC BY-SA 4.0" in corpo["texto"]["credito"]  # DR26
    assert corpo["texto"]["conteudo"] == " ".join(["honey"] * 450)


@pytest.mark.parametrize("respostas, acertos, corretas", [
    (["Right 1", "Right 2", "Right 3", "Wrong A 4", ""], 3, [True, True, True, False, False]),
    (["Wrong A 1", "Wrong B 2", "Wrong C 3", "Wrong A 4", "Wrong B 5"], 0, [False] * 5),
    ([""] * 5, 0, [False] * 5),                     # DR25: em branco conta como erro
    (["Right 1", "", "", "", "Right 5"], 2, [True, False, False, False, True]),
])
def test_acertos_e_nota(entrar_como, relogio, respostas, acertos, corretas):
    ana = entrar_como("ana@exemplo.com")
    corpo = _enviar(ana, _pronto(ana, relogio), respostas).json()
    assert corpo["acertos"] == acertos and corpo["nota"] == acertos * 2
    assert [p["correta"] for p in corpo["perguntas"]] == corretas


def test_tentativa_gravada_no_banco(entrar_como, relogio, engine_teste):
    ana = entrar_como("ana@exemplo.com")
    desafio_id = _pronto(ana, relogio)
    relogio.avancar(30)
    _enviar(ana, desafio_id, ["Right 1", "Wrong A 2", "", "Right 4", "Right 5"])

    [tentativa] = _tentativas(engine_teste)
    assert tentativa.desafio_id == desafio_id and tentativa.usuario_id == ana.get("/api/auth/me").json()["id"]
    assert tentativa.modalidade == "multipla_escolha"
    assert tentativa.respostas == ["Right 1", "Wrong A 2", "", "Right 4", "Right 5"]
    assert tentativa.avaliacao[1] == {"ordem": 2, "resposta": "Wrong A 2", "correta": False}
    assert (tentativa.acertos, tentativa.nota) == (3, 6.0)
    assert (tentativa.tempo_leitura_segundos, tentativa.tempo_resposta_segundos) == (40, 30)
    assert tentativa.avaliado_em == INICIO + timedelta(seconds=70)
    assert _estado(engine_teste, desafio_id) == "corrigido"


def test_prazo_vencido_conta_a_leitura_como_o_limite(entrar_como, relogio):
    ana = entrar_como("ana@exemplo.com")
    desafio_id = _pronto(ana, relogio, leitura=1000)  # aba fechada; voltou depois de 1000 s
    relogio.avancar(20)
    corpo = _enviar(ana, desafio_id, CERTAS).json()
    assert corpo["tempo_leitura_segundos"] == 135
    assert corpo["tempo_resposta_segundos"] == 1000 - 135 + 20


def test_get_resultado_devolve_o_mesmo_do_envio(entrar_como, relogio):
    ana = entrar_como("ana@exemplo.com")
    desafio_id = _pronto(ana, relogio)
    enviado = _enviar(ana, desafio_id, CERTAS).json()
    relogio.avancar(500)
    resultado = ana.get(f"{URL}/{desafio_id}/resultado")
    assert resultado.status_code == 200 and resultado.json() == enviado


def test_resultado_antes_do_envio(entrar_como, relogio):
    ana = entrar_como("ana@exemplo.com")
    resposta = ana.get(f"{URL}/{_pronto(ana, relogio)}/resultado")
    assert resposta.status_code == 409 and resposta.json()["codigo"] == "sem_resultado"


# --- Erros ---

@pytest.mark.parametrize("corpo", [
    {"respostas": CERTAS[:4]},
    {"respostas": CERTAS + ["Right 1"]},
    {"respostas": CERTAS[:4] + ["x" * 1001]},
    {"respostas": CERTAS, "acertos": 5},   # o cliente não manda a própria nota
    {"respostas": "Right 1"},
    {},
])
def test_corpo_invalido(entrar_como, relogio, engine_teste, corpo):
    ana = entrar_como("ana@exemplo.com")
    desafio_id = _pronto(ana, relogio)
    resposta = ana.post(f"{URL}/{desafio_id}/respostas", json=corpo)
    assert resposta.status_code == 422 and resposta.json()["codigo"] == "dados_invalidos"
    assert _tentativas(engine_teste) == []


def test_alternativa_inexistente(entrar_como, relogio, engine_teste):
    ana = entrar_como("ana@exemplo.com")
    desafio_id = _pronto(ana, relogio)

    resposta = _enviar(ana, desafio_id, ["Right 1", "Right 2", "right 3", "Right 4", "Right 5"])  # grafia diferente
    assert resposta.status_code == 422
    assert resposta.json() == {"detail": "A resposta da pergunta 3 não é uma das alternativas.",
                               "codigo": "resposta_invalida", "ordem": 3}
    assert _tentativas(engine_teste) == [] and _estado(engine_teste, desafio_id) == "respondendo"
    assert _enviar(ana, desafio_id, CERTAS).status_code == 201  # nada foi gravado: dá para enviar de novo


def test_envio_com_a_leitura_em_andamento(entrar_como, relogio, engine_teste):
    """DR28: a tela sempre encerra a leitura antes; envio em "lendo" é erro do cliente."""
    ana = entrar_como("ana@exemplo.com")
    desafio_id = ana.post(URL, json={"modalidade": "multipla_escolha"}).json()["id"]
    resposta = _enviar(ana, desafio_id, CERTAS)
    assert resposta.status_code == 409 and resposta.json()["codigo"] == "leitura_em_andamento"
    assert _tentativas(engine_teste) == [] and _estado(engine_teste, desafio_id) == "lendo"


def test_segundo_envio_e_recusado_e_o_primeiro_fica(entrar_como, relogio, engine_teste):
    ana = entrar_como("ana@exemplo.com")
    desafio_id = _pronto(ana, relogio)
    _enviar(ana, desafio_id, [""] * 5)

    segunda = _enviar(ana, desafio_id, CERTAS)
    assert segunda.status_code == 409 and segunda.json()["codigo"] == "ja_respondido"
    [tentativa] = _tentativas(engine_teste)
    assert tentativa.respostas == [""] * 5 and tentativa.acertos == 0


def test_segundo_envio_nao_refaz_a_correcao(entrar_como, relogio, monkeypatch):
    """A recusa vem antes de qualquer trabalho (no R8, seria uma chamada à LLM gasta à toa)."""
    ana = entrar_como("ana@exemplo.com")
    desafio_id = _pronto(ana, relogio)
    _enviar(ana, desafio_id, CERTAS)
    correcoes = []
    original = rc.corrigir_multipla_escolha
    monkeypatch.setattr(rc, "corrigir_multipla_escolha", lambda *a: correcoes.append(a) or original(*a))

    assert _enviar(ana, desafio_id, CERTAS).json()["codigo"] == "ja_respondido"
    assert correcoes == []


def test_corrida_entre_dois_envios_grava_uma_tentativa(engine_teste, relogio, monkeypatch):
    """As duas requisições passaram pela consulta antes de qualquer commit: o UNIQUE do banco decide."""
    with Session(engine_teste) as s:
        usuario = Usuario(email="ana@exemplo.com", senha_hash="x")
        s.add(usuario)
        s.commit()
        desafio, _ = rd.criar_desafio(s, usuario.id, fonte="wikipedia", modalidade="multipla_escolha", ppm=200)
        rd.encerrar_leitura(s, desafio)
        desafio_id = desafio.id

    with Session(engine_teste) as primeira, Session(engine_teste) as segunda:
        d1, d2 = primeira.get(ReadingChallenge, desafio_id), segunda.get(ReadingChallenge, desafio_id)
        monkeypatch.setattr(rc, "tentativa_do_desafio", lambda session, desafio: None)  # a consulta não viu nada
        rc.enviar_respostas(primeira, d1, CERTAS)
        with pytest.raises(rc.JaRespondido):
            rc.enviar_respostas(segunda, d2, [""] * 5)
    [tentativa] = _tentativas(engine_teste)
    assert tentativa.respostas == CERTAS


# A modalidade aberta (respostas gravadas e corrigidas pela LLM) fica em test_reading_avaliacao.py (R8).


# --- Isolamento ---

@pytest.mark.parametrize("metodo, sufixo", [("post", "/respostas"), ("get", "/resultado")])
def test_outra_conta_responde_404(entrar_como, relogio, engine_teste, metodo, sufixo):
    ana, bruno = entrar_como("ana@exemplo.com"), entrar_como("bruno@exemplo.com")
    desafio_id = _pronto(ana, relogio)
    if metodo == "get":
        _enviar(ana, desafio_id, CERTAS)
    argumentos = {"json": {"respostas": CERTAS}} if metodo == "post" else {}

    de_outro = getattr(bruno, metodo)(f"{URL}/{desafio_id}{sufixo}", **argumentos)
    inexistente = getattr(bruno, metodo)(f"{URL}/999999{sufixo}", **argumentos)
    assert de_outro.status_code == inexistente.status_code == 404
    assert de_outro.json() == inexistente.json()
    if metodo == "post":
        assert _tentativas(engine_teste) == []  # o Bruno não respondeu pela Ana


# --- Funções puras ---

def _pergunta(ordem: int) -> ReadingQuestion:
    return ReadingQuestion(desafio_id=1, ordem=ordem, tipo="multipla_escolha", enunciado="Q?",
                           alternativas=[f"Right {ordem}", "B", "C", "D"], resposta_correta=f"Right {ordem}",
                           justificativa="J.")


def test_corrigir_compara_a_grafia_exata():
    perguntas = [_pergunta(1), _pergunta(2)]
    assert [i["correta"] for i in rc.corrigir_multipla_escolha(perguntas, ["Right 1", "B"])] == [True, False]
    with pytest.raises(rc.RespostaInvalida):
        rc.corrigir_multipla_escolha(perguntas, ["RIGHT 1", "B"])


def test_corrigir_exige_uma_resposta_por_pergunta():
    with pytest.raises(ValueError):
        rc.corrigir_multipla_escolha([_pergunta(1)], ["Right 1", "B"])


@pytest.mark.parametrize("acertos, nota", [(0, 0.0), (1, 2.0), (3, 6.0), (5, 10.0)])
def test_nota_de_zero_a_dez(acertos, nota):
    assert rc.nota_de(acertos) == nota


# --- Conferência do tempo na submissão (guia, seção 7; R12) ---

def _forcar_fim_da_leitura(engine, desafio_id: int, fim: datetime | None) -> None:
    """Simula um horário gravado incoerente (bug ou banco alterado à mão): o encerrar do R6 nunca grava assim."""
    with Session(engine) as s:
        desafio = s.get(ReadingChallenge, desafio_id)
        desafio.leitura_encerrada_em = fim
        s.add(desafio)
        s.commit()


@pytest.mark.parametrize("fim, aceito", [
    (INICIO + timedelta(seconds=135), True),        # no prazo
    (INICIO + timedelta(seconds=140), True),        # prazo + 5 s de tolerância
    (INICIO + timedelta(seconds=141), False),       # depois da tolerância
    (INICIO - timedelta(seconds=1), False),         # antes do início
    (None, False),                                  # "respondendo" sem fim de leitura
])
def test_submissao_confere_o_tempo_de_leitura_gravado(entrar_como, relogio, engine_teste, fim, aceito):
    ana = entrar_como("ana@exemplo.com")
    desafio_id = _pronto(ana, relogio)
    _forcar_fim_da_leitura(engine_teste, desafio_id, fim)

    resposta = _enviar(ana, desafio_id, CERTAS)

    if aceito:
        assert resposta.status_code == 201
        assert resposta.json()["tempo_leitura_segundos"] == round((fim - INICIO).total_seconds())
    else:
        assert resposta.status_code == 409
        assert resposta.json() == {"detail": "O tempo de leitura deste desafio não confere. Comece um novo desafio.",
                                   "codigo": "tempo_invalido"}
        assert _tentativas(engine_teste) == [] and _estado(engine_teste, desafio_id) == "respondendo"


@pytest.mark.parametrize("leitura", [10, 135, 1000])
def test_fluxo_normal_nunca_grava_leitura_acima_do_limite(entrar_como, relogio, leitura):
    """Botão no meio, no zero, ou a aba fechada e reaberta muito depois: a submissão passa e a leitura ≤ limite."""
    ana = entrar_como("ana@exemplo.com")
    corpo = _enviar(ana, _pronto(ana, relogio, leitura=leitura), CERTAS).json()
    assert corpo["tempo_leitura_segundos"] == min(leitura, 135)


def test_leitura_dentro_do_prazo_funcao_pura():
    desafio = ReadingChallenge(usuario_id=1, texto_id=1, modalidade="aberta", ppm=200, limite_segundos=135,
                               estado="respondendo", iniciado_em=INICIO)
    for segundos, esperado in [(0, True), (140, True), (140.5, False)]:
        desafio.leitura_encerrada_em = INICIO + timedelta(seconds=segundos)
        assert rc.leitura_dentro_do_prazo(desafio) is esperado, segundos
