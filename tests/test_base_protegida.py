"""Alarme da base protegida (ver CLAUDE.md, "Base protegida").

Os Membros 1 a 3 trabalham em branches próprias e NÃO alteram estes arquivos: são a base compartilhada pelas três
features e o Membro 4 junta as branches no final. Se um deles mudar, este teste falha no merge, antes de a mudança
passar despercebida.

Mudou um destes arquivos de propósito, com a aprovação do Membro 4? Atualize o hash abaixo NO MESMO commit e
explique a mudança no README_MEMBRO{N}.md. Nunca atualize o hash só para o teste passar.
"""
import hashlib
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent

# Hash do conteúdo com finais de linha normalizados (o Git no Windows pode trocar \n por \r\n).
HASHES = {
    "app/services/llm.py":
        "ce17af77522f15da622507c8fcf85ba598fe9b65b445daa64bfc84929d59064f",
    "app/api/llm.py":
        "f3e7b33c64786589ea1828c02e930a8317af969580526d96f7de02d2fec81a4a",
    "app/erros.py":
        "75b09a4693d8cf1b285b5f92ecfa3c9f4796d0aefb182ca0d78f5431735fd74b",
    "tests/conftest.py":
        "8ed13d1e143365a01b52504f39a1274c33dd3dfa09825cd8e09d30395041b083",
    "migrations/versions/0001_baseline.py":
        "18c9c3e3ae716c71076cdfae21ba234fb77b93bb9b0a72381af2274495630400",
    "migrations/versions/0002_usuarios_e_sessoes.py":
        "57bdef0b8d2453ecf3fff5e23092808327d895e03976fa31b0afe9c95b3d9fd6",
    "migrations/versions/0003_posse_dos_decks.py":
        "cf20d3110c4fb1526e4b74282e745881cc7d43c7522c8e05698a6cf462536ab1",
    "migrations/versions/0004_configuracoes_de_estudo.py":
        "e914812c9baaa864c94d345d6000108cd4da3f20fb3a492506757319a2949f93",
    "migrations/versions/0005_waveform.py":
        "d988da8e843192a92e92f39a6a456a29df068d88c87557764d06c54516f71788",
    "migrations/versions/0006_volume_nas_configuracoes.py":
        "c63d9f09f3489b2ec09a5b2228c2850870e20fb1eef5954eefcd9be7802db099",
}


def hash_do_arquivo(caminho: str) -> str:
    conteudo = (RAIZ / caminho).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(conteudo).hexdigest()


@pytest.mark.parametrize("caminho", HASHES)
def test_arquivo_da_base_nao_foi_alterado(caminho):
    assert hash_do_arquivo(caminho) == HASHES[caminho], (
        f"{caminho} faz parte da base protegida e foi alterado. Os Membros 1 a 3 não alteram este arquivo "
        "(ver CLAUDE.md). Se a mudança foi aprovada pelo Membro 4, atualize o hash em tests/test_base_protegida.py."
    )
