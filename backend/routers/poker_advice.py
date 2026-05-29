"""
routers/poker_advice.py — Chipy AI coaching SSE endpoint for Texas Hold'em.

Design constraints (specs/texas-holdem.md §AC-R7..R9, AC-R12):
- POST /api/poker/hands/{hand_id}/advice streams text chunks via SSE.
- Mode (reads/odds) is read from the tournament's advice_mode setting; the
  prompts module routes to build_reads_prompt or build_odds_prompt.
- Final SSE event is JSON with the PokerAdviceOut shape:
  {recommended_action, confidence_tier, verdict, ev_loss_chips, principle_note}
- Only the seat that owns the hand can request advice (AC-R9).
- Rate-limited via shared slowapi limiter (10/minute).
- Anthropic client is lazy/shimmable for test mocking.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import AsyncGenerator, cast

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from backend.auth import CurrentUser
from backend.database import get_db
from backend.ratelimit import ADVICE_RATE_LIMIT, limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/poker/hands", tags=["poker_advice"])


_POKER_CHIPY_SYSTEM_PROMPT = (
    "You are Chipy, an educational Texas Hold'em coach. Speak in 1-2 short, "
    "warm sentences of plain prose. Always cite a confidence tier — "
    "DETERMINISTIC for ≤15bb push/fold or pot-odds calls vs all-ins; "
    "HEURISTIC otherwise. For HEURISTIC spots, give principles, never a single "
    "correct action. Plain text only — no markdown."
)


async def _stream_anthropic_poker(system: str, user: str) -> AsyncGenerator[str, None]:
    """Shimmable helper. Tests patch this to avoid hitting the real API."""
    import os as _os  # noqa: PLC0415

    import anthropic  # noqa: PLC0415

    model = _os.environ.get("CHIPY_MODEL", "claude-sonnet-4-6")
    client = anthropic.AsyncAnthropic()
    async with client.messages.stream(
        model=model,
        max_tokens=256,
        system=_POKER_CHIPY_SYSTEM_PROMPT + "\n\n" + system,
        messages=[{"role": "user", "content": user}],
    ) as stream:
        async for event in stream:
            if (
                hasattr(event, "delta")
                and hasattr(event.delta, "type")
                and event.delta.type == "text_delta"
            ):
                yield event.delta.text


@router.post("/{hand_id}/advice")
@limiter.limit(ADVICE_RATE_LIMIT)
async def stream_poker_advice(
    request: Request,
    hand_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream Chipy's coaching explanation for the hand in progress."""
    request.state.user_id = str(current_user)

    snapshot, mode, archetypes_by_seat, classification = await _build_advice_payload(
        hand_id, current_user, db
    )

    async def _sse_stream() -> AsyncGenerator[bytes, None]:
        from backend.game.poker.prompts import (  # noqa: PLC0415
            build_odds_prompt,
            build_reads_prompt,
        )

        if mode == "reads":
            system, user = build_reads_prompt(snapshot, archetypes_by_seat)
        else:
            system, user = build_odds_prompt(snapshot)

        try:
            async for chunk in _stream_anthropic_poker(system, user):
                payload = json.dumps({"text": chunk})
                yield f"data: {payload}\n\n".encode("utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Anthropic stream error: %s", exc)
            err_payload = json.dumps({
                "text": (
                    "(Coach unavailable right now. Using the deterministic verdict only.)"
                ),
                "error": "stream_failure",
            })
            yield f"data: {err_payload}\n\n".encode("utf-8")

        # Final event: the structured PokerAdviceOut shape
        final = {
            "recommended_action": classification.recommended_action,
            "confidence_tier": classification.confidence_tier,
            "verdict": classification.verdict,
            "ev_loss_chips": classification.ev_loss_chips,
            "principle_note": classification.principle_note,
        }
        yield f"data: {json.dumps(final)}\n\n".encode("utf-8")

    return StreamingResponse(_sse_stream(), media_type="text/event-stream")


# ─── SQL helper (single per router) ───────────────────────────────────────────


async def _build_advice_payload(
    hand_id: uuid.UUID,
    current_user: uuid.UUID,
    db: AsyncSession,
):
    """Build the DecisionSnapshot + archetypes map for the requesting user's
    current decision point. Raises HTTPException for auth + not-found."""
    from sqlalchemy import select  # noqa: PLC0415

    from backend.game.poker.archetypes import ARCHETYPE_REGISTRY  # noqa: PLC0415
    from backend.game.poker.oracle import DecisionSnapshot, classify_decision  # noqa: PLC0415
    from backend.game.poker.ranges import hand_str  # noqa: PLC0415
    from backend.game.poker.tournament import (  # noqa: PLC0415
        payout_pcts_for_seats,
        seat_position_label,
    )
    from backend.models import (  # noqa: PLC0415
        PokerHand,
        PokerHandSeat,
        PokerSeat,
        PokerTournament,
    )

    hand = (await db.execute(select(PokerHand).where(PokerHand.id == hand_id))).scalar_one_or_none()
    if hand is None:
        raise HTTPException(status_code=404, detail="Hand not found")

    tournament = (await db.execute(
        select(PokerTournament).where(PokerTournament.id == hand.tournament_id)
    )).scalar_one()

    seats = (await db.execute(
        select(PokerSeat)
        .where(PokerSeat.tournament_id == hand.tournament_id)
        .order_by(PokerSeat.seat_number)
    )).scalars().all()

    user_seat = next((s for s in seats if s.user_id == current_user), None)
    if user_seat is None:
        raise HTTPException(status_code=403, detail="Cannot request advice for another player's hand")

    user_hand_seat = (await db.execute(
        select(PokerHandSeat).where(
            PokerHandSeat.hand_id == hand_id,
            PokerHandSeat.seat_number == user_seat.seat_number,
        )
    )).scalar_one_or_none()
    if user_hand_seat is None or len(user_hand_seat.hole_cards) != 2:
        raise HTTPException(status_code=400, detail="No active hand for this user")

    hole = tuple(user_hand_seat.hole_cards)
    h_str = hand_str(
        hole[0]["value"], hole[0]["suit"],
        hole[1]["value"], hole[1]["suit"],
    )

    n_paid = len(payout_pcts_for_seats(len(seats)))
    live_seats = [s for s in seats if not s.is_bust]
    is_bubble = len(live_seats) == n_paid + 1

    snapshot = DecisionSnapshot(
        hole=hole,
        board=tuple(hand.board),
        street=cast("any", hand.street),
        position=seat_position_label(user_seat.seat_number, hand.button_seat, len(seats)),
        hand_str=h_str,
        stack_bb=user_hand_seat.final_stack / hand.big_blind if hand.big_blind else 0,
        pot_bb=hand.pot_total / hand.big_blind if hand.big_blind else 0,
        to_call_bb=(hand.current_bet_to_match - user_hand_seat.current_bet) / hand.big_blind if hand.big_blind else 0,
        n_live_opponents=max(0, len(live_seats) - 1),
        seats_remaining=len(live_seats),
        is_bubble=is_bubble,
        live_equity=None,
    )

    # Classify hypothetical "call" for the recommended_action surface — the
    # advice endpoint shows what the engine recommends; the human's actual
    # action will be classified by the act endpoint.
    classification = classify_decision(snapshot, "call", cast("any", tournament.advice_mode))

    archetypes_by_seat = {}
    for s in seats:
        if s.archetype_name and s.archetype_name in ARCHETYPE_REGISTRY:
            archetypes_by_seat[s.seat_number] = ARCHETYPE_REGISTRY[s.archetype_name]

    return snapshot, tournament.advice_mode, archetypes_by_seat, classification


__all__ = ["router", "_stream_anthropic_poker"]
