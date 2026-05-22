"""
odds.py — dealer-bust probabilities for 6-deck H17 blackjack.

Pure data + a single lookup. Values come from the canonical Wizard of Odds
dealer-outcome table for "dealer hits soft 17, 6 decks." They are pinned by
backend/tests/test_odds.py because Chipy's narration cites them verbatim.

This module has no dependencies on SQLAlchemy, the request lifecycle, or
the strategy engine — it's a fact table and one helper.
"""
from __future__ import annotations

# Keyed by the same face-value strings the rest of the codebase uses
# (see backend/game/blackjack/engine.py::card_rank). 10/J/Q/K all share the
# same bust % because they all play as a 10-value upcard.
_DEALER_BUST_PCT: dict[str, float] = {
    "2": 0.35,
    "3": 0.37,
    "4": 0.40,
    "5": 0.42,
    "6": 0.42,
    "7": 0.26,
    "8": 0.24,
    "9": 0.23,
    "10": 0.23,
    "J": 0.23,
    "Q": 0.23,
    "K": 0.23,
    "A": 0.17,
}


def dealer_bust_pct(upcard: dict) -> float:
    """Probability the dealer busts given this upcard.

    Args:
        upcard: A card dict, e.g. {"suit": "hearts", "value": "6"}. Only
            the "value" key is read.

    Returns:
        A float in [0.0, 1.0].

    Raises:
        KeyError: if ``upcard["value"]`` is not a recognized rank.
    """
    return _DEALER_BUST_PCT[upcard["value"]]
