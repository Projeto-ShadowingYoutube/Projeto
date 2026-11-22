"""Reading Challenge (Membro 1, blocos R5 e R6): criação do desafio e o tempo da leitura, sem FastAPI.

    desafio, texto = criar_desafio(session, usuario.id, fonte="wikipedia", modalidade="aberta", ppm=200)

Encadeia o texto (R3), as perguntas (R4) e o tempo limite (R2), e grava o desafio e as 5 perguntas num único
commit: ou fica tudo gravado, ou nada. O texto (ReadingText) é compartilhado entre os usuários e já foi gravado
pelo R3, à parte.

O relógio da leitura (iniciado_em) começa DEPOIS da busca e da LLM, que podem levar vários segundos: essa espera
não conta como tempo de leitura. As perguntas são gravadas agora, mas só saem do servidor no fim da leitura (R6).

Tempo da leitura (R6, decisões DR22 a DR24): o bloqueio é calculado a cada requisição, comparando o horário com o
prazo (iniciado_em + limite_segundos); não há tarefa agendada, e a regra vale mesmo depois de reiniciar o servidor.
- O texto só é entregue com o desafio em "lendo" e até o prazo + TOLERANCIA_SEGUNDOS (latência da rede).
- Encerrar a leitura (botão ou fim do tempo) passa para "respondendo" e grava leitura_encerrada_em, nunca depois do
  prazo: o tempo de leitura registrado não passa do limite. É idempotente (F5 ou clique duplo não mudam nada).
- Prazo vencido sem encerrar (aba fechada): as perguntas continuam disponíveis; a leitura conta como o limite.
Os momentos são parâmetros (padrão: agora()), para os testes controlarem o relógio.
"""
import math
from datetime import datetime, timedelta

from sqlalchemy import update
from sqlmodel import Session, select

from app.models import agora
from app.models_reading import ReadingChallenge, ReadingQuestion, ReadingText
from app.services import reading_fontes as rf
from app.services import reading_llm as rl
from app.services import reading_textos as rt

TOLERANCIA_SEGUNDOS = 5

LENDO = "lendo"
RESPONDENDO = "respondendo"


def criar_desafio(session: Session, usuario_id: int, fonte: str, modalidade: str,
                  ppm: int) -> tuple[ReadingChallenge, ReadingText]:
    """Levanta rf.TextoIndisponivel (sem texto nenhum) ou llm.ErroLLM (LLM falhou e não há reserva)."""
    if ppm not in rt.VELOCIDADES_PPM:  # confere antes de gastar rede e LLM
        raise ValueError(f"ppm inválido: {ppm!r} (use um de {rt.VELOCIDADES_PPM})")
    texto = rf.obter_texto(session, fonte)
    resultado = rl.perguntas_para_o_desafio(session, texto, modalidade)
    texto = resultado.texto  # pode ter virado um texto de reserva (a LLM falhou)

    desafio = ReadingChallenge(
        usuario_id=usuario_id, texto_id=texto.id, modalidade=modalidade, ppm=ppm,
        limite_segundos=rt.limite_leitura_segundos(texto.palavras, ppm),
        usou_reserva=resultado.usou_reserva, modelo_llm=resultado.modelo_llm,
        iniciado_em=agora(),  # depois da geração: a espera não conta como leitura
    )
    session.add(desafio)
    session.flush()  # gera o id do desafio, ainda sem commit
    session.add_all(
        ReadingQuestion(desafio_id=desafio.id, ordem=ordem, tipo=p.tipo, enunciado=p.enunciado,
                        alternativas=list(p.alternativas), resposta_correta=p.resposta_correta,
                        justificativa=p.justificativa)
        for ordem, p in enumerate(resultado.perguntas, start=1)
    )
    session.commit()
    session.refresh(desafio)
    return desafio, texto


# --- Tempo da leitura (R6) ---

def prazo_leitura(desafio: ReadingChallenge) -> datetime:
    return desafio.iniciado_em + timedelta(seconds=desafio.limite_segundos)


def segundos_restantes(desafio: ReadingChallenge, momento: datetime | None = None) -> int:
    """Segundos de leitura que faltam (0 se o prazo passou ou a leitura foi encerrada). O timer da tela usa este
    número, e não o relógio do navegador."""
    if desafio.estado != LENDO:
        return 0
    falta = (prazo_leitura(desafio) - (momento or agora())).total_seconds()
    return max(0, math.ceil(falta))


def leitura_disponivel(desafio: ReadingChallenge, momento: datetime | None = None) -> bool:
    """O texto ainda pode ser entregue? Só em "lendo" e até o prazo mais a tolerância."""
    limite = prazo_leitura(desafio) + timedelta(seconds=TOLERANCIA_SEGUNDOS)
    return desafio.estado == LENDO and (momento or agora()) <= limite


def encerrar_leitura(session: Session, desafio: ReadingChallenge,
                     momento: datetime | None = None) -> ReadingChallenge:
    """Fim da leitura: "lendo" → "respondendo". Já encerrada: não muda nada (idempotente)."""
    encerrada_em = min(momento or agora(), prazo_leitura(desafio))
    # UPDATE condicional: com duas requisições ao mesmo tempo, só a primeira grava o horário.
    session.exec(update(ReadingChallenge)
                 .where(ReadingChallenge.id == desafio.id, ReadingChallenge.estado == LENDO)
                 .values(estado=RESPONDENDO, leitura_encerrada_em=encerrada_em))
    session.commit()
    session.refresh(desafio)
    return desafio


def perguntas_do_desafio(session: Session, desafio: ReadingChallenge) -> list[ReadingQuestion]:
    consulta = (select(ReadingQuestion).where(ReadingQuestion.desafio_id == desafio.id)
                .order_by(ReadingQuestion.ordem))
    return list(session.exec(consulta).all())
