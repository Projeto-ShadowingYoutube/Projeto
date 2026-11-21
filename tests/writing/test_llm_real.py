"""Teste OPCIONAL com a LLM de verdade (Membro 3, D27): corrige redações reais e mede o tempo de cada chamada.

Desligado por padrão (como o E2E=1 da base): gasta a cota do provedor e depende de rede. Para rodar, com a
LLM_CHAVE no .env (e, se quiser, o LLM_MODELO):
    PowerShell:  $env:LLM_REAL="1"; python -m pytest tests/writing/test_llm_real.py -s --no-cov
    bash:        LLM_REAL=1 python -m pytest tests/writing/test_llm_real.py -s --no-cov
O "-s" mostra os tempos e as notas no terminal. Serve também para o Membro 4 medir no servidor de produção.

Este é o ÚNICO lugar em que a proteção da base (fixture automática llm_desligada, em tests/conftest.py) é
contornada, de propósito e só com LLM_REAL=1: a fixture abaixo devolve a chave do .env e a chamada HTTP real.
"""
import os
import time

import pytest

if not os.environ.get("LLM_REAL"):
    pytest.skip("teste com a LLM de verdade desligado (defina LLM_REAL=1)", allow_module_level=True)

from app import config  # noqa: E402
from app.schemas_writing import CATEGORIAS_AVALIADAS  # noqa: E402
from app.services import llm, writing_llm  # noqa: E402
from app.services.writing_texto import contar_palavras  # noqa: E402

TEMA = ("Some people believe that university education should be free for everyone and paid for by the government. "
        "To what extent do you agree or disagree?")

CURTA = (
    "I agree that university should be free. Many student cant pay the fees and they gives up their dreams. "
    "If the government pay, more people will study and the country will be more develop. But the goverment need "
    "money for this, so maybe taxes will increase. In my opinion, education is a investment and not a cost."
)
MEDIA = CURTA + (
    "\n\nFirstly, free education give equal opportunities. A poor student who is very intelligent can not study "
    "today because his family dont have money. This is unfair and the society lose talented people.\n\n"
    "Secondly, a educated population is better for the economy. Countries like Germany offers free university and "
    "they have strong industries. When more people have a degree, the salaries are higher and the government receive "
    "more taxes, so the investment come back.\n\n"
    "In conclusion, I strongly believe that university should be free because it create opportunities and help the "
    "economy, although the government must to plan the costs carefully."
)
REDACOES = {"curta": CURTA, "media": MEDIA}


@pytest.fixture(autouse=True)
def llm_ligada(llm_desligada, monkeypatch):
    """Desfaz a llm_desligada (que roda antes, por ser dependência): a chave do .env e o POST de verdade."""
    chave = config.configuracoes.llm_chave
    monkeypatch.setattr(config, "LLM_CHAVE", chave.get_secret_value() if chave else "")
    monkeypatch.delattr(llm._sessao, "post")  # volta ao requests.Session.post da classe
    if not llm.configurada():
        pytest.skip("LLM_CHAVE ausente no .env")


@pytest.mark.parametrize("nome", REDACOES)
def test_correcao_real(nome):
    texto = REDACOES[nome]
    inicio = time.monotonic()
    resultado = writing_llm.avaliar(
        texto=texto, enunciado=TEMA, categoria="ielts_opiniao", palavras_minimas=250, palavras=contar_palavras(texto),
    )
    segundos = time.monotonic() - inicio

    print(f"\n[{config.LLM_MODELO}] correção {nome}: {contar_palavras(texto)} palavras, {segundos:.1f} s, "
          f"nota geral {resultado.nota_geral}, trechos {len(resultado.trechos)} (descartados {resultado.descartados})")
    assert set(resultado.notas) == set(CATEGORIAS_AVALIADAS)
    assert 0 <= resultado.nota_geral <= 10
    for trecho in resultado.trechos:  # as posições valem no texto original
        assert texto[trecho["inicio"]:trecho["fim"]] == trecho["citacao"]
    assert segundos < config.LLM_TIMEOUT_SEGUNDOS


def test_avaliacao_real_do_rewrite():
    itens = [
        {"indice": 0, "categoria": "gramatica", "explicacao": "O verbo não concorda com o sujeito.",
         "instrucao": "Revise a concordância verbal.", "frase": "They gives up their dreams.",
         "reescrita": "They give up their dreams."},
        {"indice": 1, "categoria": "vocabulario", "explicacao": "Forma errada da palavra.",
         "instrucao": "Use o adjetivo correto.", "frase": "The country will be more develop.",
         "reescrita": "The country develop more."},
    ]
    inicio = time.monotonic()
    resultado = writing_llm.avaliar_reescritas(enunciado=TEMA, itens=itens)
    segundos = time.monotonic() - inicio

    print(f"\n[{config.LLM_MODELO}] rewrite (2 frases): {segundos:.1f} s, "
          f"melhorou: {[resultado.avaliacoes[i]['melhorou'] for i in (0, 1)]}")
    assert set(resultado.avaliacoes) == {0, 1}
    assert resultado.avaliacoes[0]["melhorou"] is True  # correção óbvia
    assert segundos < config.LLM_TIMEOUT_SEGUNDOS
