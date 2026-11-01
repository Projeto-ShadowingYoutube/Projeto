import numpy as np
import pytest

from app.services import avaliacao

TAXA = avaliacao.TAXA


def voz(frequencias, duracao=1.5):
    """Sinal com harmônicos (parecido com voz) cuja altura vai de frequencias[0] a frequencias[-1]."""
    t = np.arange(int(duracao * TAXA)) / TAXA
    f0 = np.interp(t, np.linspace(0, duracao, len(frequencias)), frequencias)
    fase = 2 * np.pi * np.cumsum(f0) / TAXA
    return (0.5 * np.sin(fase) + 0.25 * np.sin(2 * fase) + 0.1 * np.sin(3 * fase)).astype(np.float32)


def test_palavras_ditas_e_faltando():
    resultado = avaliacao.avaliar_palavras("So it's worth making sure.".split(), "so its worth sure".split())
    assert resultado["ditas"] == [True, True, True, False, True]
    assert resultado["nota"] == 80


def test_ritmo_ignora_a_velocidade_mas_nao_as_pausas():
    original = [0.0, 0.3, 0.6, 0.9, 1.2]
    assert avaliacao.avaliar_ritmo(original, original)["nota"] == 100
    # Tudo 50% mais lento: mesma distribuição do tempo.
    assert avaliacao.avaliar_ritmo(original, [t * 1.5 for t in original])["nota"] == 100
    # Uma pausa longa depois da 2ª palavra.
    com_pausa = avaliacao.avaliar_ritmo(original, [0.0, 0.3, 1.6, 1.9, 2.2])["nota"]
    assert com_pausa < 60
    # Palavras não ditas ficam de fora; com menos de 3, não dá para avaliar.
    assert avaliacao.avaliar_ritmo(original, [0.0, None, None, None, 1.0]) is None


def test_curva_de_altura_mede_a_frequencia():
    curva = avaliacao.curva_de_altura(voz([200, 200]))
    assert np.nanmedian(curva) == pytest.approx(200, rel=0.03)
    assert np.isnan(avaliacao.curva_de_altura(np.zeros(TAXA, dtype=np.float32))).all()


def test_entonacao_compara_a_melodia_e_nao_a_altura_da_voz():
    sobe = voz([150, 250])
    # Mesma melodia (mesmo intervalo) numa voz mais aguda e num ritmo mais lento: nota alta.
    parecida = avaliacao.avaliar_entonacao(sobe, voz([250, 416], duracao=2.2))
    assert parecida["nota"] >= 90
    # Melodia contrária: nota zero.
    assert avaliacao.avaliar_entonacao(sobe, voz([250, 150]))["nota"] == 0


def test_entonacao_usa_as_palavras_como_ancoras():
    # O usuário fica parado no começo e depois faz a mesma subida mais rápido.
    original = voz([150, 150, 250, 250], duracao=2.0)
    usuario = voz([150, 150, 150, 250, 250], duracao=2.0)
    ancoras = [(0.1, 0.1), (0.6, 1.0), (1.4, 1.5), (1.9, 1.9)]
    com_ancoras = avaliacao.avaliar_entonacao(original, usuario, ancoras)["correlacao"]
    sem_ancoras = avaliacao.avaliar_entonacao(original, usuario)["correlacao"]
    assert com_ancoras > sem_ancoras


def test_rota_de_avaliacao(client, monkeypatch):
    recebido = {}

    async def falso(*argumentos):
        recebido["argumentos"] = argumentos
        return {"nota": 90, "palavras": {"nota": 100, "ditas": [True], "reconhecido": "hello"},
                "ritmo": None, "entonacao": None, "razao_velocidade": None}

    monkeypatch.setattr(avaliacao, "avaliar_gravacao", falso)
    campos = {"video_id": "fNk_zzaMoSs", "inicio": 1, "fim": 3, "texto": "hello", "transcricao": "hello",
              "offset": 0.2, "duracao": 1.5, "velocidade": 0.75}
    resposta = client.post("/api/avaliacoes", data=campos, files={"gravacao": ("g.webm", b"audio", "audio/webm")})

    assert resposta.status_code == 200
    assert resposta.json()["nota"] == 90
    assert recebido["argumentos"] == ("fNk_zzaMoSs", 1.0, 3.0, "hello", "hello", b"audio", 0.2, 1.5, 0.75)

    invalida = client.post("/api/avaliacoes", data={**campos, "fim": 0.5}, files={"gravacao": ("g.webm", b"a")})
    assert invalida.status_code == 400


def test_entonacao_desligada_nao_entra_na_nota(monkeypatch):
    monkeypatch.setattr(avaliacao.alinhamento, "reconhecer", lambda pcm, vocabulario=None: [])
    pcm = (voz([150, 250]) * 32767).astype(np.int16).tobytes()
    resultado = avaliacao.avaliar("hello world", "hello", pcm, pcm, [[0, 0.5], [0.5, 1]], 1.0)
    assert resultado["entonacao"] is None
    # Sem ritmo (nada alinhado) e sem entonação, a nota geral é a de palavras.
    assert resultado["nota"] == resultado["palavras"]["nota"] == 50
