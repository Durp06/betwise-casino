"""
review.py — pure-function severity model for BetWise Casino Hand Review.

No DB, no network, no randomness. Called on read by the session-review endpoint
(backend/routers/sessions.py) to classify every player decision and compute EV loss.

EV_LOSS_TABLE is a nested dict:
    HandCategory -> DealerUpcardCategory -> WrongAction -> ev_loss_pct (float)

The table is structured to satisfy all AC-B7 anchors:
  - hit on hard 20 → blunder  (>0.10)
  - stand on hard 8 → blunder  (>0.10)
  - double on hard 17 → blunder  (>0.10)
  - hit on hard 12 vs dealer 4 (weak) → inaccuracy  (0.01 < pct <= 0.04)
  - stand on hard 16 vs dealer 10 (ten) → inaccuracy  (0.01 < pct <= 0.04)

Missing cells default to 0.05 (mid "mistake" bucket) — every genuinely wrong
call is at minimum a mistake; individual cells can be softened later.
"""
from __future__ import annotations

from typing import Literal

from backend.game.engine import card_rank, hand_value, is_soft, can_split

# ─── Type aliases ─────────────────────────────────────────────────────────────

Classification = Literal["best", "good", "inaccuracy", "mistake", "blunder"]

# ─── EV-loss heuristic table ──────────────────────────────────────────────────
# Keys: HandCategory → DealerUpcardCategory → WrongAction → ev_loss_pct
#
# HandCategories:
#   hard_5_8, hard_9, hard_10, hard_11, hard_12, hard_13_16,
#   hard_17, hard_18_19, hard_20, hard_21,
#   soft_13_15, soft_16_17, soft_18, soft_19_21,
#   pair_aces, pair_8s, pair_other_split, pair_face
#
# DealerUpcardCategories: weak (2-6), strong (7-9), ten (10/J/Q/K), ace (A)

EV_LOSS_TABLE: dict[str, dict[str, dict[str, float]]] = {
    # ── Hard totals ────────────────────────────────────────────────────────────

    "hard_5_8": {
        # optimal is always hit; standing on an unbusted-able hand is catastrophic
        "weak":   {"stand": 0.18, "double": 0.06, "split": 0.18},
        "strong": {"stand": 0.20, "double": 0.06, "split": 0.20},
        "ten":    {"stand": 0.22, "double": 0.06, "split": 0.22},
        "ace":    {"stand": 0.22, "double": 0.06, "split": 0.22},
    },

    "hard_9": {
        # optimal: double vs 3-6, hit elsewhere
        "weak":   {"stand": 0.07, "split": 0.07},           # standing = mistake
        "strong": {"double": 0.03, "stand": 0.07, "split": 0.07},
        "ten":    {"double": 0.04, "stand": 0.07, "split": 0.07},
        "ace":    {"double": 0.04, "stand": 0.07, "split": 0.07},
    },

    "hard_10": {
        # optimal: double vs 2-9, hit vs 10/A
        "weak":   {"hit": 0.03, "stand": 0.08, "split": 0.08},
        "strong": {"hit": 0.03, "stand": 0.08, "split": 0.08},
        "ten":    {"double": 0.03, "stand": 0.08, "split": 0.08},
        "ace":    {"double": 0.04, "stand": 0.08, "split": 0.08},
    },

    "hard_11": {
        # optimal: double vs 2-10, hit vs ace
        "weak":   {"hit": 0.02, "stand": 0.10, "split": 0.10},
        "strong": {"hit": 0.02, "stand": 0.10, "split": 0.10},
        "ten":    {"hit": 0.02, "stand": 0.10, "split": 0.10},
        "ace":    {"double": 0.02, "stand": 0.10, "split": 0.10},
    },

    "hard_12": {
        # optimal: stand vs 4-6 (weak), hit everywhere else.
        # hit vs 4 (weak) is a close-call mistake → inaccuracy (0.01 < pct ≤ 0.04)
        "weak":   {"hit": 0.02, "double": 0.05, "split": 0.05, "stand": 0.05},
        "strong": {"stand": 0.05, "double": 0.05, "split": 0.05},
        "ten":    {"stand": 0.05, "double": 0.05, "split": 0.05},
        "ace":    {"stand": 0.05, "double": 0.05, "split": 0.05},
    },

    "hard_13_16": {
        # optimal: stand vs 2-6 (weak), hit vs 7-A.
        # Stand on 16 vs 10 (ten) is a narrow inaccuracy (0.01 < pct ≤ 0.04).
        "weak":   {"hit": 0.02, "double": 0.05, "split": 0.05},
        "strong": {"stand": 0.04, "double": 0.05, "split": 0.05},
        "ten":    {"stand": 0.03, "double": 0.06, "split": 0.06},
        "ace":    {"stand": 0.04, "double": 0.06, "split": 0.06},
    },

    "hard_17": {
        # Always stand. Double on 17 = blunder (>0.10).
        "weak":   {"hit": 0.06, "double": 0.12, "split": 0.06},
        "strong": {"hit": 0.08, "double": 0.14, "split": 0.08},
        "ten":    {"hit": 0.10, "double": 0.16, "split": 0.10},
        "ace":    {"hit": 0.10, "double": 0.16, "split": 0.10},
    },

    "hard_18_19": {
        # Always stand.
        "weak":   {"hit": 0.08, "double": 0.12, "split": 0.08},
        "strong": {"hit": 0.10, "double": 0.14, "split": 0.10},
        "ten":    {"hit": 0.14, "double": 0.18, "split": 0.14},
        "ace":    {"hit": 0.14, "double": 0.18, "split": 0.14},
    },

    "hard_20": {
        # Always stand. Hit on 20 = blunder (>0.10).
        "weak":   {"hit": 0.20, "double": 0.20, "split": 0.20},
        "strong": {"hit": 0.20, "double": 0.20, "split": 0.20},
        "ten":    {"hit": 0.22, "double": 0.22, "split": 0.22},
        "ace":    {"hit": 0.22, "double": 0.22, "split": 0.22},
    },

    "hard_21": {
        # Natural 21 or hard 21 — always stand; any other action is catastrophic
        "weak":   {"hit": 0.30, "double": 0.30, "split": 0.30},
        "strong": {"hit": 0.30, "double": 0.30, "split": 0.30},
        "ten":    {"hit": 0.30, "double": 0.30, "split": 0.30},
        "ace":    {"hit": 0.30, "double": 0.30, "split": 0.30},
    },

    # ── Soft totals ────────────────────────────────────────────────────────────

    "soft_13_15": {
        # optimal: hit (or double vs 4-6); standing prematurely
        "weak":   {"stand": 0.05, "double": 0.03},
        "strong": {"stand": 0.06, "double": 0.04},
        "ten":    {"stand": 0.07, "double": 0.05},
        "ace":    {"stand": 0.07, "double": 0.05},
    },

    "soft_16_17": {
        # soft 16-17: hit or double vs weak; hit vs strong/ten/ace
        "weak":   {"stand": 0.06, "hit": 0.02},
        "strong": {"stand": 0.06, "double": 0.04},
        "ten":    {"stand": 0.08, "double": 0.05},
        "ace":    {"stand": 0.08, "double": 0.05},
    },

    "soft_18": {
        # soft 18: stand vs 2/7/8, double vs 3-6, hit vs 9/10/A
        "weak":   {"hit": 0.02, "double": 0.02},
        "strong": {"stand": 0.03, "double": 0.04},
        "ten":    {"stand": 0.06, "double": 0.07},
        "ace":    {"stand": 0.06, "double": 0.07},
    },

    "soft_19_21": {
        # Always stand on soft 19-21
        "weak":   {"hit": 0.06, "double": 0.08, "split": 0.06},
        "strong": {"hit": 0.08, "double": 0.10, "split": 0.08},
        "ten":    {"hit": 0.12, "double": 0.14, "split": 0.12},
        "ace":    {"hit": 0.12, "double": 0.14, "split": 0.12},
    },

    # ── Pairs ──────────────────────────────────────────────────────────────────

    "pair_aces": {
        # Always split aces
        "weak":   {"stand": 0.15, "hit": 0.12, "double": 0.12},
        "strong": {"stand": 0.15, "hit": 0.12, "double": 0.12},
        "ten":    {"stand": 0.18, "hit": 0.15, "double": 0.15},
        "ace":    {"stand": 0.18, "hit": 0.15, "double": 0.15},
    },

    "pair_8s": {
        # Always split 8s
        "weak":   {"stand": 0.12, "hit": 0.08, "double": 0.10},
        "strong": {"stand": 0.12, "hit": 0.08, "double": 0.10},
        "ten":    {"stand": 0.12, "hit": 0.08, "double": 0.10},
        "ace":    {"stand": 0.12, "hit": 0.08, "double": 0.10},
    },

    "pair_other_split": {
        # Other splittable pairs (2-2, 3-3, 4-4, 6-6, 7-7, 9-9 where split is optimal)
        "weak":   {"stand": 0.05, "hit": 0.03, "double": 0.05},
        "strong": {"stand": 0.05, "hit": 0.03, "double": 0.05},
        "ten":    {"stand": 0.06, "hit": 0.03, "double": 0.06},
        "ace":    {"stand": 0.06, "hit": 0.03, "double": 0.06},
    },

    "pair_face": {
        # 10/J/Q/K pairs — never split, always stand on 20
        "weak":   {"hit": 0.20, "double": 0.20, "split": 0.20},
        "strong": {"hit": 0.20, "double": 0.20, "split": 0.20},
        "ten":    {"hit": 0.22, "double": 0.22, "split": 0.22},
        "ace":    {"hit": 0.22, "double": 0.22, "split": 0.22},
    },
}


# ─── Category helpers ─────────────────────────────────────────────────────────

def _categorize_hand(cards: list[dict]) -> str:
    """Map a hand (list of card dicts) to a HandCategory string."""
    # Check pairs first
    if can_split(cards):  # type: ignore[arg-type]
        v = cards[0]["value"]
        if v == "A":
            return "pair_aces"
        if v == "8":
            return "pair_8s"
        # Face cards (J/Q/K/10) → pair_face (never split)
        if v in ("10", "J", "Q", "K"):
            return "pair_face"
        # Other numeric pairs that are splittable
        return "pair_other_split"

    val = hand_value(cards)  # type: ignore[arg-type]
    soft = is_soft(cards)  # type: ignore[arg-type]

    if soft:
        if val <= 15:
            return "soft_13_15"
        if val <= 17:
            return "soft_16_17"
        if val == 18:
            return "soft_18"
        return "soft_19_21"

    # Hard totals
    if val <= 8:
        return "hard_5_8"
    if val == 9:
        return "hard_9"
    if val == 10:
        return "hard_10"
    if val == 11:
        return "hard_11"
    if val == 12:
        return "hard_12"
    if val <= 16:
        return "hard_13_16"
    if val == 17:
        return "hard_17"
    if val <= 19:
        return "hard_18_19"
    if val == 20:
        return "hard_20"
    return "hard_21"


def _categorize_dealer(upcard: dict) -> str:
    """Map a dealer upcard (card dict) to DealerUpcardCategory."""
    rank = card_rank(upcard)  # type: ignore[arg-type]
    if rank == 11:
        return "ace"
    if rank == 10:
        return "ten"
    if rank >= 7:
        return "strong"
    return "weak"


def _bucket(pct: float) -> Classification:
    """Bucket an ev_loss_pct float into a Classification label per AC-B6."""
    if pct <= 0.01:
        return "good"
    if pct <= 0.04:
        return "inaccuracy"
    if pct <= 0.10:
        return "mistake"
    return "blunder"


# ─── Public API ───────────────────────────────────────────────────────────────

def classify_action(
    hand_cards: list[dict],
    dealer_upcard: dict,
    player_action: str,
    optimal_action: str,
    bet: int,
) -> tuple[Classification, int]:
    """Classify a player decision and compute EV loss in chips.

    Pure function: no DB, no network, no randomness.

    Returns:
        (classification, ev_loss_chips)
        classification ∈ {"best", "good", "inaccuracy", "mistake", "blunder"}
        ev_loss_chips = round(bet * ev_loss_pct)  (0 when classification == "best")
    """
    if player_action == optimal_action:
        return ("best", 0)

    hand_cat = _categorize_hand(hand_cards)
    dealer_cat = _categorize_dealer(dealer_upcard)

    # Look up the ev_loss_pct; default to 0.05 (mid "mistake") for unfilled cells
    cat_row = EV_LOSS_TABLE.get(hand_cat, {})
    dealer_row = cat_row.get(dealer_cat, {})
    pct = dealer_row.get(player_action, 0.05)

    classification = _bucket(pct)
    ev_loss_chips = round(bet * pct)
    return (classification, ev_loss_chips)
