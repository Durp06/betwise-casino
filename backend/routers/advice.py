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
from starlette.requests import Request

from backend.auth import CurrentUser
from backend.database import get_db
from backend.ratelimit import ADVICE_RATE_LIMIT, limiter
from backend.schemas import AdviceIn

router = APIRouter(prefix="/advice", tags=["advice"])

# System prompt for Chipy.
#
# Plain-text constraint: the panel renders these chunks as raw text, so any
# markdown (## headers, ** bold, * bullets, backticks) shows up literally and
# looks busted. We instruct the model to write in plain prose. The client also
# strips these defensively in ChipyCoach.tsx as a belt-and-suspenders.
_CHIPY_SYSTEM_PROMPT = (
    "You are Chipy, an expert blackjack strategy coach sitting next to a friend "
    "at the table. Speak in warm conversational prose, 1-2 short sentences. "
    "Always give a reason. "
    "Plain text only — no markdown. Do not use #, ##, **, *, backticks, or "
    "bullet points. Do not bold or italicize anything."
)


async def _stream_anthropic(messages: list[dict]) -> AsyncGenerator[str, None]:
    """Shimmable helper: streams text chunks from Anthropic.

    Tests patch backend.routers.advice._stream_anthropic to avoid real API calls.
    Lazy client construction — never fails on import even without ANTHROPIC_API_KEY.
    """
    import anthropic  # noqa: PLC0415
    import os as _os  # noqa: PLC0415

    # Model is overridable via env so we don't have to ship a new commit when
    # Anthropic rotates the recommended Sonnet/Haiku alias.
    model = _os.environ.get("CHIPY_MODEL", "claude-sonnet-4-6")
    client = anthropic.AsyncAnthropic()
    async with client.messages.stream(
        model=model,
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
@limiter.limit(ADVICE_RATE_LIMIT)
async def get_advice(
    request: Request,
    hand_id: uuid.UUID,
    body: AdviceIn,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream Chipy's coaching explanation and update the user's streak."""
    from sqlalchemy import select  # noqa: PLC0415
    from backend.models import Hand  # noqa: PLC0415

    # Stash the authenticated user on request.state so the slowapi key function
    # (in backend/ratelimit.py) keys on user instead of remote IP.
    request.state.user_id = str(current_user)

    # ── Ownership check before streaming begins ──────────────────────────────
    pre_result = await db.execute(select(Hand).where(Hand.id == hand_id))
    pre_hand = pre_result.scalar_one_or_none()
    if pre_hand is None:
        raise HTTPException(status_code=404, detail="Hand not found")
    if pre_hand.user_id != current_user:
        raise HTTPException(status_code=403, detail="Cannot request advice for another player's hand")

    async def _sse_stream() -> AsyncGenerator[bytes, None]:
        from sqlalchemy import select  # noqa: PLC0415
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
        from backend.game.blackjack import odds as _odds  # noqa: PLC0415

        hand_desc = strategy.explain_decision(
            player_cards=hand.cards,
            dealer_upcard=dealer_upcard,
            was_correct=was_correct,
            player_guess=body.player_guess,
            optimal=opt,
        )
        bust_pct = _odds.dealer_bust_pct(dealer_upcard)
        bust_pct_int = round(bust_pct * 100)
        messages = [
            {
                "role": "user",
                "content": (
                    f"I had {hand_desc} "
                    f"I guessed '{body.player_guess}' and the optimal play was '{opt}'. "
                    f"Dealer bust probability for that upcard is {bust_pct_int}% "
                    f"({bust_pct:.2f}). "
                    f"Please explain why '{opt}' is "
                    f"{'correct' if was_correct else 'the better choice'}, "
                    f"and weave the dealer bust % into your reasoning."
                ),
            }
        ]

        # ── Stream Anthropic response ────────────────────────────────────────
        try:
            async for chunk in _stream_anthropic(messages):
                yield f"data: {json.dumps({'text': chunk})}\n\n".encode()
        except Exception as e:  # noqa: BLE001
            # Anthropic failure (deprecated model, quota, network…) must reach
            # the client as an SSE event — otherwise the stream just stops with
            # no body and the frontend spinner hangs forever. Falls through
            # so the final summary event still fires (with optimal_action).
            import logging as _logging  # noqa: PLC0415

            _logging.getLogger(__name__).exception("Chipy stream failed")
            fallback_text = (
                f"(Chipy is offline right now — optimal play is to {opt}. "
                f"Tap Confirm to continue.)"
            )
            yield f"data: {json.dumps({'text': fallback_text, 'error': type(e).__name__})}\n\n".encode()

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


@router.post("/{hand_id}/pre")
@limiter.limit(ADVICE_RATE_LIMIT)
async def get_pre_advice(
    request: Request,
    hand_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream Chipy's pre-action suggestion for the given hand.

    Unlike POST /api/advice/{hand_id} (which expects a player guess and updates
    the user's streak), this endpoint just narrates the current state and
    suggests the optimal play. Used by ChipyCoach to chime in proactively
    the moment it's the player's turn — no commitment from the player yet.
    No streak update, no player_actions write.
    """
    from sqlalchemy import select  # noqa: PLC0415
    from backend.models import Hand  # noqa: PLC0415

    # Per-user rate-limit key (see backend/ratelimit.py).
    request.state.user_id = str(current_user)

    # ── Ownership check before streaming begins ──────────────────────────────
    pre_result = await db.execute(select(Hand).where(Hand.id == hand_id))
    pre_hand = pre_result.scalar_one_or_none()
    if pre_hand is None:
        raise HTTPException(status_code=404, detail="Hand not found")
    if pre_hand.user_id != current_user:
        raise HTTPException(status_code=403, detail="Cannot request advice for another player's hand")

    async def _sse_stream() -> AsyncGenerator[bytes, None]:
        from sqlalchemy import select  # noqa: PLC0415
        from backend.models import Hand, GameSession  # noqa: PLC0415
        from backend.game import strategy  # noqa: PLC0415
        from backend.game import engine as eng  # noqa: PLC0415

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

        opt = strategy.optimal_action(
            list(hand.cards),
            dealer_upcard,
            can_double=eng.can_double(list(hand.cards)),
            can_split=eng.can_split(list(hand.cards)),
        )

        # Build a plain-English description of the situation
        def _card_str(c: dict) -> str:
            return f"{c['value']} of {c['suit']}"

        cards_str = ", ".join(_card_str(c) for c in hand.cards if c)
        upcard_str = _card_str(dealer_upcard)

        messages = [
            {
                "role": "user",
                "content": (
                    f"It's my turn. I'm holding {cards_str}. Dealer shows {upcard_str}. "
                    f"Basic strategy says the best play is '{opt}'. "
                    f"In one or two short sentences, plain prose, tell me which play "
                    f"you'd recommend and the reason. No markdown — no #, **, *, or backticks."
                ),
            }
        ]

        try:
            async for chunk in _stream_anthropic(messages):
                yield f"data: {json.dumps({'text': chunk})}\n\n".encode()
        except Exception as e:  # noqa: BLE001
            import logging as _logging  # noqa: PLC0415

            _logging.getLogger(__name__).exception("Chipy pre-stream failed")
            fallback_text = f"(Chipy's quiet — basic strategy says {opt} here.)"
            yield f"data: {json.dumps({'text': fallback_text, 'error': type(e).__name__})}\n\n".encode()

        # Final summary event so the client can flip the streaming flag.
        # No streak / accuracy update — that's reserved for the post-play endpoint.
        final = {"optimal_action": opt, "phase": "pre"}
        yield f"data: {json.dumps(final)}\n\n".encode()

    return StreamingResponse(
        _sse_stream(),
        media_type="text/event-stream",
    )
