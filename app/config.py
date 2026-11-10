"""Caminhos e constantes do app, num lugar só.

Tudo o que o app gera ao rodar (banco, cache, vídeos, modelo de fala) fica em dados/, fora do Git.
O que muda entre ambientes (desenvolvimento, teste, produção) vem de variáveis de ambiente ou do
arquivo .env na raiz do projeto (ver .env.example); sem elas, valem os padrões abaixo.
"""
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ_APP = Path(__file__).resolve().parent
RAIZ_PROJETO = RAIZ_APP.parent

PASTA_TEMPLATES = RAIZ_APP / "templates"
PASTA_STATIC = RAIZ_APP / "static"

PASTA_DADOS = RAIZ_PROJETO / "dados"
ARQUIVO_BANCO = PASTA_DADOS / "estudos.db"
ARQUIVO_CACHE_LEGENDAS = PASTA_DADOS / "ultimo_video.json"
PASTA_MIDIA = PASTA_DADOS / "midia"
PASTA_MODELOS = PASTA_DADOS / "modelos"


class Configuracoes(BaseSettings):
    """Valores que dependem do ambiente. Ordem: variável de ambiente > arquivo .env > padrão daqui."""
    model_config = SettingsConfigDict(env_file=RAIZ_PROJETO / ".env", env_file_encoding="utf-8", extra="ignore")

    # Ex.: postgresql+psycopg://usuario:senha@127.0.0.1:5432/shadowing. Padrão: o SQLite local de sempre.
    database_url: str = f"sqlite:///{ARQUIVO_BANCO}"
    # Em "producao", o cookie de sessão só trafega por HTTPS (atributo Secure).
    ambiente: Literal["desenvolvimento", "producao"] = "desenvolvimento"

    # LLM (app/services/llm.py): qualquer provedor com a API no formato da OpenAI (Gemini, DeepSeek, Groq, Ollama...).
    # Sem a chave, o app sobe normalmente; só as funções de IA respondem 503 (llm_nao_configurada).
    llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    llm_modelo: str = "gemini-flash-latest"
    llm_chave: SecretStr | None = None
    llm_timeout_segundos: float = 60
    # Pede ao provedor resposta em JSON (response_format). Desligue só se o provedor recusar esse parâmetro.
    llm_modo_json: bool = True


configuracoes = Configuracoes()
DATABASE_URL = configuracoes.database_url
AMBIENTE = configuracoes.ambiente

LLM_BASE_URL = configuracoes.llm_base_url
LLM_MODELO = configuracoes.llm_modelo
LLM_CHAVE = configuracoes.llm_chave.get_secret_value() if configuracoes.llm_chave else ""
LLM_TIMEOUT_SEGUNDOS = configuracoes.llm_timeout_segundos
LLM_MODO_JSON = configuracoes.llm_modo_json
# Desafios com IA (Reading, Writing, Speaking): quantos cada CONTA pode iniciar por dia, em cada feature.
# Cada desafio custa chamadas pagas à LLM (ver app/api/llm.py, dependência exigir_cota).
LIMITE_DESAFIOS_LLM = "10/day"

# Sessão de login: nome do cookie e quanto tempo ela vale sem precisar entrar de novo.
COOKIE_SESSAO = "sessao"
DURACAO_SESSAO_DIAS = 14

# Limite de vídeos novos por CONTA: cada vídeo que não está na cache gasta um token (ver api/legendas.py).
LIMITE_TOKENS = "5/5 minute"

# Vídeos guardados em PASTA_MIDIA; os usados há mais tempo são apagados.
MAX_VIDEOS_GUARDADOS = 5
# Velocidade do vídeo: a mesma faixa do slider (templates/partials/player.html). A escolhida fica salva por usuário.
VELOCIDADE_MINIMA = 0.25
VELOCIDADE_MAXIMA = 1.5
VELOCIDADE_PADRAO = 1.0
# Volume do vídeo (0 = mudo, 1 = 100%), ao lado da velocidade na barra do player. Também fica salvo por usuário.
VOLUME_PADRAO = 1.0

# Waveform (B9): a onda de cada frase é desenhada a partir de N "peaks" (0 a 1), calculados uma vez e guardados no
# banco. 400 ≈ o máximo de barras visíveis no painel (barra de 2 px + espaço de 1 px). Mudou o cálculo? Aumente a
# versão: os registros antigos deixam de valer e cada onda é recalculada na próxima vez (ver services/waveform.py).
WAVEFORM_QUANTIDADE_PEAKS = 400
WAVEFORM_TAXA_AMOSTRAGEM = 8000  # Hz: o suficiente para o contorno da onda (não é para ouvir)
WAVEFORM_VERSAO_ALGORITMO = 1

# Duração máxima de um trecho de áudio pedido à API (segundos).
DURACAO_MAXIMA_TRECHO = 120

PADRAO_VIDEO_ID = r"^[0-9A-Za-z_-]{11}$"
