"""
test_chat.py — in-game player chat HTTP endpoint + sanitizer tests.

Covers the polymorphic chat feature across BOTH multiplayer games:
- post requires a seat (403 when not seated);
- post → get round-trips the message;
- body validation: empty/whitespace → 400, > 500 chars → 400, control chars
  stripped;
- STORED-XSS: angle-bracket markup is stored verbatim and returned unchanged
  (the API neither executes nor strips it — the client renders it inert);
- bad table_kind → 404;
- cross-table isolation between two tables.

Two humans share one app via a mutable current-user holder (FastAPI
dependency_overrides are global per app), mirroring test_holdem_endpoints.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from tests.conftest import OTHER_USER_ID, TEST_USER_ID, seed_table, seed_user


@pytest_asyncio.fixture
async def multi(db):
    """An AsyncClient + an `as_user(uid)` switch sharing one db session."""
    from backend.auth import get_current_user  # noqa: PLC0415
    from backend.database import get_db  # noqa: PLC0415
    from backend.main import app  # noqa: PLC0415

    holder = {"uid": TEST_USER_ID}

    async def _override_user():
        return holder["uid"]

    async def _override_db():
        yield db

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_db] = _override_db

    def as_user(uid) -> None:
        holder["uid"] = uid if isinstance(uid, uuid.UUID) else uuid.UUID(str(uid))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, as_user

    app.dependency_overrides.clear()


# ─── seat-seeding helpers ──────────────────────────────────────────────────────


async def _seed_blackjack_seat(db, user_id: uuid.UUID, username: str):
    """Seed a User + a CasinoTable + a TableSeat for that user. Returns the table."""
    from backend.models import TableSeat  # noqa: PLC0415

    await seed_user(db, user_id, username)
    table = await seed_table(db, name="Chat BJ Table")
    # Find the lowest free physical seat (1-based for blackjack).
    from sqlalchemy import select  # noqa: PLC0415

    occupied = {
        row[0]
        for row in (await db.execute(
            select(TableSeat.seat_number).where(TableSeat.table_id == table.id)
        )).fetchall()
    }
    seat_no = next(n for n in range(1, table.max_seats + 1) if n not in occupied)
    seat = TableSeat(
        id=uuid.uuid4(),
        table_id=table.id,
        user_id=user_id,
        seat_number=seat_no,
        joined_at=datetime.now(timezone.utc),
    )
    db.add(seat)
    await db.commit()
    return table


async def _seed_holdem_seat(db, user_id: uuid.UUID, username: str):
    """Seed a User + a HoldemTable + a HoldemSeat for that user. Returns the table."""
    from backend.models import HoldemSeat, HoldemTable  # noqa: PLC0415

    await seed_user(db, user_id, username)
    table = HoldemTable(
        id=uuid.uuid4(),
        name="Chat Holdem Table",
        small_blind=50,
        big_blind=100,
        min_buy_in=2_000,
        max_buy_in=20_000,
        max_seats=6,
        button_pos=None,
        status="waiting",
        created_at=datetime.now(timezone.utc),
    )
    db.add(table)
    await db.flush()
    seat = HoldemSeat(
        id=uuid.uuid4(),
        table_id=table.id,
        user_id=user_id,
        seat_number=0,
        stack=10_000,
        status="active",
        joined_at=datetime.now(timezone.utc),
    )
    db.add(seat)
    await db.commit()
    return table


async def _post(ac, as_user, uid, kind, table_id, body):
    as_user(uid)
    return await ac.post(f"/api/chat/{kind}/{table_id}/messages", json={"body": body})


async def _get(ac, as_user, uid, kind, table_id):
    as_user(uid)
    return await ac.get(f"/api/chat/{kind}/{table_id}/messages")


# ─── unit test: the pure sanitizer ─────────────────────────────────────────────


def test_sanitize_body_strips_control_chars_and_trims():
    from backend.routers.chat import _sanitize_body  # noqa: PLC0415

    assert _sanitize_body("  hello  ") == "hello"
    assert _sanitize_body("ab\x00\x07cd") == "abcd"
    # unicode + emoji survive
    assert _sanitize_body("café 🎲") == "café 🎲"


def test_sanitize_body_rejects_empty_and_overlong():
    from fastapi import HTTPException  # noqa: PLC0415

    from backend.routers.chat import _sanitize_body  # noqa: PLC0415

    for bad in ("", "   ", "\x00\x07"):
        with pytest.raises(HTTPException) as exc:
            _sanitize_body(bad)
        assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        _sanitize_body("x" * 501)
    assert exc.value.status_code == 400


# ─── seat requirement ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_post_requires_seat_blackjack(multi, db):
    ac, as_user = multi
    table = await _seed_blackjack_seat(db, TEST_USER_ID, "alice")
    # OTHER_USER_ID is a real user but NOT seated → 403.
    await seed_user(db, OTHER_USER_ID, "bob")
    r = await _post(ac, as_user, OTHER_USER_ID, "blackjack", table.id, "hi")
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_post_requires_seat_holdem(multi, db):
    ac, as_user = multi
    table = await _seed_holdem_seat(db, TEST_USER_ID, "alice")
    await seed_user(db, OTHER_USER_ID, "bob")
    r = await _post(ac, as_user, OTHER_USER_ID, "holdem", table.id, "hi")
    assert r.status_code == 403, r.text


# ─── round trip ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_post_then_get_round_trips_blackjack(multi, db):
    ac, as_user = multi
    table = await _seed_blackjack_seat(db, TEST_USER_ID, "alice")
    r = await _post(ac, as_user, TEST_USER_ID, "blackjack", table.id, "nice hand!")
    assert r.status_code == 201, r.text
    posted = r.json()
    assert posted["body"] == "nice hand!"
    assert posted["username"] == "alice"
    assert posted["table_kind"] == "blackjack"

    g = await _get(ac, as_user, TEST_USER_ID, "blackjack", table.id)
    assert g.status_code == 200
    rows = g.json()
    assert len(rows) == 1
    assert rows[0]["body"] == "nice hand!"


@pytest.mark.asyncio
async def test_post_then_get_round_trips_holdem(multi, db):
    ac, as_user = multi
    table = await _seed_holdem_seat(db, TEST_USER_ID, "alice")
    r = await _post(ac, as_user, TEST_USER_ID, "holdem", table.id, "raise it up")
    assert r.status_code == 201, r.text
    g = await _get(ac, as_user, TEST_USER_ID, "holdem", table.id)
    assert g.status_code == 200
    rows = g.json()
    assert len(rows) == 1
    assert rows[0]["body"] == "raise it up"


# ─── body validation over HTTP ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_post_rejects_empty_and_whitespace(multi, db):
    ac, as_user = multi
    table = await _seed_blackjack_seat(db, TEST_USER_ID, "alice")
    for bad in ("", "    "):
        r = await _post(ac, as_user, TEST_USER_ID, "blackjack", table.id, bad)
        assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_post_rejects_overlong(multi, db):
    ac, as_user = multi
    table = await _seed_blackjack_seat(db, TEST_USER_ID, "alice")
    r = await _post(ac, as_user, TEST_USER_ID, "blackjack", table.id, "x" * 501)
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_post_strips_control_chars(multi, db):
    ac, as_user = multi
    table = await _seed_blackjack_seat(db, TEST_USER_ID, "alice")
    r = await _post(ac, as_user, TEST_USER_ID, "blackjack", table.id, "ab\x00\x07cd")
    assert r.status_code == 201, r.text
    g = await _get(ac, as_user, TEST_USER_ID, "blackjack", table.id)
    body = g.json()[0]["body"]
    assert body == "abcd"
    assert "\x00" not in body and "\x07" not in body


# ─── STORED-XSS: markup stored verbatim, not executed nor stripped ──────────────


@pytest.mark.asyncio
async def test_stored_xss_body_returned_verbatim(multi, db):
    ac, as_user = multi
    table = await _seed_holdem_seat(db, TEST_USER_ID, "alice")

    payloads = [
        "<script>alert('x')</script>",
        "<img src=x onerror=alert(1)>",
    ]
    for p in payloads:
        r = await _post(ac, as_user, TEST_USER_ID, "holdem", table.id, p)
        assert r.status_code == 201, r.text
        # The API returns it unchanged: angle brackets intact, not escaped.
        assert r.json()["body"] == p

    g = await _get(ac, as_user, TEST_USER_ID, "holdem", table.id)
    bodies = [m["body"] for m in g.json()]
    for p in payloads:
        assert p in bodies  # stored verbatim — the client renders it as inert text


# ─── bad table_kind ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bad_table_kind_get_404(multi, db):
    ac, as_user = multi
    await seed_user(db, TEST_USER_ID, "alice")
    r = await _get(ac, as_user, TEST_USER_ID, "roulette", uuid.uuid4())
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_bad_table_kind_post_404(multi, db):
    ac, as_user = multi
    await seed_user(db, TEST_USER_ID, "alice")
    r = await _post(ac, as_user, TEST_USER_ID, "roulette", uuid.uuid4(), "hi")
    assert r.status_code == 404, r.text


# ─── cross-table isolation ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cross_table_isolation(multi, db):
    ac, as_user = multi
    # Two blackjack tables; alice seated at both via a fresh seat each.
    await seed_user(db, TEST_USER_ID, "alice")
    table_a = await seed_table(db, name="Table A")
    table_b = await seed_table(db, name="Table B")
    from backend.models import TableSeat  # noqa: PLC0415

    for tbl in (table_a, table_b):
        db.add(TableSeat(
            id=uuid.uuid4(),
            table_id=tbl.id,
            user_id=TEST_USER_ID,
            seat_number=1,
            joined_at=datetime.now(timezone.utc),
        ))
    await db.commit()

    r = await _post(ac, as_user, TEST_USER_ID, "blackjack", table_a.id, "message in A")
    assert r.status_code == 201, r.text

    # Table B's GET must not see Table A's message.
    g_b = await _get(ac, as_user, TEST_USER_ID, "blackjack", table_b.id)
    assert g_b.status_code == 200
    assert g_b.json() == []

    g_a = await _get(ac, as_user, TEST_USER_ID, "blackjack", table_a.id)
    assert [m["body"] for m in g_a.json()] == ["message in A"]
