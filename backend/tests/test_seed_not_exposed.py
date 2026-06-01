"""
test_seed_not_exposed.py — regression guard for security finding **P3**
(server-only RNG seed leaked to clients).

The deterministic poker deck is reconstructable from the per-tournament `seed`
(see poker_game.py: ``create_deck(seed=hand.seed)`` and the per-hand derivation
``hand_seed = tournament.seed * 31 + next_number``). If a client can read the
seed, it can recompute every future board and every opponent's hole cards. So
the fix removes the ``seed`` field from the two client-facing schemas that
carried it — ``PokerTournamentOut`` and ``PokerHandReplayOut`` — and from the
TS types.

These tests assert the CORRECT post-fix behavior: ``seed`` must NOT appear in
either schema's ``model_dump()``, and the polled ``/state`` JSON must not carry
a ``seed`` key. They are intentionally written to FAIL until the schemas.py fix
lands (the field is still present at the time of writing) and to stay green
forever after.

Style mirrors the rest of the suite: pytest-asyncio + in-memory SQLite, the
``client`` / ``db`` fixtures and ``seed_user`` helper from conftest.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.schemas import PokerHandReplayOut, PokerTournamentOut
from backend.tests.conftest import TEST_USER_ID, seed_user


def _tournament_like() -> SimpleNamespace:
    """An ORM-ish object exposing every PokerTournamentOut source attribute —
    deliberately INCLUDING ``seed`` — so the assertion proves the schema drops
    it on serialization even when the backing row still carries it."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        bot_count=3,
        advice_mode="odds",
        buy_in_cents=5_000,
        starting_stack_chips=1_500,
        hands_per_level=10,
        seed=1234567,  # server-only RNG material — must never surface
        status="active",
        button_seat=0,
        current_hand_number=0,
        created_at=datetime.now(timezone.utc),
    )


def _replay_like() -> SimpleNamespace:
    """An ORM-ish object for PokerHandReplayOut, again carrying a ``seed`` the
    schema must not expose."""
    return SimpleNamespace(
        hand_id=uuid.uuid4(),
        hand_number=1,
        seed=7654321,  # server-only RNG material — must never surface
        button_seat=0,
        board=[],
        seats=[],
        actions=[],
        result=None,
    )


# ─── Schema-level guards (no DB, fast + deterministic) ───────────────────────


def test_poker_tournament_out_omits_seed():
    """P3: PokerTournamentOut must not expose the RNG seed."""
    model = PokerTournamentOut.model_validate(_tournament_like())
    dumped = model.model_dump()
    assert "seed" not in dumped, "seed leaked from PokerTournamentOut.model_dump()"
    # belt-and-suspenders: not a declared field either
    assert "seed" not in PokerTournamentOut.model_fields, "seed still declared on PokerTournamentOut"
    # serialized JSON (what actually crosses the wire) must also be clean
    assert "seed" not in model.model_dump_json()


def test_poker_hand_replay_out_omits_seed():
    """P3: PokerHandReplayOut must not expose the RNG seed."""
    model = PokerHandReplayOut.model_validate(_replay_like())
    dumped = model.model_dump()
    assert "seed" not in dumped, "seed leaked from PokerHandReplayOut.model_dump()"
    assert "seed" not in PokerHandReplayOut.model_fields, "seed still declared on PokerHandReplayOut"
    assert "seed" not in model.model_dump_json()


# ─── Endpoint-level guard (the payload a real client actually receives) ──────


@pytest.mark.asyncio
async def test_create_and_state_endpoints_omit_seed(client, db):
    """The POST create response and the polled GET /state payload must carry no
    ``seed`` key — neither at the top level nor nested under ``tournament``."""
    await seed_user(db, TEST_USER_ID, "seed-guard-user", chip_balance=100_000)

    create_resp = await client.post(
        "/api/poker/tournaments",
        json={
            "bot_count": 3,
            "advice_mode": "odds",
            "buy_in_cents": 5_000,
            "starting_stack_chips": 1_500,
            "hands_per_level": 10,
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    assert "seed" not in created, f"seed leaked from create-tournament response: {created}"

    tournament_id = created["id"]
    state_resp = await client.get(f"/api/poker/tournaments/{tournament_id}/state")
    assert state_resp.status_code == 200, state_resp.text
    state = state_resp.json()

    # No seed anywhere in the serialized payload, top-level or nested.
    assert "seed" not in state
    assert "seed" not in state.get("tournament", {}), (
        f"seed leaked under /state .tournament: {state.get('tournament')}"
    )
    # Strongest assertion: the substring "seed" appears nowhere in the wire bytes.
    assert "seed" not in state_resp.text, "seed leaked somewhere in the /state JSON body"
