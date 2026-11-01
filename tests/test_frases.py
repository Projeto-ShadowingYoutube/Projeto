from types import SimpleNamespace

import pytest

from app.services.frases import segmentar_frases


def blocos(*dados):
    return [SimpleNamespace(text=t, start=s, duration=d) for t, s, d in dados]


def textos(frases):
    return [f["texto_limpo"] for f in frases]


def test_junta_blocos_ate_o_fim_da_sentenca():
    frases = segmentar_frases(blocos(
        ("Now, I imagine the coordinates", 0.0, 2.0),
        ("were already familiar.", 2.0, 2.0),
        ("Next sentence here.", 4.0, 2.0),
    ))
    assert textos(frases) == ["Now, I imagine the coordinates were already familiar.", "Next sentence here."]
    assert (frases[0]["tempo_inicio"], frases[0]["tempo_fim"]) == (0.0, 4.0)


def test_frase_curta_e_juntada_a_seguinte_sem_perder_texto():
    frases = segmentar_frases(blocos(("Yes.", 0.0, 0.5), ("Let's go.", 0.6, 1.5)))
    assert textos(frases) == ["Yes. Let's go."]


def test_pausa_longa_fecha_a_frase_mesmo_sem_pontuacao():
    frases = segmentar_frases(blocos(("so this is the idea", 0.0, 2.0), ("and then we move on", 3.0, 2.0)))
    assert textos(frases) == ["so this is the idea", "and then we move on"]


def test_frase_longa_e_quebrada_na_virgula():
    frases = segmentar_frases(blocos(
        ("When you have a pair of numbers,", 0.0, 3.0),
        ("that is meant to describe", 3.0, 3.0),
        ("a vector in the plane.", 6.0, 3.0),
    ))
    assert textos(frases) == ["When you have a pair of numbers,", "that is meant to describe a vector in the plane."]
    assert all(f["tempo_fim"] - f["tempo_inicio"] <= 8.0 for f in frases)


def test_remove_ruido_e_repeticoes_seguidas():
    frases = segmentar_frases(blocos(
        ("[Music]", 0.0, 2.0),
        (">> Hello there.", 2.0, 2.0),
        ("Hello there.", 4.0, 1.0),
        ("♪ la la ♪ Goodbye.", 6.0, 2.0),
    ))
    assert textos(frases) == ["Hello there.", "la la Goodbye."]
    assert frases[0]["tempo_fim"] == 5.0


def test_sobreposicao_de_legenda_automatica_e_removida():
    frases = segmentar_frases(blocos(("first part of speech", 0.0, 4.0), ("second part", 2.5, 3.0)))
    assert frases[0]["tempo_fim"] <= 2.5 or len(frases) == 1
    assert all(a["tempo_fim"] <= b["tempo_inicio"] for a, b in zip(frases, frases[1:]))


def test_tempos_das_palavras_acompanham_o_texto():
    frases = segmentar_frases(blocos(("Hello there, my friend.", 1.0, 2.0), ("How are you?", 3.2, 1.0)))
    for frase in frases:
        tempos = frase["tempos_palavras"]
        assert len(tempos) == len(frase["texto_limpo"].split())
        assert tempos[0][0] == 0
        assert tempos[-1][1] == pytest.approx(frase["tempo_fim"] - frase["tempo_inicio"], abs=0.01)
        assert all(inicio < fim for inicio, fim in tempos)
    # Palavra longa demora mais que palavra curta.
    hello, there, my, friend = frases[0]["tempos_palavras"]
    assert friend[1] - friend[0] > my[1] - my[0]
