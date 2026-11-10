"""Serviço ÚNICO de LLM do projeto, compartilhado por Reading, Writing e Speaking (documentado no README, seção "LLM").

Base protegida: os Membros 1 a 3 USAM este módulo, não o alteram (ver CLAUDE.md). Os prompts de cada feature ficam
no serviço da própria feature; aqui não existe nada específico de Reading, Writing ou Speaking.

Uso (sempre numa rota "def" ou em asyncio.to_thread: a chamada é bloqueante e pode levar vários segundos):

    from pydantic import BaseModel
    from app.services import llm

    class Correcao(BaseModel):
        nota: int
        comentario: str

    correcao = llm.gerar_json(sistema="Você corrige redações...", usuario=texto, modelo=Correcao)
    correcao.nota  # objeto já validado

Como funciona:
- Fala com qualquer provedor que tenha a API no formato da OpenAI (POST {LLM_BASE_URL}/chat/completions).
  Trocar de provedor (Gemini, DeepSeek, Groq, Ollama local) é só mudar o .env: LLM_BASE_URL, LLM_MODELO, LLM_CHAVE.
- O schema do modelo Pydantic vai junto das instruções, e a resposta é validada com ele.
- Resposta fora do formato: UMA nova tentativa, mostrando os erros ao modelo. Falhou de novo → LLMRespostaInvalida.
  Timeout e falhas de rede NÃO são repetidos (a pessoa já esperou o timeout inteiro).
- Toda falha vira uma subclasse de ErroLLM, que o app transforma no erro padrão {detail, codigo} (app/erros.py).
  Quem precisa reagir à falha (ex.: marcar a tentativa como "erro_avaliacao") captura ErroLLM e relança.
- A chave nunca aparece em log nem em mensagem de erro.
"""
import json
import logging
import time
from typing import TypeVar

import requests
from pydantic import BaseModel, ValidationError

from app import config

logger = logging.getLogger("uvicorn.error")

T = TypeVar("T", bound=BaseModel)

TENTATIVAS = 2  # a primeira + uma nova tentativa quando a resposta vem fora do formato
TIMEOUT_CONEXAO = 5  # segundos para conectar; o tempo de resposta é config.LLM_TIMEOUT_SEGUNDOS

INSTRUCAO_JSON = (
    "Responda SOMENTE com um objeto JSON válido, sem texto antes ou depois e sem blocos de código, "
    "seguindo exatamente este JSON Schema:\n{schema}"
)
INSTRUCAO_CORRECAO = (
    "A sua resposta anterior não seguiu o formato pedido. Problemas encontrados:\n{problemas}\n"
    "Responda de novo SOMENTE com o objeto JSON corrigido."
)

_sessao = requests.Session()


# --- Erros (cada um vira {detail, codigo} com o status abaixo, pelo handler de app/erros.py) ---

class ErroLLM(Exception):
    status = 502
    codigo = "llm_indisponivel"
    mensagem_padrao = "O serviço de IA está indisponível agora. Tente de novo em instantes."

    def __init__(self, mensagem: str | None = None):
        self.mensagem = mensagem or self.mensagem_padrao
        super().__init__(self.mensagem)


class LLMNaoConfigurada(ErroLLM):
    status = 503
    codigo = "llm_nao_configurada"
    mensagem_padrao = "As funções de IA não estão configuradas neste servidor."


class LLMIndisponivel(ErroLLM):
    """Rede fora, provedor com erro, chave recusada ou limite do provedor atingido (429)."""


class LLMTempoEsgotado(ErroLLM):
    status = 504
    codigo = "llm_tempo_esgotado"
    mensagem_padrao = "O serviço de IA demorou demais para responder. Tente de novo."


class LLMRespostaInvalida(ErroLLM):
    codigo = "llm_resposta_invalida"
    mensagem_padrao = "O serviço de IA devolveu uma resposta fora do formato esperado. Tente de novo."


# --- Interface pública ---

def configurada() -> bool:
    """Há provedor, modelo e chave? (O Ollama local aceita qualquer chave: use, por exemplo, LLM_CHAVE=ollama.)"""
    return bool(config.LLM_BASE_URL and config.LLM_MODELO and config.LLM_CHAVE)


def modelo_em_uso() -> str:
    """Nome do modelo configurado. Grave-o junto do resultado (ex.: feedback do Writing) para comparar depois."""
    return config.LLM_MODELO


def gerar_json(*, sistema: str, usuario: str, modelo: type[T], temperatura: float = 0.2,
               max_tokens: int | None = None) -> T:
    """Pede uma resposta em JSON e devolve um objeto `modelo` já validado.

    sistema: as instruções da tarefa (o "papel" do modelo). usuario: o conteúdo a processar (texto, redação...).
    Levanta LLMNaoConfigurada, LLMIndisponivel, LLMTempoEsgotado ou LLMRespostaInvalida.
    """
    if not configurada():
        raise LLMNaoConfigurada()
    schema = json.dumps(modelo.model_json_schema(), ensure_ascii=False)
    mensagens = [
        {"role": "system", "content": f"{sistema}\n\n{INSTRUCAO_JSON.format(schema=schema)}"},
        {"role": "user", "content": usuario},
    ]
    for tentativa in range(1, TENTATIVAS + 1):
        texto = _chamar(mensagens, temperatura, max_tokens)
        try:
            return modelo.model_validate_json(_extrair_json(texto))
        except ValidationError as erro:
            problemas = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'resposta'}: {e['msg']}" for e in erro.errors())
            logger.warning("LLM: resposta fora do formato (tentativa %d de %d): %s", tentativa, TENTATIVAS,
                           problemas[:300])
            mensagens += [
                {"role": "assistant", "content": texto},
                {"role": "user", "content": INSTRUCAO_CORRECAO.format(problemas=problemas)},
            ]
    raise LLMRespostaInvalida()


# --- Internos ---

def _extrair_json(texto: str) -> str:
    """Tolera o que os modelos costumam acrescentar: blocos ```json``` e frases antes/depois do objeto."""
    inicio, fim = texto.find("{"), texto.rfind("}")
    return texto[inicio:fim + 1] if inicio != -1 and fim > inicio else texto


def _chamar(mensagens: list[dict], temperatura: float, max_tokens: int | None) -> str:
    """Uma chamada a /chat/completions. Devolve o texto da resposta."""
    corpo = {"model": config.LLM_MODELO, "messages": mensagens, "temperature": temperatura}
    if max_tokens:
        corpo["max_tokens"] = max_tokens
    if config.LLM_MODO_JSON:
        corpo["response_format"] = {"type": "json_object"}
    url = config.LLM_BASE_URL.rstrip("/") + "/chat/completions"

    inicio = time.monotonic()
    try:
        resposta = _sessao.post(url, json=corpo, headers={"Authorization": f"Bearer {config.LLM_CHAVE}"},
                                timeout=(TIMEOUT_CONEXAO, config.LLM_TIMEOUT_SEGUNDOS))
    except requests.Timeout as erro:
        logger.warning("LLM: sem resposta em %s s (%s)", config.LLM_TIMEOUT_SEGUNDOS, config.LLM_MODELO)
        raise LLMTempoEsgotado() from erro
    except requests.RequestException as erro:
        logger.warning("LLM: falha de conexão com o provedor (%s)", type(erro).__name__)
        raise LLMIndisponivel() from erro

    if resposta.status_code == 429:
        logger.warning("LLM: o provedor recusou por limite de uso (429)")
        raise LLMIndisponivel("O serviço de IA atingiu o limite de uso. Tente de novo em alguns minutos.")
    if resposta.status_code in (401, 403):
        logger.error("LLM: o provedor recusou a chave (%s). Confira LLM_CHAVE e LLM_BASE_URL.", resposta.status_code)
        raise LLMIndisponivel()
    if resposta.status_code >= 400:
        logger.warning("LLM: o provedor respondeu %s: %s", resposta.status_code, resposta.text[:300])
        raise LLMIndisponivel()

    try:
        dados = resposta.json()
        texto = dados["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as erro:
        logger.warning("LLM: resposta do provedor sem o formato da API: %s", resposta.text[:300])
        raise LLMRespostaInvalida() from erro
    if not isinstance(texto, str) or not texto.strip():
        raise LLMRespostaInvalida()

    logger.info("LLM: %s respondeu em %.1f s (uso: %s)", config.LLM_MODELO, time.monotonic() - inicio,
                dados.get("usage"))
    return texto
