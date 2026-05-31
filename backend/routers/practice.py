"""
routers/practice.py — Stateless practice grading endpoint for BetWise Casino.

POST /api/practice/grade: given a hand + dealer_upcard + player_action, returns
  the optimal action, EV breakdown, classification, dealer bust probability, and
  an explanation.

Design constraints (specs/blackjack-study.md Pillar 4):
- Stateless: no DB reads or writes. Auth via CurrentUser (JWT check only).
- Pure call chain: strategy.py → ev.py → review.py → odds.py → strategy.explain_decision.
- Empty hand → 400. Malformed body → 422 (Pydantic validation).
- No async calls into game logic (all pure-sync).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from starlette.requests import Request

from backend.auth import CurrentUser
from backend.ratelimit import PRACTICE_RATE_LIMIT, limiter
from backend.schemas import PracticeGradeIn, PracticeGradeOut  # CardIn used inside PracticeGradeIn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/practice", tags=["practice"])


# ─── Route handlers ───────────────────────────────────────────────────────────

@router.post("/grade", response_model=PracticeGradeOut)
@limiter.limit(PRACTICE_RATE_LIMIT)
async def grade_practice(
    request: Request,
    body: PracticeGradeIn,
    current_user: CurrentUser,  # noqa: ARG001  — auth guard only; no DB access
) -> PracticeGradeOut:
    """Grade a practice drill action.

    Stateless: reads no DB tables, writes no player_actions.
    Auth required (CurrentUser) to prevent unauthenticated access.
    Rate-limited per user (mirrors advice.py CSO hardening; see backend/ratelimit.py).
    """
    # Stash user_id on request.state so the limiter keys per-user (not per-IP).
    request.state.user_id = str(current_user)
    return _grade(body)


# ─── Pure helper ─────────────────────────────────────────────────────────────

def _grade(body: PracticeGradeIn) -> PracticeGradeOut:
    """Compute optimal_action, EV breakdown, classification, and explanation.

    Pure function: no DB, no network. All dependencies are pure-sync modules.
    """
    from backend.game.blackjack import ev as ev_mod  # noqa: PLC0415
    from backend.game import strategy  # noqa: PLC0415
    from backend.game.blackjack.odds import dealer_bust_pct  # noqa: PLC0415
    from backend.game.review import classify_action  # noqa: PLC0415
    from backend.game.blackjack.engine import can_double as _can_double, can_split as _can_split  # noqa: PLC0415

    # Convert Pydantic CardIn models to plain dicts for pure-function compatibility.
    hand_dicts: list[dict] = [{"suit": c.suit, "value": c.value} for c in body.hand]
    upcard_dict: dict = {"suit": body.dealer_upcard.suit, "value": body.dealer_upcard.value}

    if not hand_dicts:
        raise HTTPException(status_code=400, detail="hand must not be empty")

    # Compute optimal action
    c_double = _can_double(hand_dicts)  # type: ignore[arg-type]
    c_split = _can_split(hand_dicts)  # type: ignore[arg-type]
    optimal = strategy.optimal_action(
        hand_dicts,
        upcard_dict,
        can_double=c_double,
        can_split=c_split,
    )

    # Compute EV breakdown
    action_evs_map = ev_mod.action_evs(hand_dicts, upcard_dict, can_double=c_double, can_split=c_split)
    best_act, b_ev = ev_mod.best_action_ev(hand_dicts, upcard_dict, can_double=c_double, can_split=c_split)

    ev_of_played = action_evs_map.get(body.action)
    if ev_of_played is None:
        ev_of_played = b_ev  # fallback for unmodeled actions
    ev_delta_val = max(0.0, b_ev - ev_of_played)

    # Classify action (uses EV-delta grading + Sharp tier)
    cls, _ = classify_action(
        hand_dicts, upcard_dict, body.action, optimal, bet=1000,  # dummy bet; class only
    )

    # Dealer bust probability
    d_bust_pct = dealer_bust_pct(upcard_dict)

    # Human-readable explanation
    was_correct = body.action == optimal
    explanation = strategy.explain_decision(
        player_cards=hand_dicts,
        dealer_upcard=upcard_dict,
        was_correct=was_correct,
        player_guess=body.action,
        optimal=optimal,
    )

    return PracticeGradeOut(
        optimal_action=optimal,
        action_evs=action_evs_map,
        best_ev=b_ev,
        ev_delta=ev_delta_val,
        classification=cls,
        dealer_bust_pct=d_bust_pct,
        explanation=explanation,
    )
