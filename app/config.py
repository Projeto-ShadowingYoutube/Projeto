"""Caminhos e constantes do app, num lugar só.

Tudo o que o app gera ao rodar (banco, cache, vídeos, modelo de fala) fica em dados/, fora do Git.
"""
from pathlib import Path

RAIZ_APP = Path(__file__).resolve().parent
RAIZ_PROJETO = RAIZ_APP.parent

PASTA_TEMPLATES = RAIZ_APP / "templates"
PASTA_STATIC = RAIZ_APP / "static"

PASTA_DADOS = RAIZ_PROJETO / "dados"
ARQUIVO_BANCO = PASTA_DADOS / "estudos.db"
ARQUIVO_CACHE_LEGENDAS = PASTA_DADOS / "ultimo_video.json"
PASTA_MIDIA = PASTA_DADOS / "midia"
PASTA_MODELOS = PASTA_DADOS / "modelos"

# Limite de vídeos novos por usuário (IP): cada vídeo que não está na cache gasta um token.
LIMITE_TOKENS = "5/5 minute"

# Vídeos guardados em PASTA_MIDIA; os usados há mais tempo são apagados.
MAX_VIDEOS_GUARDADOS = 5
# Duração máxima de um trecho de áudio pedido à API (segundos).
DURACAO_MAXIMA_TRECHO = 120

PADRAO_VIDEO_ID = r"^[0-9A-Za-z_-]{11}$"
