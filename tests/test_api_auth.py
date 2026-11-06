import hashlib
from datetime import timedelta

from argon2 import PasswordHasher
from sqlmodel import Session, select

from app import config
from app.models import Sessao, Usuario, agora

EMAIL = "ana@exemplo.com"
SENHA = "senha-forte-123"


def cadastrar(client, email=EMAIL, senha=SENHA):
    return client.post("/api/auth/cadastro", json={"email": email, "senha": senha})


def entrar(client, email=EMAIL, senha=SENHA):
    return client.post("/api/auth/login", json={"email": email, "senha": senha})


def test_cadastro_cria_conta_e_ja_entra(client):
    resposta = cadastrar(client)

    assert resposta.status_code == 201
    assert resposta.json() == {"id": resposta.json()["id"], "email": EMAIL}  # nada de hash na resposta
    assert client.get("/api/auth/me").json()["email"] == EMAIL


def test_senha_e_guardada_so_como_hash_argon2id(client, engine_teste):
    cadastrar(client)

    with Session(engine_teste) as session:
        usuario = session.exec(select(Usuario)).one()
    assert usuario.senha_hash.startswith("$argon2id$")
    assert SENHA not in usuario.senha_hash


def test_email_repetido_da_409_mesmo_com_outras_maiusculas(client):
    cadastrar(client)
    client.cookies.clear()

    resposta = cadastrar(client, email="ANA@Exemplo.COM")

    assert resposta.status_code == 409
    assert resposta.json()["detail"] == "Este e-mail já está cadastrado."


def test_cadastro_valida_email_e_tamanho_da_senha(client):
    assert cadastrar(client, email="nao-e-email").status_code == 422
    assert cadastrar(client, senha="curta").status_code == 422
    assert cadastrar(client, senha="x" * 129).status_code == 422


def test_login_grava_cookie_httponly_samesite_e_com_validade(client):
    cadastrar(client)
    client.cookies.clear()

    resposta = entrar(client, email="  Ana@Exemplo.com ")  # e-mail normalizado também no login

    assert resposta.status_code == 200
    cookie = resposta.headers["set-cookie"]
    assert cookie.startswith(f"{config.COOKIE_SESSAO}=")
    assert "HttpOnly" in cookie
    assert "samesite=lax" in cookie.lower()
    assert f"Max-Age={config.DURACAO_SESSAO_DIAS * 86400}" in cookie
    assert "Secure" not in cookie  # em desenvolvimento roda em http://
    assert client.get("/api/auth/me").status_code == 200


def test_cookie_e_secure_em_producao(client, monkeypatch):
    monkeypatch.setattr(config, "AMBIENTE", "producao")

    assert "Secure" in cadastrar(client).headers["set-cookie"]


def test_senha_errada_e_email_inexistente_tem_a_mesma_resposta(client):
    cadastrar(client)
    client.cookies.clear()

    senha_errada = entrar(client, senha="outra-senha-123")
    email_inexistente = entrar(client, email="ninguem@exemplo.com")

    assert senha_errada.status_code == email_inexistente.status_code == 401
    assert senha_errada.json() == email_inexistente.json() == {"detail": "E-mail ou senha incorretos."}
    assert "set-cookie" not in senha_errada.headers


def test_me_sem_cookie_ou_com_token_inventado_da_401(client):
    assert client.get("/api/auth/me").status_code == 401

    client.cookies.set(config.COOKIE_SESSAO, "token-inventado")
    assert client.get("/api/auth/me").status_code == 401


def test_banco_guarda_o_hash_do_token_e_nao_o_token(client, engine_teste):
    cadastrar(client)
    token = client.cookies.get(config.COOKIE_SESSAO)

    with Session(engine_teste) as session:
        sessao = session.exec(select(Sessao)).one()
    assert sessao.token_hash != token
    assert sessao.token_hash == hashlib.sha256(token.encode()).hexdigest()


def test_logout_revoga_a_sessao_no_servidor(client):
    cadastrar(client)
    token = client.cookies.get(config.COOKIE_SESSAO)

    resposta = client.post("/api/auth/logout")

    assert resposta.status_code == 204
    assert f'{config.COOKIE_SESSAO}=""' in resposta.headers["set-cookie"]  # cookie apagado no navegador
    # Mesmo quem guardou uma cópia do cookie não entra mais:
    client.cookies.set(config.COOKIE_SESSAO, token)
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/logout").status_code == 204  # sair de novo não é erro


def test_sessao_vencida_da_401_e_e_apagada(client, engine_teste):
    cadastrar(client)
    with Session(engine_teste) as session:
        sessao = session.exec(select(Sessao)).one()
        sessao.expira_em = agora() - timedelta(minutes=1)
        session.add(sessao)
        session.commit()

    assert client.get("/api/auth/me").status_code == 401
    with Session(engine_teste) as session:
        assert session.exec(select(Sessao)).all() == []


def test_login_refaz_hash_criado_com_parametros_antigos(client, engine_teste):
    hash_antigo = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash(SENHA)
    with Session(engine_teste) as session:
        session.add(Usuario(email=EMAIL, senha_hash=hash_antigo))
        session.commit()

    assert entrar(client).status_code == 200

    with Session(engine_teste) as session:
        novo = session.exec(select(Usuario)).one().senha_hash
    assert novo != hash_antigo
    assert PasswordHasher().check_needs_rehash(novo) is False


def test_rotas_de_decks_exigem_login(client):
    """Desde o B5 (antes, no B4, eram públicas). O isolamento completo está em test_isolamento.py."""
    assert client.get("/api/decks").status_code == 401
    cadastrar(client)
    assert client.get("/api/decks").status_code == 200
