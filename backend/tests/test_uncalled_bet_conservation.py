"""
test_uncalled_bet_conservation.py — regression tests for the uncalled-bet fix.

Guards the ENGINE-level money fixes in backend/game/poker/state.py:

  * P2 (over-award): an over-committer's excess must NOT be handed to the sole
    survivor — it must be REFUNDED to the over-committer at street collection.
  * P4 (chip destruction): the excess must NOT be swept into a side-pot tier
    eligible to zero non-folded seats and then destroyed. The refund in
    advance_street guarantees no side-pot tier is ever eligible to nobody, and
    award_pots is hardened (defense-in-depth) to intersect named winners with
    each pot's eligible set so an ineligible "winner" cannot over-award.

These are pure-sync engine tests (no DB, like test_holdem_showdown.py): we drive
backend.game.poker.state directly so the over-bet/all-in-for-less lines are
explicit and deterministic.

The fixes may not all be applied yet — these tests assert the CORRECT post-fix
behavior per the security spec (fix/pr6-security-round2).
"""

from __future__ import annotations

from backend.game.poker.showdown import decide_winners_per_pot
from backend.game.poker.state import (
    advance_street,
    apply_action,
    award_pots,
    compute_side_pots,
    create_state,
    street_closed,
    total_chips_in_play,
)


def _card(value: str, suit: str) -> dict:
    return {"suit": suit, "value": value}


# ─── (a) Heads-up: over-bet vs all-in-for-less → uncalled bet refunded ─────────


def test_hu_overraise_vs_short_call_refunds_uncalled_excess() -> None:
    """P2/P4: seat A (BTN) raises far beyond seat B who calls all-in for less.

    On advance_street the uncalled excess (m1 - m2) must be refunded to A's
    stack — not collected into the pot (where the lone survivor would steal it
    or an empty-eligible tier would destroy it). A keeps chips throughout, so
    is_all_in is irrelevant here.
    """
    # HU, button=0 → seat 0 is SB/BTN (acts first preflop), seat 1 is BB.
    s = create_state([1000, 100], button_seat=0, small_blind=5, big_blind=10)
    initial_total = total_chips_in_play(s)
    assert initial_total == 1100

    # Seat 0 over-raises to 200 (far beyond seat 1's 100-chip stack).
    s = apply_action(s, 0, "raise", amount=200)
    # Seat 1 calls all-in for less (only 100 total committable).
    s = apply_action(s, 1, "all_in")

    a_before = s.seats[0].stack          # A's stack the instant before collection
    assert s.seats[0].current_bet == 200  # m1 (sole topper)
    assert s.seats[1].current_bet == 100  # m2 (the only other seat)
    assert s.seats[1].is_all_in
    assert street_closed(s)

    s = advance_street(s)

    # A refunded exactly the uncalled excess m1 - m2 = 200 - 100 = 100.
    assert s.seats[0].stack == a_before + (200 - 100)
    # The refund moved chips current_bet → stack: no chips minted or destroyed.
    assert total_chips_in_play(s) == initial_total
    # Pot now holds only the CONTESTED chips (100 from each seat), not the excess.
    assert s.pot_committed == 200
    # A is not all-in (it had chips left after the raise).
    assert not s.seats[0].is_all_in


def test_hu_allin_for_more_refund_clears_all_in_flag() -> None:
    """P2/P4 + is_all_in clearing: A shoves for MORE than B's all-in-for-less.

    A is briefly is_all_in (stack 0), but after the uncalled excess is refunded
    A has chips again, so advance_street must clear A.is_all_in.
    """
    # HU: seat 0 = SB/BTN, seat 1 = BB. A (150) covers B (100).
    s = create_state([150, 100], button_seat=0, small_blind=5, big_blind=10)
    initial_total = total_chips_in_play(s)
    assert initial_total == 250

    s = apply_action(s, 0, "all_in")  # A shoves to 150 total
    s = apply_action(s, 1, "all_in")  # B shoves to 100 total (for less)

    assert s.seats[0].current_bet == 150  # m1
    assert s.seats[1].current_bet == 100  # m2
    assert s.seats[0].is_all_in           # A momentarily all-in (stack 0)
    a_before = s.seats[0].stack
    assert a_before == 0

    s = advance_street(s)

    refund = 150 - 100
    assert s.seats[0].stack == a_before + refund   # A refunded the uncalled 50
    assert not s.seats[0].is_all_in                # cleared: A has chips again
    assert s.seats[1].is_all_in                    # B is genuinely all-in
    assert total_chips_in_play(s) == initial_total  # conserved across refund
    assert s.pot_committed == 200                   # only the contested 100+100


def test_hu_equal_all_ins_no_refund() -> None:
    """Guard the boundary: when ≥2 seats tie at the top commitment there is NO
    refund (the bet WAS fully called). The refund logic must not fire here."""
    s = create_state([100, 100], button_seat=0, small_blind=5, big_blind=10)
    initial_total = total_chips_in_play(s)

    s = apply_action(s, 0, "all_in")  # both shove to 100
    s = apply_action(s, 1, "all_in")
    assert s.seats[0].current_bet == 100
    assert s.seats[1].current_bet == 100

    a_before, b_before = s.seats[0].stack, s.seats[1].stack
    s = advance_street(s)

    # Tie at the top → no refund to either seat.
    assert s.seats[0].stack == a_before
    assert s.seats[1].stack == b_before
    assert s.pot_committed == 200
    assert total_chips_in_play(s) == initial_total


# ─── (b) 3-handed: over-bet vs two all-ins-for-less → no destroy, eligibility ──


def _three_handed_overbet_to_complete():
    """Build the canonical 3-handed line and run it through to a complete hand.

    Seat 0 (deep, 500) over-raises to 300. Seats 1 (60) and 2 (100) each call
    all-in for less, at two distinct levels. Returns (state, initial_total).
    """
    s = create_state([500, 60, 100], button_seat=0, small_blind=5, big_blind=10)
    initial_total = total_chips_in_play(s)
    assert initial_total == 660

    # 3-handed: first to act preflop is (BB+1) % 3 = seat 0.
    s = apply_action(s, 0, "raise", amount=300)  # massive over-bet
    s = apply_action(s, 1, "all_in")             # seat 1 all-in for 60 total
    s = apply_action(s, 2, "all_in")             # seat 2 all-in for 100 total
    assert street_closed(s)

    while s.street != "complete":
        s = advance_street(s)
    return s, initial_total


def test_3way_overbet_refund_no_empty_eligible_pot() -> None:
    """P4 root cause: after the refund, NO side-pot tier is eligible to zero
    non-folded seats (which is where chips were being destroyed)."""
    s, initial_total = _three_handed_overbet_to_complete()

    # Refund happened on the preflop→flop transition: seat 0's uncalled excess
    # over the second-highest commitment (100) is returned.
    # m1 = 300 (seat 0), m2 = max(60, 100) = 100 → refund = 200.
    assert s.seats[0].total_committed == 100   # 300 committed, 200 refunded
    assert s.seats[1].total_committed == 60
    assert s.seats[2].total_committed == 100

    pots = compute_side_pots(s)
    # Main pot: level 60 × 3 contributors = 180, eligible {0,1,2}.
    # Side pot: (100-60) × 2 = 80, eligible {0,2}.
    assert pots == [(180, [0, 1, 2]), (80, [0, 2])]

    # The invariant under test: every pot is eligible to ≥1 non-folded seat.
    for amount, eligible in pots:
        assert amount > 0
        assert len(eligible) >= 1

    # Chips conserved across the whole betting phase (refund + collection).
    assert total_chips_in_play(s) == initial_total
    # Pot holds exactly the contested chips: 180 + 80 = 260.
    assert s.pot_committed == 260


def test_3way_overbet_award_no_destroy_no_ineligible_credit() -> None:
    """P2/P4 end-to-end: advance through to award and assert (1) no chips are
    destroyed, (2) no seat is credited from a pot it is not eligible for.

    winners_per_pot is produced by the real showdown resolver, so eligibility
    is exercised exactly as production would compute it.
    """
    s, initial_total = _three_handed_overbet_to_complete()
    pots = compute_side_pots(s)

    # Board with no flush/straight; seats reach showdown with distinct made hands.
    board = [
        _card("K", "clubs"), _card("7", "diamonds"), _card("2", "hearts"),
        _card("9", "spades"), _card("4", "clubs"),
    ]
    holes = {
        0: [_card("A", "spades"), _card("A", "diamonds")],   # pair of aces
        1: [_card("7", "spades"), _card("7", "clubs")],      # trip sevens (board 7)
        2: [_card("Q", "spades"), _card("Q", "diamonds")],   # pair of queens
    }

    winners = decide_winners_per_pot(s, holes, board)
    # Main pot (eligible all): seat 1's trips beat both pairs → [1].
    # Side pot (eligible {0,2}): seat 0's AA beats seat 2's QQ → [0].
    assert winners == [[1], [0]]

    before = total_chips_in_play(s)
    awarded = award_pots(s, winners)

    # (1) Nothing destroyed, nothing minted.
    assert total_chips_in_play(awarded) == before == initial_total
    assert sum(seat.stack for seat in awarded.seats) == initial_total
    assert awarded.pot_committed == 0

    # (2) No seat credited from a pot it is not eligible for.
    #   Seat 1 wins ONLY the main pot (180); it is NOT eligible for the side pot.
    #   Seat 0's pre-award stack is 400 (after the 200 refund); +80 side = 480.
    assert awarded.seats[0].stack == 400 + 80   # side pot only
    assert awarded.seats[1].stack == 0 + 180    # main pot only
    assert awarded.seats[2].stack == 0          # lost both pots it contested

    # Cross-check eligibility against the pot table: a seat's winnings never
    # exceed the sum of the pots for which it is actually eligible.
    eligible_pot_totals = {i: 0 for i in range(len(s.seats))}
    for amount, eligible in pots:
        for seat_idx in eligible:
            eligible_pot_totals[seat_idx] += amount
    gains = {i: awarded.seats[i].stack - s.seats[i].stack for i in range(len(s.seats))}
    for seat_idx, gained in gains.items():
        assert gained <= eligible_pot_totals[seat_idx]


def test_award_pots_rejects_ineligible_winner() -> None:
    """P2/P4 defense-in-depth: award_pots must intersect named winners with each
    pot's eligible set. A caller naming an INELIGIBLE seat as a winner must NOT
    over-award it (and chips must stay conserved — never destroyed)."""
    s, initial_total = _three_handed_overbet_to_complete()
    pots = compute_side_pots(s)
    assert pots == [(180, [0, 1, 2]), (80, [0, 2])]

    # Maliciously/incorrectly name seat 1 (NOT eligible) as the side-pot winner.
    awarded = award_pots(s, [[1], [1]])

    # Over-award blocked: ineligible seat 1 collects ONLY the main pot it is
    # eligible for (180), never the 80 side pot it is not eligible for.
    assert awarded.seats[1].stack - s.seats[1].stack == 180
    # The 80 side pot named to ineligible seat 1 is NOT handed to seat 1 — but it
    # is also NOT destroyed: it is returned to its rightful eligible contenders
    # (seats 0 and 2), so chips stay conserved (fail-closed, never fail-open).
    side_returned = (
        (awarded.seats[0].stack - s.seats[0].stack)
        + (awarded.seats[2].stack - s.seats[2].stack)
    )
    assert side_returned == 80
    # CONSERVATION: every chip in every pot is credited to an eligible seat;
    # nothing is minted and nothing is destroyed.
    assert sum(seat.stack for seat in awarded.seats) == initial_total
