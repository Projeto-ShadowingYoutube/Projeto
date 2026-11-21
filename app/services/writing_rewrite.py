"""Rewrite Challenge (Membro 3, W8): seleção das frases problemáticas, rodadas, comparação e histórico.

Depois da correção, o sistema escolhe até MAX_PROBLEMAS frases (a partir dos trechos do feedback) e a pessoa as
reescreve, seguindo a instrução de cada problema (gerada na correção, W5). Uma chamada à LLM avalia a rodada inteira.
Nada é sobrescrito: cada reescrita é uma linha nova em WritingRewrite, com a cópia da frase original e da instrução.
O histórico original → feedback → reescritas sai dessas ligações.

    rodada 1: os problemas selecionados          rodada 2: só os que não melhoraram (D21)    máximo: 2 rodadas (D4)

Sem FastAPI: as falhas de regra são ErroDesafio; as da LLM (llm.ErroLLM) sobem sem tratamento, e NADA é gravado
nesse caso (D23): a rodada não é gasta, e a tela mantém os textos para reenviar.
"""
import difflib
import re

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models_writing import AVALIADA, WritingAttempt, WritingFeedback, WritingPrompt, WritingRewrite
from app.services import writing_llm
from app.services.writing_avaliacao import feedback_de
from app.services.writing_desafios import ErroDesafio

MAX_PROBLEMAS = 3  # D4
MAX_RODADAS = 2  # D4


class RedacaoNaoAvaliada(ErroDesafio):
    mensagem = "Esta redação ainda não foi corrigida: o Rewrite Challenge começa depois da correção."


class SemProblemas(ErroDesafio):
    mensagem = "A correção não apontou trechos problemáticos nesta redação: não há frases para reescrever."


class RewriteConcluido(ErroDesafio):
    mensagem = "O Rewrite Challenge desta redação já terminou."


class ReescritasInvalidas(ErroDesafio):
    mensagem = "Envie exatamente uma reescrita para cada frase desta rodada."


class RodadaJaEnviada(ErroDesafio):
    mensagem = "Esta rodada já foi enviada."


# --- Funções puras ---

_INICIO_DE_FRASE = re.compile(r"[.!?]+(?=\s)|\n")  # o que termina a frase anterior (o ponto de "3.5" não conta)
_FIM_DE_FRASE = re.compile(r"[.!?]+(?=\s|$)|\n")


def extrair_frase(texto: str, inicio: int, fim: int) -> tuple[int, int]:
    """Limites [comeco, final) da frase que contém o trecho [inicio, fim). Frases terminam em . ! ? (seguidos de
    espaço ou do fim do texto) ou numa quebra de linha. Limitação conhecida: abreviações como "e.g." cortam a frase
    antes (o pior caso é uma frase menor)."""
    comeco = 0
    for marca in _INICIO_DE_FRASE.finditer(texto, 0, inicio):
        comeco = marca.end()
    while comeco < inicio and texto[comeco].isspace():
        comeco += 1

    # Procura a partir do último caractere do trecho: se a citação já termina no ponto final, ele conta.
    marca = _FIM_DE_FRASE.search(texto, max(inicio, fim - 1))
    if marca is None:
        final = len(texto)
    else:
        final = marca.start() if marca.group() == "\n" else marca.end()
    while final > fim and texto[final - 1].isspace():
        final -= 1
    return comeco, max(final, fim)


def selecionar_problemas(texto: str, trechos: list[dict]) -> list[dict]:
    """Até MAX_PROBLEMAS problemas para reescrever, sempre os mesmos para o mesmo feedback (determinístico):
    1) do mais grave ao menos grave (empate: a posição no texto);
    2) 1ª passada: um por categoria (o treino varia); 2ª passada: completa com os próximos mais graves;
    3) uma frase só entra uma vez (dois trechos na mesma frase = uma reescrita).
    Devolve na ordem do texto: [{indice, inicio_frase, fim_frase, frase}] (indice = posição em `trechos`)."""
    ordem = sorted(range(len(trechos)), key=lambda i: (-trechos[i]["gravidade"], trechos[i]["inicio"]))
    escolhidos: list[dict] = []
    frases_usadas: set[tuple[int, int]] = set()
    categorias_usadas: set[str] = set()
    for primeira_passada in (True, False):
        for indice in ordem:
            if len(escolhidos) == MAX_PROBLEMAS:
                break
            trecho = trechos[indice]
            if any(e["indice"] == indice for e in escolhidos):
                continue
            if primeira_passada and trecho["categoria"] in categorias_usadas:
                continue
            limites = extrair_frase(texto, trecho["inicio"], trecho["fim"])
            if limites in frases_usadas:
                continue
            frases_usadas.add(limites)
            categorias_usadas.add(trecho["categoria"])
            escolhidos.append({
                "indice": indice, "inicio_frase": limites[0], "fim_frase": limites[1],
                "frase": texto[limites[0]:limites[1]],
            })
    return sorted(escolhidos, key=lambda e: e["inicio_frase"])


_PEDACO = re.compile(r"\s+|\w+|[^\w\s]")  # palavras, espaços e pontuação: juntos, cobrem o texto inteiro


def comparar(original: str, reescrita: str) -> list[dict]:
    """Comparação palavra a palavra (difflib): [{tipo: igual | removido | adicionado, texto}].
    Garantias: "igual" + "removido" reconstroem a original; "igual" + "adicionado" reconstroem a reescrita."""
    antes, depois = _PEDACO.findall(original), _PEDACO.findall(reescrita)
    pedacos: list[dict] = []

    def acrescentar(tipo: str, partes: list[str]) -> None:
        if not partes:
            return
        if pedacos and pedacos[-1]["tipo"] == tipo:
            pedacos[-1]["texto"] += "".join(partes)
        else:
            pedacos.append({"tipo": tipo, "texto": "".join(partes)})

    for operacao, i1, i2, j1, j2 in difflib.SequenceMatcher(None, antes, depois, autojunk=False).get_opcodes():
        if operacao == "equal":
            acrescentar("igual", antes[i1:i2])
        else:
            acrescentar("removido", antes[i1:i2])
            acrescentar("adicionado", depois[j1:j2])
    return pedacos


# --- Desafio, rodadas e envio ---

def _contexto(session: Session, tentativa: WritingAttempt) -> tuple[WritingFeedback, list[dict]]:
    if tentativa.estado != AVALIADA:
        raise RedacaoNaoAvaliada()
    feedback = feedback_de(session, tentativa)
    problemas = selecionar_problemas(tentativa.texto, feedback.trechos)
    if not problemas:
        raise SemProblemas()
    return feedback, problemas


def _reescritas(session: Session, feedback: WritingFeedback) -> list[WritingRewrite]:
    consulta = (
        select(WritingRewrite).where(WritingRewrite.feedback_id == feedback.id)
        .order_by(WritingRewrite.rodada, WritingRewrite.indice_trecho)
    )
    return list(session.exec(consulta).all())


def _pendentes(problemas: list[dict], feitas: list[WritingRewrite]) -> tuple[int, list[dict]]:
    """(rodadas já feitas, problemas da próxima rodada). Rodada 2: só os que não melhoraram na rodada 1 (D21)."""
    rodadas_feitas = max((r.rodada for r in feitas), default=0)
    if rodadas_feitas == 0:
        return 0, problemas
    if rodadas_feitas >= MAX_RODADAS:
        return rodadas_feitas, []
    nao_melhorados = {r.indice_trecho for r in feitas if r.rodada == rodadas_feitas and not r.avaliacao["melhorou"]}
    return rodadas_feitas, [p for p in problemas if p["indice"] in nao_melhorados]


def desafio(session: Session, tentativa: WritingAttempt) -> dict:
    """O estado do Rewrite: a rodada atual, os problemas a reescrever e o histórico (com a comparação)."""
    feedback, problemas = _contexto(session, tentativa)
    feitas = _reescritas(session, feedback)
    rodadas_feitas, pendentes = _pendentes(problemas, feitas)
    concluido = not pendentes
    trechos = feedback.trechos
    return {
        "concluido": concluido,
        "rodada_atual": None if concluido else rodadas_feitas + 1,
        "rodadas_restantes": 0 if concluido else MAX_RODADAS - rodadas_feitas,
        "problemas": [] if concluido else [{
            "indice": p["indice"], "categoria": trechos[p["indice"]]["categoria"],
            "gravidade": trechos[p["indice"]]["gravidade"], "citacao": trechos[p["indice"]]["citacao"],
            "frase": p["frase"], "explicacao": trechos[p["indice"]]["explicacao"],
            "instrucao": trechos[p["indice"]]["instrucao_reescrita"],
        } for p in pendentes],
        "historico": [{
            "rodada": r.rodada, "indice": r.indice_trecho, "categoria": trechos[r.indice_trecho]["categoria"],
            "frase_original": r.trecho_original, "instrucao": r.instrucao, "reescrita": r.reescrita,
            "avaliacao": r.avaliacao, "comparacao": comparar(r.trecho_original, r.reescrita),
            "criado_em": r.criado_em,
        } for r in feitas],
    }


def enviar(session: Session, tentativa: WritingAttempt, reescritas: list[tuple[int, str]]) -> None:
    """Grava uma rodada: uma linha por problema, com a avaliação da LLM. Falha da LLM: nada é gravado (D23)."""
    feedback, problemas = _contexto(session, tentativa)
    rodadas_feitas, pendentes = _pendentes(problemas, _reescritas(session, feedback))
    if not pendentes:
        raise RewriteConcluido()

    recebidas = dict(reescritas)
    if len(recebidas) != len(reescritas) or set(recebidas) != {p["indice"] for p in pendentes}:
        raise ReescritasInvalidas()

    trechos = feedback.trechos
    itens = [{
        "indice": p["indice"], "categoria": trechos[p["indice"]]["categoria"],
        "explicacao": trechos[p["indice"]]["explicacao"], "instrucao": trechos[p["indice"]]["instrucao_reescrita"],
        "frase": p["frase"], "reescrita": recebidas[p["indice"]],
    } for p in pendentes]
    tema = session.get(WritingPrompt, tentativa.prompt_id)
    resultado = writing_llm.avaliar_reescritas(enunciado=tema.enunciado, itens=itens)

    rodada = rodadas_feitas + 1
    for item in itens:
        session.add(WritingRewrite(
            feedback_id=feedback.id, rodada=rodada, indice_trecho=item["indice"], trecho_original=item["frase"],
            instrucao=item["instrucao"], reescrita=item["reescrita"], avaliacao=resultado.avaliacoes[item["indice"]],
            modelo=resultado.modelo, versao_prompt=resultado.versao_prompt,
        ))
    try:
        session.commit()
    except IntegrityError as erro:  # envio duplo: a mesma rodada gravada por outra requisição (UNIQUE)
        session.rollback()
        raise RodadaJaEnviada() from erro
