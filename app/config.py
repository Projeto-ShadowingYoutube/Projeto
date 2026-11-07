"""Caminhos e constantes do app, num lugar só.

Tudo o que o app gera ao rodar (banco, cache, vídeos, modelo de fala) fica em dados/, fora do Git.
O que muda entre ambientes (desenvolvimento, teste, produção) vem de variáveis de ambiente ou do
arquivo .env na raiz do projeto (ver .env.example); sem elas, valem os padrões abaixo.
"""
from pathlib import Path
from typing import Literal

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


configuracoes = Configuracoes()
DATABASE_URL = configuracoes.database_url
AMBIENTE = configuracoes.ambiente

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

# Waveform (B9): a onda de cada frase é desenhada a partir de N "peaks" (0 a 1), calculados uma vez e guardados no
# banco. 400 ≈ o máximo de barras visíveis no painel (barra de 2 px + espaço de 1 px). Mudou o cálculo? Aumente a
# versão: os registros antigos deixam de valer e cada onda é recalculada na próxima vez (ver services/waveform.py).
WAVEFORM_QUANTIDADE_PEAKS = 400
WAVEFORM_TAXA_AMOSTRAGEM = 8000  # Hz: o suficiente para o contorno da onda (não é para ouvir)
WAVEFORM_VERSAO_ALGORITMO = 1

# Duração máxima de um trecho de áudio pedido à API (segundos).
DURACAO_MAXIMA_TRECHO = 120

PADRAO_VIDEO_ID = r"^[0-9A-Za-z_-]{11}$"
