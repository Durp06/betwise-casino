"""
test_session_review.py — Hand Review session-level endpoint tests.

Maps 1-to-1 to acceptance criteria AC-B1 through AC-B11 and AC-T1.
All tests are expected to FAIL until the implementer completes:
  - backend/schemas.py  (ReviewActionOut, SessionReviewOut)
  - backend/game/review.py  (classify_action)
  - backend/routers/sessions.py  (GET /api/sessions/{id}/review)
  - backend/main.py  (router registration)
"""

from __future__ import annotations

import pytest

from tests.conftest import (
    OTHER_USER_ID,
    TEST_USER_ID,
    seed_actions,
    seed_hand,
    seed_session,
    seed_table,
    seed_user,
)


# ─── AC-B4, AC-B5: Pydantic schema exports ───────────────────────────────────

def test_schemas_export_review_types():
    """AC-B4 / AC-B5 — schemas.py must export ReviewActionOut and SessionReviewOut."""
    from backend.schemas import ReviewActionOut, SessionReviewOut  # noqa: F401


# ─── classify_action unit tests ──────────────────────────────────────────────

def _h(value: str, suit: str = "hearts") -> dict:
    """Helper: build a card dict."""
    return {"suit": suit, "value": value}


class TestClassifyActionBest:
    def test_correct_play_is_best_with_zero_loss(self):
        """AC-B6 — player_action == optimal_action returns ('best', 0)."""
        from backend.game.review import classify_action  # type: ignore[import]

        cls, loss = classify_action(
            [_h("5"), _h("3")], _h("6"), "hit", "hit", bet=1000,
        )
        assert cls == "best"
        assert loss == 0


class TestClassifyActionBlunder:
    def test_hit_on_hard_20_is_blunder(self):
        """AC-B7 anchor: hit on hard 20 (any dealer upcard) → blunder."""
        from backend.game.review import classify_action  # type: ignore[import]

        cls, loss = classify_action(
            [_h("K", "spades"), _h("Q")], _h("6"), "hit", "stand", bet=1000,
        )
        assert cls == "blunder"
        assert loss > 100  # > 10% of 1000

    def test_stand_on_hard_8_is_blunder(self):
        """AC-B7 anchor: stand on hard 8 (any dealer upcard) → blunder."""
        from backend.game.review import classify_action  # type: ignore[import]

        cls, _ = classify_action(
            [_h("5"), _h("3")], _h("6"), "stand", "hit", bet=1000,
        )
        assert cls == "blunder"

    def test_double_on_hard_17_is_blunder(self):
        """AC-B7 anchor: double on hard 17 (any dealer upcard) → blunder."""
        from backend.game.review import classify_action  # type: ignore[import]

        cls, _ = classify_action(
            [_h("10"), _h("7")], _h("6"), "double", "stand", bet=1000,
        )
        assert cls == "blunder"


class TestClassifyActionInaccuracy:
    def test_hit_hard_12_vs_4_is_inaccuracy(self):
        """AC-B7 anchor: hard 12 vs dealer 4, optimal is stand, player hits → inaccuracy.

        Basic strategy: hard 12 vs 4 = STAND is optimal.
        Hit here is a close-call deviation that falls in the inaccuracy bucket
        (0.01 < ev_loss_pct <= 0.04).
        """
        from backend.game.review import classify_action  # type: ignore[import]

        cls, _ = classify_action(
            [_h("7"), _h("5")], _h("4"), "hit", "stand", bet=1000,
        )
        assert cls == "inaccuracy"

    def test_stand_hard_16_vs_10_is_inaccuracy(self):
        """AC-B7 anchor: hard 16 vs dealer 10, optimal is hit, player stands → inaccuracy."""
        from backend.game.review import classify_action  # type: ignore[import]

        cls, _ = classify_action(
            [_h("10"), _h("6")], _h("10", "clubs"), "stand", "hit", bet=1000,
        )
        assert cls == "inaccuracy"


class TestClassifyActionDeterministic:
    def test_same_inputs_same_outputs(self):
        """AC-B7 reproducibility: pure function — same inputs always produce same outputs."""
        from backend.game.review import classify_action  # type: ignore[import]

        a = classify_action([_h("10"), _h("Q")], _h("6"), "hit", "stand", bet=1000)
        b = classify_action([_h("10"), _h("Q")], _h("6"), "hit", "stand", bet=1000)
        assert a == b


class TestClassifyActionPairRouting:
    """Regression for oracle finding: splittable pairs in non-split spots
    used to fall into the pair_other_split bucket even when basic strategy
    said to play the hand total. 4,4 vs 2 → strategy says HIT (it's hard
    8); standing on it should be graded as a hard-8 blunder, not pair-bucket
    noise.
    """

    def test_stand_on_44_vs_2_is_blunder_treated_as_hard_8(self):
        from backend.game.review import classify_action  # type: ignore[import]

        # 4,4 vs dealer 2 — strategy.py PAIRS["4"][2] is HIT (treat as hard 8),
        # so optimal_action recorded is "hit". Player stood. This is the
        # same situation as stand-on-hard-8-vs-6 → blunder.
        cls, _ = classify_action(
            [_h("4"), _h("4", "spades")], _h("2"), "stand", "hit", bet=1000,
        )
        assert cls == "blunder", (
            f"4,4 vs 2 with optimal=hit should be graded as a hard-8 blunder; got {cls}"
        )

    def test_split_aces_still_uses_pair_bucket(self):
        from backend.game.review import classify_action  # type: ignore[import]

        # A,A is always split; missing the split is a real pair-bucket call.
        # Should NOT fall through to hard/soft totals.
        cls, _ = classify_action(
            [_h("A"), _h("A", "spades")], _h("6"), "stand", "split", bet=1000,
        )
        assert cls == "blunder"

    def test_split_88_still_uses_pair_bucket(self):
        from backend.game.review import classify_action  # type: ignore[import]

        # 8,8 is always split; standing on it is a pair-bucket blunder.
        cls, _ = classify_action(
            [_h("8"), _h("8", "spades")], _h("10", "clubs"), "stand", "split", bet=1000,
        )
        assert cls == "blunder"


class TestClassifyActionHard11VsAce:
    """Regression for oracle finding: the hard_11/ace row used to grade
    'double' as the wrong action, but strategy.py says double IS optimal
    here. The deviation that needs grading is 'hit' (the common defensive
    play), and it should land in the inaccuracy bucket, not full mistake.
    """

    def test_hit_on_hard_11_vs_ace_is_inaccuracy(self):
        from backend.game.review import classify_action  # type: ignore[import]

        cls, _ = classify_action(
            [_h("6"), _h("5")], _h("A", "spades"), "hit", "double", bet=1000,
        )
        assert cls == "inaccuracy", (
            f"hit on hard 11 vs ace (optimal=double) should be inaccuracy; got {cls}"
        )


@pytest.mark.asyncio
async def test_review_uses_per_action_bet_when_hand_doubled(client, db):
    """Regression for oracle finding: pre-double actions used to be re-priced
    at the doubled stake because the loop passed hand.bet (the final, doubled
    value) into every classify_action call. A wrong stand BEFORE the double
    should be priced at the initial bet, not 2x.
    """
    user = await seed_user(db, TEST_USER_ID, "doublepricing")
    table = await seed_table(db)
    session = await seed_session(db, table.id, status="finished")
    # Final bet is 2000 because the hand was doubled. Initial was 1000.
    hand = await seed_hand(db, session.id, user.id, bet=2000)
    actions = await seed_actions(db, hand.id, user.id, [
        # A wrong stand on hard 16 vs 10 → inaccuracy. Pre-double, so the
        # EV cost should be ~3% of 1000 = ~30 chips, NOT ~3% of 2000 = ~60.
        {"action": "stand", "optimal_action": "hit", "was_correct": False,
         "hand_snapshot": [{"suit": "hearts", "value": "10"},
                           {"suit": "clubs", "value": "6"}],
         "dealer_upcard": {"suit": "spades", "value": "10"}},
        # The double itself — wagered 2x. Doesn't matter for this test.
        {"action": "double", "optimal_action": "double", "was_correct": True,
         "hand_snapshot": [{"suit": "hearts", "value": "10"},
                           {"suit": "clubs", "value": "6"}],
         "dealer_upcard": {"suit": "spades", "value": "10"}},
    ])

    resp = await client.get(f"/api/sessions/{session.id}/review")
    assert resp.status_code == 200
    body = resp.json()
    pre_double_loss = body["actions"][0]["ev_loss_chips"]
    # If the bug were present, pre_double_loss would be ~60 (3% of 2000).
    # With the fix it should be ~30 (3% of 1000). Allow a wide band for the
    # heuristic bucket; the key assertion is that it's STRICTLY less than
    # what 2x pricing would produce.
    assert pre_double_loss < 50, (
        f"pre-double action got re-priced at doubled stake: ev_loss={pre_double_loss}"
    )


# ─── Endpoint tests ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_review_returns_200_for_owner_with_actions(client, db):
    """AC-B1, AC-B4, AC-B11 — 200 for the calling user who has a hand with actions.

    Seeds 2 actions: one correct hit (best), one wrong stand on hard 8 vs 6 (blunder).
    Expects accuracy=0.5, blunder classification on the second action.
    """
    user = await seed_user(db, TEST_USER_ID, "reviewuser")
    table = await seed_table(db)
    session = await seed_session(db, table.id, status="playing")
    hand = await seed_hand(db, session.id, user.id, bet=1000)
    await seed_actions(db, hand.id, user.id, [
        {
            "action": "hit",
            "player_guess": "hit",
            "optimal_action": "hit",
            "was_correct": True,
            "hand_snapshot": [{"suit": "hearts", "value": "5"}, {"suit": "clubs", "value": "3"}],
            "dealer_upcard": {"suit": "clubs", "value": "6"},
        },
        {
            "action": "stand",
            "player_guess": "stand",
            "optimal_action": "hit",
            "was_correct": False,
            "hand_snapshot": [{"suit": "hearts", "value": "5"}, {"suit": "clubs", "value": "3"}],
            "dealer_upcard": {"suit": "clubs", "value": "6"},
        },
    ])

    resp = await client.get(f"/api/sessions/{session.id}/review")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["session_id"] == str(session.id)
    assert body["hand_id"] == str(hand.id)
    assert body["total_actions"] == 2
    assert body["optimal_count"] == 1
    assert body["accuracy"] == pytest.approx(0.5)
    assert len(body["actions"]) == 2
    # Actions ordered ascending by created_at
    assert body["actions"][0]["action"] == "hit"
    assert body["actions"][1]["action"] == "stand"
    # Wrong call: stand on hard 8 vs dealer 6 → blunder
    assert body["actions"][1]["classification"] == "blunder"
    # Total ev_lost_chips equals at least the blunder's individual loss
    assert body["ev_lost_chips"] >= body["actions"][1]["ev_loss_chips"]


@pytest.mark.asyncio
async def test_review_404_when_session_has_no_caller_hand_and_finished(client, db):
    """AC-B2 — 404 when session is finished and caller has no hand in it.

    The 'detail' field must NOT be the generic FastAPI 'Not Found' string —
    it must come from the session-review handler, confirming the route exists.
    """
    await seed_user(db, TEST_USER_ID, "ownerless")
    table = await seed_table(db)
    session = await seed_session(db, table.id, status="finished")

    resp = await client.get(f"/api/sessions/{session.id}/review")
    assert resp.status_code == 404
    # Must be a handler-level 404, NOT a generic "route not found" 404.
    # If the router isn't registered yet, FastAPI returns {"detail": "Not Found"}
    # which does NOT contain "hand" or "session" in the message.
    detail = resp.json().get("detail", "")
    assert detail != "Not Found", (
        "Got a generic 404 — the /api/sessions/{id}/review route is not registered yet."
    )


@pytest.mark.asyncio
async def test_review_403_when_no_caller_hand_and_session_unfinished(client, db):
    """AC-B3 — 403 when caller has no hand and session is still in progress."""
    await seed_user(db, TEST_USER_ID, "stranger")
    other = await seed_user(db, OTHER_USER_ID, "other")
    table = await seed_table(db)
    session = await seed_session(db, table.id, status="playing")
    # Another user has a hand so the session is non-empty; caller (TEST_USER_ID) has none.
    await seed_hand(db, session.id, other.id, bet=1000)

    resp = await client.get(f"/api/sessions/{session.id}/review")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_review_worst_action_is_largest_ev_loss(client, db):
    """AC-B8 — worst_action_id points to the action with the strictly largest ev_loss_chips.

    Seeds two wrong actions: inaccuracy (stand on hard 16 vs 10) and blunder (hit on hard 20).
    Expects worst_action_id == blunder action id.
    """
    user = await seed_user(db, TEST_USER_ID, "worsttest")
    table = await seed_table(db)
    session = await seed_session(db, table.id, status="finished")
    hand = await seed_hand(db, session.id, user.id, bet=1000)
    actions = await seed_actions(db, hand.id, user.id, [
        # Small mistake: stand on hard 16 vs 10 → inaccuracy
        {
            "action": "stand",
            "player_guess": "stand",
            "optimal_action": "hit",
            "was_correct": False,
            "hand_snapshot": [{"suit": "hearts", "value": "10"}, {"suit": "clubs", "value": "6"}],
            "dealer_upcard": {"suit": "spades", "value": "10"},
        },
        # Large mistake: hit on hard 20 → blunder
        {
            "action": "hit",
            "player_guess": "hit",
            "optimal_action": "stand",
            "was_correct": False,
            "hand_snapshot": [{"suit": "hearts", "value": "K"}, {"suit": "clubs", "value": "Q"}],
            "dealer_upcard": {"suit": "spades", "value": "6"},
        },
    ])

    resp = await client.get(f"/api/sessions/{session.id}/review")
    assert resp.status_code == 200
    body = resp.json()
    # The blunder (second action, hard 20 hit) has the larger ev_loss_chips
    assert body["worst_action_id"] == str(actions[1].id)


@pytest.mark.asyncio
async def test_review_worst_action_none_when_all_correct(client, db):
    """AC-B8 — worst_action_id is None when every action is 'best'."""
    user = await seed_user(db, TEST_USER_ID, "perfect")
    table = await seed_table(db)
    session = await seed_session(db, table.id, status="playing")
    hand = await seed_hand(db, session.id, user.id, bet=1000)
    await seed_actions(db, hand.id, user.id, [
        {
            "action": "stand",
            "player_guess": "stand",
            "optimal_action": "stand",
            "was_correct": True,
            "hand_snapshot": [{"suit": "hearts", "value": "10"}, {"suit": "clubs", "value": "9"}],
            "dealer_upcard": {"suit": "spades", "value": "6"},
        },
    ])

    resp = await client.get(f"/api/sessions/{session.id}/review")
    assert resp.status_code == 200
    body = resp.json()
    assert body["worst_action_id"] is None
    assert body["ev_lost_chips"] == 0


@pytest.mark.asyncio
async def test_review_empty_actions_returns_zero_accuracy(client, db):
    """AC-B11 — accuracy is 0.0 when total_actions is 0 (hand exists but no actions yet)."""
    user = await seed_user(db, TEST_USER_ID, "noactions")
    table = await seed_table(db)
    session = await seed_session(db, table.id, status="playing")
    await seed_hand(db, session.id, user.id, bet=1000)

    resp = await client.get(f"/api/sessions/{session.id}/review")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_actions"] == 0
    assert body["accuracy"] == 0.0
    assert body["ev_lost_chips"] == 0
    assert body["worst_action_id"] is None
