"""
icm.py — Independent Chip Model (Harville recursion) for Texas Hold'em SNGs.

Design constraints (specs/texas-holdem.md §AC-B26..AC-B27):
- Pure functions, no DB, no network.
- Implements the Harville (1973) recursion adapted from horse-racing finish
  probabilities to poker stacks-as-tickets.
- icm_equity returns each seat's prize-pool equity in $ (cents).
- icm_breakeven_call_equity computes the equity threshold at which calling
  an all-in is 0-EV in $-terms (ICM-adjusted, vs the chip-EV value).

Reference: specs/texas-holdem-reference.md §9.
"""

from __future__ import annotations

from functools import lru_cache


def _normalize_stacks(stacks: list[int]) -> tuple[float, ...]:
    total = sum(stacks)
    if total <= 0:
        raise ValueError("All stacks zero — cannot normalize")
    return tuple(s / total for s in stacks)


def harville_finish_distribution(stacks: list[int]) -> list[list[float]]:
    """Return the n×n matrix M where M[i][j] = P(seat i finishes in position j).

    Uses the Harville recursion: P(seat i finishes 1st) = stack_i / sum;
    P(seat i finishes kth) given seat j finished higher = recursive call on
    the reduced field.

    Complexity: O(n × 2^n). Practical up to n ≈ 9 (BetWise SNG max).
    """
    n = len(stacks)
    if n == 0:
        return []
    if any(s < 0 for s in stacks):
        raise ValueError("Stacks must be non-negative")
    if sum(stacks) == 0:
        raise ValueError("At least one stack must be positive")

    # Memoize subset evaluations via a recursive helper. Subsets are encoded
    # as bitmask of remaining seats.
    stacks_t = tuple(stacks)

    @lru_cache(maxsize=None)
    def prob_win_in_subset(seat: int, subset: int) -> float:
        """P(seat wins | only the seats in `subset` remain)."""
        total = 0.0
        for s in range(n):
            if subset & (1 << s):
                total += stacks_t[s]
        if total == 0:
            return 0.0
        return stacks_t[seat] / total

    M = [[0.0] * n for _ in range(n)]
    full = (1 << n) - 1

    # P(seat i finishes 1st)
    for i in range(n):
        M[i][0] = prob_win_in_subset(i, full)

    # For higher positions: enumerate orderings of who finished above.
    # Position k (0-indexed): seat i finishes in position k iff some subset of
    # k other seats finished above i. We sum over all valid orderings.
    # Use straightforward recursive enumeration. For n ≤ 9 this is fast enough.
    def enumerate_position(target_seat: int, target_pos: int) -> float:
        """P(target_seat finishes in target_pos, 0-indexed)."""
        if target_pos == 0:
            return prob_win_in_subset(target_seat, full)
        # Recursive: sum over all orderings of who finished above target_seat.
        # We accumulate: for each subset of (target_pos) seats not including
        # target_seat, compute P(those seats finished in that order in their
        # positions) × P(target_seat wins the remainder).
        total = 0.0

        def recurse(remaining_above: int, prefix_subset: int, prefix_prob: float) -> None:
            nonlocal total
            if remaining_above == 0:
                # target_seat wins the remaining field
                remaining = full & ~prefix_subset
                if remaining & (1 << target_seat) == 0:
                    return
                total += prefix_prob * prob_win_in_subset(target_seat, remaining)
                return
            current_field = full & ~prefix_subset
            for next_seat in range(n):
                bit = 1 << next_seat
                if not (current_field & bit):
                    continue
                if next_seat == target_seat:
                    continue
                p_next = prob_win_in_subset(next_seat, current_field)
                recurse(remaining_above - 1, prefix_subset | bit, prefix_prob * p_next)

        recurse(target_pos, 0, 1.0)
        return total

    for i in range(n):
        for pos in range(1, n):
            M[i][pos] = enumerate_position(i, pos)

    return M


def icm_equity(stacks: list[int], payouts: list[float]) -> list[float]:
    """Return each seat's prize-pool equity in $-units.

    `stacks` is a list of chip stacks (length n). `payouts` is a list of
    monetary prizes (any unit — cents, dollars), padded with 0s for unpaid
    finishes (length ≥ n). Returns a length-n list where index i is seat i's
    equity = sum_k (P(seat_i finishes in pos k) × payouts[k]).
    """
    n = len(stacks)
    if len(payouts) < n:
        payouts = list(payouts) + [0.0] * (n - len(payouts))
    M = harville_finish_distribution(stacks)
    return [sum(M[i][k] * payouts[k] for k in range(n)) for i in range(n)]


def icm_breakeven_call_equity(
    stacks_before: list[int],
    payouts: list[float],
    hero_seat: int,
    opp_seat: int,
    pot_before_call: int,
    opp_bet: int,
) -> float:
    """Equity threshold (in [0, 1]) at which calling an all-in is 0-EV in $.

    Solves: E_call(equity) = E_fold, where E_call and E_fold are computed via
    ICM on the post-action stacks.

    `pot_before_call` is the chips in the pot before hero's call (so the total
    pot at showdown if hero calls is pot_before_call + 2*opp_bet ... actually
    pot_before_call + opp_bet for hero matching, but opp_bet was already in
    pot. We use the convention: pot_before_call already includes opp_bet, and
    hero adds `opp_bet` to call.)

    Approach: binary search on equity ∈ [0, 1].
    """
    n = len(stacks_before)
    if hero_seat == opp_seat or not (0 <= hero_seat < n and 0 <= opp_seat < n):
        raise ValueError("hero_seat and opp_seat must be distinct valid indices")

    # Fold: hero loses 0; opp gains 0 from hero. Stacks unchanged.
    fold_equity = icm_equity(stacks_before, payouts)[hero_seat]

    # Call: hero adds opp_bet to pot. Outcome depends on equity:
    #   - If hero wins: hero stack += pot_before_call (was hero's contribution
    #     already?). Simpler model: ignore the bookkeeping nuance and treat
    #     the "called all-in" as an effective stack transfer.
    # For the threshold, we use the simplest correct formulation:
    #   - Hero contributes opp_bet to call. Total at risk = opp_bet.
    #   - Win: hero stack += opp_bet (wins opp's bet). Opp stack -= opp_bet
    #     effectively (already in pot).
    #   - Lose: hero stack -= opp_bet. Opp stack += opp_bet.
    # We assume both stacks are large enough to cover opp_bet (no all-in
    # corner case — that's handled separately in a full implementation).
    # For threshold solving, we operate on (stacks ± opp_bet).

    # Convention: stacks_before already reflects opp's all-in being committed
    # (those chips are in the pot, removed from opp's stack). Hero is deciding
    # whether to call by paying `opp_bet` from hero's stack.
    #
    # When hero calls and wins: hero gains pot_before_call (won the pot,
    # offset by their call). Opp's stack is unchanged (their chips were
    # already removed pre-decision).
    # When hero calls and loses: hero pays opp_bet from stack. Opp gains
    # pot_before_call + opp_bet (the entire pot they won).
    def call_ev(equity_value: float) -> float:
        win_stacks = list(stacks_before)
        lose_stacks = list(stacks_before)
        # WIN: hero recoups call and wins the dead money.
        win_stacks[hero_seat] += pot_before_call
        # LOSE: hero pays the call; opp wins the whole pot.
        lose_stacks[hero_seat] -= opp_bet
        lose_stacks[opp_seat] += pot_before_call + opp_bet
        win_stacks = [max(0, s) for s in win_stacks]
        lose_stacks = [max(0, s) for s in lose_stacks]
        win_eq = icm_equity(win_stacks, payouts)[hero_seat]
        lose_eq = icm_equity(lose_stacks, payouts)[hero_seat]
        return equity_value * win_eq + (1 - equity_value) * lose_eq

    # Binary search for the equity where call_ev == fold_equity
    lo, hi = 0.0, 1.0
    for _ in range(40):  # 40 iterations → ~1e-12 precision
        mid = (lo + hi) / 2
        if call_ev(mid) >= fold_equity:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


__all__ = [
    "harville_finish_distribution",
    "icm_equity",
    "icm_breakeven_call_equity",
]
