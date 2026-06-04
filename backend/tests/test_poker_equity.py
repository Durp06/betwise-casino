"""Tests for the Monte-Carlo hand-equity engine + odds payload."""

from __future__ import annotations

from backend.game.poker.cards import parse_card
from backend.game.poker.equity import estimate_equity, hand_odds, made_hand_name


def _cards(*ss: str) -> list:
    return [parse_card(s) for s in ss]


def test_pocket_aces_heads_up_preflop_is_strong_favorite() -> None:
    eq = estimate_equity(_cards("As", "Ah"), [], 1)
    assert 0.80 <= eq.win <= 0.90, eq
    assert abs((eq.win + eq.tie + eq.lose) - 1.0) < 1e-6


def test_made_nut_flush_is_near_certain() -> None:
    eq = estimate_equity(_cards("Ah", "Kh"), _cards("Qh", "7h", "2h"), 1)
    assert eq.win >= 0.95, eq


def test_equity_is_deterministic_for_same_situation() -> None:
    a = estimate_equity(_cards("Ks", "Qd"), _cards("Jh", "Tc", "2s"), 2)
    b = estimate_equity(_cards("Ks", "Qd"), _cards("Jh", "Tc", "2s"), 2)
    assert a == b  # seeded RNG → reproducible


def test_made_hand_name_postflop_and_none_preflop() -> None:
    assert made_hand_name(_cards("8h", "8d"), _cards("8s", "Kd", "2c")) == "three of a kind"
    assert made_hand_name(_cards("8h", "8d"), []) is None


def test_hand_odds_payload_shape_and_pot_odds() -> None:
    # pot=100, to_call=50 → required_equity = 50/(100+50+50) = 0.25
    odds = hand_odds(_cards("As", "Ah"), [], pot=100, to_call=50, n_opponents=1, street="preflop")
    assert set(odds) == {
        "win_pct", "tie_pct", "lose_pct", "pot_odds_pct", "made_hand", "n_opponents", "street",
    }
    assert odds["pot_odds_pct"] == 0.25
    assert odds["n_opponents"] == 1
    assert odds["street"] == "preflop"
    assert odds["made_hand"] is None  # preflop
    assert 0.0 <= odds["win_pct"] <= 1.0


def test_hand_odds_no_bet_to_call_is_zero_pot_odds() -> None:
    odds = hand_odds(_cards("As", "Ah"), _cards("Kd", "7c", "2h"), pot=80, to_call=0, n_opponents=1, street="flop")
    assert odds["pot_odds_pct"] == 0.0
