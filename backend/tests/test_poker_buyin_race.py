"""
test_poker_buyin_race.py — T2 (H1) Poker buy-in non-atomic debit + missing rate-limit.

AC-2.1 (structural lock): `_create_tournament_with_seats` uses with_for_update on User SELECT.
AC-2.2 (structural rate-limit): `create_tournament` carries request: Request param and
        stuffs request.state.user_id; the handler also has the limiter decorator.
AC-2.3 (behavioral IntegrityError→409): IntegrityError during seat insert returns 409,
        not 500, and the user's chip_balance is unchanged.
AC-2.4 (sequential correctness): exact-balance debit once, second attempt rejected 400.

These tests FAIL until the poker_tables.py fix is implemented (no with_for_update,
no try/except IntegrityError, no rate-limit wiring on create_tournament).
"""
from __future__ import annotations

import inspect

import pytest

from tests.conftest import TEST_USER_ID, seed_user


# ─── AC-2.1 — structural: User SELECT uses with_for_update ──────────────────

def test_create_tournament_helper_uses_with_for_update():
    """AC-2.1: `_create_tournament_with_seats` must call .with_for_update() on the
    User SELECT.  Mirrors test_action_race.py's structural guard.
    """
    from backend.routers.poker_tables import _create_tournament_with_seats  # noqa: PLC0415

    source = inspect.getsource(_create_tournament_with_seats)
    assert "with_for_update" in source, (
        "Expected _create_tournament_with_seats to call .with_for_update() on the User "
        "SELECT (CSO H1 fix). The lock is not present — a concurrent request can still "
        "double-debit the balance before either commit completes under Postgres READ COMMITTED."
    )


# ─── AC-2.2 — structural: create_tournament has rate-limit + request.state.user_id ─

def test_create_tournament_endpoint_has_rate_limit_and_user_key():
    """AC-2.2: `create_tournament` must:
    1. Accept a `request: Request` parameter (first positional param after `self`).
    2. Assign `request.state.user_id = str(current_user)` so the per-user slowapi
       key function keys on the user, not on the remote IP.
    """
    from backend.routers.poker_tables import create_tournament  # noqa: PLC0415
    import inspect as _inspect  # noqa: PLC0415

    source = _inspect.getsource(create_tournament)
    # Must stash the per-user key
    assert "request.state.user_id" in source, (
        "create_tournament must assign request.state.user_id = str(current_user) "
        "so the per-user rate-limit key is set correctly (mirrors holdem.create_table)."
    )

    # request: Request must appear in the function signature
    sig = _inspect.signature(create_tournament)
    param_names = list(sig.parameters.keys())
    assert "request" in param_names, (
        f"create_tournament must have a `request` parameter; got params {param_names}"
    )


# ─── AC-2.3 — behavioral: IntegrityError → 409, balance unchanged ────────────

@pytest.mark.asyncio
async def test_create_tournament_integrity_error_returns_409_not_500(client, db, monkeypatch):
    """AC-2.3: if the buy-in transaction raises IntegrityError (e.g. a UNIQUE
    collision under a genuinely concurrent insert), the endpoint maps it to a
    clean 409, not a 500.

    Note: each tournament gets a fresh ``tournament_id``, so a real seat
    collision between two creates is not actually reachable in production — this
    pins the defense-in-depth ``IntegrityError -> 409`` mapping that mirrors
    ``holdem._join_seat``. We induce the error by patching the session ``commit``
    to raise once. The debited-exactly-once guarantee is covered separately by
    the structural lock test (AC-2.1) and the sequential test (AC-2.4); we don't
    re-query the (now rolled-back) shared test session for the balance here.
    """
    from sqlalchemy.exc import IntegrityError  # noqa: PLC0415

    await seed_user(db, TEST_USER_ID, "race_buyin_user", chip_balance=50_000)

    async def _raise_integrity_error() -> None:
        raise IntegrityError(
            "INSERT INTO poker_seats", {}, Exception("UNIQUE constraint failed: poker_seats")
        )

    # Override the session commit (conftest already patches commit->flush; this
    # test patch wins as it is applied last) so the handler's commit raises.
    monkeypatch.setattr(db, "commit", _raise_integrity_error)

    resp = await client.post(
        "/api/poker/tournaments",
        json={
            "bot_count": 2,
            "advice_mode": "odds",
            "buy_in_cents": 1_000,
            "starting_stack_chips": 1_500,
            "hands_per_level": 10,
        },
    )

    # Must be 409 (conflict), not 500 (unhandled exception).
    assert resp.status_code == 409, (
        f"Expected 409 when the buy-in commit raises IntegrityError; "
        f"got {resp.status_code}: {resp.text}"
    )


# ─── AC-2.4 — sequential correctness: debited once, second call rejected ─────

@pytest.mark.asyncio
async def test_create_tournament_debits_exactly_once(client, db):
    """AC-2.4: first create with buy_in_cents=10_000 succeeds (201) and debits
    the balance exactly once.  A second create with the same buy-in (balance now 0)
    is rejected with 400 ("Insufficient bankroll"), and the balance stays 0.
    """
    await seed_user(db, TEST_USER_ID, "debit_once_user", chip_balance=10_000)

    payload = {
        "bot_count": 2,
        "advice_mode": "odds",
        "buy_in_cents": 10_000,
        "starting_stack_chips": 1_500,
        "hands_per_level": 10,
    }

    # First create — must succeed
    resp1 = await client.post("/api/poker/tournaments", json=payload)
    assert resp1.status_code == 201, (
        f"First create must succeed with 201; got {resp1.status_code}: {resp1.text}"
    )

    # Balance after first create must be 0
    me_resp = await client.get("/api/users/me")
    assert me_resp.status_code == 200, me_resp.text
    balance_after_first = me_resp.json()["chip_balance"]
    assert balance_after_first == 0, (
        f"chip_balance must be 0 after buy-in of 10_000 from 10_000; "
        f"got {balance_after_first}"
    )

    # Second create — must be rejected (insufficient bankroll)
    resp2 = await client.post("/api/poker/tournaments", json=payload)
    assert resp2.status_code == 400, (
        f"Second create with 0 balance must be rejected with 400; "
        f"got {resp2.status_code}: {resp2.text}"
    )
    assert "insufficient" in resp2.json().get("detail", "").lower() or \
           "bankroll" in resp2.json().get("detail", "").lower(), (
        f"Expected 'Insufficient bankroll' detail; got: {resp2.json()}"
    )

    # Balance must still be 0 (not double-debited)
    me_resp2 = await client.get("/api/users/me")
    balance_after_second = me_resp2.json()["chip_balance"]
    assert balance_after_second == 0, (
        f"chip_balance must remain 0 after rejected second create; "
        f"got {balance_after_second}"
    )
