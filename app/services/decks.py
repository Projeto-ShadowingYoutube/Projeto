"""Regras dos Decks e Cards: nomes sem repetição, contagens do dashboard e revisão espaçada."""
from datetime import datetime, timedelta

from sqlmodel import Session, col, or_, select

from app.models import Card, Deck, agora

# Intervalo base até a próxima revisão, em dias. Ele dobra a cada revisão já feita no Card (até 180 dias).
DIAS_POR_DIFICULDADE = {"dificil": 1, "medio": 3, "facil": 7}
INTERVALO_MAXIMO_DIAS = 180


def nome_unico(session: Session, usuario_id: int, nome: str, ignorar_id: int | None = None) -> str:
    """Evita nomes repetidos entre os Decks do usuário: "Baralho", "Baralho (2)"... Nome vazio vira "Deck"."""
    base = nome.strip() or "Deck"
    consulta = select(Deck.nome).where(
        Deck.usuario_id == usuario_id, col(Deck.nome).startswith(base, autoescape=True),
    )
    if ignorar_id is not None:
        consulta = consulta.where(Deck.id != ignorar_id)
    existentes = set(session.exec(consulta).all())

    if base not in existentes:
        return base
    contador = 2
    while f"{base} ({contador})" in existentes:
        contador += 1
    return f"{base} ({contador})"


def resumo_dos_decks(session: Session, usuario_id: int) -> list[dict]:
    """Cada Deck do usuário com as contagens do dashboard (Cards novos, a revisar e total) e a data da próxima
    revisão agendada (a mais próxima entre os Cards já revisados; None se nenhum foi revisado). Ela permite à página
    de revisão dizer "tudo revisado, próxima em 2 dias" em vez de uma tela vazia (B12)."""
    momento = agora()
    cards_por_deck: dict[int, list[Card]] = {}
    cards_do_usuario = select(Card).join(Deck).where(Deck.usuario_id == usuario_id)
    for card in session.exec(cards_do_usuario).all():
        cards_por_deck.setdefault(card.deck_id, []).append(card)

    resumo = []
    for deck in session.exec(select(Deck).where(Deck.usuario_id == usuario_id).order_by(Deck.id)).all():
        cards = cards_por_deck.get(deck.id, [])
        agendadas = [c.data_proxima_revisao for c in cards if c.revisao > 0]
        resumo.append({
            "id": deck.id,
            "nome": deck.nome,
            "novos": sum(1 for c in cards if c.revisao == 0),
            "revisar": sum(1 for c in cards if c.revisao > 0 and c.data_proxima_revisao <= momento),
            "quantidade_total": len(cards),
            "proxima_revisao": min(agendadas) if agendadas else None,
        })
    return resumo


def card_repetido(session: Session, deck_id: int, texto: str) -> bool:
    consulta = select(Card.id).where(Card.deck_id == deck_id, Card.texto_legenda == texto)
    return session.exec(consulta).first() is not None


def cards_para_revisar(session: Session, deck_id: int) -> list[Card]:
    """Os Cards novos e os com data de revisão vencida."""
    consulta = (
        select(Card)
        .where(Card.deck_id == deck_id)
        .where(or_(Card.revisao == 0, Card.data_proxima_revisao <= agora()))
        .order_by(Card.id)
    )
    return list(session.exec(consulta).all())


def proxima_revisao(dificuldade: str, revisoes_feitas: int, momento: datetime) -> datetime:
    dias = min(DIAS_POR_DIFICULDADE[dificuldade] * 2 ** revisoes_feitas, INTERVALO_MAXIMO_DIAS)
    return momento + timedelta(days=dias)
