"""API fechada por padrão (B13): sem login, toda rota /api responde 401, menos as de autenticação.

O teste percorre as rotas REGISTRADAS no app (e não uma lista escrita à mão): uma rota nova criada sem proteção
quebra este teste, a não ser que seja incluída de propósito em ROTAS_PUBLICAS.
"""
import re

import pytest
from fastapi.routing import APIRoute

from app.main import app
from app.services import midia

# Rotas que respondem sem login, de propósito.
ROTAS_PUBLICAS = ("/api/auth/",)

# Valores válidos para os parâmetros do caminho (o 401 tem de vir antes de qualquer validação ou busca).
# Parâmetro que não está aqui (ex.: rotas novas com {attempt_id}) recebe "1".
VALORES = {"video_id": "abcdefghijk", "deck_id": "1", "card_id": "1"}


def _rotas_da_api():
    for rota in app.routes:
        if isinstance(rota, APIRoute) and rota.path.startswith("/api/") and not rota.path.startswith(ROTAS_PUBLICAS):
            caminho = re.sub(r"\{(\w+)\}", lambda m: VALORES.get(m.group(1), "1"), rota.path)
            for metodo in sorted(rota.methods - {"HEAD"}):
                yield pytest.param(metodo, caminho, id=f"{metodo} {rota.path}")


ROTAS = list(_rotas_da_api())


def test_a_lista_de_rotas_inclui_as_de_conteudo():
    """Garante que o teste abaixo realmente cobre as rotas protegidas no B13 (e não uma lista vazia)."""
    ids = {p.id for p in ROTAS}
    esperadas = (
        "GET /api/videos/{video_id}/status", "GET /api/videos/{video_id}", "GET /api/videos/{video_id}/waveform",
        "GET /api/videos/{video_id}/audio", "GET /api/videos/{video_id}/palavras", "POST /api/avaliacoes",
        "GET /api/dicionario", "GET /api/decks", "GET /api/legendas", "PATCH /api/configuracoes",
        "GET /api/llm/situacao",
    )
    for esperada in esperadas:
        assert esperada in ids, esperada


@pytest.mark.parametrize("metodo, caminho", ROTAS)
def test_sem_login_toda_rota_da_api_responde_401(client, metodo, caminho):
    resposta = client.request(metodo, caminho)

    assert resposta.status_code == 401, f"{metodo} {caminho} respondeu {resposta.status_code} sem login"
    assert resposta.json() == {"detail": "Faça login para continuar.", "codigo": "nao_autenticado"}


def test_sem_login_o_status_nao_inicia_download(client, monkeypatch):
    """A rota mais sensível: antes do B13, qualquer pessoa podia mandar o servidor baixar vídeos do YouTube."""
    baixados = []
    monkeypatch.setattr(midia.youtube, "baixar_video", lambda *args: baixados.append(args))
    midia._downloads.clear()

    assert client.get("/api/videos/abcdefghijk/status").status_code == 401
    assert baixados == [] and midia._downloads == {}


def test_rotas_de_autenticacao_continuam_publicas(client):
    login = client.post("/api/auth/login", json={"email": "x@exemplo.com", "senha": "y"})
    assert login.status_code == 401  # credencial errada, e não "faça login"
    cadastro = client.post("/api/auth/cadastro", json={"email": "novo@exemplo.com", "senha": "senha-forte-123"})
    assert cadastro.status_code == 201
