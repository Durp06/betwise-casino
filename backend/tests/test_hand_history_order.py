"""
test_hand_history_order.py — Task 5 schema + history-ordering tests.

Maps 1-to-1 to acceptance criteria:
  AC-M-HIST1  — Hand.created_at column exists, timezone-aware
  AC-M-HIST3  — User.total_decisions column exists, default 0
  AC-R-HIST1  — GET /api/users/{id}/hands returns hands newest-first
  AC-R-HIST2  — _deal_hand sets a non-null created_at on new Hand rows

All tests are expected to FAIL until Task 5 is implemented:
  - backend/models.py  (add Hand.created_at + User.total_decisions)
  - backend/routers/game.py  (_deal_hand sets created_at explicitly)
  - backend/routers/users.py  (_get_user_hands orders by created_at DESC)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import (
    TEST_USER_ID,
    seed_hand,
    seed_session,
    seed_table,
    seed_user,
)


# ─── AC-M-HIST1: Hand.created_at column exists and is timezone-aware ─────────

def test_hand_created_at_column_exists_and_is_timezone_aware():
    """AC-M-HIST1 — Hand.__table__.columns['created_at'] exists and is timezone-aware."""
    from backend.models import Hand  # noqa: PLC0415
    from sqlalchemy import DateTime  # noqa: PLC0415

    col = Hand.__table__.columns.get("created_at")
    assert col is not None, "Hand model is missing a 'created_at' column"
    assert isinstance(col.type, DateTime), f"created_at column type is {col.type!r}, expected DateTime"
    assert col.type.timezone is True, (
        f"created_at column must be timezone=True (got timezone={col.type.timezone!r})"
    )


# ─── AC-M-HIST3: User.total_decisions column exists, default 0 ───────────────

def test_user_total_decisions_column_exists_with_default_zero():
    """AC-M-HIST3 — User.__table__.columns['total_decisions'] exists, default 0."""
    from backend.models import User  # noqa: PLC0415

    col = User.__table__.columns.get("total_decisions")
    assert col is not None, "User model is missing a 'total_decisions' column"
    # Default should be 0 (stored as a ColumnDefault with a scalar arg of 0)
    assert col.default is not None, "total_decisions column must have a default"
    assert col.default.arg == 0, (
        f"total_decisions default arg should be 0, got {col.default.arg!r}"
    )


@pytest.mark.asyncio
async def test_seeded_user_has_total_decisions_zero(db):
    """AC-M-HIST3 — a freshly seeded user has total_decisions == 0."""
    user = await seed_user(db, TEST_USER_ID, "histuser1")
    assert hasattr(user, "total_decisions"), (
        "User model does not have a total_decisions attribute"
    )
    assert user.total_decisions == 0, (
        f"Expected total_decisions == 0 for a new user, got {user.total_decisions}"
    )


# ─── AC-R-HIST1: GET /api/users/{id}/hands returns hands newest-first ─────────

@pytest.mark.asyncio
async def test_get_user_hands_returns_newest_first(client, db):
    """AC-R-HIST1 — GET /api/users/{id}/hands returns hands ordered newest-first.

    Seeds three hands with distinct created_at values separated by seconds and
    asserts the response lists them in descending (newest-first) order.
    """
    user = await seed_user(db, TEST_USER_ID, "histuser2")
    table = await seed_table(db)
    session = await seed_session(db, table.id, status="playing")

    now = datetime.now(timezone.utc)
    # oldest hand
    hand_oldest = await seed_hand(
        db, session.id, user.id,
        cards=[{"suit": "hearts", "value": "2"}, {"suit": "clubs", "value": "3"}],
        created_at=now - timedelta(seconds=20),
    )
    # middle hand — need a fresh session because of UNIQUE(session_id, user_id)
    table2 = await seed_table(db, name="Table B")
    session2 = await seed_session(db, table2.id, status="playing")
    hand_mid = await seed_hand(
        db, session2.id, user.id,
        cards=[{"suit": "diamonds", "value": "5"}, {"suit": "spades", "value": "6"}],
        created_at=now - timedelta(seconds=10),
    )
    # newest hand
    table3 = await seed_table(db, name="Table C")
    session3 = await seed_session(db, table3.id, status="playing")
    hand_newest = await seed_hand(
        db, session3.id, user.id,
        cards=[{"suit": "clubs", "value": "9"}, {"suit": "hearts", "value": "10"}],
        created_at=now,
    )

    resp = await client.get(f"/api/users/{TEST_USER_ID}/hands")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) >= 3, f"Expected at least 3 hands, got {len(body)}"

    returned_ids = [item["id"] for item in body]
    newest_idx = returned_ids.index(str(hand_newest.id))
    mid_idx = returned_ids.index(str(hand_mid.id))
    oldest_idx = returned_ids.index(str(hand_oldest.id))

    assert newest_idx < mid_idx < oldest_idx, (
        f"Hands are not newest-first: newest={newest_idx}, mid={mid_idx}, oldest={oldest_idx}"
    )


# ─── AC-R-HIST2: _deal_hand sets a non-null created_at ───────────────────────

@pytest.mark.asyncio
async def test_dealt_hand_has_non_null_created_at(client, db):
    """AC-R-HIST2 — a hand created via POST /api/tables/{id}/deal has a non-null created_at.

    Verifies via GET /api/users/{id}/hands that the live-dealt hand appears
    in the list (proving created_at was set and the ordering query works for
    live-dealt hands, not only seeded ones).
    """
    from sqlalchemy import select  # noqa: PLC0415
    from backend.models import Hand, TableSeat  # noqa: PLC0415

    user = await seed_user(db, TEST_USER_ID, "histuser3")
    table = await seed_table(db, min_bet=100)

    # Seat the user first (required by deal endpoint)
    seat = TableSeat(
        id=uuid.uuid4(),
        table_id=table.id,
        user_id=user.id,
        seat_number=1,
    )
    db.add(seat)
    await db.commit()

    resp = await client.post(f"/api/tables/{table.id}/deal", json={"bet": 100})
    assert resp.status_code == 200, resp.text
    hand_id = resp.json()["id"]

    # Fetch hand directly from DB and check created_at
    result = await db.execute(select(Hand).where(Hand.id == uuid.UUID(hand_id)))
    hand = result.scalar_one_or_none()
    assert hand is not None
    assert hasattr(hand, "created_at"), "Dealt Hand missing created_at attribute"
    assert hand.created_at is not None, "Dealt Hand has created_at == None"
    # Must be timezone-aware
    assert hand.created_at.tzinfo is not None, "Dealt Hand created_at is timezone-naive"
