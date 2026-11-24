"""Rotas do Reading Challenge (Membro 1). Rotas finas: as regras ficam em app/services/reading_*.py.

Todas exigem login (dependência no router). Cada usuário só enxerga os próprios desafios: um desafio de outra
conta responde 404, igual a um inexistente (padrão _deck de app/api/decks.py).

A rota que cria o desafio gasta 1 da cota diária (exigir_cota("reading")) e é "def": a busca do texto e a LLM
bloqueiam, e o FastAPI a roda numa thread à parte.

Leitura (R6): o texto só sai dentro do prazo (senão 409 "leitura_encerrada"); encerrar a leitura libera as perguntas
sem as respostas. As regras de tempo ficam em app/services/reading_desafios.py.

Respostas (R7): POST /respostas grava a tentativa (e corrige a múltipla escolha); GET /resultado devolve o mesmo
resultado. As regras ficam em app/services/reading_correcao.py.

Abertas (R8): o POST /respostas grava as respostas e só depois chama a LLM para corrigir; se a LLM falhar, o estado
fica "erro_avaliacao", o erro padrão da LLM sai (502/503/504) e POST /avaliar tenta de novo
(app/services/reading_avaliacao.py).
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.api.auth import usuario_atual, usuario_opcional
from app.api.llm import exigir_cota
from app.api.paginas import pagina_protegida
from app.db import get_session
from app.erros import ErroDaApi
from app.models import Usuario
from app.models_reading import ReadingChallenge, ReadingText
from app.schemas_reading import (
    DesafioCriado,
    ItemHistorico,
    LeituraEncerrada,
    NovoDesafio,
    PerguntaParaResponder,
    RespostasEnviadas,
    ResultadoDesafio,
    ResumoDesafio,
    TextoParaLer,
)
from app.services import reading_avaliacao as ra
from app.services import reading_correcao as rc
from app.services import reading_desafios as rd
from app.services import reading_fontes as rf

router = APIRouter(prefix="/api/reading", tags=["reading"], dependencies=[Depends(usuario_atual)])
# Página HTML (R9): sem login, vai para /login?proximo=/reading (pagina_protegida, de app/api/paginas.py).
paginas = APIRouter(default_response_class=HTMLResponse, include_in_schema=False)


@paginas.get("/reading")
def pagina_reading(request: Request, usuario: Usuario | None = Depends(usuario_opcional)):
    return pagina_protegida(request, usuario, "reading.html")


def _desafio(
    desafio_id: int, usuario: Usuario = Depends(usuario_atual), session: Session = Depends(get_session),
) -> ReadingChallenge:
    desafio = session.get(ReadingChallenge, desafio_id)
    if not desafio or desafio.usuario_id != usuario.id:
        raise HTTPException(status_code=404, detail="Desafio não encontrado.")
    return desafio


@router.post("/challenges", response_model=DesafioCriado, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(exigir_cota("reading"))])
def criar_desafio(corpo: NovoDesafio, usuario: Usuario = Depends(usuario_atual),
                  session: Session = Depends(get_session)):
    try:
        desafio, texto = rd.criar_desafio(session, usuario.id, fonte=corpo.fonte, modalidade=corpo.modalidade,
                                          ppm=corpo.ppm)
    except rf.TextoIndisponivel:
        raise ErroDaApi(502, "Não foi possível obter um texto agora. Tente de novo em instantes.",
                        codigo="texto_indisponivel") from None
    return _criado(desafio, texto)


@router.get("/challenges", response_model=list[ItemHistorico])
def listar_desafios(usuario: Usuario = Depends(usuario_atual), session: Session = Depends(get_session)):
    """Histórico (R10): os 50 desafios mais recentes da conta."""
    return rd.historico(session, usuario.id)


@router.get("/challenges/{desafio_id}", response_model=ResumoDesafio)
def obter_desafio(desafio: ReadingChallenge = Depends(_desafio)):
    return _resumo(desafio)


@router.get("/challenges/{desafio_id}/texto", response_model=TextoParaLer)
def obter_texto(desafio: ReadingChallenge = Depends(_desafio), session: Session = Depends(get_session)):
    momento = rd.agora()
    if not rd.leitura_disponivel(desafio, momento):
        raise ErroDaApi(409, "O tempo de leitura deste desafio acabou.", codigo="leitura_encerrada")
    texto = session.get(ReadingText, desafio.texto_id)
    return {**_texto(texto), "segundos_restantes": rd.segundos_restantes(desafio, momento)}


@router.post("/challenges/{desafio_id}/encerrar-leitura", response_model=LeituraEncerrada)
def encerrar_leitura(desafio: ReadingChallenge = Depends(_desafio), session: Session = Depends(get_session)):
    desafio = rd.encerrar_leitura(session, desafio)
    perguntas = [PerguntaParaResponder.model_validate(p) for p in rd.perguntas_do_desafio(session, desafio)]
    return {**_resumo(desafio), "perguntas": perguntas}


@router.post("/challenges/{desafio_id}/respostas", response_model=ResultadoDesafio,
             status_code=status.HTTP_201_CREATED)
def enviar_respostas(corpo: RespostasEnviadas, desafio: ReadingChallenge = Depends(_desafio),
                     session: Session = Depends(get_session)):
    try:
        tentativa = rc.enviar_respostas(session, desafio, corpo.respostas)
    except rc.LeituraEmAndamento:
        raise ErroDaApi(409, "Encerre a leitura antes de enviar as respostas.",
                        codigo="leitura_em_andamento") from None
    except rc.JaRespondido:
        raise ErroDaApi(409, "As respostas deste desafio já foram enviadas.", codigo="ja_respondido") from None
    except rc.RespostaInvalida as erro:
        raise ErroDaApi(422, f"A resposta da pergunta {erro.ordem} não é uma das alternativas.",
                        codigo="resposta_invalida", ordem=erro.ordem) from None
    if tentativa.modalidade == "aberta":
        tentativa = ra.avaliar_abertas(session, desafio, tentativa)  # ErroLLM: respostas já gravadas
    return _resultado(session, desafio, tentativa)


@router.post("/challenges/{desafio_id}/avaliar", response_model=ResultadoDesafio)
def avaliar_de_novo(desafio: ReadingChallenge = Depends(_desafio), session: Session = Depends(get_session)):
    try:
        tentativa = ra.reavaliar(session, desafio)
    except ra.AvaliacaoIndisponivel:
        raise ErroDaApi(409, "Este desafio não está aguardando uma nova correção.",
                        codigo="avaliacao_indisponivel") from None
    return _resultado(session, desafio, tentativa)


@router.get("/challenges/{desafio_id}/resultado", response_model=ResultadoDesafio)
def obter_resultado(desafio: ReadingChallenge = Depends(_desafio), session: Session = Depends(get_session)):
    tentativa = rc.tentativa_do_desafio(session, desafio)
    if tentativa is None:
        raise ErroDaApi(409, "Este desafio ainda não tem respostas.", codigo="sem_resultado")
    return _resultado(session, desafio, tentativa)


def _resultado(session: Session, desafio: ReadingChallenge, tentativa) -> dict:
    session.refresh(desafio)
    por_ordem = {item["ordem"]: item for item in tentativa.avaliacao}
    perguntas = []
    for pergunta, resposta in zip(rd.perguntas_do_desafio(session, desafio), tentativa.respostas, strict=True):
        avaliacao = por_ordem.get(pergunta.ordem, {})
        perguntas.append({
            "ordem": pergunta.ordem, "tipo": pergunta.tipo, "enunciado": pergunta.enunciado,
            "alternativas": pergunta.alternativas, "resposta": resposta, "correta": avaliacao.get("correta"),
            "pontuacao": _pontuacao(avaliacao),
            "resposta_correta": pergunta.resposta_correta, "justificativa": pergunta.justificativa,
            "comentario": avaliacao.get("comentario"),
        })
    return {
        "id": desafio.id, "estado": desafio.estado, "modalidade": tentativa.modalidade,
        "usou_reserva": desafio.usou_reserva, "acertos": tentativa.acertos, "nota": tentativa.nota,
        "tempo_leitura_segundos": tentativa.tempo_leitura_segundos,
        "tempo_resposta_segundos": tentativa.tempo_resposta_segundos,
        "enviado_em": tentativa.enviado_em, "avaliado_em": tentativa.avaliado_em,
        "texto": _texto(session.get(ReadingText, desafio.texto_id)), "perguntas": perguntas,
    }


def _pontuacao(avaliacao: dict) -> float | None:
    """A aberta grava a pontuação (R8); na múltipla escolha ela sai do acerto (1 ou 0)."""
    if "pontuacao" in avaliacao:
        return avaliacao["pontuacao"]
    if "correta" in avaliacao:
        return 1.0 if avaliacao["correta"] else 0.0
    return None


def _resumo(desafio: ReadingChallenge) -> dict:
    return ResumoDesafio.model_validate(
        {**desafio.model_dump(), "segundos_restantes": rd.segundos_restantes(desafio)}).model_dump()


def _texto(texto: ReadingText) -> dict:
    return {"titulo": texto.titulo, "conteudo": texto.conteudo, "palavras": texto.palavras, "fonte": texto.fonte,
            "url": texto.url, "credito": rf.credito(texto)}


def _criado(desafio: ReadingChallenge, texto: ReadingText) -> dict:
    return {**_resumo(desafio), "texto": _texto(texto)}
