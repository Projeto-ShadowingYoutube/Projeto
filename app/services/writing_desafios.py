"""Regras do Writing Challenge: criar a redação, autosave e envio, com o prazo valendo no servidor (Membro 3, W3).

Sem FastAPI: as falhas são exceções próprias (ErroDesafio), que app/api/writing.py traduz para o erro padrão da API.
O "agora" vem como parâmetro: assim os testes simulam o tempo passando sem esperar.

Prazo (decisão D2 do README_MEMBRO3.md): até TOLERANCIA_PRAZO_SEGUNDOS depois do prazo, tudo funciona (folga para a
rede). Depois disso, o autosave é recusado e o envio IGNORA o texto que chegou e envia o último autosave. Assim
ninguém perde a redação, e ninguém ganha tempo extra burlando o timer da tela.
"""
import math
from datetime import datetime, timedelta

from sqlmodel import Session, select

from app.models_writing import ENVIADA, RASCUNHO, WritingAttempt
from app.services.writing_temas import sortear_tema
from app.services.writing_texto import contar_palavras

TOLERANCIA_PRAZO_SEGUNDOS = 30
MAX_CARACTERES = 10_000  # D3: protege o banco e o custo da LLM (usado no schema de entrada)
MIN_PALAVRAS_ENVIO = 50  # D3: abaixo disso não vale gastar uma correção
LIMITE_LISTA = 50  # quantas redações a lista devolve (as mais recentes)


class ErroDesafio(Exception):
    mensagem = "Não foi possível concluir a operação."

    def __init__(self, mensagem: str | None = None):
        self.mensagem = mensagem or self.mensagem
        super().__init__(self.mensagem)


class SemTemas(ErroDesafio):
    mensagem = "Não há temas disponíveis para esta categoria no momento."


class RedacaoJaEnviada(ErroDesafio):
    mensagem = "Esta redação já foi enviada e não pode mais ser alterada."


class PrazoEncerrado(ErroDesafio):
    mensagem = "O tempo desta redação acabou. O último texto salvo será o enviado."


class RedacaoCurta(ErroDesafio):
    def __init__(self, palavras: int):
        self.palavras = palavras
        super().__init__(
            f"A redação precisa de pelo menos {MIN_PALAVRAS_ENVIO} palavras para ser enviada (tem {palavras})."
        )


def prazo_encerrado(tentativa: WritingAttempt, agora: datetime) -> bool:
    """O prazo, mais a tolerância, já passou?"""
    return agora > tentativa.prazo + timedelta(seconds=TOLERANCIA_PRAZO_SEGUNDOS)


def segundos_restantes(tentativa: WritingAttempt, agora: datetime) -> int:
    """Quanto falta para o prazo, pelo relógio do servidor (0 se acabou ou se a redação já foi enviada)."""
    if tentativa.estado != RASCUNHO:
        return 0
    return max(0, math.ceil((tentativa.prazo - agora).total_seconds()))


def criar(session: Session, usuario_id: int, categoria: str | None, agora: datetime) -> WritingAttempt:
    """Sorteia um tema (None = "Surpresa") e abre a redação em rascunho, com o prazo já gravado."""
    tema = sortear_tema(session, categoria)
    if tema is None:
        raise SemTemas()
    tentativa = WritingAttempt(
        usuario_id=usuario_id, prompt_id=tema.id, iniciada_em=agora,
        prazo=agora + timedelta(seconds=tema.tempo_limite_segundos),
    )
    return _salvar(session, tentativa)


def listar(session: Session, usuario_id: int) -> list[WritingAttempt]:
    """As redações da conta, mais recentes primeiro."""
    consulta = (
        select(WritingAttempt).where(WritingAttempt.usuario_id == usuario_id)
        .order_by(WritingAttempt.iniciada_em.desc(), WritingAttempt.id.desc()).limit(LIMITE_LISTA)
    )
    return list(session.exec(consulta).all())


def autosave(session: Session, tentativa: WritingAttempt, texto: str, agora: datetime) -> WritingAttempt:
    if tentativa.estado != RASCUNHO:
        raise RedacaoJaEnviada()
    if prazo_encerrado(tentativa, agora):
        raise PrazoEncerrado()
    tentativa.texto = texto
    tentativa.palavras = contar_palavras(texto)
    tentativa.salva_em = agora
    return _salvar(session, tentativa)


def enviar(session: Session, tentativa: WritingAttempt, texto: str, agora: datetime) -> bool:
    """Congela a redação (estado "enviada"). Devolve True se o prazo tinha acabado e foi enviado o último autosave
    no lugar do texto recebido (D2). Menos de MIN_PALAVRAS_ENVIO palavras: RedacaoCurta, nada muda (D10)."""
    if tentativa.estado != RASCUNHO:
        raise RedacaoJaEnviada()
    usou_ultimo_salvamento = prazo_encerrado(tentativa, agora)
    texto_final = tentativa.texto if usou_ultimo_salvamento else texto
    palavras = contar_palavras(texto_final)
    if palavras < MIN_PALAVRAS_ENVIO:
        raise RedacaoCurta(palavras)

    tentativa.texto = texto_final
    if not usou_ultimo_salvamento:
        tentativa.salva_em = agora
    tentativa.palavras = palavras
    tentativa.enviada_em = agora
    tentativa.estado = ENVIADA
    _salvar(session, tentativa)
    return usou_ultimo_salvamento


def _salvar(session: Session, tentativa: WritingAttempt) -> WritingAttempt:
    session.add(tentativa)
    session.commit()
    session.refresh(tentativa)
    return tentativa
