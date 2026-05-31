"""
test_practice_grade.py — Task 7 practice grading endpoint tests.

Maps 1-to-1 to acceptance criteria:
  AC-S-PR1  — PracticeGradeIn / PracticeGradeOut schemas exist
  AC-R-PR1  — POST /api/practice/grade requires auth, returns 200 for valid body
  AC-R-PR2  — [10,6] vs 10, action=stand → optimal=hit, classification=inaccuracy,
              dealer_bust_pct==0.23
  AC-R-PR3  — [10,6] vs 10, action=hit → optimal=hit, classification=sharp
  AC-R-PR4  — malformed body → 422; empty hand [] → 400
  AC-R-PR5  — explanation is a non-empty string

All tests are expected to FAIL until Task 7 is implemented:
  - backend/schemas.py (PracticeGradeIn + PracticeGradeOut)
  - backend/routers/practice.py (POST /api/practice/grade)
  - backend/main.py (practice router registered)

NOTE on dealer_bust_pct for upcard "10":
  From backend/game/blackjack/odds.py: _DEALER_BUST_PCT["10"] == 0.23.
  The test pins this value directly from the odds module to remain in sync.
"""
from __future__ import annotations

import pytest

from tests.conftest import TEST_USER_ID, seed_user


# ─── AC-S-PR1: schemas exist ──────────────────────────────────────────────────

def test_practice_grade_in_schema_exists():
    """AC-S-PR1 — PracticeGradeIn schema is importable from backend.schemas."""
    from backend.schemas import PracticeGradeIn  # noqa: F401


def test_practice_grade_out_schema_exists():
    """AC-S-PR1 — PracticeGradeOut schema is importable from backend.schemas."""
    from backend.schemas import PracticeGradeOut  # noqa: F401


def test_practice_grade_in_has_required_fields():
    """AC-S-PR1 — PracticeGradeIn has 'hand', 'dealer_upcard', 'action' fields."""
    from backend.schemas import PracticeGradeIn  # noqa: PLC0415

    fields = PracticeGradeIn.model_fields
    for fname in ("hand", "dealer_upcard", "action"):
        assert fname in fields, f"PracticeGradeIn missing required field '{fname}'"


def test_practice_grade_out_has_required_fields():
    """AC-S-PR1 — PracticeGradeOut has all required response fields."""
    from backend.schemas import PracticeGradeOut  # noqa: PLC0415

    fields = PracticeGradeOut.model_fields
    required = [
        "optimal_action", "action_evs", "best_ev", "ev_delta",
        "classification", "dealer_bust_pct", "explanation",
    ]
    for fname in required:
        assert fname in fields, f"PracticeGradeOut missing required field '{fname}'"


# ─── AC-R-PR1: endpoint requires auth, returns 200 for valid body ─────────────

@pytest.mark.asyncio
async def test_practice_grade_requires_auth(db, monkeypatch):
    """AC-R-PR1 — POST /api/practice/grade without auth returns 401."""
    from httpx import ASGITransport, AsyncClient  # noqa: PLC0415
    from backend.main import app  # noqa: PLC0415

    # The conftest sets BETWISE_DEV_USER_ID globally (auth bypass active for all
    # tests). To exercise the real JWT path and get a 401, clear it first —
    # mirrors test_endpoints.py::test_weakness_endpoint_requires_auth_returns_401.
    monkeypatch.delenv("BETWISE_DEV_USER_ID", raising=False)

    # Raw client with NO auth overrides
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.post(
            "/api/practice/grade",
            json={
                "hand": [{"suit": "hearts", "value": "10"}, {"suit": "clubs", "value": "6"}],
                "dealer_upcard": {"suit": "spades", "value": "10"},
                "action": "stand",
            },
        )
    assert resp.status_code == 401, (
        f"Expected 401 without auth, got {resp.status_code}: {resp.text}"
    )


@pytest.mark.asyncio
async def test_practice_grade_returns_200_for_valid_body(client, db):
    """AC-R-PR1 — POST /api/practice/grade returns 200 for a valid body (authenticated)."""
    await seed_user(db, TEST_USER_ID, "practiceuser1")

    resp = await client.post(
        "/api/practice/grade",
        json={
            "hand": [{"suit": "hearts", "value": "10"}, {"suit": "clubs", "value": "6"}],
            "dealer_upcard": {"suit": "spades", "value": "10"},
            "action": "stand",
        },
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "optimal_action" in body
    assert "classification" in body


@pytest.mark.asyncio
async def test_practice_grade_is_stateless(client, db):
    """AC-R-PR1 — practice endpoint is stateless: does NOT write to DB.

    First asserts the endpoint returns 200 (will fail until the route exists),
    then asserts no PlayerAction rows were created.
    """
    from sqlalchemy import select, func  # noqa: PLC0415
    from backend.models import PlayerAction  # noqa: PLC0415

    await seed_user(db, TEST_USER_ID, "practiceuser_stateless")

    # Count actions before
    result = await db.execute(select(func.count()).select_from(PlayerAction))
    count_before = result.scalar()

    resp = await client.post(
        "/api/practice/grade",
        json={
            "hand": [{"suit": "hearts", "value": "10"}, {"suit": "clubs", "value": "6"}],
            "dealer_upcard": {"suit": "spades", "value": "10"},
            "action": "hit",
        },
    )
    # Route must exist before we can verify statelessness
    assert resp.status_code == 200, (
        f"POST /api/practice/grade should return 200 (route not yet implemented): "
        f"{resp.status_code} {resp.text}"
    )

    result = await db.execute(select(func.count()).select_from(PlayerAction))
    count_after = result.scalar()
    assert count_after == count_before, (
        f"practice/grade must not write to player_actions; "
        f"count changed {count_before} → {count_after}"
    )


# ─── AC-R-PR2: [10,6] vs 10, action=stand ─────────────────────────────────────

@pytest.mark.asyncio
async def test_practice_grade_stand_hard_16_vs_10(client, db):
    """AC-R-PR2 — hand=[10,6], dealer_upcard=10, action=stand →
    optimal_action=='hit', classification=='inaccuracy', dealer_bust_pct==0.23.

    dealer_bust_pct for upcard 10 is read from odds.py to stay in sync.
    """
    from backend.game.blackjack.odds import dealer_bust_pct  # noqa: PLC0415

    expected_bust_pct = dealer_bust_pct({"suit": "spades", "value": "10"})

    await seed_user(db, TEST_USER_ID, "practiceuser2")

    resp = await client.post(
        "/api/practice/grade",
        json={
            "hand": [{"suit": "hearts", "value": "10"}, {"suit": "clubs", "value": "6"}],
            "dealer_upcard": {"suit": "spades", "value": "10"},
            "action": "stand",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["optimal_action"] == "hit", (
        f"hard 16 vs 10: optimal_action should be 'hit', got {body['optimal_action']!r}"
    )
    assert body["classification"] == "inaccuracy", (
        f"stand hard 16 vs 10: classification should be 'inaccuracy', "
        f"got {body['classification']!r}"
    )
    assert body["dealer_bust_pct"] == pytest.approx(expected_bust_pct), (
        f"dealer_bust_pct should be {expected_bust_pct} (from odds.py), "
        f"got {body['dealer_bust_pct']}"
    )


# ─── AC-R-PR3: [10,6] vs 10, action=hit → sharp ──────────────────────────────

@pytest.mark.asyncio
async def test_practice_grade_hit_hard_16_vs_10_is_sharp(client, db):
    """AC-R-PR3 — hand=[10,6], dealer_upcard=10, action=hit →
    optimal_action=='hit', classification=='sharp'.
    """
    await seed_user(db, TEST_USER_ID, "practiceuser3")

    resp = await client.post(
        "/api/practice/grade",
        json={
            "hand": [{"suit": "hearts", "value": "10"}, {"suit": "clubs", "value": "6"}],
            "dealer_upcard": {"suit": "spades", "value": "10"},
            "action": "hit",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["optimal_action"] == "hit", (
        f"hard 16 vs 10: optimal_action should be 'hit', got {body['optimal_action']!r}"
    )
    assert body["classification"] == "sharp", (
        f"hit hard 16 vs 10 (optimal+Sharp set): classification should be 'sharp', "
        f"got {body['classification']!r}"
    )


# ─── AC-R-PR4: malformed body → 422; empty hand → 400 ────────────────────────

@pytest.mark.asyncio
async def test_practice_grade_missing_dealer_upcard_is_422(client, db):
    """AC-R-PR4 — missing dealer_upcard → 422."""
    await seed_user(db, TEST_USER_ID, "practiceuser4a")

    resp = await client.post(
        "/api/practice/grade",
        json={
            "hand": [{"suit": "hearts", "value": "10"}, {"suit": "clubs", "value": "6"}],
            # dealer_upcard intentionally absent
            "action": "stand",
        },
    )
    assert resp.status_code == 422, (
        f"missing dealer_upcard should return 422, got {resp.status_code}"
    )


@pytest.mark.asyncio
async def test_practice_grade_bad_card_value_is_422(client, db):
    """AC-R-PR4 — bad card value (e.g. 'Z') → 422."""
    await seed_user(db, TEST_USER_ID, "practiceuser4b")

    resp = await client.post(
        "/api/practice/grade",
        json={
            "hand": [{"suit": "hearts", "value": "Z"}, {"suit": "clubs", "value": "6"}],
            "dealer_upcard": {"suit": "spades", "value": "10"},
            "action": "stand",
        },
    )
    assert resp.status_code == 422, (
        f"bad card value should return 422, got {resp.status_code}"
    )


@pytest.mark.asyncio
async def test_practice_grade_illegal_action_is_422(client, db):
    """AC-R-PR4 — illegal action literal → 422."""
    await seed_user(db, TEST_USER_ID, "practiceuser4c")

    resp = await client.post(
        "/api/practice/grade",
        json={
            "hand": [{"suit": "hearts", "value": "10"}, {"suit": "clubs", "value": "6"}],
            "dealer_upcard": {"suit": "spades", "value": "10"},
            "action": "surrender",  # not in Action literal
        },
    )
    assert resp.status_code == 422, (
        f"illegal action should return 422, got {resp.status_code}"
    )


@pytest.mark.asyncio
async def test_practice_grade_empty_hand_is_400(client, db):
    """AC-R-PR4 — empty hand [] → 400 (handler-level guard, not 422)."""
    await seed_user(db, TEST_USER_ID, "practiceuser4d")

    resp = await client.post(
        "/api/practice/grade",
        json={
            "hand": [],
            "dealer_upcard": {"suit": "spades", "value": "10"},
            "action": "stand",
        },
    )
    assert resp.status_code == 400, (
        f"empty hand should return 400, got {resp.status_code}: {resp.text}"
    )


# ─── AC-R-PR5: explanation is a non-empty string ─────────────────────────────

@pytest.mark.asyncio
async def test_practice_grade_explanation_is_non_empty_string(client, db):
    """AC-R-PR5 — explanation field is a non-empty human-readable string."""
    await seed_user(db, TEST_USER_ID, "practiceuser5")

    resp = await client.post(
        "/api/practice/grade",
        json={
            "hand": [{"suit": "hearts", "value": "10"}, {"suit": "clubs", "value": "6"}],
            "dealer_upcard": {"suit": "spades", "value": "10"},
            "action": "hit",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert "explanation" in body, "PracticeGradeOut missing 'explanation' field"
    explanation = body["explanation"]
    assert isinstance(explanation, str), f"explanation should be str, got {type(explanation)}"
    assert len(explanation.strip()) > 0, "explanation must be a non-empty string"


# ─── Endpoint registered under /api ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_practice_grade_route_is_under_api_prefix(client, db):
    """AC-R-PR1 — endpoint is accessible at /api/practice/grade (not /practice/grade).

    Asserts the route returns 200 (or a schema validation error), not 404/405,
    proving it is registered under the /api prefix.
    """
    await seed_user(db, TEST_USER_ID, "practiceuser_prefix")

    resp = await client.post(
        "/api/practice/grade",
        json={
            "hand": [{"suit": "hearts", "value": "10"}, {"suit": "clubs", "value": "6"}],
            "dealer_upcard": {"suit": "spades", "value": "10"},
            "action": "stand",
        },
    )
    # 404 or 405 means the router is not registered under /api
    assert resp.status_code not in (404, 405), (
        f"POST /api/practice/grade returned {resp.status_code} — "
        f"router not registered in main.py under /api prefix"
    )
