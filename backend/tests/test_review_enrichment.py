"""
test_review_enrichment.py — Task 6 review enrichment tests.

Maps 1-to-1 to acceptance criteria:
  AC-S-REV1  — ReviewActionOut has new optional fields
  AC-S-REV2  — SessionReviewOut has sharp_count + blunder_count
  AC-R-REV1  — GET /api/sessions/{id}/review populates per-action EV fields
  AC-R-REV2  — session with one Sharp + one blunder → sharp_count==1, blunder_count==1
  AC-R-REV3  — existing review behavior unchanged (guard against regression)

All tests are expected to FAIL until Task 6 is implemented:
  - backend/schemas.py (ReviewActionOut + SessionReviewOut extended)
  - backend/routers/sessions.py (_get_session_review enriched)
"""
from __future__ import annotations

import pytest

from tests.conftest import (
    TEST_USER_ID,
    seed_actions,
    seed_hand,
    seed_session,
    seed_table,
    seed_user,
)


def _h(value: str, suit: str = "hearts") -> dict:
    return {"suit": suit, "value": value}


# ─── AC-S-REV1: ReviewActionOut has new optional EV fields ───────────────────

def test_review_action_out_has_action_evs_field():
    """AC-S-REV1 — ReviewActionOut has 'action_evs: dict[str, float]' field."""
    from backend.schemas import ReviewActionOut  # noqa: PLC0415

    fields = ReviewActionOut.model_fields
    assert "action_evs" in fields, (
        "ReviewActionOut is missing 'action_evs' field (AC-S-REV1)"
    )


def test_review_action_out_has_best_action_field():
    """AC-S-REV1 — ReviewActionOut has 'best_action: str' field."""
    from backend.schemas import ReviewActionOut  # noqa: PLC0415

    fields = ReviewActionOut.model_fields
    assert "best_action" in fields, (
        "ReviewActionOut is missing 'best_action' field (AC-S-REV1)"
    )


def test_review_action_out_has_best_ev_field():
    """AC-S-REV1 — ReviewActionOut has 'best_ev: float' field."""
    from backend.schemas import ReviewActionOut  # noqa: PLC0415

    fields = ReviewActionOut.model_fields
    assert "best_ev" in fields, "ReviewActionOut is missing 'best_ev' field (AC-S-REV1)"


def test_review_action_out_has_ev_delta_field():
    """AC-S-REV1 — ReviewActionOut has 'ev_delta: float' field."""
    from backend.schemas import ReviewActionOut  # noqa: PLC0415

    fields = ReviewActionOut.model_fields
    assert "ev_delta" in fields, "ReviewActionOut is missing 'ev_delta' field (AC-S-REV1)"


def test_review_action_out_has_dealer_bust_pct_field():
    """AC-S-REV1 — ReviewActionOut has 'dealer_bust_pct: float' field."""
    from backend.schemas import ReviewActionOut  # noqa: PLC0415

    fields = ReviewActionOut.model_fields
    assert "dealer_bust_pct" in fields, (
        "ReviewActionOut is missing 'dealer_bust_pct' field (AC-S-REV1)"
    )


def test_review_action_out_existing_fields_unchanged():
    """AC-S-REV1 — Existing ReviewActionOut fields are still present."""
    from backend.schemas import ReviewActionOut  # noqa: PLC0415

    fields = ReviewActionOut.model_fields
    required_existing = [
        "id", "hand_id", "user_id", "action", "player_guess", "optimal_action",
        "was_correct", "hand_snapshot", "dealer_upcard", "created_at",
        "classification", "ev_loss_chips",
    ]
    for fname in required_existing:
        assert fname in fields, (
            f"ReviewActionOut is missing previously existing field '{fname}'"
        )


# ─── AC-S-REV2: SessionReviewOut has sharp_count + blunder_count ─────────────

def test_session_review_out_has_sharp_count():
    """AC-S-REV2 — SessionReviewOut has 'sharp_count: int' field."""
    from backend.schemas import SessionReviewOut  # noqa: PLC0415

    fields = SessionReviewOut.model_fields
    assert "sharp_count" in fields, (
        "SessionReviewOut is missing 'sharp_count' field (AC-S-REV2)"
    )


def test_session_review_out_has_blunder_count():
    """AC-S-REV2 — SessionReviewOut has 'blunder_count: int' field."""
    from backend.schemas import SessionReviewOut  # noqa: PLC0415

    fields = SessionReviewOut.model_fields
    assert "blunder_count" in fields, (
        "SessionReviewOut is missing 'blunder_count' field (AC-S-REV2)"
    )


def test_session_review_out_existing_fields_unchanged():
    """AC-S-REV2 — Existing SessionReviewOut fields still present."""
    from backend.schemas import SessionReviewOut  # noqa: PLC0415

    fields = SessionReviewOut.model_fields
    required = [
        "session_id", "hand_id", "total_actions", "optimal_count",
        "accuracy", "ev_lost_chips", "worst_action_id", "actions",
    ]
    for fname in required:
        assert fname in fields, (
            f"SessionReviewOut is missing previously existing field '{fname}'"
        )


# ─── AC-R-REV1: endpoint populates per-action EV fields ───────────────────────

@pytest.mark.asyncio
async def test_review_populates_action_evs_and_dealer_bust_pct(client, db):
    """AC-R-REV1 — GET /api/sessions/{id}/review populates action_evs (non-empty),
    best_action, best_ev, ev_delta, dealer_bust_pct per action.

    dealer_bust_pct for upcard '6' is 0.42 per odds.py.
    """
    user = await seed_user(db, TEST_USER_ID, "revuser1")
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
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["actions"]) == 1
    action = body["actions"][0]

    # action_evs must be a non-empty dict
    assert "action_evs" in action, "action 'action_evs' field missing (AC-R-REV1)"
    assert isinstance(action["action_evs"], dict), "action_evs must be a dict"
    assert len(action["action_evs"]) > 0, "action_evs must be non-empty"

    # best_action must be a string
    assert "best_action" in action, "action 'best_action' field missing"
    assert isinstance(action["best_action"], str)

    # best_ev is a float
    assert "best_ev" in action, "action 'best_ev' field missing"

    # ev_delta is a non-negative float
    assert "ev_delta" in action, "action 'ev_delta' field missing"
    assert action["ev_delta"] >= 0.0

    # dealer_bust_pct for upcard '6' must be 0.42 (from odds.py)
    assert "dealer_bust_pct" in action, "action 'dealer_bust_pct' field missing"
    assert action["dealer_bust_pct"] == pytest.approx(0.42), (
        f"dealer_bust_pct for upcard '6' should be 0.42, got {action['dealer_bust_pct']}"
    )


@pytest.mark.asyncio
async def test_review_populates_aggregates(client, db):
    """AC-R-REV1 — GET /api/sessions/{id}/review response includes sharp_count and blunder_count."""
    user = await seed_user(db, TEST_USER_ID, "revuser_agg")
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
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert "sharp_count" in body, "SessionReviewOut missing 'sharp_count' (AC-R-REV1)"
    assert "blunder_count" in body, "SessionReviewOut missing 'blunder_count' (AC-R-REV1)"
    assert isinstance(body["sharp_count"], int)
    assert isinstance(body["blunder_count"], int)


# ─── AC-R-REV2: one Sharp + one blunder → sharp_count==1, blunder_count==1 ───

@pytest.mark.asyncio
async def test_review_counts_sharp_and_blunder(client, db):
    """AC-R-REV2 — session with one Sharp decision + one blunder → sharp_count==1, blunder_count==1.

    Sharp decision: hit hard 16 vs 10 (optimal=hit → Sharp set).
    Blunder: hit on hard 20 vs 6 (optimal=stand).
    """
    user = await seed_user(db, TEST_USER_ID, "revuser2")
    table = await seed_table(db)
    session = await seed_session(db, table.id, status="finished")
    hand = await seed_hand(db, session.id, user.id, bet=1000)
    await seed_actions(db, hand.id, user.id, [
        # Sharp decision: player hit hard 16 vs 10 — optimal=hit, Sharp set
        {
            "action": "hit",
            "player_guess": "hit",
            "optimal_action": "hit",
            "was_correct": True,
            "hand_snapshot": [{"suit": "hearts", "value": "10"}, {"suit": "clubs", "value": "6"}],
            "dealer_upcard": {"suit": "spades", "value": "10"},
        },
        # Blunder: player hit hard 20 vs 6 — optimal=stand, massive EV loss
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
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["sharp_count"] == 1, (
        f"Expected sharp_count == 1, got {body['sharp_count']}"
    )
    assert body["blunder_count"] == 1, (
        f"Expected blunder_count == 1, got {body['blunder_count']}"
    )


# ─── AC-R-REV3: existing review behavior unchanged ────────────────────────────

@pytest.mark.asyncio
async def test_review_existing_accuracy_behavior_unchanged(client, db):
    """AC-R-REV3 — existing review behavior preserved: accuracy, access rules,
    empty-actions → zero accuracy, worst_action ordering.
    """
    user = await seed_user(db, TEST_USER_ID, "revuser3")
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

    # Legacy fields still correct
    assert body["session_id"] == str(session.id)
    assert body["hand_id"] == str(hand.id)
    assert body["total_actions"] == 2
    assert body["optimal_count"] == 1
    assert body["accuracy"] == pytest.approx(0.5)
    assert len(body["actions"]) == 2
    assert body["actions"][0]["action"] == "hit"
    assert body["actions"][1]["action"] == "stand"
    assert body["actions"][1]["classification"] == "blunder"


@pytest.mark.asyncio
async def test_review_empty_actions_returns_zero_sharp_and_blunder(client, db):
    """AC-R-REV3 — empty actions → sharp_count == 0, blunder_count == 0."""
    user = await seed_user(db, TEST_USER_ID, "revuser4")
    table = await seed_table(db)
    session = await seed_session(db, table.id, status="playing")
    await seed_hand(db, session.id, user.id, bet=1000)

    resp = await client.get(f"/api/sessions/{session.id}/review")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_actions"] == 0
    assert body["accuracy"] == 0.0
    assert body.get("sharp_count", 0) == 0
    assert body.get("blunder_count", 0) == 0
