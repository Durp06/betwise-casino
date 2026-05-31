"""
test_holdem_showdown.py — pure tests for the multiplayer Hold'em showdown
resolver (backend/game/poker/showdown.py). No DB; constructs BettingState
directly so side-pot scenarios are explicit.

Covers spec §AC-S1: category ordering, kickers, split pots, side-pot
eligibility (folded seats contribute but can't win), and play-the-board chops.
"""

from __future__ import annotations

from backend.game.poker.showdown import decide_winners_per_pot
from backend.game.poker.state import (
    BettingState,
    Seat,
    award_pots,
    compute_side_pots,
    total_chips_in_play,
)


def _card(value: str, suit: str) -> dict:
    return {"suit": suit, "value": value}


def _state(commitments: list[int], *, folded: tuple[int, ...] = (), button: int = 0) -> BettingState:
    """A terminal (street='complete') state where each seat has committed
    `commitments[i]` chips this hand and current_bet is already swept to 0."""
    seats = tuple(
        Seat(
            seat_number=i,
            stack=0,
            current_bet=0,
            total_committed=c,
            is_folded=(i in folded),
            is_all_in=True,
            has_acted_this_street=True,
        )
        for i, c in enumerate(commitments)
    )
    return BettingState(
        seats=seats,
        button_seat=button,
        small_blind=1,
        big_blind=2,
        ante=0,
        street="complete",
        current_bet_to_match=0,
        min_raise_increment=2,
        last_aggressor_seat=None,
        pot_committed=sum(commitments),
    )


def test_higher_pair_beats_lower_pair_single_pot():
    state = _state([100, 100])
    board = [_card("K", "clubs"), _card("7", "diamonds"), _card("2", "hearts"),
             _card("9", "spades"), _card("4", "clubs")]
    holes = {
        0: [_card("A", "spades"), _card("A", "diamonds")],   # pair of aces
        1: [_card("Q", "spades"), _card("Q", "diamonds")],   # pair of queens
    }
    assert decide_winners_per_pot(state, holes, board) == [[0]]


def test_kicker_decides():
    state = _state([100, 100])
    board = [_card("A", "clubs"), _card("7", "diamonds"), _card("2", "hearts"),
             _card("9", "spades"), _card("4", "clubs")]
    holes = {
        0: [_card("A", "spades"), _card("K", "diamonds")],   # AA, K kicker
        1: [_card("A", "hearts"), _card("Q", "diamonds")],   # AA, Q kicker
    }
    assert decide_winners_per_pot(state, holes, board) == [[0]]


def test_flush_beats_straight():
    state = _state([100, 100])
    board = [_card("5", "hearts"), _card("9", "hearts"), _card("K", "hearts"),
             _card("6", "spades"), _card("7", "diamonds")]
    holes = {
        0: [_card("2", "hearts"), _card("4", "hearts")],     # flush (hearts)
        1: [_card("8", "spades"), _card("4", "clubs")],      # 5-6-7-8-9 straight
    }
    assert decide_winners_per_pot(state, holes, board) == [[0]]


def test_play_the_board_chops():
    state = _state([100, 100])
    # Broadway straight entirely on the board — both seats play it.
    board = [_card("10", "clubs"), _card("J", "diamonds"), _card("Q", "hearts"),
             _card("K", "spades"), _card("A", "clubs")]
    holes = {
        0: [_card("2", "spades"), _card("3", "diamonds")],
        1: [_card("4", "spades"), _card("5", "diamonds")],
    }
    winners = decide_winners_per_pot(state, holes, board)
    assert winners == [[0, 1]]


def test_split_pot_awards_evenly():
    state = _state([100, 100])
    board = [_card("10", "clubs"), _card("J", "diamonds"), _card("Q", "hearts"),
             _card("K", "spades"), _card("A", "clubs")]
    holes = {
        0: [_card("2", "spades"), _card("3", "diamonds")],
        1: [_card("4", "spades"), _card("5", "diamonds")],
    }
    winners = decide_winners_per_pot(state, holes, board)
    before = total_chips_in_play(state)
    awarded = award_pots(state, winners)
    # Each gets half of the 200 pot.
    assert awarded.seats[0].stack == 100
    assert awarded.seats[1].stack == 100
    assert total_chips_in_play(awarded) == before


def test_side_pots_eligibility_and_winners():
    # Seat 2 is all-in for 50; seats 0,1 commit 100 each.
    state = _state([100, 100, 50])
    pots = compute_side_pots(state)
    # main pot 150 eligible to all; side pot 100 eligible to 0,1 only.
    assert pots == [(150, [0, 1, 2]), (100, [0, 1])]
    board = [_card("K", "clubs"), _card("7", "diamonds"), _card("2", "hearts"),
             _card("9", "spades"), _card("4", "clubs")]
    holes = {
        0: [_card("Q", "spades"), _card("Q", "diamonds")],   # QQ
        1: [_card("J", "spades"), _card("J", "diamonds")],   # JJ
        2: [_card("A", "spades"), _card("A", "diamonds")],   # AA (best) — short stack
    }
    winners = decide_winners_per_pot(state, holes, board)
    # Seat 2 wins the main pot (best hand, eligible). Side pot to seat 0 (QQ > JJ).
    assert winners == [[2], [0]]

    before = total_chips_in_play(state)
    awarded = award_pots(state, winners)
    assert awarded.seats[2].stack == 150   # main pot
    assert awarded.seats[0].stack == 100   # side pot
    assert awarded.seats[1].stack == 0
    assert total_chips_in_play(awarded) == before


def test_folded_seat_contributes_but_cannot_win():
    # Seat 1 folded after committing 100; seats 0,2 contest.
    state = _state([100, 100, 100], folded=(1,))
    board = [_card("K", "clubs"), _card("7", "diamonds"), _card("2", "hearts"),
             _card("9", "spades"), _card("4", "clubs")]
    holes = {
        0: [_card("A", "spades"), _card("A", "diamonds")],   # AA (only live winner)
        2: [_card("Q", "spades"), _card("Q", "diamonds")],   # QQ
    }
    winners = decide_winners_per_pot(state, holes, board)
    # One merged pot of 300, eligible {0,2}; seat 0 wins it all. Seat 1 nowhere.
    assert winners == [[0]]
    awarded = award_pots(state, winners)
    assert awarded.seats[0].stack == 300


def test_sole_live_seat_wins_all_pots():
    state = _state([100, 50], folded=(1,))
    board = [_card("K", "clubs"), _card("7", "diamonds"), _card("2", "hearts")]
    holes = {0: [_card("A", "spades"), _card("A", "diamonds")]}
    winners = decide_winners_per_pot(state, holes, board)
    # Only seat 0 is a contender across all pots.
    assert all(w == [0] for w in winners)
