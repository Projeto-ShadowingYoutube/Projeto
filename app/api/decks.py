"""Rotas de Decks (baralhos) e Cards, incluindo a revisão espaçada."""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session

from app.db import get_session
from app.models import Card, Deck, agora
from app.schemas import AvaliacaoCard, CardParaRevisar, DeckSalvo, NomeDeck, NovoCard, ResumoDeck, RevisaoSalva
from app.services import decks

router = APIRouter(prefix="/api", tags=["decks"])


def _deck(deck_id: int, session: Session = Depends(get_session)) -> Deck:
    deck = session.get(Deck, deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck não encontrado.")
    return deck


def _card(card_id: int, session: Session = Depends(get_session)) -> Card:
    card = session.get(Card, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card não encontrado.")
    return card


def _salvar(session: Session, objeto):
    session.add(objeto)
    session.commit()
    session.refresh(objeto)
    return objeto


@router.get("/decks", response_model=list[ResumoDeck])
def listar_decks(session: Session = Depends(get_session)):
    return decks.resumo_dos_decks(session)


@router.post("/decks", response_model=DeckSalvo, status_code=status.HTTP_201_CREATED)
def criar_deck(corpo: NomeDeck, session: Session = Depends(get_session)):
    return _salvar(session, Deck(nome=decks.nome_unico(session, corpo.nome)))


@router.patch("/decks/{deck_id}", response_model=DeckSalvo)
def renomear_deck(corpo: NomeDeck, deck: Deck = Depends(_deck), session: Session = Depends(get_session)):
    deck.nome = decks.nome_unico(session, corpo.nome, ignorar_id=deck.id)
    return _salvar(session, deck)


@router.delete("/decks/{deck_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_deck(deck: Deck = Depends(_deck), session: Session = Depends(get_session)):
    session.delete(deck)  # os Cards vão junto (cascade)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/decks/{deck_id}/cards", status_code=status.HTTP_201_CREATED)
def salvar_card(corpo: NovoCard, deck: Deck = Depends(_deck), session: Session = Depends(get_session)):
    if decks.card_repetido(session, deck.id, corpo.texto_legenda):
        raise HTTPException(status_code=409, detail="Este card já foi salvo anteriormente nesse Deck.")
    card = _salvar(session, Card(**corpo.model_dump(), deck_id=deck.id))
    return {"id": card.id}


@router.get("/decks/{deck_id}/revisao", response_model=list[CardParaRevisar])
def cards_para_revisar(deck: Deck = Depends(_deck), session: Session = Depends(get_session)):
    """Cards do Deck que precisam de revisão agora: os novos e os com data de revisão vencida."""
    return decks.cards_para_revisar(session, deck.id)


@router.post("/cards/{card_id}/avaliacao", response_model=RevisaoSalva)
def avaliar_card(corpo: AvaliacaoCard, card: Card = Depends(_card), session: Session = Depends(get_session)):
    card.data_proxima_revisao = decks.proxima_revisao(corpo.dificuldade, card.revisao, agora())
    card.revisao += 1
    _salvar(session, card)
    return {
        "card_id": card.id,
        "nova_revisao": card.data_proxima_revisao.isoformat(),
        "numero_revisoes": card.revisao,
    }


@router.delete("/cards/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_card(card: Card = Depends(_card), session: Session = Depends(get_session)):
    session.delete(card)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
