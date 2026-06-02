"""backend.game.pai_gow.cards — card representation and deck for Pai Gow.

53-card deck (52 standard + 1 joker). Joker uses the sentinel
`{"suit": "joker", "value": "JK"}`. See spec §7.1 for joker semantics
and §12.4 for the canonical-form contract that uses `card_sort_key`.

All functions are pure (no DB, no implicit random state — `shuffle_deck`
takes an explicit seed).
"""
from __future__ import annotations

import random
from typing import Optional

# Card is just a dict matching CLAUDE.md rule 2 — kept as `dict` rather than
# a TypedDict so existing JSON-column reads round-trip without conversion.
Card = dict

SUITS: tuple[str, ...] = ("hearts", "diamonds", "clubs", "spades")
VALUES: tuple[str, ...] = ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")

JOKER: Card = {"suit": "joker", "value": "JK"}

# Rank ordering used by evaluator + canonical-form (spec §12.4).
RANK_ORDER: dict[str, int] = {
    "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
    "10": 10, "J": 11, "Q": 12, "K": 13, "A": 14,
}
# Suit ordering for canonical sort (spec §12.4 — clubs < diamonds < hearts < spades).
SUIT_ORDER: dict[str, int] = {
    "clubs": 1, "diamonds": 2, "hearts": 3, "spades": 4,
}


def is_joker(card: Card) -> bool:
    """True if the card is the joker sentinel."""
    return card.get("suit") == "joker"


def card_rank(card: Card) -> int:
    """Numeric rank, A=14 (high). Joker returns 14 (semi-wild default = Ace).

    The evaluator uses this for hand scoring; the canonical form uses it for
    rank-sort before suit relabeling (spec §12.4).
    """
    if is_joker(card):
        return 14
    return RANK_ORDER[card["value"]]


def card_sort_key(card: Card) -> tuple[int, int]:
    """Sort key producing canonical order: rank descending, suit ascending.

    The negative rank gives descending order under Python's natural sort.
    Joker is sorted ABOVE Ace as a defensive measure — in canonical_form
    (canonical.py) the joker is extracted before sorting, so this only
    matters if a joker leaks into the sort by accident.
    """
    if is_joker(card):
        return (-15, 0)
    return (-card_rank(card), SUIT_ORDER[card["suit"]])


def create_deck(with_joker: bool = True) -> list[Card]:
    """Create a fresh 53-card deck (52 + joker by default).

    Returns a new list each call — safe to mutate. Order is suit-major then
    rank-ascending; use `shuffle_deck` to randomize.
    """
    deck: list[Card] = []
    for suit in SUITS:
        for value in VALUES:
            deck.append({"suit": suit, "value": value})
    if with_joker:
        deck.append(dict(JOKER))
    return deck


def shuffle_deck(deck: list[Card], seed: Optional[int] = None) -> list[Card]:
    """Return a shuffled copy of `deck`. Does NOT mutate input.

    If `seed` is provided, the shuffle is deterministic — useful for tests
    and the demo-prep seeded qualifying-hand fixture (AC-T-demo-prep).
    """
    out = list(deck)
    rng = random.Random(seed)
    rng.shuffle(out)
    return out


def deal_card(deck: list[Card]) -> tuple[Card, list[Card]]:
    """Pop the top card (last element) off the deck.

    Returns `(card, remaining_deck)`. Does NOT mutate input — returns a new
    list for `remaining`. Raises `IndexError` if `deck` is empty.
    """
    if not deck:
        raise IndexError("Cannot deal from empty deck")
    return deck[-1], list(deck[:-1])


def deal_cards(deck: list[Card], n: int) -> tuple[list[Card], list[Card]]:
    """Deal `n` cards from the top of `deck`. Returns `(dealt, remaining)`.

    `dealt` is the slice `deck[-n:]` (top n in their original deck order).
    Does NOT mutate input. Raises `ValueError` on negative `n`, `IndexError`
    if `n` exceeds deck size.
    """
    if n < 0:
        raise ValueError("n must be non-negative")
    if n > len(deck):
        raise IndexError(f"Cannot deal {n} cards from a deck of {len(deck)}")
    if n == 0:
        return [], list(deck)
    return list(deck[-n:]), list(deck[:-n])
