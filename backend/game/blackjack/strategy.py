"""
strategy.py — Complete basic-strategy engine for BetWise Casino (BRONZE nontrivial piece).

Design constraints (specs/betwise-casino.md §T6):
- 6-deck, dealer hits soft 17.
- HARD_TOTALS, SOFT_TOTALS, PAIRS are canonical lookup tables, not heuristics.
- optimal_action() is a pure function (no DB, no network).
- explain_decision() is a pure function returning a human-readable string.

Table source: Standard 6-deck dealer-hits-soft-17 basic strategy.
Dealer upcard ranks: 2-10, and 11 (Ace).
"""

from __future__ import annotations

from typing import Literal

from backend.game.blackjack.engine import can_split as _can_split_cards
from backend.game.blackjack.engine import card_rank, hand_value, is_soft

Action = Literal["hit", "stand", "double", "split"]

# ─── Lookup tables ────────────────────────────────────────────────────────────
# Keys: player total (or pair value string) × dealer upcard rank (2-11)
# Actions: "H"=hit, "S"=stand, "D"=double, "P"=split
# After table is defined we map letters to full strings.

# HARD TOTALS — keyed by (player_hard_total, dealer_upcard_rank)
# Dealer ranks: 2, 3, 4, 5, 6, 7, 8, 9, 10, 11(=Ace)
_H = "hit"
_S = "stand"
_D = "double"
_P = "split"

HARD_TOTALS: dict[int, dict[int, Action]] = {
    # hard 5-8: always hit
    5:  {2:_H, 3:_H, 4:_H, 5:_H, 6:_H, 7:_H, 8:_H, 9:_H, 10:_H, 11:_H},
    6:  {2:_H, 3:_H, 4:_H, 5:_H, 6:_H, 7:_H, 8:_H, 9:_H, 10:_H, 11:_H},
    7:  {2:_H, 3:_H, 4:_H, 5:_H, 6:_H, 7:_H, 8:_H, 9:_H, 10:_H, 11:_H},
    8:  {2:_H, 3:_H, 4:_H, 5:_H, 6:_H, 7:_H, 8:_H, 9:_H, 10:_H, 11:_H},
    # hard 9: double vs 3-6, else hit
    9:  {2:_H, 3:_D, 4:_D, 5:_D, 6:_D, 7:_H, 8:_H, 9:_H, 10:_H, 11:_H},
    # hard 10: double vs 2-9, else hit
    10: {2:_D, 3:_D, 4:_D, 5:_D, 6:_D, 7:_D, 8:_D, 9:_D, 10:_H, 11:_H},
    # hard 11: double vs 2-A (all upcards) per 6-deck H17 chart
    11: {2:_D, 3:_D, 4:_D, 5:_D, 6:_D, 7:_D, 8:_D, 9:_D, 10:_D, 11:_D},
    # hard 12: stand vs 4-6, else hit
    12: {2:_H, 3:_H, 4:_S, 5:_S, 6:_S, 7:_H, 8:_H, 9:_H, 10:_H, 11:_H},
    # hard 13-14: stand vs 2-6, else hit
    13: {2:_S, 3:_S, 4:_S, 5:_S, 6:_S, 7:_H, 8:_H, 9:_H, 10:_H, 11:_H},
    14: {2:_S, 3:_S, 4:_S, 5:_S, 6:_S, 7:_H, 8:_H, 9:_H, 10:_H, 11:_H},
    # hard 15: stand vs 2-6, else hit
    15: {2:_S, 3:_S, 4:_S, 5:_S, 6:_S, 7:_H, 8:_H, 9:_H, 10:_H, 11:_H},
    # hard 16: stand vs 2-6, else hit
    16: {2:_S, 3:_S, 4:_S, 5:_S, 6:_S, 7:_H, 8:_H, 9:_H, 10:_H, 11:_H},
    # hard 17+: always stand
    17: {2:_S, 3:_S, 4:_S, 5:_S, 6:_S, 7:_S, 8:_S, 9:_S, 10:_S, 11:_S},
    18: {2:_S, 3:_S, 4:_S, 5:_S, 6:_S, 7:_S, 8:_S, 9:_S, 10:_S, 11:_S},
    19: {2:_S, 3:_S, 4:_S, 5:_S, 6:_S, 7:_S, 8:_S, 9:_S, 10:_S, 11:_S},
    20: {2:_S, 3:_S, 4:_S, 5:_S, 6:_S, 7:_S, 8:_S, 9:_S, 10:_S, 11:_S},
    21: {2:_S, 3:_S, 4:_S, 5:_S, 6:_S, 7:_S, 8:_S, 9:_S, 10:_S, 11:_S},
}

# SOFT TOTALS — keyed by (soft_total, dealer_upcard_rank)
# soft 13 = A+2, soft 14 = A+3, ..., soft 21 = A+10 (but BJ is handled separately)
SOFT_TOTALS: dict[int, dict[int, Action]] = {
    # soft 13 (A+2): double vs 5-6, else hit
    13: {2:_H, 3:_H, 4:_H, 5:_D, 6:_D, 7:_H, 8:_H, 9:_H, 10:_H, 11:_H},
    # soft 14 (A+3): double vs 5-6, else hit
    14: {2:_H, 3:_H, 4:_H, 5:_D, 6:_D, 7:_H, 8:_H, 9:_H, 10:_H, 11:_H},
    # soft 15 (A+4): double vs 4-6, else hit
    15: {2:_H, 3:_H, 4:_D, 5:_D, 6:_D, 7:_H, 8:_H, 9:_H, 10:_H, 11:_H},
    # soft 16 (A+5): double vs 4-6, else hit
    16: {2:_H, 3:_H, 4:_D, 5:_D, 6:_D, 7:_H, 8:_H, 9:_H, 10:_H, 11:_H},
    # soft 17 (A+6): double vs 3-6, else hit
    17: {2:_H, 3:_D, 4:_D, 5:_D, 6:_D, 7:_H, 8:_H, 9:_H, 10:_H, 11:_H},
    # soft 18 (A+7): double vs 2-6, stand vs 7-8, hit vs 9/10/A
    18: {2:_D, 3:_D, 4:_D, 5:_D, 6:_D, 7:_S, 8:_S, 9:_H, 10:_H, 11:_H},
    # soft 19 (A+8): stand always (double vs 6 in some charts; standard is stand)
    19: {2:_S, 3:_S, 4:_S, 5:_S, 6:_S, 7:_S, 8:_S, 9:_S, 10:_S, 11:_S},
    # soft 20 (A+9): always stand
    20: {2:_S, 3:_S, 4:_S, 5:_S, 6:_S, 7:_S, 8:_S, 9:_S, 10:_S, 11:_S},
    # soft 21 = blackjack — not a valid reachable lookup (is_blackjack returns before this)
    21: {2:_S, 3:_S, 4:_S, 5:_S, 6:_S, 7:_S, 8:_S, 9:_S, 10:_S, 11:_S},
}

# PAIRS — keyed by (pair_value_str, dealer_upcard_rank)
# pair_value "A","2","3","4","5","6","7","8","9","10" (J/Q/K alias to "10")
# Special: 5-5 is explicitly "hit"/"double" as hard 10, never split
PAIRS: dict[str, dict[int, Action]] = {
    # A-A: always split
    "A":  {2:_P, 3:_P, 4:_P, 5:_P, 6:_P, 7:_P, 8:_P, 9:_P, 10:_P, 11:_P},
    # 2-2: split vs 2-7, hit vs 8-A
    "2":  {2:_P, 3:_P, 4:_P, 5:_P, 6:_P, 7:_P, 8:_H, 9:_H, 10:_H, 11:_H},
    # 3-3: split vs 2-7, hit vs 8-A
    "3":  {2:_P, 3:_P, 4:_P, 5:_P, 6:_P, 7:_P, 8:_H, 9:_H, 10:_H, 11:_H},
    # 4-4: hit always (split vs 5-6 in some charts; standard is hit)
    "4":  {2:_H, 3:_H, 4:_H, 5:_P, 6:_P, 7:_H, 8:_H, 9:_H, 10:_H, 11:_H},
    # 5-5: treat as hard 10 — NEVER split (hard-coded as not-split in optimal_action)
    "5":  {2:_D, 3:_D, 4:_D, 5:_D, 6:_D, 7:_D, 8:_D, 9:_D, 10:_H, 11:_H},
    # 6-6: split vs 2-6, hit vs 7-A
    "6":  {2:_P, 3:_P, 4:_P, 5:_P, 6:_P, 7:_H, 8:_H, 9:_H, 10:_H, 11:_H},
    # 7-7: split vs 2-7, hit vs 8-A
    "7":  {2:_P, 3:_P, 4:_P, 5:_P, 6:_P, 7:_P, 8:_H, 9:_H, 10:_H, 11:_H},
    # 8-8: always split
    "8":  {2:_P, 3:_P, 4:_P, 5:_P, 6:_P, 7:_P, 8:_P, 9:_P, 10:_P, 11:_P},
    # 9-9: split vs 2-6, 8-9; stand vs 7, 10, A
    "9":  {2:_P, 3:_P, 4:_P, 5:_P, 6:_P, 7:_S, 8:_P, 9:_P, 10:_S, 11:_S},
    # 10-10 (and J/Q/K): always stand
    "10": {2:_S, 3:_S, 4:_S, 5:_S, 6:_S, 7:_S, 8:_S, 9:_S, 10:_S, 11:_S},
}


# ─── Pair key helper ──────────────────────────────────────────────────────────

def _pair_key(cards: list[dict]) -> str | None:
    """Return the PAIRS table key for a splittable hand, or None if not splittable.

    J/Q/K all alias to "10". Returns None for 5-5 (explicitly not a split pair).
    """
    if not _can_split_cards(cards):
        return None
    v = cards[0]["value"]
    if v in ("J", "Q", "K"):
        return "10"
    if v == "A":
        return "A"
    # 5-5: not a pair for split purposes
    if v == "5":
        return None
    return v


# ─── optimal_action ───────────────────────────────────────────────────────────

def optimal_action(
    player_cards: list[dict],
    dealer_upcard: dict,
    can_double: bool = True,
    can_split: bool = True,
) -> Action:
    """Return the canonical basic-strategy action for the given situation.

    Parameters
    ----------
    player_cards : list of Card dicts
    dealer_upcard : single Card dict (the face-up card)
    can_double : True if doubling down is legal (only on initial 2 cards)
    can_split : True if splitting is legal (only on initial 2 matching-rank cards)

    Returns
    -------
    One of: "hit", "stand", "double", "split"
    """
    dealer_rank = card_rank(dealer_upcard)

    # Step 1: Check pairs first (if splitting is allowed)
    if can_split:
        pkey = _pair_key(player_cards)
        if pkey is not None:
            pair_action = PAIRS[pkey][dealer_rank]
            if pair_action == "split":
                return "split"
            # Falls through to total-based logic below if pair table says non-split

    # Step 2: Compute total
    total = hand_value(player_cards)
    soft = is_soft(player_cards)

    # Step 3: Lookup action from SOFT_TOTALS or HARD_TOTALS
    if soft and total in SOFT_TOTALS:
        action = SOFT_TOTALS[total][dealer_rank]
    else:
        # Clamp totals above 21 to 21 (already bust, but shouldn't happen pre-action)
        lookup_total = min(max(total, 5), 21)
        action = HARD_TOTALS[lookup_total][dealer_rank]

    # Step 4: Downgrade "double" when can_double=False
    if action == "double" and not can_double:
        # For soft 18+ stands are preferred when cannot double; otherwise hit
        if soft and total >= 19:
            return "stand"
        # Soft 18 vs 7/8 would have been stand — but double->stand for soft 18
        # when can't double we hit (the table shows double for soft 18 vs 2-6;
        # downgrade to hit for those)
        return "hit"

    return action


# ─── explain_decision ─────────────────────────────────────────────────────────

def explain_decision(
    player_cards: list[dict],
    dealer_upcard: dict,
    was_correct: bool,
    player_guess: str,
    optimal: str,
) -> str:
    """Build a human-readable explanation of a strategy decision.

    Returns a string naming the hand category, dealer upcard, and a brief reason.
    Pure function — no DB, no network.

    Example: "soft 17 vs dealer 6: with a soft 17, doubling is the optimal play
    because the dealer is likely to bust."
    """
    total = hand_value(player_cards)
    soft = is_soft(player_cards)
    dealer_rank = card_rank(dealer_upcard)
    dealer_val = dealer_upcard["value"]

    # Build hand description
    if _can_split_cards(player_cards):
        v = player_cards[0]["value"]
        if v == "A":
            hand_desc = "pair of aces"
        elif v in ("J", "Q", "K", "10"):
            hand_desc = "pair of 10s"
        else:
            hand_desc = f"pair of {v}s"
    elif soft:
        hand_desc = f"soft {total}"
    else:
        hand_desc = f"hard {total}"

    # Build brief reason
    if optimal == "split":
        reason = "splitting improves your expected value in this situation"
    elif optimal == "double":
        reason = "the dealer is vulnerable and doubling maximizes your expected return"
    elif optimal == "stand":
        if dealer_rank <= 6:
            reason = "the dealer is likely to bust with a weak upcard"
        else:
            reason = "your total is strong enough to risk the dealer drawing up"
    else:  # hit
        if total < 12:
            reason = "your total is low and you cannot bust with one card"
        elif soft:
            reason = "you cannot bust on a soft hand and need more total"
        else:
            reason = "you need more total to beat the dealer's strong upcard"

    correctness = "Correct!" if was_correct else f"The optimal play was {optimal}."
    return (
        f"{hand_desc} vs dealer {dealer_val}: {correctness} "
        f"With {hand_desc}, {optimal} is optimal because {reason}."
    )
