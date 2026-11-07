"""Formato único de todas as respostas de erro da API (documentado no README, seção "Formato dos erros da API").

    {"detail": "mensagem para a pessoa, em português", "codigo": "identificador_estavel", ...campos extras}

- detail: sempre texto. É o que a interface mostra. Pode mudar de redação.
- codigo: identificador para programas (o front, testes, quem integra). Não muda.
- extras: só quando o erro precisa (ex.: 429 traz tokens_restantes; 422 traz erros campo a campo).

As rotas continuam levantando HTTPException(status, "mensagem"): os handlers daqui acrescentam o codigo.
Para um codigo próprio ou campos extras, levante ErroDaApi. Exceções não tratadas viram um 500 genérico:
a stack vai para o log do servidor e nunca para o cliente.
"""
import logging
from http import HTTPStatus

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("uvicorn.error")

# codigo padrão de cada status (quando a rota não informa um próprio).
CODIGOS = {
    400: "requisicao_invalida",
    401: "nao_autenticado",
    403: "acesso_negado",
    404: "nao_encontrado",
    405: "metodo_nao_permitido",
    409: "conflito",
    413: "conteudo_grande_demais",
    422: "dados_invalidos",
    429: "limite_atingido",
    500: "erro_interno",
    502: "servico_externo_indisponivel",
}

# Mensagens no lugar das padrão do Starlette/FastAPI, que vêm em inglês ("Not Found").
MENSAGENS_PADRAO = {
    404: "Recurso não encontrado.",
    405: "Método não permitido para este endereço.",
    500: "Erro interno. Tente novamente em instantes.",
}


class ErroDaApi(HTTPException):
    """HTTPException com codigo próprio e/ou campos extras na resposta.
    Ex.: raise ErroDaApi(429, "Seus tokens acabaram.", codigo="limite_de_tokens", tokens_restantes=0)"""

    def __init__(self, status_code: int, detail: str, codigo: str | None = None, headers: dict | None = None,
                 **extras):
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.codigo = codigo
        self.extras = extras


def codigo_do_status(status: int) -> str:
    return CODIGOS.get(status, "erro_interno" if status >= 500 else "requisicao_invalida")


def resposta_de_erro(status: int, detail: str, codigo: str | None = None, headers: dict | None = None,
                     **extras) -> JSONResponse:
    """A única forma de montar uma resposta de erro. Use direto só onde os handlers não alcançam (middlewares)."""
    corpo = {"detail": detail, "codigo": codigo or codigo_do_status(status), **extras}
    return JSONResponse(status_code=status, content=corpo, headers=headers)


async def _erro_http(request: Request, erro: StarletteHTTPException) -> JSONResponse:
    """HTTPException das rotas, e as do próprio framework (rota inexistente → 404, método errado → 405)."""
    detail = erro.detail
    try:
        frase_em_ingles = HTTPStatus(erro.status_code).phrase
    except ValueError:
        frase_em_ingles = None
    if not isinstance(detail, str) or not detail or detail == frase_em_ingles:
        detail = MENSAGENS_PADRAO.get(erro.status_code, "Não foi possível atender a requisição.")
    return resposta_de_erro(
        erro.status_code, detail, getattr(erro, "codigo", None), getattr(erro, "headers", None),
        **getattr(erro, "extras", {}),
    )


# --- 422: validação dos dados de entrada (Pydantic) ---

def _campo(local: tuple) -> str:
    """("body", "senha") → "senha"; ("query", "inicio") → "inicio"; ("body",) → "corpo"."""
    partes = [str(parte) for parte in local if parte not in ("body", "query", "path", "form", "header", "cookie")]
    return ".".join(partes) or "corpo"


def _mensagem(problema: dict) -> str:
    """Mensagem em português para os tipos de erro mais comuns; nos outros, a do Pydantic."""
    tipo, contexto, original = problema.get("type", ""), problema.get("ctx") or {}, problema.get("msg", "")
    if tipo == "missing":
        return "campo obrigatório"
    if tipo == "string_too_short":
        return f"mínimo de {contexto.get('min_length')} caracteres"
    if tipo == "string_too_long":
        return f"máximo de {contexto.get('max_length')} caracteres"
    if tipo == "string_pattern_mismatch":
        return "formato inválido"
    if tipo in ("int_parsing", "float_parsing", "int_type", "float_type"):
        return "precisa ser um número"
    if tipo == "greater_than":
        return f"precisa ser maior que {contexto.get('gt')}"
    if tipo == "greater_than_equal":
        return f"precisa ser maior ou igual a {contexto.get('ge')}"
    if tipo == "less_than":
        return f"precisa ser menor que {contexto.get('lt')}"
    if tipo == "less_than_equal":
        return f"precisa ser menor ou igual a {contexto.get('le')}"
    if tipo == "literal_error":
        return f"valor não permitido (use {contexto.get('expected')})"
    if tipo == "json_invalid":
        return "JSON inválido"
    if tipo == "extra_forbidden":
        return "campo desconhecido"
    if tipo == "value_error" and "email address" in original:
        return "e-mail inválido"
    if tipo == "value_error":
        return original.removeprefix("Value error, ")  # validadores nossos já escrevem em português
    return original


async def _erro_de_validacao(request: Request, erro: RequestValidationError) -> JSONResponse:
    erros = [{"campo": _campo(problema.get("loc", ())), "mensagem": _mensagem(problema)} for problema in erro.errors()]
    resumo = "; ".join(f"{e['campo']}: {e['mensagem']}" for e in erros)
    return resposta_de_erro(422, f"Dados inválidos: {resumo}.", erros=erros)


# --- 500: qualquer exceção não tratada ---

async def capturar_erros_inesperados(request: Request, call_next):
    """Middleware (e não exception handler): o handler de Exception do Starlette responde e depois RELANÇA o erro,
    e o uvicorn registra a mesma stack de novo ("Exception in ASGI application"). Aqui o erro para: um registro só."""
    try:
        return await call_next(request)
    except Exception as erro:
        # A stack fica no log (para quem mantém o sistema). O cliente recebe só a mensagem genérica: detalhes
        # internos (caminhos, SQL, versões) numa resposta ajudariam um atacante.
        logger.error("Erro inesperado em %s %s", request.method, request.url.path, exc_info=erro)
        return resposta_de_erro(500, MENSAGENS_PADRAO[500])


def registrar(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _erro_http)
    app.add_exception_handler(RequestValidationError, _erro_de_validacao)
    # Chame registrar() DEPOIS de adicionar os outros middlewares (o último adicionado é o mais externo):
    # assim o capturador envolve todos eles.
    app.middleware("http")(capturar_erros_inesperados)
