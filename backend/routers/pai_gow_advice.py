"""routers/pai_gow_advice.py — Chipy SSE endpoints for Pai Gow.

Endpoints (spec §12.1):
  POST /api/pai-gow/advice/{hand_id}/pre  — pre-set Chipy suggestion (SSE)
  POST /api/pai-gow/advice/{hand_id}      — post-set Chipy explanation (SSE)

`_stream_anthropic` is **duplicated** from blackjack's `advice.py` per the
spec §17 Q1 resolution — avoiding shared-file edits keeps the PG PR
merge-safe against the in-flight hold'em branches. v2 may extract a shared
`_chipy.py` once the dust settles.

**Streak updates are NOT done in this router.** They live in
`state.submit_player_set` at the moment the hand is committed, so the
streak count is correct even if the player never opens the advice panel.
The advice endpoints here only render Chipy's explanatory text.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from backend.auth import CurrentUser
from backend.database import get_db
from backend.game.pai_gow import optimal_set as _optimal_set
from backend.ratelimit import ADVICE_RATE_LIMIT, limiter
from backend.schemas import PaiGowAdviceIn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pai-gow/advice", tags=["pai-gow-advice"])


# System prompt for Chipy-for-PG. Plain text only — the front-end renders the
# stream as raw text and markdown would show as literal characters. Matches the
# blackjack Chipy prompt's tone.
_CHIPY_PG_SYSTEM_PROMPT = (
    "You are Chipy, an expert Pai Gow Poker strategy coach sitting next to a "
    "friend at the table. Speak in warm conversational prose, 1-2 short "
    "sentences. Always give a reason rooted in hand strength or §7.3 "
    "comparison. Plain text only — no markdown. Do not use #, ##, **, *, "
    "backticks, or bullet points. Do not bold or italicize anything."
)


async def _stream_anthropic(messages: list[dict]) -> AsyncGenerator[str, None]:
    """Shimmable streaming helper — duplicated from blackjack `advice.py` per
    §17 Q1. Tests patch this with the `mock_anthropic` fixture.
    """
    import os as _os  # noqa: PLC0415

    import anthropic  # noqa: PLC0415

    model = _os.environ.get("CHIPY_MODEL", "claude-sonnet-4-6")
    client = anthropic.AsyncAnthropic()
    async with client.messages.stream(
        model=model,
        max_tokens=256,
        system=_CHIPY_PG_SYSTEM_PROMPT,
        messages=messages,
    ) as stream:
        async for event in stream:
            if (
                hasattr(event, "delta")
                and hasattr(event.delta, "type")
                and event.delta.type == "text_delta"
            ):
                yield event.delta.text


def _cards_str(cards: list[dict]) -> str:
    """Compact human-readable card listing for the prompt."""
    return ", ".join(f"{c['value']}{c['suit'][0].upper()}" for c in cards if c)


# ─── Route handlers ─────────────────────────────────────────────────────────


@router.post("/{hand_id}/pre")
@limiter.limit(ADVICE_RATE_LIMIT)
async def get_pre_advice(
    request: Request,
    hand_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream Chipy's pre-set suggestion for a freshly-dealt hand.

    Reads the dealt 7 cards, computes the optimal split via
    `optimal_set.find_optimal`, and asks Chipy to explain why that split is
    optimal in plain prose.
    """
    from backend.models import PaiGowPlayerHand  # noqa: PLC0415

    request.state.user_id = str(current_user)

    pre = (
        await db.execute(
            select(PaiGowPlayerHand).where(PaiGowPlayerHand.id == hand_id)
        )
    ).scalar_one_or_none()
    if pre is None:
        raise HTTPException(status_code=404, detail="Pai Gow hand not found")
    if pre.user_id != current_user:
        raise HTTPException(
            status_code=403,
            detail="Cannot request advice for another player's hand",
        )

    async def _sse_stream() -> AsyncGenerator[bytes, None]:
        from backend.models import PaiGowPlayerHand as _Hand  # noqa: PLC0415

        # Reload (the pre-check copy may be stale by the time the stream runs).
        result = await db.execute(select(_Hand).where(_Hand.id == hand_id))
        hand = result.scalar_one_or_none()
        if hand is None:
            yield b"data: {\"error\": \"Pai Gow hand not found\"}\n\n"
            return

        dealt = list(hand.dealt_cards)
        optimal = _optimal_set.find_optimal(dealt)
        front_str = _cards_str(list(optimal.front))
        back_str = _cards_str(list(optimal.back))

        messages = [
            {
                "role": "user",
                "content": (
                    f"I just got dealt these 7 cards in Pai Gow Poker: "
                    f"{_cards_str(dealt)}. Basic strategy suggests splitting "
                    f"with {front_str} in the front (2-card hand) and "
                    f"{back_str} in the back (5-card hand). "
                    f"In one or two short sentences, plain prose, explain why "
                    f"this is the strongest legal split for me."
                ),
            }
        ]

        try:
            async for chunk in _stream_anthropic(messages):
                yield f"data: {json.dumps({'text': chunk})}\n\n".encode()
        except Exception as e:  # noqa: BLE001
            logger.exception("Chipy PG pre-stream failed")
            fallback = (
                f"(Chipy is offline — basic strategy says split {front_str} "
                f"front and {back_str} back.)"
            )
            yield f"data: {json.dumps({'text': fallback, 'error': type(e).__name__})}\n\n".encode()

        final = {
            "optimal_front": list(optimal.front),
            "optimal_back": list(optimal.back),
            "reasoning_key": optimal.reasoning_key,
            "phase": "pre",
        }
        yield f"data: {json.dumps(final)}\n\n".encode()

    return StreamingResponse(_sse_stream(), media_type="text/event-stream")


@router.post("/{hand_id}")
@limiter.limit(ADVICE_RATE_LIMIT)
async def get_post_advice(
    request: Request,
    hand_id: uuid.UUID,
    body: PaiGowAdviceIn,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream Chipy's post-set explanation: evaluates the player's submitted
    split against the optimal and explains the difference (or confirms the
    play was optimal). Does NOT update the streak — that happens in
    `state.submit_player_set` at commit time.
    """
    from backend.models import PaiGowPlayerHand  # noqa: PLC0415

    request.state.user_id = str(current_user)

    pre = (
        await db.execute(
            select(PaiGowPlayerHand).where(PaiGowPlayerHand.id == hand_id)
        )
    ).scalar_one_or_none()
    if pre is None:
        raise HTTPException(status_code=404, detail="Pai Gow hand not found")
    if pre.user_id != current_user:
        raise HTTPException(
            status_code=403,
            detail="Cannot request advice for another player's hand",
        )

    async def _sse_stream() -> AsyncGenerator[bytes, None]:
        from backend.models import PaiGowPlayerHand as _Hand  # noqa: PLC0415

        result = await db.execute(select(_Hand).where(_Hand.id == hand_id))
        hand = result.scalar_one_or_none()
        if hand is None:
            yield b"data: {\"error\": \"Pai Gow hand not found\"}\n\n"
            return

        dealt = list(hand.dealt_cards)
        evaluation = _optimal_set.evaluate_split(dealt, body.front, body.back)
        player_front_str = _cards_str(body.front)
        player_back_str = _cards_str(body.back)
        optimal_front_str = _cards_str(evaluation.optimal_front)
        optimal_back_str = _cards_str(evaluation.optimal_back)

        if evaluation.is_optimal:
            content = (
                f"I split my Pai Gow hand as {player_front_str} in the front "
                f"and {player_back_str} in the back. That matches basic "
                f"strategy exactly. In one or two short sentences, plain prose, "
                f"tell me what makes this the right call."
            )
        else:
            content = (
                f"I split my Pai Gow hand as {player_front_str} in the front "
                f"and {player_back_str} in the back. The optimal split was "
                f"{optimal_front_str} front and {optimal_back_str} back. "
                f"In one or two short sentences, plain prose, tell me what the "
                f"optimal split would have given me that mine didn't."
            )

        messages = [{"role": "user", "content": content}]

        try:
            async for chunk in _stream_anthropic(messages):
                yield f"data: {json.dumps({'text': chunk})}\n\n".encode()
        except Exception as e:  # noqa: BLE001
            logger.exception("Chipy PG post-stream failed")
            fallback = (
                f"(Chipy is offline — "
                f"{'you played it right.' if evaluation.is_optimal else f'optimal was {optimal_front_str} / {optimal_back_str}.'})"
            )
            yield f"data: {json.dumps({'text': fallback, 'error': type(e).__name__})}\n\n".encode()

        final = {
            "is_optimal": evaluation.is_optimal,
            "ev_loss_unit_cents": evaluation.ev_loss_unit_cents,
            "optimal_front": list(evaluation.optimal_front),
            "optimal_back": list(evaluation.optimal_back),
            "reasoning_key": evaluation.reasoning_key,
            "phase": "post",
        }
        yield f"data: {json.dumps(final)}\n\n".encode()

    return StreamingResponse(_sse_stream(), media_type="text/event-stream")
