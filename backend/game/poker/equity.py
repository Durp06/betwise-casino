"""
equity.py — Monte-Carlo hand equity for Texas Hold'em.

Estimates a hero hand's win / tie / lose probability versus N random opponent
hands by simulating the rest of the deal and scoring with the existing
`best_5_of_7` evaluator. Pure (no DB / network); the RNG is seeded so the same
situation returns the same estimate (reproducible + testable).

Used by both the solo poker advice endpoint and the multiplayer Hold'em odds
endpoint so the on-felt odds graphic is identical across both games.
"""

from __future__ import annotations

import random
from typing import NamedTuple

from .cards import RANKS, SUITS, Card, remove_cards
from .evaluator import best_5_of_7, category_name, rank_hand

# Default simulation count — ~800 keeps the "Ask Chipy" round-trip snappy
# (<~1s even multiway) while holding the standard error near ±2%.
DEFAULT_ITERATIONS = 800
# Cap the simulated field; multiway equity past 5 villains is already tiny and
# the extra evaluations only slow the request.
MAX_SIM_OPPONENTS = 5


class EquityResult(NamedTuple):
    win: float
    tie: float
    lose: float


def _full_deck() -> list[Card]:
    return [{"suit": s, "value": v} for s in SUITS for v in RANKS]


def estimate_equity(
    hole: list[Card] | tuple[Card, ...],
    board: list[Card] | tuple[Card, ...],
    n_opponents: int,
    iterations: int = DEFAULT_ITERATIONS,
    seed: int = 1_234_567,
) -> EquityResult:
    """Monte-Carlo win/tie/lose probability for `hole` vs `n_opponents` random
    hands given the current `board` (0, 3, 4, or 5 cards).

    Tie counts a split pot as a partial loss conceptually but is reported
    separately so the UI can show win / tie / lose. Returns equal thirds-ish
    fallbacks only if inputs are unusable (handled by the caller, which should
    pass a valid 2-card hole)."""
    n_opp = max(1, min(int(n_opponents), MAX_SIM_OPPONENTS))
    hole = list(hole)
    board = list(board)
    if len(hole) != 2:
        raise ValueError("estimate_equity needs exactly 2 hole cards")
    if len(board) not in (0, 3, 4, 5):
        raise ValueError("board must have 0, 3, 4, or 5 cards")

    deck = remove_cards(_full_deck(), hole + board)
    need_board = 5 - len(board)
    draw = need_board + 2 * n_opp
    rng = random.Random(seed)

    wins = ties = 0
    for _ in range(iterations):
        sample = rng.sample(deck, draw)
        full_board = board + sample[:need_board]
        hero = best_5_of_7(hole + full_board).cmp_key()
        idx = need_board
        best_opp = None
        for _k in range(n_opp):
            opp = best_5_of_7(sample[idx : idx + 2] + full_board).cmp_key()
            idx += 2
            if best_opp is None or opp > best_opp:
                best_opp = opp
        if hero > best_opp:  # type: ignore[operator]
            wins += 1
        elif hero == best_opp:
            ties += 1

    win = wins / iterations
    tie = ties / iterations
    return EquityResult(win=round(win, 4), tie=round(tie, 4), lose=round(1.0 - win - tie, 4))


def made_hand_name(hole: list[Card] | tuple[Card, ...], board: list[Card] | tuple[Card, ...]) -> str | None:
    """The hero's CURRENT best 5-card hand name (e.g. 'two pair'), or None
    preflop / before a hand is made (need ≥3 board cards)."""
    hole = list(hole)
    board = list(board)
    if len(board) < 3 or len(hole) != 2:
        return None
    return category_name(rank_hand(hole, board))


def hand_odds(
    hole: list[Card] | tuple[Card, ...],
    board: list[Card] | tuple[Card, ...],
    pot: float,
    to_call: float,
    n_opponents: int,
    street: str,
    iterations: int = DEFAULT_ITERATIONS,
) -> dict:
    """Assemble the on-felt odds payload (shape matches schemas.PokerOddsOut).

    `pot` and `to_call` are passed straight to required_equity — units cancel
    (bb or chips both work) since the result is a ratio. Used by both the solo
    poker advice endpoint and the multiplayer Hold'em odds endpoint.
    """
    from .pot_odds import required_equity  # noqa: PLC0415

    eq = estimate_equity(hole, board, n_opponents, iterations=iterations)
    pot_odds = required_equity(pot, to_call) if to_call and to_call > 0 else 0.0
    return {
        "win_pct": eq.win,
        "tie_pct": eq.tie,
        "lose_pct": eq.lose,
        "pot_odds_pct": round(float(pot_odds), 4),
        "made_hand": made_hand_name(hole, board),
        "n_opponents": max(1, int(n_opponents)),
        "street": street,
    }
