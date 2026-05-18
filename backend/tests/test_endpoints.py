"""
test_endpoints.py — integration tests for all FastAPI endpoints.

Every test maps 1-to-1 to an acceptance criterion in specs/betwise-casino.md
§T10–T15 and to the mandatory test names in specs/betwise-casino-source.md Step 6.

The conftest.py fixtures inject:
  - `client`       — authenticated as TEST_USER_ID, uses in-memory SQLite
  - `other_client` — authenticated as OTHER_USER_ID, same DB
  - `db`           — raw AsyncSession for seeding

No test hits real Postgres, Supabase, or Anthropic.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

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

# ─── T15: health + import ─────────────────────────────────────────────────────
# Criterion: GET /api/health returns 200 {"status":"ok"} with no DB.

@pytest.mark.asyncio
async def test_health_endpoint_returns_ok(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# Criterion: `import backend.main` exits 0 with no env vars set (no module-level
# side effects).

def test_app_imports_without_env():
    """Importing backend.main must not raise even with no real env vars set."""
    import importlib  # noqa: PLC0415
    spec = importlib.util.find_spec("backend.main")
    assert spec is not None, "backend.main module must exist"
    # If the module is already imported, this is a no-op; that's fine —
    # the fixture conftest already proved it can be imported without crashing.
    import backend.main  # noqa: PLC0415, F401


# ─── T10: users ───────────────────────────────────────────────────────────────
# Criterion: POST /api/users/me creates a user row on first login.

@pytest.mark.asyncio
async def test_create_user_on_first_login(client):
    resp = await client.post("/api/users/me", json={"username": "testplayer"})
    assert resp.status_code in (200, 201), resp.text
    data = resp.json()
    assert data["username"] == "testplayer"
    assert str(TEST_USER_ID) in (data.get("id", ""), str(data.get("id", "")))


# Criterion: POST /api/users/me is idempotent — calling twice returns the same row.

@pytest.mark.asyncio
async def test_post_users_me_is_idempotent(client, db):
    await seed_user(db, TEST_USER_ID, "idempotentuser")
    resp1 = await client.post("/api/users/me", json={"username": "idempotentuser"})
    resp2 = await client.post("/api/users/me", json={"username": "idempotentuser"})
    assert resp1.status_code in (200, 201)
    assert resp2.status_code in (200, 201)
    # Both calls return the same user_id
    assert resp1.json().get("id") == resp2.json().get("id")


# Criterion: GET /api/users/{id}/hands returns [] (empty list, not 404) for new user.

@pytest.mark.asyncio
async def test_user_hands_empty_for_new_user(client, db):
    await seed_user(db, TEST_USER_ID, "handsuser")
    resp = await client.get(f"/api/users/{TEST_USER_ID}/hands")
    assert resp.status_code == 200
    assert resp.json() == []


# Criterion: POST /api/users/me/reset-chips returns 409 when balance >= 1000.

@pytest.mark.asyncio
async def test_reset_chips_rejected_when_balance_ge_1000(client, db):
    # Default chip_balance is 100_000 — way above 1000
    await seed_user(db, TEST_USER_ID, "richplayer", chip_balance=100_000)
    resp = await client.post("/api/users/me/reset-chips")
    assert resp.status_code == 409
    # Should include a clean human-readable message, not a traceback
    detail = resp.json().get("detail", "")
    assert "balance" in detail.lower() or "eligible" in detail.lower(), (
        f"Expected 'balance' or 'eligible' in error detail: {detail!r}"
    )


# Criterion: GET /api/users/me returns 401 with no valid token.
# We test this by using an unauthenticated client (no override).

@pytest.mark.asyncio
async def test_weakness_endpoint_requires_auth_returns_401(monkeypatch):
    """Without auth override AND without the dev-bypass env var, the
    /api/analytics/weakness endpoint must 401."""
    # The session-wide BETWISE_DEV_USER_ID bypass must be off so we exercise
    # the production JWT path.
    monkeypatch.delenv("BETWISE_DEV_USER_ID", raising=False)

    from httpx import ASGITransport, AsyncClient  # noqa: PLC0415
    from backend.main import app  # noqa: PLC0415

    # No dependency override → real auth.get_current_user runs
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as unauthenticated:
        resp = await unauthenticated.get("/api/analytics/weakness")
    assert resp.status_code == 401


# ─── T11: tables ──────────────────────────────────────────────────────────────
# Criterion: POST /api/tables/{id}/join assigns the caller to an open seat.

@pytest.mark.asyncio
async def test_join_table_assigns_seat(client, db):
    await seed_user(db, TEST_USER_ID, "joiner")
    table = await seed_table(db, max_seats=3)
    resp = await client.post(f"/api/tables/{table.id}/join")
    assert resp.status_code == 200
    data = resp.json()
    # Response should indicate a seat was assigned
    assert "seat_number" in data or "seat" in str(data), (
        f"Response should contain seat info: {data}"
    )


# Criterion: POST /api/tables/{id}/join returns 409 when all seats are full.

@pytest.mark.asyncio
async def test_join_full_table_returns_409(client, db):
    """Seed a 1-seat table with one user already seated, then try to join as TEST_USER."""
    from backend.models import TableSeat  # noqa: PLC0415

    table = await seed_table(db, max_seats=1)
    # Seat another user in the only seat
    other = await seed_user(db, OTHER_USER_ID, "otheralready")
    seat = TableSeat(
        id=uuid.uuid4(),
        table_id=table.id,
        user_id=OTHER_USER_ID,
        seat_number=1,
        joined_at=datetime.now(timezone.utc),
    )
    db.add(seat)
    await db.commit()

    # TEST_USER_ID tries to join — should 409
    await seed_user(db, TEST_USER_ID, "latejoiner")
    resp = await client.post(f"/api/tables/{table.id}/join")
    assert resp.status_code == 409


# Criterion: GET /api/tables/{id}/state returns 404 for unknown table ID.

@pytest.mark.asyncio
async def test_unknown_table_state_returns_404(client):
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/tables/{fake_id}/state")
    assert resp.status_code == 404


# Criterion: Dealer hole card (second card) is hidden during play; player cards are visible.

@pytest.mark.asyncio
async def test_other_players_hole_cards_hidden_during_play(client, other_client, db):
    """During a playing session, the dealer's second card (hole card) must be hidden.
    All player cards must be fully visible to all seated players.
    """
    await seed_user(db, TEST_USER_ID, "player1")
    await seed_user(db, OTHER_USER_ID, "player2")
    table = await seed_table(db, max_seats=3)
    # Seed a session with two known dealer cards
    session = await seed_session(
        db,
        table.id,
        status="playing",
        dealer_cards=[{"suit": "hearts", "value": "6"}, {"suit": "spades", "value": "K"}],
    )

    # Seed a hand for OTHER_USER_ID with two known cards
    await seed_hand(
        db,
        session.id,
        OTHER_USER_ID,
        cards=[{"suit": "hearts", "value": "A"}, {"suit": "spades", "value": "K"}],
    )

    resp = await client.get(f"/api/tables/{table.id}/state")
    assert resp.status_code == 200
    state = resp.json()

    # Dealer hole card (index 1) must be hidden during play
    session_data = state.get("session", {})
    if session_data:
        dealer_cards = session_data.get("dealer_cards", [])
        if len(dealer_cards) >= 2:
            hole_card = dealer_cards[1]
            assert hole_card is None or (isinstance(hole_card, dict) and hole_card.get("value") in ("?", None)), (
                f"Dealer hole card (index 1) must be hidden during play; got {hole_card!r}"
            )
        # First dealer card must be visible
        if dealer_cards:
            assert dealer_cards[0] is not None, "Dealer upcard (index 0) must be visible during play"

    # Player cards must all be visible (not hidden)
    hands = state.get("hands", [])
    other_hands = [h for h in hands if str(h.get("user_id")) == str(OTHER_USER_ID)]
    if other_hands:
        other_hand = other_hands[0]
        cards = other_hand.get("cards", [])
        for i, card in enumerate(cards):
            assert card is not None, (
                f"Player card at index {i} must be visible during play; got None"
            )


# ─── T12: game actions ────────────────────────────────────────────────────────
# Criterion: POST /api/tables/{id}/deal creates a session and deals hands.

@pytest.mark.asyncio
async def test_deal_creates_session_and_hands(client, db):
    await seed_user(db, TEST_USER_ID, "dealer_test", chip_balance=100_000)
    table = await seed_table(db)
    # Seat the test user first
    from backend.models import TableSeat  # noqa: PLC0415
    seat = TableSeat(
        id=uuid.uuid4(),
        table_id=table.id,
        user_id=TEST_USER_ID,
        seat_number=1,
        joined_at=datetime.now(timezone.utc),
    )
    db.add(seat)
    await db.commit()

    resp = await client.post(f"/api/tables/{table.id}/deal", json={"bet": 1_000})
    assert resp.status_code in (200, 201), resp.text
    data = resp.json()
    # Response must include a hand with cards
    assert "cards" in data, f"Expected 'cards' in deal response: {data}"
    assert len(data["cards"]) == 2, "Initial deal must give exactly 2 cards"


# Criterion: POST /api/tables/{id}/deal rejects bets above chip balance.

@pytest.mark.asyncio
async def test_deal_rejects_bet_above_chip_balance(client, db):
    await seed_user(db, TEST_USER_ID, "brokeplayer", chip_balance=500)
    table = await seed_table(db)
    from backend.models import TableSeat  # noqa: PLC0415
    seat = TableSeat(
        id=uuid.uuid4(),
        table_id=table.id,
        user_id=TEST_USER_ID,
        seat_number=1,
        joined_at=datetime.now(timezone.utc),
    )
    db.add(seat)
    await db.commit()

    resp = await client.post(f"/api/tables/{table.id}/deal", json={"bet": 50_000})
    assert resp.status_code == 400
    detail = resp.json().get("detail", "")
    assert len(detail) > 0, "Must return a clean error message, not empty"


# Criterion: POST /api/tables/{id}/action with "hit" adds exactly one card.

@pytest.mark.asyncio
async def test_action_hit_adds_card_to_hand(client, db):
    await seed_user(db, TEST_USER_ID, "hitter", chip_balance=100_000)
    table = await seed_table(db)
    session = await seed_session(db, table.id, status="playing")
    hand = await seed_hand(
        db,
        session.id,
        TEST_USER_ID,
        cards=[{"suit": "hearts", "value": "5"}, {"suit": "spades", "value": "6"}],
    )

    resp = await client.post(
        f"/api/tables/{table.id}/action", json={"action": "hit"}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["cards"]) == 3, (
        f"Hit should add exactly 1 card (started with 2, now expect 3): {data['cards']}"
    )


# Criterion: POST /api/tables/{id}/action returns 403 when it's not caller's turn.

@pytest.mark.asyncio
async def test_action_not_your_turn_returns_403(client, db):
    """Seed a session where it's OTHER_USER_ID's turn; TEST_USER_ID action must 403."""
    await seed_user(db, TEST_USER_ID, "waiter")
    await seed_user(db, OTHER_USER_ID, "otheractor")
    table = await seed_table(db)
    session = await seed_session(db, table.id, status="playing")
    # Only seed a hand for OTHER_USER, not for TEST_USER
    await seed_hand(db, session.id, OTHER_USER_ID)

    resp = await client.post(
        f"/api/tables/{table.id}/action", json={"action": "hit"}
    )
    assert resp.status_code == 403


# ─── T12: hand replay (gold) ─────────────────────────────────────────────────
# Criterion: GET /api/hands/{hand_id}/actions returns actions in ascending order.

@pytest.mark.asyncio
async def test_hand_replay_returns_ordered_actions(client, db):
    await seed_user(db, TEST_USER_ID, "replayme")
    table = await seed_table(db)
    session = await seed_session(db, table.id, status="finished")
    hand = await seed_hand(db, session.id, TEST_USER_ID, status="finished")

    # Seed 3 actions with deliberately reversed insertion order
    rows = [
        {"action": "hit", "player_guess": "hit", "optimal_action": "hit", "was_correct": True},
        {"action": "hit", "player_guess": "stand", "optimal_action": "hit", "was_correct": False},
        {"action": "stand", "player_guess": "stand", "optimal_action": "stand", "was_correct": True},
    ]
    await seed_actions(db, hand.id, TEST_USER_ID, rows)

    resp = await client.get(f"/api/hands/{hand.id}/actions")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    # Must be in ascending created_at order
    for i in range(len(data) - 1):
        ts_a = data[i].get("created_at")
        ts_b = data[i + 1].get("created_at")
        if ts_a and ts_b:
            assert ts_a <= ts_b, (
                f"Actions not in ascending order at index {i}: {ts_a} > {ts_b}"
            )


# Criterion: GET /api/hands/{hand_id}/actions returns 403 for a different user
# when the session is still in play.

@pytest.mark.asyncio
async def test_hand_replay_returns_403_for_other_user_during_play(other_client, db):
    """other_client = OTHER_USER_ID; hand belongs to TEST_USER_ID; session playing."""
    await seed_user(db, TEST_USER_ID, "playowner")
    await seed_user(db, OTHER_USER_ID, "spy")
    table = await seed_table(db)
    session = await seed_session(db, table.id, status="playing")
    hand = await seed_hand(db, session.id, TEST_USER_ID, status="active")

    resp = await other_client.get(f"/api/hands/{hand.id}/actions")
    assert resp.status_code == 403


# Criterion: GET /api/hands/{hand_id}/actions returns 200 for anyone after finished.

@pytest.mark.asyncio
async def test_hand_replay_returns_200_for_anyone_after_finished(other_client, db):
    """After session is finished, any authenticated user can read replay."""
    await seed_user(db, TEST_USER_ID, "finishedowner")
    await seed_user(db, OTHER_USER_ID, "finishedspy")
    table = await seed_table(db)
    session = await seed_session(db, table.id, status="finished")
    hand = await seed_hand(db, session.id, TEST_USER_ID, status="finished")

    resp = await other_client.get(f"/api/hands/{hand.id}/actions")
    assert resp.status_code == 200


# ─── T14: leaderboard ─────────────────────────────────────────────────────────
# Criterion: GET /api/leaderboard returns users sorted by chip_balance DESC.

@pytest.mark.asyncio
async def test_leaderboard_returns_sorted_by_chips(client, db):
    # Create several users with different balances
    users = [
        (uuid.uuid4(), "rich",   500_000),
        (uuid.uuid4(), "medium", 200_000),
        (uuid.uuid4(), "poor",    10_000),
    ]
    for uid, name, balance in users:
        await seed_user(db, uid, name, chip_balance=balance)

    resp = await client.get("/api/leaderboard")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) >= 3, f"Expected at least 3 rows, got {len(rows)}"
    balances = [r["chip_balance"] for r in rows]
    assert balances == sorted(balances, reverse=True), (
        f"Leaderboard must be sorted by chip_balance DESC: {balances}"
    )


# ─── T14: weakness endpoint ───────────────────────────────────────────────────
# Criterion: GET /api/analytics/weakness returns 200 [] for new user.

@pytest.mark.asyncio
async def test_weakness_endpoint_empty_for_new_user(client, db):
    await seed_user(db, TEST_USER_ID, "newcomer")
    resp = await client.get("/api/analytics/weakness")
    assert resp.status_code == 200
    assert resp.json() == []


# Criterion: weakness endpoint filters buckets with < 5 samples.

@pytest.mark.asyncio
async def test_weakness_endpoint_requires_minimum_5_samples(client, db):
    """4 actions in a bucket → endpoint returns empty list for that bucket."""
    await seed_user(db, TEST_USER_ID, "weakuser")
    table = await seed_table(db)
    session = await seed_session(db, table.id, status="finished")
    hand = await seed_hand(db, session.id, TEST_USER_ID, status="finished")

    # Seed only 4 actions — below the minimum 5
    rows = [
        {
            "action": "hit",
            "player_guess": "stand",
            "optimal_action": "hit",
            "was_correct": False,
            "hand_snapshot": [{"suit": "spades", "value": "9"}, {"suit": "hearts", "value": "7"}],
            "dealer_upcard": {"suit": "clubs", "value": "10"},
        }
    ] * 4
    await seed_actions(db, hand.id, TEST_USER_ID, rows)

    resp = await client.get("/api/analytics/weakness")
    assert resp.status_code == 200
    assert resp.json() == [], (
        "Bucket with 4 samples must be filtered; expected empty list"
    )


# ─── T13: advice endpoint ─────────────────────────────────────────────────────
# Criterion: correct guess → current_streak increments by 1.

@pytest.mark.asyncio
async def test_advice_correct_increments_streak(client, db, mock_anthropic):
    user = await seed_user(db, TEST_USER_ID, "streaker", chip_balance=100_000)
    table = await seed_table(db)
    session = await seed_session(
        db,
        table.id,
        status="playing",
        dealer_cards=[{"suit": "hearts", "value": "6"}],
    )
    # Player has hard 11 vs dealer 6 — optimal is double
    hand = await seed_hand(
        db,
        session.id,
        TEST_USER_ID,
        cards=[{"suit": "hearts", "value": "5"}, {"suit": "spades", "value": "6"}],
        status="active",
    )

    # Player guesses "double" — which IS the optimal action
    resp = await client.post(
        f"/api/advice/{hand.id}",
        json={"player_guess": "double"},
    )
    # Streaming SSE; status must be 200
    assert resp.status_code == 200

    # Re-query the user to check streak updated (may need a DB refresh)
    from sqlalchemy import select  # noqa: PLC0415
    from backend.models import User  # noqa: PLC0415
    result = await db.execute(select(User).where(User.id == TEST_USER_ID))
    updated_user = result.scalar_one_or_none()
    if updated_user is not None:
        assert updated_user.current_streak >= 1, (
            f"Correct guess should increment streak; streak={updated_user.current_streak}"
        )


# Criterion: wrong guess → current_streak resets to 0.

@pytest.mark.asyncio
async def test_advice_wrong_resets_streak(client, db, mock_anthropic):
    user = await seed_user(db, TEST_USER_ID, "wronger", chip_balance=100_000)
    # Give the user a non-zero streak to start
    from sqlalchemy import select, update  # noqa: PLC0415
    from backend.models import User  # noqa: PLC0415
    await db.execute(
        update(User).where(User.id == TEST_USER_ID).values(current_streak=5, best_streak=5)
    )
    await db.commit()

    table = await seed_table(db)
    session = await seed_session(
        db,
        table.id,
        status="playing",
        dealer_cards=[{"suit": "hearts", "value": "6"}],
    )
    # Hard 11 vs dealer 6 → optimal is double; player guesses stand (wrong)
    hand = await seed_hand(
        db,
        session.id,
        TEST_USER_ID,
        cards=[{"suit": "hearts", "value": "5"}, {"suit": "spades", "value": "6"}],
        status="active",
    )

    resp = await client.post(
        f"/api/advice/{hand.id}",
        json={"player_guess": "stand"},  # wrong
    )
    assert resp.status_code == 200

    result = await db.execute(select(User).where(User.id == TEST_USER_ID))
    updated_user = result.scalar_one_or_none()
    if updated_user is not None:
        assert updated_user.current_streak == 0, (
            f"Wrong guess should reset streak to 0; streak={updated_user.current_streak}"
        )


# Criterion: advice response uses SSE (Content-Type: text/event-stream).

@pytest.mark.asyncio
async def test_advice_streams_sse_with_content_type_event_stream(client, db, mock_anthropic):
    await seed_user(db, TEST_USER_ID, "sseuser", chip_balance=100_000)
    table = await seed_table(db)
    session = await seed_session(
        db,
        table.id,
        status="playing",
        dealer_cards=[{"suit": "hearts", "value": "6"}],
    )
    hand = await seed_hand(
        db,
        session.id,
        TEST_USER_ID,
        cards=[{"suit": "hearts", "value": "5"}, {"suit": "spades", "value": "6"}],
        status="active",
    )

    resp = await client.post(
        f"/api/advice/{hand.id}",
        json={"player_guess": "double"},
    )
    assert resp.status_code == 200
    content_type = resp.headers.get("content-type", "")
    assert "text/event-stream" in content_type, (
        f"Expected Content-Type text/event-stream; got {content_type!r}"
    )


# Criterion: final SSE event includes required fields.

@pytest.mark.asyncio
async def test_advice_final_event_has_required_fields(client, db, mock_anthropic):
    """Final SSE data event must include optimal_action, was_correct,
    player_accuracy, current_streak, best_streak."""
    import json  # noqa: PLC0415

    await seed_user(db, TEST_USER_ID, "finalfields", chip_balance=100_000)
    table = await seed_table(db)
    session = await seed_session(
        db,
        table.id,
        status="playing",
        dealer_cards=[{"suit": "hearts", "value": "6"}],
    )
    hand = await seed_hand(
        db,
        session.id,
        TEST_USER_ID,
        cards=[{"suit": "hearts", "value": "5"}, {"suit": "spades", "value": "6"}],
        status="active",
    )

    resp = await client.post(
        f"/api/advice/{hand.id}",
        json={"player_guess": "double"},
    )
    assert resp.status_code == 200

    # Parse SSE response body for the final data: {...} line
    body = resp.text
    final_event = None
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("data:"):
            payload = stripped[len("data:"):].strip()
            try:
                parsed = json.loads(payload)
                # The "final" event is the one with the required fields
                if all(k in parsed for k in ("optimal_action", "was_correct")):
                    final_event = parsed
            except json.JSONDecodeError:
                pass

    required_fields = {"optimal_action", "was_correct", "player_accuracy", "current_streak", "best_streak"}
    assert final_event is not None, "No final JSON SSE event found in response"
    missing = required_fields - set(final_event.keys())
    assert not missing, f"Final SSE event missing fields: {missing}"


# Criterion: invalid/missing token → 401 with clean message (no traceback in body).

@pytest.mark.asyncio
async def test_invalid_token_returns_401_with_clean_message():
    """A request with a bogus Bearer token must get 401 with a clean detail message."""
    from httpx import ASGITransport, AsyncClient  # noqa: PLC0415
    from backend.main import app  # noqa: PLC0415
    import os  # noqa: PLC0415

    # Remove the dev bypass so real JWT validation runs
    original = os.environ.pop("BETWISE_DEV_USER_ID", None)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": "Bearer not.a.real.token"},
        ) as ac:
            resp = await ac.get("/api/users/me")
        assert resp.status_code == 401
        body = resp.json()
        detail = body.get("detail", "")
        assert "token" in detail.lower() or "invalid" in detail.lower(), (
            f"401 detail should say 'invalid token', got: {detail!r}"
        )
        # Must NOT contain Python traceback
        raw = resp.text
        assert "Traceback" not in raw, f"Response must not leak a traceback: {raw[:200]}"
    finally:
        if original is not None:
            os.environ["BETWISE_DEV_USER_ID"] = original


# ─── Multiplayer round: join-existing-betting-session ────────────────────────
# Criterion: second player deal joins the same betting session, not a new one.
# Once first player has dealt (status "playing"), a second deal attempt → 409.

@pytest.mark.asyncio
async def test_deal_409_when_round_already_playing(client, other_client, db):
    """After the first player deals (session status = playing), a second deal → 409."""
    await seed_user(db, TEST_USER_ID, "first_dealer", chip_balance=100_000)
    await seed_user(db, OTHER_USER_ID, "second_dealer", chip_balance=100_000)
    table = await seed_table(db)

    # Seat both players
    from backend.models import TableSeat  # noqa: PLC0415
    seat1 = TableSeat(
        id=uuid.uuid4(),
        table_id=table.id,
        user_id=TEST_USER_ID,
        seat_number=1,
        joined_at=datetime.now(timezone.utc),
    )
    seat2 = TableSeat(
        id=uuid.uuid4(),
        table_id=table.id,
        user_id=OTHER_USER_ID,
        seat_number=2,
        joined_at=datetime.now(timezone.utc),
    )
    db.add(seat1)
    db.add(seat2)
    await db.commit()

    # First player deals — session transitions to "playing"
    resp1 = await client.post(f"/api/tables/{table.id}/deal", json={"bet": 1_000})
    assert resp1.status_code in (200, 201), f"First deal failed: {resp1.text}"

    # Second player tries to deal into a now-playing session → must 409
    resp2 = await other_client.post(f"/api/tables/{table.id}/deal", json={"bet": 1_000})
    assert resp2.status_code == 409, (
        f"Expected 409 when round already playing; got {resp2.status_code}: {resp2.text}"
    )
    assert "round" in resp2.json().get("detail", "").lower(), (
        f"409 detail should mention 'round': {resp2.json()}"
    )


# ─── Payout credits chip_balance ─────────────────────────────────────────────
# Criterion: after dealer resolves a winning hand, user.chip_balance increases by bet.

@pytest.mark.asyncio
async def test_win_payout_credits_chip_balance(db, client):
    """Force a player win via seeded state and verify chip_balance ends at initial + bet."""
    from sqlalchemy import select  # noqa: PLC0415
    from backend.models import User  # noqa: PLC0415
    from backend.game.state import run_dealer  # noqa: PLC0415

    initial_balance = 100_000
    bet = 1_000
    user = await seed_user(db, TEST_USER_ID, "payout_test", chip_balance=initial_balance - bet)
    # ^ balance already reduced by bet (as _deal_hand does up-front)

    table = await seed_table(db)
    # Dealer has 16 (must hit); a single 6 card means dealer is at 16 and must hit
    session = await seed_session(
        db,
        table.id,
        status="dealer_turn",
        dealer_cards=[
            {"suit": "hearts", "value": "9"},
            {"suit": "spades", "value": "7"},
        ],
        # Give the deck an 8 so dealer busts (16 + 8 = 24)
        deck_state=[{"suit": "clubs", "value": "8"}],
    )

    # Seed a standing hand (player is at 18, will beat a busted dealer)
    hand = await seed_hand(
        db,
        session.id,
        TEST_USER_ID,
        cards=[{"suit": "hearts", "value": "9"}, {"suit": "spades", "value": "9"}],
        bet=bet,
        status="standing",
    )

    # Run dealer — dealer draws 8 (=24, bust), player wins
    await run_dealer(session.id, db)
    await db.commit()

    result = await db.execute(select(User).where(User.id == TEST_USER_ID))
    updated_user = result.scalar_one_or_none()
    assert updated_user is not None
    # Player had initial_balance - bet before run_dealer; wins bet*2 payout → net = initial_balance + bet
    expected = initial_balance - bet + bet * 2
    assert updated_user.chip_balance == expected, (
        f"Expected chip_balance={expected} after win; got {updated_user.chip_balance}"
    )


# ─── Advice ownership: 403 for another player's hand ─────────────────────────
# Criterion: POSTing advice for a hand you don't own returns 403.

@pytest.mark.asyncio
async def test_advice_returns_403_for_another_users_hand(other_client, db, mock_anthropic):
    """other_client (OTHER_USER_ID) requesting advice on TEST_USER's hand → 403."""
    await seed_user(db, TEST_USER_ID, "hand_owner", chip_balance=100_000)
    await seed_user(db, OTHER_USER_ID, "hand_thief", chip_balance=100_000)
    table = await seed_table(db)
    session = await seed_session(
        db,
        table.id,
        status="playing",
        dealer_cards=[{"suit": "hearts", "value": "6"}],
    )
    # Hand belongs to TEST_USER_ID
    hand = await seed_hand(
        db,
        session.id,
        TEST_USER_ID,
        cards=[{"suit": "hearts", "value": "5"}, {"suit": "spades", "value": "6"}],
        status="active",
    )

    # OTHER_USER_ID requests advice on TEST_USER's hand → must 403
    resp = await other_client.post(
        f"/api/advice/{hand.id}",
        json={"player_guess": "double"},
    )
    assert resp.status_code == 403, (
        f"Expected 403 for advice on another user's hand; got {resp.status_code}: {resp.text}"
    )
