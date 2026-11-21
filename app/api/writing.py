"""Rotas do Writing Challenge (Membro 3; ver README_MEMBRO3.md, seção "API").

Todas exigem login (dependência no router: rotas novas já nascem protegidas). Cada usuário só enxerga as próprias
redações: uma de outra conta responde 404, igual a uma que não existe (conferido num lugar só, em _tentativa).
As regras ficam em services/writing_desafios.py; aqui só a tradução para HTTP.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.api.auth import usuario_atual, usuario_opcional
from app.api.llm import exigir_cota
from app.api.paginas import pagina_protegida
from app.db import get_session
from app.erros import ErroDaApi
from app.models import Usuario, agora
from app.models_writing import WritingAttempt, WritingPrompt
from app.schemas_writing import (
    AutosaveSalvo,
    CategoriaWriting,
    DesafioRewrite,
    NovasReescritas,
    NovoDesafio,
    ResumoTentativa,
    TentativaWriting,
    TextoRedacao,
)
from app.services import writing_avaliacao, writing_desafios, writing_rewrite
from app.services.writing_avaliacao import LimiteDeAvaliacoes, RedacaoJaAvaliada, RedacaoNaoEnviada
from app.services.writing_desafios import (
    MIN_PALAVRAS_ENVIO,
    ErroDesafio,
    PrazoEncerrado,
    RedacaoCurta,
    RedacaoJaEnviada,
    SemTemas,
)
from app.services.writing_rewrite import (
    RedacaoNaoAvaliada,
    ReescritasInvalidas,
    RewriteConcluido,
    RodadaJaEnviada,
    SemProblemas,
)
from app.services.writing_temas import CATEGORIAS

router = APIRouter(prefix="/api/writing", tags=["writing"], dependencies=[Depends(usuario_atual)])
# Página HTML (navegação pelo HTMX). Sem login, pagina_protegida leva ao /login?proximo=/writing.
paginas = APIRouter(default_response_class=HTMLResponse, include_in_schema=False)


@paginas.get("/writing")
def pagina_writing(request: Request, usuario: Usuario | None = Depends(usuario_opcional)):
    return pagina_protegida(request, usuario, "writing.html")


# Exceção do serviço → (status, codigo). Códigos próprios documentados no README_MEMBRO3.md.
_ERROS = {
    SemTemas: (status.HTTP_503_SERVICE_UNAVAILABLE, "sem_temas"),
    RedacaoJaEnviada: (status.HTTP_409_CONFLICT, "redacao_ja_enviada"),
    PrazoEncerrado: (status.HTTP_409_CONFLICT, "prazo_encerrado"),
    RedacaoCurta: (422, "redacao_curta"),
    RedacaoJaAvaliada: (status.HTTP_409_CONFLICT, "redacao_ja_avaliada"),
    RedacaoNaoEnviada: (status.HTTP_409_CONFLICT, "redacao_nao_enviada"),
    LimiteDeAvaliacoes: (status.HTTP_409_CONFLICT, "limite_de_avaliacoes"),
    RedacaoNaoAvaliada: (status.HTTP_409_CONFLICT, "redacao_nao_avaliada"),
    SemProblemas: (status.HTTP_409_CONFLICT, "sem_problemas"),
    RewriteConcluido: (status.HTTP_409_CONFLICT, "rewrite_concluido"),
    RodadaJaEnviada: (status.HTTP_409_CONFLICT, "rodada_ja_enviada"),
    ReescritasInvalidas: (422, "reescritas_invalidas"),
}


def _erro_da_api(erro: ErroDesafio) -> ErroDaApi:
    status_http, codigo = _ERROS[type(erro)]
    extras = {"palavras": erro.palavras, "minimo": MIN_PALAVRAS_ENVIO} if isinstance(erro, RedacaoCurta) else {}
    return ErroDaApi(status_http, erro.mensagem, codigo=codigo, **extras)


def _tentativa(
    attempt_id: int, usuario: Usuario = Depends(usuario_atual), session: Session = Depends(get_session),
) -> WritingAttempt:
    tentativa = session.get(WritingAttempt, attempt_id)
    if not tentativa or tentativa.usuario_id != usuario.id:
        raise HTTPException(status_code=404, detail="Redação não encontrada.")
    return tentativa


def _nome_da_categoria(slug: str) -> str:
    categoria = CATEGORIAS.get(slug)
    return categoria.nome if categoria else slug  # tema de uma categoria que deixou de existir: mostra o slug


def _resposta(session: Session, tentativa: WritingAttempt, usou_ultimo_salvamento: bool = False) -> dict:
    tema = session.get(WritingPrompt, tentativa.prompt_id)
    feedback = writing_avaliacao.feedback_de(session, tentativa)
    return {
        **tentativa.model_dump(include={
            "id", "estado", "texto", "palavras", "iniciada_em", "prazo", "salva_em", "enviada_em",
        }),
        "categoria": tema.categoria,
        "categoria_nome": _nome_da_categoria(tema.categoria),
        "enunciado": tema.enunciado,
        "tempo_limite_segundos": tema.tempo_limite_segundos,
        "palavras_minimas": tema.palavras_minimas,
        "segundos_restantes": writing_desafios.segundos_restantes(tentativa, agora()),
        "usou_ultimo_salvamento": usou_ultimo_salvamento,
        "avaliacoes_restantes": writing_avaliacao.avaliacoes_restantes(tentativa),
        "feedback": feedback.model_dump() if feedback else None,
    }


@router.get("/categorias", response_model=list[CategoriaWriting])
def listar_categorias():
    return [{"slug": slug, **vars(categoria)} for slug, categoria in CATEGORIAS.items()]


# A cota é gasta pela dependência, antes da validação do corpo: uma requisição inválida (422) ou sem tema (503)
# também conta um desafio. Decisão D9 do README_MEMBRO3.md: seguir o padrão do CLAUDE.md (a tela só envia
# categorias vindas de GET /categorias).
@router.post(
    "/challenges", response_model=TentativaWriting, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(exigir_cota("writing"))],
)
def criar_desafio(
    corpo: NovoDesafio | None = None, usuario: Usuario = Depends(usuario_atual),
    session: Session = Depends(get_session),
):
    try:
        tentativa = writing_desafios.criar(session, usuario.id, corpo.categoria if corpo else None, agora())
    except ErroDesafio as erro:
        raise _erro_da_api(erro) from erro
    return _resposta(session, tentativa)


@router.get("/attempts", response_model=list[ResumoTentativa])
def listar_redacoes(usuario: Usuario = Depends(usuario_atual), session: Session = Depends(get_session)):
    tentativas = writing_desafios.listar(session, usuario.id)
    notas = writing_avaliacao.notas_gerais(session, [t.id for t in tentativas])
    resumos = []
    for tentativa in tentativas:
        categoria = session.get(WritingPrompt, tentativa.prompt_id).categoria
        resumos.append({
            **tentativa.model_dump(include={"id", "estado", "palavras", "iniciada_em", "enviada_em"}),
            "categoria": categoria, "categoria_nome": _nome_da_categoria(categoria),
            "nota_geral": notas.get(tentativa.id),
        })
    return resumos


@router.get("/attempts/{attempt_id}", response_model=TentativaWriting)
def obter_redacao(tentativa: WritingAttempt = Depends(_tentativa), session: Session = Depends(get_session)):
    return _resposta(session, tentativa)


@router.patch("/attempts/{attempt_id}", response_model=AutosaveSalvo)
def autosave(
    corpo: TextoRedacao, tentativa: WritingAttempt = Depends(_tentativa), session: Session = Depends(get_session),
):
    try:
        writing_desafios.autosave(session, tentativa, corpo.texto, agora())
    except ErroDesafio as erro:
        raise _erro_da_api(erro) from erro
    return {
        "palavras": tentativa.palavras, "salva_em": tentativa.salva_em,
        "segundos_restantes": writing_desafios.segundos_restantes(tentativa, agora()),
    }


# Rotas "def" (não async): a correção chama a LLM, que bloqueia por alguns segundos (roda no threadpool).
@router.post("/attempts/{attempt_id}/submissao", response_model=TentativaWriting)
def enviar_redacao(
    corpo: TextoRedacao, tentativa: WritingAttempt = Depends(_tentativa), session: Session = Depends(get_session),
):
    """Grava o texto (commit) e só então corrige. Falha da LLM: a redação fica em erro_avaliacao e a resposta é o
    erro da LLM (502/503/504, D17); o texto continua salvo."""
    try:
        usou_ultimo_salvamento = writing_desafios.enviar(session, tentativa, corpo.texto, agora())
        writing_avaliacao.avaliar_redacao(session, tentativa)
    except ErroDesafio as erro:
        raise _erro_da_api(erro) from erro
    return _resposta(session, tentativa, usou_ultimo_salvamento)


@router.post("/attempts/{attempt_id}/avaliacao", response_model=TentativaWriting)
def avaliar_de_novo(tentativa: WritingAttempt = Depends(_tentativa), session: Session = Depends(get_session)):
    """"Avaliar de novo" depois de uma falha (até MAX_AVALIACOES por redação). Não gasta a cota diária."""
    try:
        writing_avaliacao.avaliar_redacao(session, tentativa)
    except ErroDesafio as erro:
        raise _erro_da_api(erro) from erro
    return _resposta(session, tentativa)


# --- Rewrite Challenge (W8) ---

@router.get("/attempts/{attempt_id}/rewrite", response_model=DesafioRewrite)
def obter_rewrite(tentativa: WritingAttempt = Depends(_tentativa), session: Session = Depends(get_session)):
    try:
        return writing_rewrite.desafio(session, tentativa)
    except ErroDesafio as erro:
        raise _erro_da_api(erro) from erro


@router.post("/attempts/{attempt_id}/rewrite", response_model=DesafioRewrite)
def enviar_rewrite(
    corpo: NovasReescritas, tentativa: WritingAttempt = Depends(_tentativa), session: Session = Depends(get_session),
):
    """Uma rodada inteira (uma reescrita por problema), avaliada numa chamada à LLM. Falha da LLM: nada é gravado e a
    rodada não é gasta (D23); a resposta é o erro da LLM. Não gasta a cota diária."""
    try:
        writing_rewrite.enviar(session, tentativa, [(r.indice, r.texto) for r in corpo.reescritas])
        return writing_rewrite.desafio(session, tentativa)
    except ErroDesafio as erro:
        raise _erro_da_api(erro) from erro
