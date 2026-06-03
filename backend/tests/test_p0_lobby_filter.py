"""
test_p0_lobby_filter.py — Phase-0 backend acceptance criteria.

Covers:
  AC P0-2a: GET /api/tables returns only waiting+playing tables (finished excluded).
  AC P0-2b: Results are ordered waiting before playing, then created_at DESC within
            each status bucket.

Each test maps 1-to-1 to one AC and must fail until _list_tables is updated.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta

from tests.conftest import seed_table, seed_user, TEST_USER_ID


# ─── AC P0-2a: backend filter — finished tables must be absent ─────────────────

@pytest.mark.asyncio
async def test_p0_2a_finished_table_absent_from_list(client, db):
    """
    AC P0-2a: GET /api/tables returns only tables with status in
    ('waiting', 'playing'). A table with status='finished' must NOT appear.
    """
    await seed_user(db, TEST_USER_ID, "lobby-filter-user")

    waiting_table  = await seed_table(db, name="Waiting Room",  status="waiting")
    playing_table  = await seed_table(db, name="Active Game",   status="playing")
    finished_table = await seed_table(db, name="Done Table",    status="finished")

    resp = await client.get("/api/tables")
    assert resp.status_code == 200

    data = resp.json()
    ids_returned = {row["id"] for row in data}

    assert str(waiting_table.id) in ids_returned, "waiting table must appear"
    assert str(playing_table.id) in ids_returned, "playing table must appear"
    assert str(finished_table.id) not in ids_returned, (
        "finished table must NOT appear in GET /api/tables (AC P0-2a)"
    )


# ─── AC P0-2b: ordering — waiting before playing, then created_at DESC ─────────

@pytest.mark.asyncio
async def test_p0_2b_waiting_before_playing_in_response(client, db):
    """
    AC P0-2b: waiting tables sort before playing tables regardless of created_at.
    Seed a PLAYING table first (older), then a WAITING table (newer).
    The WAITING table must be at index 0 in the response.
    """
    await seed_user(db, TEST_USER_ID, "lobby-order-user")

    now = datetime.now(timezone.utc)

    # Seed playing first so it has an older created_at in natural DB order
    from backend.models import CasinoTable  # noqa: PLC0415
    import uuid as _uuid  # noqa: PLC0415

    older_playing = CasinoTable(
        id=_uuid.uuid4(),
        name="Older Playing",
        min_bet=500,
        max_bet=50_000,
        max_seats=3,
        status="playing",
        created_at=now - timedelta(seconds=10),
    )
    db.add(older_playing)

    newer_waiting = CasinoTable(
        id=_uuid.uuid4(),
        name="Newer Waiting",
        min_bet=500,
        max_bet=50_000,
        max_seats=3,
        status="waiting",
        created_at=now,
    )
    db.add(newer_waiting)
    await db.commit()

    resp = await client.get("/api/tables")
    assert resp.status_code == 200

    data = resp.json()
    # Must have at least two rows (the ones we just seeded)
    assert len(data) >= 2, "expected at least two tables"

    # Find positions of our tables
    ids_in_order = [row["id"] for row in data]
    pos_waiting = ids_in_order.index(str(newer_waiting.id))
    pos_playing = ids_in_order.index(str(older_playing.id))

    assert pos_waiting < pos_playing, (
        f"waiting table must appear before playing table (AC P0-2b): "
        f"waiting={pos_waiting}, playing={pos_playing}"
    )
