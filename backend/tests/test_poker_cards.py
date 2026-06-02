"""
test_poker_cards.py — covers AC-B1 from specs/texas-holdem.md.

The card primitives are pure and stdlib-only, so these tests run fast and
serve as a smoke check for the whole `backend.game.poker` package import.
"""
from __future__ import annotations

import pytest

from backend.game.poker import cards
from backend.game.poker.cards import (
    RANKS,
    SUITS,
    Card,
    card_str,
    create_deck,
    deal,
    parse_card,
    rank_int,
    remove_cards,
    shuffle,
)


def test_module_imports_clean() -> None:
    """Importing the poker package should not raise."""
    from backend.game import poker  # noqa: F401, PLC0415

    assert poker.GAME_TYPE == "poker"


def test_create_deck_has_52_distinct_cards() -> None:
    deck = create_deck()
    assert len(deck) == 52
    keys = {(c["suit"], c["value"]) for c in deck}
    assert len(keys) == 52


def test_create_deck_all_suits_and_ranks_present() -> None:
    deck = create_deck()
    for suit in SUITS:
        for value in RANKS:
            assert {"suit": suit, "value": value} in deck


def test_create_deck_seeded_is_reproducible() -> None:
    d1 = create_deck(seed=42)
    d2 = create_deck(seed=42)
    assert d1 == d2


def test_create_deck_different_seeds_produce_different_orders() -> None:
    d1 = create_deck(seed=1)
    d2 = create_deck(seed=2)
    assert d1 != d2


def test_create_deck_no_seed_is_random_likely_different() -> None:
    d1 = create_deck()
    d2 = create_deck()
    # Two unseeded shuffles being identical has probability ~1/52! — vanishingly
    # small. If this ever flakes you've found a bug.
    assert d1 != d2


def test_shuffle_does_not_mutate_input() -> None:
    deck = create_deck(seed=7)
    snapshot = list(deck)
    _ = shuffle(deck, seed=99)
    assert deck == snapshot


def test_deal_returns_correct_split() -> None:
    deck = create_deck(seed=5)
    dealt, remaining = deal(deck, n=2)
    assert len(dealt) == 2
    assert len(remaining) == 50
    assert dealt + remaining == deck


def test_deal_does_not_mutate_input() -> None:
    deck = create_deck(seed=5)
    snapshot = list(deck)
    _ = deal(deck, n=5)
    assert deck == snapshot


def test_deal_raises_when_insufficient_cards() -> None:
    deck = create_deck()[:3]
    with pytest.raises(ValueError):
        deal(deck, n=5)


def test_rank_int_table() -> None:
    cases: list[tuple[str, int]] = [
        ("2", 2), ("3", 3), ("4", 4), ("5", 5), ("6", 6),
        ("7", 7), ("8", 8), ("9", 9), ("10", 10),
        ("J", 11), ("Q", 12), ("K", 13), ("A", 14),
    ]
    for value, expected in cases:
        c: Card = {"suit": "hearts", "value": value}
        assert rank_int(c) == expected


def test_card_str_roundtrip() -> None:
    for v in ("2", "5", "9", "10", "J", "Q", "K", "A"):
        for suit in SUITS:
            c: Card = {"suit": suit, "value": v}
            roundtrip = parse_card(card_str(c))
            assert roundtrip == c


def test_remove_cards_removes_by_value_match() -> None:
    deck = create_deck()
    to_remove: list[Card] = [
        {"suit": "hearts", "value": "A"},
        {"suit": "spades", "value": "K"},
    ]
    reduced = remove_cards(deck, to_remove)
    assert len(reduced) == 50
    for c in to_remove:
        assert c not in reduced


def test_remove_cards_does_not_mutate_input() -> None:
    deck = create_deck()
    snapshot = list(deck)
    _ = remove_cards(deck, [{"suit": "hearts", "value": "A"}])
    assert deck == snapshot
