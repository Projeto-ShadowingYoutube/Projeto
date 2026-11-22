"""Reading Challenge (Membro 1, bloco R5): criação do desafio, sem FastAPI (testável isoladamente).

    desafio, texto = criar_desafio(session, usuario.id, fonte="wikipedia", modalidade="aberta", ppm=200)

Encadeia o texto (R3), as perguntas (R4) e o tempo limite (R2), e grava o desafio e as 5 perguntas num único
commit: ou fica tudo gravado, ou nada. O texto (ReadingText) é compartilhado entre os usuários e já foi gravado
pelo R3, à parte.

O relógio da leitura (iniciado_em) começa DEPOIS da busca e da LLM, que podem levar vários segundos: essa espera
não conta como tempo de leitura. As perguntas são gravadas agora, mas só saem do servidor no fim da leitura (R6).
"""
from sqlmodel import Session

from app.models import agora
from app.models_reading import ReadingChallenge, ReadingQuestion, ReadingText
from app.services import reading_fontes as rf
from app.services import reading_llm as rl
from app.services import reading_textos as rt


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
