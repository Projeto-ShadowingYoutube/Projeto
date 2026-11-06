"""Regras de contas e sessões: hash de senha (Argon2id), cadastro, login e validação do token de sessão.

Senha x token, por que hashes diferentes:
- A senha é escolhida por uma pessoa e pode ser fraca: usamos Argon2id, lento de propósito, para que testar
  milhões de senhas num banco vazado seja caro.
- O token de sessão tem 256 bits aleatórios: ninguém o adivinha, então um hash rápido (SHA-256) basta. Guardamos
  só o hash, e assim quem lê o banco não consegue se passar pelo usuário.
"""
import hashlib
import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlmodel import Session, col, delete, select

from app import config
from app.models import Sessao, Usuario, agora

_hasher = PasswordHasher()  # parâmetros padrão da biblioteca (argon2id, 64 MiB, t=3), alinhados à OWASP
# Hash de uma senha qualquer: verificado quando o e-mail não existe, para o tempo de resposta ser o mesmo.
_HASH_FALSO = _hasher.hash("senha-que-nao-existe")


class EmailJaCadastrado(Exception):
    """Já existe uma conta com esse e-mail."""


def normalizar_email(email: str) -> str:
    return email.strip().lower()


def _hash_do_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def cadastrar(session: Session, email: str, senha: str) -> Usuario:
    email = normalizar_email(email)
    if session.exec(select(Usuario.id).where(Usuario.email == email)).first() is not None:
        raise EmailJaCadastrado
    usuario = Usuario(email=email, senha_hash=_hasher.hash(senha))
    session.add(usuario)
    session.commit()
    session.refresh(usuario)
    return usuario


def autenticar(session: Session, email: str, senha: str) -> Usuario | None:
    """O usuário, se e-mail e senha conferirem; senão None (sem dizer qual dos dois estava errado)."""
    usuario = session.exec(select(Usuario).where(Usuario.email == normalizar_email(email))).first()
    try:
        _hasher.verify(usuario.senha_hash if usuario else _HASH_FALSO, senha)
    except (VerificationError, InvalidHashError):
        return None
    if usuario is None:
        return None
    if _hasher.check_needs_rehash(usuario.senha_hash):
        # Os parâmetros recomendados mudaram desde o cadastro: aproveita que temos a senha e refaz o hash.
        usuario.senha_hash = _hasher.hash(senha)
        session.add(usuario)
        session.commit()
    return usuario


def criar_sessao(session: Session, usuario: Usuario) -> str:
    """Abre uma sessão e devolve o token (vai só para o cookie; no banco fica o hash dele)."""
    momento = agora()
    # Faxina: as sessões vencidas desse usuário não servem para mais nada.
    session.exec(delete(Sessao).where(Sessao.usuario_id == usuario.id, col(Sessao.expira_em) <= momento))
    token = secrets.token_urlsafe(32)
    session.add(Sessao(
        token_hash=_hash_do_token(token),
        usuario_id=usuario.id,
        data_criacao=momento,
        expira_em=momento + timedelta(days=config.DURACAO_SESSAO_DIAS),
    ))
    session.commit()
    return token


def usuario_da_sessao(session: Session, token: str) -> Usuario | None:
    """O dono de uma sessão válida; None se o token não existir ou a sessão tiver vencido (e então a apaga)."""
    sessao = session.exec(select(Sessao).where(Sessao.token_hash == _hash_do_token(token))).first()
    if sessao is None:
        return None
    if sessao.expira_em <= agora():
        session.delete(sessao)
        session.commit()
        return None
    return session.get(Usuario, sessao.usuario_id)


def encerrar_sessao(session: Session, token: str) -> None:
    """Logout: apaga a sessão. O mesmo token deixa de funcionar, mesmo que alguém tenha copiado o cookie."""
    session.exec(delete(Sessao).where(Sessao.token_hash == _hash_do_token(token)))
    session.commit()
