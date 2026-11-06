"""Caminhos e constantes do app, num lugar só.

Tudo o que o app gera ao rodar (banco, cache, vídeos, modelo de fala) fica em dados/, fora do Git.
O que muda entre ambientes (desenvolvimento, teste, produção) vem de variáveis de ambiente ou do
arquivo .env na raiz do projeto (ver .env.example); sem elas, valem os padrões abaixo.
"""
from pathlib import Path

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

    # Ex.: postgresql+psycopg://usuario:senha@localhost:5432/shadowing. Padrão: o SQLite local de sempre.
    database_url: str = f"sqlite:///{ARQUIVO_BANCO}"


configuracoes = Configuracoes()
DATABASE_URL = configuracoes.database_url

# Limite de vídeos novos por usuário (IP): cada vídeo que não está na cache gasta um token.
LIMITE_TOKENS = "5/5 minute"

# Vídeos guardados em PASTA_MIDIA; os usados há mais tempo são apagados.
MAX_VIDEOS_GUARDADOS = 5
# Duração máxima de um trecho de áudio pedido à API (segundos).
DURACAO_MAXIMA_TRECHO = 120

PADRAO_VIDEO_ID = r"^[0-9A-Za-z_-]{11}$"
