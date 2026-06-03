"""
test_pai_gow_cards.py — unit tests for backend/game/pai_gow/cards.py.

Covers deck construction (52 + joker), joker representation, dealing,
shuffle determinism, and the sort-key + rank helpers used by the evaluator
and the canonical-form hash (spec §12.4).
"""
from __future__ import annotations

import pytest

from backend.game.pai_gow.cards import (
    JOKER,
    SUITS,
    VALUES,
    card_rank,
    card_sort_key,
    create_deck,
    deal_card,
    deal_cards,
    is_joker,
    shuffle_deck,
)


# ─── Deck construction ───────────────────────────────────────────────────────


def test_create_deck_has_53_cards_with_joker():
    assert len(create_deck()) == 53


def test_create_deck_has_52_cards_without_joker():
    assert len(create_deck(with_joker=False)) == 52


def test_create_deck_contains_every_suit_value_pair():
    deck = create_deck()
    suited = [c for c in deck if c["suit"] != "joker"]
    expected = {(s, v) for s in SUITS for v in VALUES}
    actual = {(c["suit"], c["value"]) for c in suited}
    assert actual == expected


def test_create_deck_includes_joker_sentinel():
    deck = create_deck()
    jokers = [c for c in deck if c["suit"] == "joker"]
    assert len(jokers) == 1
    assert jokers[0] == JOKER


def test_create_deck_returns_independent_lists():
    """Each create_deck() call returns a fresh list — mutating one doesn't
    affect another (matters for the round.deck_state pattern in §9.2)."""
    a = create_deck()
    b = create_deck()
    a.pop()
    assert len(b) == 53


# ─── Joker detection ─────────────────────────────────────────────────────────


def test_is_joker_true_for_joker_sentinel():
    assert is_joker(JOKER) is True
    assert is_joker({"suit": "joker", "value": "JK"}) is True


def test_is_joker_false_for_regular_cards():
    assert is_joker({"suit": "hearts", "value": "A"}) is False
    assert is_joker({"suit": "spades", "value": "2"}) is False


# ─── card_rank ───────────────────────────────────────────────────────────────


def test_card_rank_returns_2_to_14_for_regular_cards():
    assert card_rank({"suit": "hearts", "value": "2"}) == 2
    assert card_rank({"suit": "hearts", "value": "10"}) == 10
    assert card_rank({"suit": "hearts", "value": "J"}) == 11
    assert card_rank({"suit": "hearts", "value": "Q"}) == 12
    assert card_rank({"suit": "hearts", "value": "K"}) == 13
    assert card_rank({"suit": "hearts", "value": "A"}) == 14


def test_card_rank_joker_returns_ace_value():
    """Default semi-wild role is Ace (spec §7.1)."""
    assert card_rank(JOKER) == 14


# ─── card_sort_key (canonical-form contract — spec §12.4) ────────────────────


def test_card_sort_key_descending_by_rank():
    cards = [
        {"suit": "hearts", "value": "5"},
        {"suit": "hearts", "value": "K"},
        {"suit": "hearts", "value": "2"},
    ]
    cards.sort(key=card_sort_key)
    assert [c["value"] for c in cards] == ["K", "5", "2"]


def test_card_sort_key_same_rank_orders_by_suit_clubs_first():
    """Suit order: clubs < diamonds < hearts < spades (spec §12.4)."""
    cards = [
        {"suit": "spades", "value": "K"},
        {"suit": "clubs", "value": "K"},
        {"suit": "hearts", "value": "K"},
        {"suit": "diamonds", "value": "K"},
    ]
    cards.sort(key=card_sort_key)
    assert [c["suit"] for c in cards] == ["clubs", "diamonds", "hearts", "spades"]


# ─── Deal ────────────────────────────────────────────────────────────────────


def test_deal_card_returns_top_and_remaining():
    deck = create_deck()
    expected_top = deck[-1]
    card, remaining = deal_card(deck)
    assert card == expected_top
    assert len(remaining) == 52


def test_deal_card_does_not_mutate_input():
    deck = create_deck()
    original_len = len(deck)
    deal_card(deck)
    assert len(deck) == original_len


def test_deal_card_empty_raises():
    with pytest.raises(IndexError):
        deal_card([])


def test_deal_cards_n_returns_correct_count():
    deck = create_deck()
    dealt, remaining = deal_cards(deck, 7)
    assert len(dealt) == 7
    assert len(remaining) == 46


def test_deal_cards_zero_is_noop():
    deck = create_deck()
    dealt, remaining = deal_cards(deck, 0)
    assert dealt == []
    assert len(remaining) == 53


def test_deal_cards_too_many_raises():
    deck = create_deck()
    with pytest.raises(IndexError):
        deal_cards(deck, 100)


def test_deal_cards_n_does_not_mutate_input():
    deck = create_deck()
    deal_cards(deck, 7)
    assert len(deck) == 53


def test_deal_cards_negative_raises():
    with pytest.raises(ValueError):
        deal_cards(create_deck(), -1)


# ─── Shuffle determinism (matters for AC-T-demo-prep seeded fixtures) ────────


def test_shuffle_deck_same_seed_same_result():
    a = shuffle_deck(create_deck(), seed=42)
    b = shuffle_deck(create_deck(), seed=42)
    assert a == b


def test_shuffle_deck_different_seed_different_result():
    a = shuffle_deck(create_deck(), seed=1)
    b = shuffle_deck(create_deck(), seed=2)
    assert a != b


def test_shuffle_deck_preserves_card_count():
    deck = create_deck()
    shuffled = shuffle_deck(deck, seed=42)
    assert len(shuffled) == len(deck)


def test_shuffle_deck_preserves_card_multiset():
    deck = create_deck()
    shuffled = shuffle_deck(deck, seed=42)
    deck_set = frozenset((c["suit"], c["value"]) for c in deck)
    shuffled_set = frozenset((c["suit"], c["value"]) for c in shuffled)
    assert deck_set == shuffled_set


def test_shuffle_deck_does_not_mutate_input():
    deck = create_deck()
    deck_copy = list(deck)
    shuffle_deck(deck, seed=42)
    assert deck == deck_copy
