"""
routers/advice.py — Chipy AI coaching endpoint for BetWise Casino.

Design constraints (specs/betwise-casino.md §T13):
- Anthropic client is instantiated inside the handler (lazy, not at module import).
- Streak update happens in the same AsyncSession as the request.
- SSE response via StreamingResponse with media_type="text/event-stream".
- Final SSE event is JSON with {optimal_action, was_correct, player_accuracy,
  current_streak, best_streak}.
- No write to player_actions here — that's game.py's job.
- _stream_anthropic is a shimmable helper so tests can patch it.
"""

from __future__ import annotations

import json
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import CurrentUser
from backend.database import get_db
from backend.schemas import AdviceIn

router = APIRouter(prefix="/advice", tags=["advice"])

# System prompt for Chipy (verbatim from source spec Step 3)
_CHIPY_SYSTEM_PROMPT = (
    "You are Chipy, an expert blackjack strategy coach. "
    "Explain decisions clearly and concisely in 2-3 sentences. "
    "Be encouraging and educational. Focus on the mathematical reasoning."
)


async def _stream_anthropic(messages: list[dict]) -> AsyncGenerator[str, None]:
    """Shimmable helper: streams text chunks from Anthropic.

    Tests patch backend.routers.advice._stream_anthropic to avoid real API calls.
    Lazy client construction — never fails on import even without ANTHROPIC_API_KEY.
    """
    import anthropic  # noqa: PLC0415

    client = anthropic.AsyncAnthropic()
    async with client.messages.stream(
        model="claude-sonnet-4-20250514",
        max_tokens=256,
        system=_CHIPY_SYSTEM_PROMPT,
        messages=messages,
    ) as stream:
        async for event in stream:
            if (
                hasattr(event, "delta")
                and hasattr(event.delta, "type")
                and event.delta.type == "text_delta"
            ):
                yield event.delta.text


# ─── Route handlers ───────────────────────────────────────────────────────────

@router.post("/{hand_id}")
async def get_advice(
    hand_id: uuid.UUID,
    body: AdviceIn,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream Chipy's coaching explanation and update the user's streak."""
    from sqlalchemy import select  # noqa: PLC0415
    from backend.models import Hand  # noqa: PLC0415

    # ── Ownership check before streaming begins ──────────────────────────────
    pre_result = await db.execute(select(Hand).where(Hand.id == hand_id))
    pre_hand = pre_result.scalar_one_or_none()
    if pre_hand is None:
        raise HTTPException(status_code=404, detail="Hand not found")
    if pre_hand.user_id != current_user:
        raise HTTPException(status_code=403, detail="Cannot request advice for another player's hand")

    async def _sse_stream() -> AsyncGenerator[bytes, None]:
        from sqlalchemy import select, update  # noqa: PLC0415
        from backend.models import Hand, GameSession, User  # noqa: PLC0415
        from backend.game import strategy  # noqa: PLC0415
        from backend.game import engine as eng  # noqa: PLC0415

        # ── Load hand + session ──────────────────────────────────────────────
        result = await db.execute(select(Hand).where(Hand.id == hand_id))
        hand = result.scalar_one_or_none()
        if hand is None:
            yield b"data: {\"error\": \"Hand not found\"}\n\n"
            return

        result = await db.execute(
            select(GameSession).where(GameSession.id == hand.session_id)
        )
        session = result.scalar_one_or_none()
        if session is None:
            yield b"data: {\"error\": \"Session not found\"}\n\n"
            return

        dealer_cards = list(session.dealer_cards)
        dealer_upcard = dealer_cards[0] if dealer_cards else {"suit": "spades", "value": "2"}

        # ── Compute optimal action ───────────────────────────────────────────
        opt = strategy.optimal_action(
            hand.cards,
            dealer_upcard,
            can_double=eng.can_double(hand.cards),
            can_split=eng.can_split(hand.cards),
        )
        was_correct = body.player_guess == opt

        # ── Update streak (gold feature) ─────────────────────────────────────
        result = await db.execute(select(User).where(User.id == current_user))
        user = result.scalar_one_or_none()
        if user is not None:
            if was_correct:
                user.current_streak += 1
                if user.current_streak > user.best_streak:
                    user.best_streak = user.current_streak
            else:
                user.current_streak = 0
            # Update accuracy stats (total_hands / correct_decisions NOT updated here —
            # that's the game action endpoint's job; we only track streak in advice)
            await db.flush()
            await db.refresh(user)
            current_streak = user.current_streak
            best_streak = user.best_streak
            player_accuracy = (
                user.correct_decisions / user.total_hands
                if user.total_hands > 0
                else 0.0
            )
        else:
            current_streak = 0
            best_streak = 0
            player_accuracy = 0.0

        # ── Build Chipy prompt ───────────────────────────────────────────────
        hand_desc = strategy.explain_decision(
            player_cards=hand.cards,
            dealer_upcard=dealer_upcard,
            was_correct=was_correct,
            player_guess=body.player_guess,
            optimal=opt,
        )
        messages = [
            {
                "role": "user",
                "content": (
                    f"I had {hand_desc} "
                    f"I guessed '{body.player_guess}' and the optimal play was '{opt}'. "
                    f"Please explain why '{opt}' is {'correct' if was_correct else 'the better choice'}."
                ),
            }
        ]

        # ── Stream Anthropic response ────────────────────────────────────────
        async for chunk in _stream_anthropic(messages):
            yield f"data: {json.dumps({'text': chunk})}\n\n".encode()

        # ── Final summary event ──────────────────────────────────────────────
        final = {
            "optimal_action": opt,
            "was_correct": was_correct,
            "player_accuracy": player_accuracy,
            "current_streak": current_streak,
            "best_streak": best_streak,
        }
        yield f"data: {json.dumps(final)}\n\n".encode()

    return StreamingResponse(
        _sse_stream(),
        media_type="text/event-stream",
    )
