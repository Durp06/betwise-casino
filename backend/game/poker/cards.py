"""
cards.py — pure card primitives for Texas Hold'em.

Design constraints (specs/texas-holdem.md §AC-B1):
- Card wire format mirrors blackjack: {"suit": "hearts"|..., "value": "2"-"10"|"J"|"Q"|"K"|"A"}.
- Internal rank int: 2-14 (Ace = 14). Wheel handling lives in the evaluator.
- create_deck(seed) is reproducible: same seed → identical order.
- deal does not mutate its input.
- All functions pure (no DB, no network).
"""

from __future__ import annotations

import random
from typing import TypedDict


# ─── Card type ────────────────────────────────────────────────────────────────


class Card(TypedDict):
    suit: str
    value: str


SUITS: tuple[str, ...] = ("hearts", "diamonds", "clubs", "spades")
RANKS: tuple[str, ...] = ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")


# Internal rank int mapping. Ace = 14 normally; the evaluator handles A-2-3-4-5
# (wheel) as a straight by ALSO treating A as rank 1 inside the straight check.
_RANK_INT: dict[str, int] = {
    "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
    "10": 10, "J": 11, "Q": 12, "K": 13, "A": 14,
}


def rank_int(card: Card) -> int:
    """Return the numeric rank of a card (2-14, ace = 14)."""
    return _RANK_INT[card["value"]]


def rank_str_to_int(value: str) -> int:
    """Convenience: convert a rank-string '2'..'A' → its int."""
    return _RANK_INT[value]


def rank_int_to_str(rank: int) -> str:
    """Inverse of rank_str_to_int. Raises ValueError for out-of-range."""
    for s, v in _RANK_INT.items():
        if v == rank:
            return s
    raise ValueError(f"No rank string for rank int {rank}")


# ─── Deck factory + shuffle ───────────────────────────────────────────────────


def create_deck(seed: int | None = None) -> list[Card]:
    """Return a freshly shuffled 52-card deck.

    With a seed, the shuffle is deterministic — same seed → same order.
    Without a seed, the shuffle is random.

    Uses Python's stdlib Mersenne-Twister via `random.Random(seed)`, which
    `random.shuffle` implements as Fisher-Yates (Durstenfeld). Pinning the
    seed pins the entire hand: board cards, hole cards, and (via the
    archetype RNG) the bot decisions.
    """
    deck: list[Card] = [
        {"suit": suit, "value": value}
        for suit in SUITS
        for value in RANKS
    ]
    rng = random.Random(seed)
    rng.shuffle(deck)
    return deck


def shuffle(deck: list[Card], seed: int | None = None) -> list[Card]:
    """Return a new shuffled copy of `deck`. Does NOT mutate the input."""
    out = list(deck)
    random.Random(seed).shuffle(out)
    return out


def deal(deck: list[Card], n: int = 1) -> tuple[list[Card], list[Card]]:
    """Pop n cards from the top of the deck.

    Returns (dealt_cards, remaining_deck). Does NOT mutate the input.
    Raises ValueError if the deck has fewer than n cards.
    """
    if len(deck) < n:
        raise ValueError(f"Cannot deal {n} cards from a deck of {len(deck)}")
    dealt = deck[:n]
    remaining = deck[n:]
    return dealt, remaining


# ─── Helpers ──────────────────────────────────────────────────────────────────


def card_str(card: Card) -> str:
    """Compact display string: '9h', 'Th', 'Ad'. Useful for tests + logs."""
    suit_short = {"hearts": "h", "diamonds": "d", "clubs": "c", "spades": "s"}[card["suit"]]
    value_short = "T" if card["value"] == "10" else card["value"]
    return f"{value_short}{suit_short}"


def parse_card(s: str) -> Card:
    """Parse a compact card string ('9h', 'Th', 'Ad', '10h' also accepted)."""
    if s.startswith("10"):
        value, suit_short = "10", s[2:]
    else:
        value_char, suit_short = s[0], s[1:]
        value = "10" if value_char == "T" else value_char
    suit = {"h": "hearts", "d": "diamonds", "c": "clubs", "s": "spades"}[suit_short]
    if value not in RANKS:
        raise ValueError(f"Unknown rank in card string {s!r}")
    return {"suit": suit, "value": value}


def remove_cards(deck: list[Card], cards: list[Card]) -> list[Card]:
    """Return a new deck with the specified cards removed (by suit + value match)."""
    keys = {(c["suit"], c["value"]) for c in cards}
    return [c for c in deck if (c["suit"], c["value"]) not in keys]
