"""
test_bet_validation.py — T7 (L2) Negative-bet & table-bound validation.

AC-7.1: POST /api/tables/{id}/deal with bet=0 or bet=-100 returns 422 (Pydantic gt=0).
AC-7.2: constructing a CasinoTable with min_bet<=0 raises an integrity/constraint
        error at flush (ORM CheckConstraint "min_bet > 0").
AC-7.3: CasinoTable with max_bet < min_bet raises the constraint error; a valid
        0 < min_bet <= max_bet table commits cleanly (no false positive).

These tests FAIL until:
  - backend/schemas.py DealIn.bet changes to `Field(gt=0)`
  - backend/models.py CasinoTable gains the two new CheckConstraints
"""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from tests.conftest import TEST_USER_ID, seed_table, seed_user


# ─── AC-7.1 — bet=0 and bet=-100 are rejected with 422 ──────────────────────

@pytest.mark.asyncio
async def test_deal_rejects_zero_bet(client, db):
    """AC-7.1a: POST /api/tables/{id}/deal with bet=0 must return 422."""
    await seed_user(db, TEST_USER_ID, "betval_user_zero", chip_balance=100_000)
    table = await seed_table(db)

    resp = await client.post(
        f"/api/tables/{table.id}/deal",
        json={"bet": 0},
    )
    assert resp.status_code == 422, (
        f"Expected 422 for bet=0 (Pydantic gt=0 constraint); "
        f"got {resp.status_code}: {resp.text}"
    )


@pytest.mark.asyncio
async def test_deal_rejects_negative_bet(client, db):
    """AC-7.1b: POST /api/tables/{id}/deal with bet=-100 must return 422."""
    await seed_user(db, TEST_USER_ID, "betval_user_neg", chip_balance=100_000)
    table = await seed_table(db)

    resp = await client.post(
        f"/api/tables/{table.id}/deal",
        json={"bet": -100},
    )
    assert resp.status_code == 422, (
        f"Expected 422 for bet=-100 (Pydantic gt=0 constraint); "
        f"got {resp.status_code}: {resp.text}"
    )


# ─── AC-7.2 — CasinoTable with min_bet<=0 raises constraint error ────────────

@pytest.mark.asyncio
async def test_casino_table_min_bet_zero_raises_constraint(db):
    """AC-7.2: inserting a CasinoTable with min_bet=0 must raise an
    IntegrityError at flush (the ORM CheckConstraint 'min_bet > 0').
    """
    import uuid as _uuid  # noqa: PLC0415
    from datetime import datetime, timezone  # noqa: PLC0415
    from backend.models import CasinoTable  # noqa: PLC0415

    bad_table = CasinoTable(
        id=_uuid.uuid4(),
        name="Bad Min Bet Table",
        min_bet=0,       # violates min_bet > 0
        max_bet=50_000,
        max_seats=3,
        status="waiting",
        created_at=datetime.now(timezone.utc),
    )
    db.add(bad_table)

    with pytest.raises((IntegrityError, Exception)) as exc_info:
        await db.flush()

    # The error must be an integrity/constraint violation, not an unrelated error
    error_str = str(exc_info.value).lower()
    assert any(kw in error_str for kw in ("integrity", "constraint", "check")), (
        f"Expected an IntegrityError / CheckConstraint violation for min_bet=0; "
        f"got: {exc_info.value}"
    )

    # Roll back so the session is clean for teardown
    await db.rollback()


# ─── AC-7.3 — max_bet < min_bet raises constraint; valid table commits ok ────

@pytest.mark.asyncio
async def test_casino_table_max_bet_lt_min_bet_raises_constraint(db):
    """AC-7.3a: CasinoTable with max_bet < min_bet must raise the constraint error."""
    import uuid as _uuid  # noqa: PLC0415
    from datetime import datetime, timezone  # noqa: PLC0415
    from backend.models import CasinoTable  # noqa: PLC0415

    bad_table = CasinoTable(
        id=_uuid.uuid4(),
        name="Bad Max Bet Table",
        min_bet=1_000,
        max_bet=500,     # violates max_bet >= min_bet
        max_seats=3,
        status="waiting",
        created_at=datetime.now(timezone.utc),
    )
    db.add(bad_table)

    with pytest.raises((IntegrityError, Exception)) as exc_info:
        await db.flush()

    error_str = str(exc_info.value).lower()
    assert any(kw in error_str for kw in ("integrity", "constraint", "check")), (
        f"Expected IntegrityError for max_bet < min_bet; got: {exc_info.value}"
    )

    await db.rollback()


@pytest.mark.asyncio
async def test_casino_table_valid_bets_commit_cleanly(db):
    """AC-7.3b: a valid CasinoTable with 0 < min_bet <= max_bet must commit
    without error (no false positive from the new constraints).
    """
    import uuid as _uuid  # noqa: PLC0415
    from datetime import datetime, timezone  # noqa: PLC0415
    from backend.models import CasinoTable  # noqa: PLC0415

    valid_table = CasinoTable(
        id=_uuid.uuid4(),
        name="Valid Bet Table",
        min_bet=500,
        max_bet=50_000,
        max_seats=3,
        status="waiting",
        created_at=datetime.now(timezone.utc),
    )
    db.add(valid_table)
    # Must not raise
    await db.flush()
    # If we reach here, no constraint was violated — test passes
