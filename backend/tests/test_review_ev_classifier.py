"""
test_review_ev_classifier.py — Task 4 EV-delta classifier + Sharp tier tests.

Maps 1-to-1 to acceptance criteria:
  AC-B-CLS1  — optimal non-Sharp play → ("best", 0)
  AC-B-CLS2  — optimal play in Sharp set → ("sharp", 0)
  AC-B-CLS3  — wrong action classified by EV-delta buckets (Decision #4)
  AC-B-CLS4  — existing anchors preserved (blunder/inaccuracy cases)
  AC-B-CLS5  — split fallback: A,A and 8,8 miss → blunder; 4,4 vs 2 stand → blunder
  AC-B-CLS6  — Sharp curated set exact membership + obvious plays NOT sharp
  AC-B-CLS7  — classify_action is pure and deterministic
  AC-B-CLS8  — per-action bet pricing: pre-double wrong stand priced at initial bet

All tests are expected to FAIL until Task 4 is implemented:
  - backend/game/blackjack/review.py  (EV-delta grading + Sharp tier)
  - backend/schemas.py  (Classification widened to include "sharp")

NOTE: AC-B-CLS4 anchors must ALSO pass after the new classifier lands;
      these tests mirror the assertions in test_session_review.py so the
      implementer knows both files must be green simultaneously.
"""
from __future__ import annotations

import pytest


def _h(value: str, suit: str = "hearts") -> dict:
    """Build a card dict."""
    return {"suit": suit, "value": value}


# ─── AC-B-CLS1: optimal non-Sharp play → ("best", 0) ─────────────────────────

class TestCLS1OptimalNonSharp:
    def test_stand_hard_20_is_best_not_sharp(self):
        """AC-B-CLS1 — stand hard 20 vs any upcard → ('best', 0). Not in Sharp set."""
        from backend.game.review import classify_action  # noqa: PLC0415

        cls, loss = classify_action(
            [_h("K", "spades"), _h("Q")], _h("6"), "stand", "stand", bet=1000
        )
        assert cls == "best", f"stand hard 20 (optimal) should be 'best', got {cls!r}"
        assert loss == 0

    def test_hit_hard_5_is_best_not_sharp(self):
        """AC-B-CLS1 — hit hard 5 vs 6 → ('best', 0). Plain obvious play, not sharp."""
        from backend.game.review import classify_action  # noqa: PLC0415

        cls, loss = classify_action(
            [_h("2"), _h("3")], _h("6"), "hit", "hit", bet=500
        )
        assert cls == "best", f"hit hard 5 (optimal) should be 'best', got {cls!r}"
        assert loss == 0

    def test_stand_hard_19_is_best_not_sharp(self):
        """AC-B-CLS1 — stand hard 19 vs any upcard → ('best', 0). Not sharp."""
        from backend.game.review import classify_action  # noqa: PLC0415

        cls, loss = classify_action(
            [_h("10"), _h("9")], _h("8"), "stand", "stand", bet=1000
        )
        assert cls == "best", f"stand hard 19 (optimal) should be 'best', got {cls!r}"
        assert loss == 0


# ─── AC-B-CLS2: optimal play in Sharp set → ("sharp", 0) ─────────────────────

class TestCLS2SharpTier:
    def test_hit_hard_16_vs_10_is_sharp(self):
        """AC-B-CLS2 — hit hard 16 vs 10 (optimal=hit, Sharp set member) → ('sharp', 0)."""
        from backend.game.review import classify_action  # noqa: PLC0415

        cls, loss = classify_action(
            [_h("10"), _h("6")], _h("10", "clubs"), "hit", "hit", bet=1000
        )
        assert cls == "sharp", (
            f"hit hard 16 vs 10 (optimal+Sharp) should be 'sharp', got {cls!r}"
        )
        assert loss == 0

    def test_stand_hard_12_vs_4_is_sharp(self):
        """AC-B-CLS2 — stand hard 12 vs 4 (optimal=stand, Sharp set) → ('sharp', 0)."""
        from backend.game.review import classify_action  # noqa: PLC0415

        cls, loss = classify_action(
            [_h("7"), _h("5")], _h("4"), "stand", "stand", bet=1000
        )
        assert cls == "sharp", (
            f"stand hard 12 vs 4 (optimal+Sharp) should be 'sharp', got {cls!r}"
        )
        assert loss == 0

    def test_hit_soft_18_vs_9_is_sharp(self):
        """AC-B-CLS2 — hit soft 18 vs 9 (counterintuitive optimal=hit, Sharp set) → ('sharp', 0)."""
        from backend.game.review import classify_action  # noqa: PLC0415

        cls, loss = classify_action(
            [_h("A"), _h("7", "clubs")], _h("9"), "hit", "hit", bet=1000
        )
        assert cls == "sharp", (
            f"hit soft 18 vs 9 (optimal+Sharp) should be 'sharp', got {cls!r}"
        )
        assert loss == 0

    def test_double_soft_18_vs_6_is_sharp(self):
        """AC-B-CLS2 — double soft 18 vs 6 (optimal=double, Sharp set soft-double) → ('sharp', 0)."""
        from backend.game.review import classify_action  # noqa: PLC0415

        cls, loss = classify_action(
            [_h("A"), _h("7", "clubs")], _h("6"), "double", "double", bet=1000
        )
        assert cls == "sharp", (
            f"double soft 18 vs 6 (optimal+Sharp) should be 'sharp', got {cls!r}"
        )
        assert loss == 0


# ─── AC-B-CLS3: wrong actions classified by EV-delta buckets ─────────────────

class TestCLS3EVDeltaBuckets:
    """Each test picks a case that should land clearly in a specific bucket.

    Bucket thresholds (delta = ev_best - ev_played, in bet units):
      delta <= 0.005        → "best"
      0.005 < delta <= 0.02 → "good"
      0.02 < delta <= 0.05  → "inaccuracy"
      0.05 < delta <= 0.12  → "mistake"
      delta > 0.12          → "blunder"
    """

    def test_hit_hard_20_vs_6_is_blunder(self):
        """AC-B-CLS3 — hit hard 20 (optimal=stand) → blunder; ev_loss_chips > 0."""
        from backend.game.review import classify_action  # noqa: PLC0415

        cls, loss = classify_action(
            [_h("K", "spades"), _h("Q")], _h("6"), "hit", "stand", bet=1000
        )
        assert cls == "blunder", f"hit hard 20 vs 6 should be blunder, got {cls!r}"
        assert loss > 0, "ev_loss_chips must be > 0 for a blunder"

    def test_stand_hard_8_vs_6_is_blunder(self):
        """AC-B-CLS3 — stand hard 8 (optimal=hit) → blunder."""
        from backend.game.review import classify_action  # noqa: PLC0415

        cls, loss = classify_action(
            [_h("5"), _h("3")], _h("6"), "stand", "hit", bet=1000
        )
        assert cls == "blunder", f"stand hard 8 vs 6 should be blunder, got {cls!r}"
        assert loss > 0

    def test_stand_hard_16_vs_10_is_inaccuracy(self):
        """AC-B-CLS3 — stand hard 16 vs 10 (optimal=hit) → inaccuracy."""
        from backend.game.review import classify_action  # noqa: PLC0415

        cls, _ = classify_action(
            [_h("10"), _h("6")], _h("10", "clubs"), "stand", "hit", bet=1000
        )
        assert cls == "inaccuracy", f"stand hard 16 vs 10 should be inaccuracy, got {cls!r}"

    def test_hit_hard_12_vs_4_is_inaccuracy(self):
        """AC-B-CLS3 — hit hard 12 vs 4 (optimal=stand) → inaccuracy."""
        from backend.game.review import classify_action  # noqa: PLC0415

        cls, _ = classify_action(
            [_h("7"), _h("5")], _h("4"), "hit", "stand", bet=1000
        )
        assert cls == "inaccuracy", f"hit hard 12 vs 4 should be inaccuracy, got {cls!r}"

    def test_ev_loss_chips_equals_round_bet_times_delta(self):
        """AC-B-CLS3 — ev_loss_chips == round(bet * delta) per spec Decision #4."""
        from backend.game.review import classify_action  # noqa: PLC0415
        from backend.game.blackjack.ev import action_evs, best_action_ev  # noqa: PLC0415

        hand = [_h("K", "spades"), _h("Q")]
        upcard = _h("6")
        bet = 2000

        cls, loss = classify_action(hand, upcard, "hit", "stand", bet=bet)
        evs = action_evs(hand, upcard, can_double=False, can_split=False)
        _, ev_best = best_action_ev(hand, upcard, can_double=False, can_split=False)
        ev_played = evs.get("hit", evs.get("stand", 0.0))
        delta = max(0.0, ev_best - ev_played)
        expected_loss = round(bet * delta)
        assert loss == expected_loss, (
            f"ev_loss_chips {loss} != round({bet} * {delta:.4f}) = {expected_loss}"
        )


# ─── AC-B-CLS4: anchor cases preserved ───────────────────────────────────────

class TestCLS4Anchors:
    """Mirror the exact anchor assertions from test_session_review.py.

    These must pass under the new EV-based classifier — they are the
    immovable pegs the implementer must not displace.
    """

    def test_hit_hard_20_is_blunder(self):
        """AC-B-CLS4 anchor — hit on hard 20 → blunder."""
        from backend.game.review import classify_action  # noqa: PLC0415

        cls, loss = classify_action(
            [_h("K", "spades"), _h("Q")], _h("6"), "hit", "stand", bet=1000
        )
        assert cls == "blunder"
        assert loss > 100

    def test_stand_hard_8_is_blunder(self):
        """AC-B-CLS4 anchor — stand on hard 8 → blunder."""
        from backend.game.review import classify_action  # noqa: PLC0415

        cls, _ = classify_action(
            [_h("5"), _h("3")], _h("6"), "stand", "hit", bet=1000
        )
        assert cls == "blunder"

    def test_double_hard_17_is_blunder(self):
        """AC-B-CLS4 anchor — double on hard 17 → blunder."""
        from backend.game.review import classify_action  # noqa: PLC0415

        cls, _ = classify_action(
            [_h("10"), _h("7")], _h("6"), "double", "stand", bet=1000
        )
        assert cls == "blunder"

    def test_hit_hard_12_vs_4_is_inaccuracy(self):
        """AC-B-CLS4 anchor — hit hard 12 vs 4 (optimal=stand) → inaccuracy."""
        from backend.game.review import classify_action  # noqa: PLC0415

        cls, _ = classify_action(
            [_h("7"), _h("5")], _h("4"), "hit", "stand", bet=1000
        )
        assert cls == "inaccuracy"

    def test_stand_hard_16_vs_10_is_inaccuracy(self):
        """AC-B-CLS4 anchor — stand hard 16 vs 10 (optimal=hit) → inaccuracy."""
        from backend.game.review import classify_action  # noqa: PLC0415

        cls, _ = classify_action(
            [_h("10"), _h("6")], _h("10", "clubs"), "stand", "hit", bet=1000
        )
        assert cls == "inaccuracy"

    def test_hit_hard_11_vs_ace_is_inaccuracy(self):
        """AC-B-CLS4 anchor — hit hard 11 vs ace (optimal=double) → inaccuracy."""
        from backend.game.review import classify_action  # noqa: PLC0415

        cls, _ = classify_action(
            [_h("6"), _h("5")], _h("A", "spades"), "hit", "double", bet=1000
        )
        assert cls == "inaccuracy", (
            f"hit hard 11 vs ace (optimal=double) should be inaccuracy; got {cls!r}"
        )


# ─── AC-B-CLS5: split fallback for always-split pairs ────────────────────────

class TestCLS5SplitFallback:
    def test_miss_split_aces_is_blunder(self):
        """AC-B-CLS5 — A,A with optimal=split, player stands → blunder."""
        from backend.game.review import classify_action  # noqa: PLC0415

        cls, _ = classify_action(
            [_h("A"), _h("A", "spades")], _h("6"), "stand", "split", bet=1000
        )
        assert cls == "blunder", f"missing split aces should be blunder, got {cls!r}"

    def test_miss_split_88_is_blunder(self):
        """AC-B-CLS5 — 8,8 with optimal=split, player stands → blunder."""
        from backend.game.review import classify_action  # noqa: PLC0415

        cls, _ = classify_action(
            [_h("8"), _h("8", "spades")], _h("10", "clubs"), "stand", "split", bet=1000
        )
        assert cls == "blunder", f"missing split 8s should be blunder, got {cls!r}"

    def test_stand_44_vs_2_is_blunder(self):
        """AC-B-CLS5 — 4,4 vs 2, optimal=hit, player stands → blunder (treated as hard 8)."""
        from backend.game.review import classify_action  # noqa: PLC0415

        cls, _ = classify_action(
            [_h("4"), _h("4", "spades")], _h("2"), "stand", "hit", bet=1000
        )
        assert cls == "blunder", f"4,4 vs 2 stand (optimal=hit) should be blunder, got {cls!r}"


# ─── AC-B-CLS6: Sharp curated set exact membership ────────────────────────────

class TestCLS6SharpCuratedSet:
    """Test each category of Sharp-set membership and non-membership.

    Sharp set per spec Decision #5:
      - stand hard 12 vs {4, 5, 6}
      - hit hard 16 vs {10, A}
      - double soft 13–18 vs weak (upcard 4, 5, 6 — the soft-double cells)
      - hit soft 18 vs {9, 10, A}
      - split 8s vs {9, 10, A}  (handled as "split optimal → blunder" in v1;
        when player plays optimally the score is sharp — but split is 501 so
        classify_action receives optimal="split" only when the player DID split,
        which is currently impossible. Test the stand-hard-12 and hit-16 and
        hit-soft-18 cases which are reachable.)
      - split aces (any upcard) — same caveat; not directly testable via classify_action

    Obvious plays NOT in sharp set: stand hard 20, hit hard 5, stand hard 19.
    """

    def test_stand_hard_12_vs_5_is_sharp(self):
        """AC-B-CLS6 — stand 12 vs 5 → 'sharp'."""
        from backend.game.review import classify_action  # noqa: PLC0415

        cls, _ = classify_action(
            [_h("7"), _h("5")], _h("5"), "stand", "stand", bet=1000
        )
        assert cls == "sharp", f"stand hard 12 vs 5 should be sharp, got {cls!r}"

    def test_stand_hard_12_vs_6_is_sharp(self):
        """AC-B-CLS6 — stand 12 vs 6 → 'sharp'."""
        from backend.game.review import classify_action  # noqa: PLC0415

        cls, _ = classify_action(
            [_h("7"), _h("5")], _h("6"), "stand", "stand", bet=1000
        )
        assert cls == "sharp", f"stand hard 12 vs 6 should be sharp, got {cls!r}"

    def test_hit_hard_16_vs_ace_is_sharp(self):
        """AC-B-CLS6 — hit hard 16 vs A → 'sharp'."""
        from backend.game.review import classify_action  # noqa: PLC0415

        cls, _ = classify_action(
            [_h("10"), _h("6")], _h("A", "spades"), "hit", "hit", bet=1000
        )
        assert cls == "sharp", f"hit hard 16 vs A should be sharp, got {cls!r}"

    def test_double_soft_15_vs_6_is_sharp(self):
        """AC-B-CLS6 — double soft 15 vs 6 (soft-double cell) → 'sharp'."""
        from backend.game.review import classify_action  # noqa: PLC0415

        # A+4 = soft 15, upcard 6 → strategy says double
        cls, _ = classify_action(
            [_h("A"), _h("4", "clubs")], _h("6"), "double", "double", bet=1000
        )
        assert cls == "sharp", f"double soft 15 vs 6 should be sharp, got {cls!r}"

    def test_hit_soft_18_vs_10_is_sharp(self):
        """AC-B-CLS6 — hit soft 18 vs 10 → 'sharp'."""
        from backend.game.review import classify_action  # noqa: PLC0415

        cls, _ = classify_action(
            [_h("A"), _h("7", "clubs")], _h("10", "clubs"), "hit", "hit", bet=1000
        )
        assert cls == "sharp", f"hit soft 18 vs 10 should be sharp, got {cls!r}"

    def test_hit_soft_18_vs_ace_is_sharp(self):
        """AC-B-CLS6 — hit soft 18 vs A → 'sharp'."""
        from backend.game.review import classify_action  # noqa: PLC0415

        cls, _ = classify_action(
            [_h("A"), _h("7", "clubs")], _h("A", "spades"), "hit", "hit", bet=1000
        )
        assert cls == "sharp", f"hit soft 18 vs A should be sharp, got {cls!r}"

    # Obvious plays — must NOT be sharp
    def test_stand_hard_20_vs_6_is_best_not_sharp(self):
        """AC-B-CLS6 — stand hard 20 vs 6 → 'best', NOT 'sharp'."""
        from backend.game.review import classify_action  # noqa: PLC0415

        cls, _ = classify_action(
            [_h("K", "spades"), _h("Q")], _h("6"), "stand", "stand", bet=1000
        )
        assert cls == "best", f"stand hard 20 (obvious play) should be 'best', got {cls!r}"

    def test_hit_hard_5_vs_6_is_best_not_sharp(self):
        """AC-B-CLS6 — hit hard 5 vs 6 → 'best', NOT 'sharp'."""
        from backend.game.review import classify_action  # noqa: PLC0415

        cls, _ = classify_action(
            [_h("2"), _h("3")], _h("6"), "hit", "hit", bet=1000
        )
        assert cls == "best", f"hit hard 5 (obvious play) should be 'best', got {cls!r}"

    def test_stand_hard_19_vs_8_is_best_not_sharp(self):
        """AC-B-CLS6 — stand hard 19 vs 8 → 'best', NOT 'sharp'."""
        from backend.game.review import classify_action  # noqa: PLC0415

        cls, _ = classify_action(
            [_h("10"), _h("9")], _h("8"), "stand", "stand", bet=1000
        )
        assert cls == "best", f"stand hard 19 (obvious play) should be 'best', got {cls!r}"


# ─── AC-B-CLS7: pure and deterministic ───────────────────────────────────────

class TestCLS7Deterministic:
    def test_same_inputs_same_outputs(self):
        """AC-B-CLS7 — classify_action is pure: same inputs → identical outputs."""
        from backend.game.review import classify_action  # noqa: PLC0415

        a = classify_action([_h("10"), _h("Q")], _h("6"), "hit", "stand", bet=1000)
        b = classify_action([_h("10"), _h("Q")], _h("6"), "hit", "stand", bet=1000)
        assert a == b

    def test_sharp_case_deterministic(self):
        """AC-B-CLS7 — Sharp case is also deterministic."""
        from backend.game.review import classify_action  # noqa: PLC0415

        a = classify_action([_h("10"), _h("6")], _h("10", "clubs"), "hit", "hit", bet=1000)
        b = classify_action([_h("10"), _h("6")], _h("10", "clubs"), "hit", "hit", bet=1000)
        assert a == b


# ─── AC-B-CLS8: pre-double action priced at initial bet ───────────────────────

class TestCLS8PerActionBetPricing:
    def test_wrong_stand_before_double_priced_at_initial_bet(self):
        """AC-B-CLS8 — a wrong stand (inaccuracy) is priced at initial bet, not 2×.

        stand hard 16 vs 10 (optimal=hit) is ~3% EV loss.
        At 1000 chips: ~30. At 2000 chips: ~60. The test asserts the result
        with bet=1000 is less than 50 (if the bug were present it would use 2000).
        """
        from backend.game.review import classify_action  # noqa: PLC0415

        # Pass bet=1000 (the initial bet before doubling)
        cls, loss_at_initial = classify_action(
            [_h("10"), _h("6")], _h("10", "clubs"), "stand", "hit", bet=1000
        )
        assert cls == "inaccuracy"

        # Pass bet=2000 (doubled stake — what the bugged version would use)
        _, loss_at_doubled = classify_action(
            [_h("10"), _h("6")], _h("10", "clubs"), "stand", "hit", bet=2000
        )

        # The loss at initial bet must be exactly half of loss at doubled bet
        # (linear pricing — if the delta is the same, chips scale with bet).
        assert loss_at_initial < loss_at_doubled, (
            "ev_loss_chips should scale with bet; initial-bet loss must be less than doubled-bet loss"
        )
        # And the initial-bet loss should be < 50 (the anchor from test_session_review.py)
        assert loss_at_initial < 50, (
            f"pre-double action priced at initial bet should give < 50 chips loss, "
            f"got {loss_at_initial} — check bet=1000 is being used"
        )


# ─── Classification Literal includes "sharp" ──────────────────────────────────

def test_classification_literal_includes_sharp():
    """AC-B-CLS2 prerequisite — Classification type includes 'sharp'."""
    from backend.schemas import Classification  # noqa: PLC0415
    import typing  # noqa: PLC0415

    # Pydantic/Literal: get_args returns the allowed values
    args = typing.get_args(Classification)
    assert "sharp" in args, (
        f"Classification literal does not include 'sharp'; got: {args}"
    )
