"""
test_starting_balance.py — AC-B1, AC-B2, AC-B3, AC-B6.

Tests map 1:1 to acceptance criteria from specs/centralized-money-system.md §3
(Backend section).  All tests are EXPECTED to fail (red) until the
implementation adds STARTING_BALANCE_CENTS to backend/models.py and updates the
dependent code paths.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from tests.conftest import TEST_USER_ID


# ─── AC-B1: constant exists and equals 5_000_000 ──────────────────────────────

def test_starting_balance_constant_is_5_000_000() -> None:
    """AC-B1: STARTING_BALANCE_CENTS must exist in backend.models and equal 5_000_000."""
    from backend.models import STARTING_BALANCE_CENTS  # noqa: PLC0415

    assert STARTING_BALANCE_CENTS == 5_000_000, (
        f"expected STARTING_BALANCE_CENTS == 5_000_000, got {STARTING_BALANCE_CENTS}"
    )


# ─── AC-B2: ORM default produces 5_000_000 without explicit chip_balance ──────

@pytest.mark.asyncio
async def test_new_user_default_balance_via_orm(db) -> None:
    """AC-B2: A User() created without chip_balance and flushed gets chip_balance == 5_000_000."""
    from backend.models import User  # noqa: PLC0415

    fresh_id = uuid.uuid4()
    user = User(
        id=fresh_id,
        username=f"defaultbal_{fresh_id.hex[:8]}",
        total_hands=0,
        correct_decisions=0,
        current_streak=0,
        best_streak=0,
        created_at=datetime.now(timezone.utc),
        # chip_balance intentionally omitted — must use column default
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    assert user.chip_balance == 5_000_000, (
        f"new User without chip_balance should default to 5_000_000, got {user.chip_balance}"
    )


# ─── AC-B3: POST /api/users/me brand-new user returns chip_balance == 5_000_000 ─

@pytest.mark.asyncio
async def test_upsert_me_new_user_gets_starting_balance(client) -> None:
    """AC-B3: POST /api/users/me for a brand-new user returns chip_balance == 5_000_000.

    The `client` fixture is authenticated as TEST_USER_ID with no pre-seeded user,
    so this call exercises the upsert create path in _upsert_user.
    """
    resp = await client.post("/api/users/me", json={"username": "newbalanceuser"})
    assert resp.status_code in (200, 201), f"expected 200/201, got {resp.status_code}: {resp.text}"

    data = resp.json()
    assert data["chip_balance"] == 5_000_000, (
        f"expected chip_balance == 5_000_000 for brand-new user, got {data['chip_balance']}"
    )


# ─── AC-B6: no 100_000/100000 literals remain in the starting-balance paths ───

def test_no_old_literal_in_starting_balance_paths() -> None:
    """AC-B6: The three files that define/set the starting balance must reference
    STARTING_BALANCE_CENTS, and no *starting-balance* assignment may use the old
    raw literal (100_000 / 100000) instead of the constant.

    Originally this scanned each whole file for the literal, on the assumption that
    the only other occurrence in the repo was a test-fixture override. That
    assumption no longer holds: the Pai Gow Fortune pool
    (models.FortunePool.amount_cents / seed_cents) legitimately defaults to
    100_000 (a $1,000 progressive-pool seed floor) — an unrelated literal that
    landed on main and is not a starting-balance path. So we scope the guard to
    lines that actually assign a user chip balance, which is what AC-B6 cares
    about: a regression would reintroduce 100_000 on a `chip_balance` line.
    """
    import pathlib  # noqa: PLC0415
    import re  # noqa: PLC0415

    repo_root = pathlib.Path(__file__).parent.parent.parent  # betwise-casino/

    files_to_check = [
        repo_root / "backend" / "models.py",
        repo_root / "backend" / "routers" / "users.py",
        repo_root / "backend" / "dev_seed.py",
    ]
    old_literal = re.compile(r"\b100_?000\b")

    for path in files_to_check:
        source = path.read_text(encoding="utf-8")
        assert "STARTING_BALANCE_CENTS" in source, (
            f"{path.name}: expected 'STARTING_BALANCE_CENTS' to appear "
            "(starting-balance paths must reference the constant)"
        )
        for lineno, line in enumerate(source.splitlines(), start=1):
            if "chip_balance" not in line:
                continue
            assert not old_literal.search(line), (
                f"{path.name}:{lineno}: a chip_balance (starting-balance) line uses the "
                f"old raw literal instead of STARTING_BALANCE_CENTS: {line.strip()!r}"
            )
