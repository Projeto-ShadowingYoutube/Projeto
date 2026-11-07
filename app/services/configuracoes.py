"""Configurações individuais de estudo (hoje: a velocidade preferida do vídeo).

A linha de cada usuário só existe depois do primeiro salvamento; até lá, valem os padrões. Assim, usuários
antigos não precisam de migração de dados, e uma preferência nova é só uma coluna com valor padrão.
"""
from sqlmodel import Session

from app.config import VELOCIDADE_PADRAO
from app.models import ConfiguracaoEstudo, agora

PADROES = {"velocidade": VELOCIDADE_PADRAO}


def obter(session: Session, usuario_id: int) -> dict:
    configuracao = session.get(ConfiguracaoEstudo, usuario_id)
    if configuracao is None:
        return dict(PADROES)
    return {"velocidade": configuracao.velocidade}


def atualizar(session: Session, usuario_id: int, mudancas: dict) -> dict:
    """Aplica só os campos informados (PATCH) e devolve a configuração completa."""
    if "velocidade" in mudancas:
        mudancas["velocidade"] = round(mudancas["velocidade"], 2)  # o slider anda de 0.05 em 0.05
    if mudancas:
        configuracao = session.get(ConfiguracaoEstudo, usuario_id) or ConfiguracaoEstudo(usuario_id=usuario_id)
        for campo, valor in mudancas.items():
            setattr(configuracao, campo, valor)
        configuracao.data_atualizacao = agora()
        session.add(configuracao)
        session.commit()
    return obter(session, usuario_id)
