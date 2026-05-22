"""
test_advice_drill.py — POST /api/advice/{hand_id} must hand Anthropic the
dealer-bust % as a fact so Chipy can cite it.

AC-T2 / AC-B3.

Contract: "the substring 'dealer bust' (case-insensitive) and the numeric %
both appear somewhere in the messages= (or system=) kwarg passed to
anthropic.AsyncAnthropic().messages.stream(...)."

The exact wording in the prompt is left to the implementer; only the presence
of these facts is asserted.

Pattern note: the existing conftest.py `mock_anthropic` fixture patches
`anthropic.AsyncAnthropic` at the class level and returns the mock object.
We introspect `mock.return_value.messages.stream.call_args` to read what was
sent to Anthropic — the same technique works whether advice.py builds a
`messages=` list or embeds facts in `system=`.
"""
from __future__ import annotations

import pytest

from tests.conftest import (
    TEST_USER_ID,
    seed_hand,
    seed_session,
    seed_table,
    seed_user,
)


# ─── Helper ───────────────────────────────────────────────────────────────────

def _captured_prompt_text(mock_anthropic) -> str:
    """Concatenate every text field that was passed to Anthropic's stream call.

    Returns the combined content lowercased for case-insensitive matching.
    Asserts that the call actually happened (fails fast if the handler never
    reached the Anthropic call).
    """
    instance = mock_anthropic.return_value
    call_args = instance.messages.stream.call_args
    assert call_args is not None, (
        "anthropic.AsyncAnthropic().messages.stream was never called — "
        "did the advice endpoint return early or raise before reaching Anthropic?"
    )
    kwargs = call_args.kwargs
    parts: list[str] = []

    # system= kwarg (a plain string in the current implementation)
    system = kwargs.get("system")
    if isinstance(system, str):
        parts.append(system)

    # messages= kwarg (list of {role, content} dicts)
    for msg in kwargs.get("messages", []):
        content = msg.get("content", "")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            # Content blocks: each may be {"type":"text","text":"..."}
            for block in content:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    parts.append(block["text"])

    return "\n".join(parts).lower()


# ─── Tests ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_post_advice_prompt_includes_dealer_bust_pct(client, db, mock_anthropic):
    """AC-B3: dealer upcard 6 → bust % = 0.42 / 42%.

    The post-play prompt sent to Anthropic must mention:
      - the phrase "dealer bust" (case-insensitive), AND
      - the numeric percentage in any of the forms "42%", "42 %", or "0.42".
    """
    await seed_user(db, TEST_USER_ID, "drill_player_6", chip_balance=100_000)
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
    # Drain the body so the async generator runs to completion, ensuring the
    # Anthropic mock receives its call before we inspect call_args.
    _ = resp.text

    combined = _captured_prompt_text(mock_anthropic)

    assert "dealer bust" in combined, (
        f"Expected prompt to contain 'dealer bust'; combined text was:\n{combined!r}"
    )
    assert any(token in combined for token in ("42%", "42 %", "0.42")), (
        f"Expected dealer-bust % (42% / 0.42) in prompt; combined text was:\n{combined!r}"
    )


@pytest.mark.asyncio
async def test_post_advice_prompt_uses_correct_pct_per_upcard(client, db, mock_anthropic):
    """AC-B3 (second upcard): dealer upcard A → bust % = 0.17 / 17%.

    Verifies the prompt value changes with a different dealer upcard — not
    just a hardcoded constant.
    """
    await seed_user(db, TEST_USER_ID, "drill_player_ace", chip_balance=100_000)
    table = await seed_table(db)
    session = await seed_session(
        db,
        table.id,
        status="playing",
        dealer_cards=[{"suit": "spades", "value": "A"}],
    )
    hand = await seed_hand(
        db,
        session.id,
        TEST_USER_ID,
        cards=[{"suit": "hearts", "value": "10"}, {"suit": "spades", "value": "9"}],
        status="active",
    )

    resp = await client.post(
        f"/api/advice/{hand.id}",
        json={"player_guess": "stand"},
    )
    assert resp.status_code == 200
    _ = resp.text

    combined = _captured_prompt_text(mock_anthropic)

    # "dealer bust" phrase still required
    assert "dealer bust" in combined, (
        f"Expected prompt to contain 'dealer bust'; combined text was:\n{combined!r}"
    )
    # Numeric form for Ace upcard
    assert any(token in combined for token in ("17%", "17 %", "0.17")), (
        f"Expected dealer-bust % (17% / 0.17) in prompt; combined text was:\n{combined!r}"
    )
