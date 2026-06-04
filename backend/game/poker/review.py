"""
review.py — compute-on-read decision review assembly for Texas Hold'em.

Pure, sync. Given a finished hand's already-persisted rows (deck/board, the
big-blind size, the dealt hole cards per engine seat, and the ordered action
log), this module replays the hand through ``backend.game.poker.state`` and, for
each action belonging to the requesting user, builds a ``DecisionSnapshot``,
computes win-equity via ``backend.game.poker.equity.hand_equity``, and grades it
with ``oracle.classify_decision``.

Design constraints (specs/poker-review-pr2.md "Shared backend assembly"):
- No DB, no network — the router loads rows and passes plain data in.
- Reproducible: equity is seeded from a stable hash of the hand id, so the same
  hand reviewed twice yields identical verdicts/equities.
- Range model: multiplayer → ``default_range()`` per live opponent; solo → the
  bot archetype range when available, else ``default_range()``.
- pot_bb is the pot BEFORE the bet faced (the convention ``required_equity`` and
  the oracle's EV math expect).
- Opponent hole cards never leave this module — equity is range-based, so only
  the hero's hole cards are required as concrete cards.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional

from .cards import Card
from .equity import Range, default_range, hand_equity
from .oracle import DecisionSnapshot, Verdict, classify_decision
from .ranges import hand_str
from .state import (
    BettingState,
    SeatAction,
    advance_street,
    apply_action,
    create_state,
    street_closed,
)
from .tournament import seat_position_label

# Chips per big blind used by the oracle when it converts ev_loss_bb back to
# chips (oracle multiplies bb by 100). We never read that chip value here — we
# carry ev_loss_bb directly — but keep MC iteration budget aligned with PR2.
_MAX_EQUITY_ITERS = 2000

# Streets in dealing order; index = how many board cards are visible.
_STREET_BOARD_LEN: dict[str, int] = {
    "preflop": 0,
    "flop": 3,
    "turn": 4,
    "river": 5,
    "complete": 5,
}

_GRADED_VERDICTS: frozenset[Verdict] = frozenset(
    {"best", "good", "inaccuracy", "mistake", "blunder"}
)


# ─── Inputs ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ReviewSeatRow:
    """One engine seat in a finished hand (game-agnostic)."""

    seat_number: int                  # engine index 0..k-1
    starting_stack: int
    hole_cards: tuple[Card, ...]      # 2 cards, or () for a seat with no cards
    is_hero: bool                     # True iff this seat belongs to the caller


@dataclass(frozen=True)
class ReviewActionRow:
    """One logged action (blind/ante posts included), in action_index order."""

    seat_number: int
    action: str                       # fold|check|call|raise|all_in|post_blind|post_ante
    amount: int                       # chips paid this action (engine current_bet delta)
    is_hero: bool                     # True iff this action belongs to the caller


@dataclass(frozen=True)
class ReviewHandInput:
    """Everything the assembly needs for one finished hand. Pure data."""

    hand_id: str
    game: str                         # "holdem" | "poker"
    big_blind: int
    small_blind: int
    button_seat: int
    ante: int
    board: tuple[Card, ...]           # full board reached in the hand (0..5 cards)
    seats: tuple[ReviewSeatRow, ...]
    actions: tuple[ReviewActionRow, ...]
    hero_hole: tuple[Card, ...]       # the caller's two hole cards
    n_seats: int
    villain_ranges: Optional[tuple[Range, ...]] = None
    # Per-live-opponent ranges to use for solo (archetype-derived). When None,
    # default_range() is used for every live opponent (multiplayer).


# ─── Output ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GradedAction:
    """One graded caller decision in a HandReview."""

    action_index: int
    street: str
    action: str
    amount_bb: float
    verdict: Verdict
    confidence_tier: str
    recommended_action: Optional[str]
    equity: Optional[float]
    required_equity: Optional[float]
    ev_loss_bb: Optional[float]
    explanation: Optional[str]


@dataclass(frozen=True)
class HandReview:
    """Per-hand decision review for one caller."""

    hand_id: str
    game: str
    your_hole: tuple[Card, ...]
    board: tuple[Card, ...]
    graded_count: int
    accuracy: float
    ev_lost_bb: float
    worst_action_index: Optional[int]
    actions: tuple[GradedAction, ...]


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _stable_seed(hand_id: str) -> int:
    """Deterministic non-negative 31-bit seed derived from the hand id.

    Uses BLAKE2b so it does not depend on PYTHONHASHSEED (Python's builtin
    ``hash`` is salted per-process and would break reproducibility across runs).
    """
    digest = hashlib.blake2b(hand_id.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") & 0x7FFFFFFF


def _to_seat_action(action: str) -> SeatAction:
    return action  # type: ignore[return-value]


def _hero_hand_str(hole: tuple[Card, ...]) -> str:
    if len(hole) != 2:
        return ""
    return hand_str(hole[0]["value"], hole[0]["suit"], hole[1]["value"], hole[1]["suit"])


def _board_for_street(full_board: tuple[Card, ...], street: str) -> tuple[Card, ...]:
    """Slice the full board down to what was visible on the given street."""
    n = _STREET_BOARD_LEN.get(street, 0)
    return tuple(full_board[:n])


# ─── Assembly ──────────────────────────────────────────────────────────────────


def build_hand_review(data: ReviewHandInput) -> HandReview:
    """Replay a finished hand and grade every action belonging to the caller.

    Returns a HandReview with one GradedAction per caller action (in order).
    Ungradeable spots carry verdict ``no_verdict`` with confidence_tier
    ``HEURISTIC`` and null EV fields; they do NOT count toward graded_count.
    """
    seed = _stable_seed(data.hand_id)
    hero_hole = data.hero_hole
    hero_hand_str = _hero_hand_str(hero_hole)

    # Rebuild the opening state. create_state posts blinds/antes itself, so the
    # logged post_blind/post_ante actions are NOT re-applied below.
    starting_stacks = [s.starting_stack for s in sorted(data.seats, key=lambda s: s.seat_number)]
    state: BettingState = create_state(
        starting_stacks=starting_stacks,
        button_seat=data.button_seat,
        small_blind=data.small_blind,
        big_blind=data.big_blind,
        ante=data.ante,
    )

    graded: list[GradedAction] = []
    bb = float(data.big_blind) if data.big_blind else 1.0

    for idx, rec in enumerate(data.actions):
        if rec.action in ("post_blind", "post_ante"):
            # create_state already posted these; skip in the replay.
            continue

        # Advance any closed streets BEFORE this action so the snapshot's
        # street/board/pot reflect the moment the caller decided.
        while street_closed(state) and state.street != "complete":
            state = advance_street(state)

        if rec.is_hero:
            graded.append(
                _grade_one(
                    data=data,
                    state=state,
                    rec=rec,
                    action_index=idx,
                    seed=seed,
                    bb=bb,
                    hero_hole=hero_hole,
                    hero_hand_str=hero_hand_str,
                )
            )

        # Apply the action to move the replay forward. apply_action expects a
        # `raise` amount to be the absolute raise-to LEVEL. The two games store it
        # differently in their action logs:
        #   - holdem.py logs the chips PAID (the engine's current_bet delta), so
        #     convert: raise_to = current_bet_before + delta.
        #   - poker_game.py logs the absolute raise-to level already (body.amount
        #     for humans, the computed raise-to for bots), so pass it through.
        # call/check/fold/all_in derive/ignore the amount in apply_action.
        apply_amount = rec.amount
        if rec.action == "raise" and data.game == "holdem":
            seat_before = state.seats[rec.seat_number]
            apply_amount = seat_before.current_bet + rec.amount
        try:
            state = apply_action(state, rec.seat_number, _to_seat_action(rec.action), apply_amount)
        except ValueError:
            # The stored log should always be legal; if a raise-to can't be
            # reconstructed (e.g. a short all-in logged as a raise), fall back to
            # an all-in so the replay does not abort mid-hand.
            state = apply_action(state, rec.seat_number, "all_in", 0)

    return _finalize(data, hero_hole, graded)


def _grade_one(
    *,
    data: ReviewHandInput,
    state: BettingState,
    rec: ReviewActionRow,
    action_index: int,
    seed: int,
    bb: float,
    hero_hole: tuple[Card, ...],
    hero_hand_str: str,
) -> GradedAction:
    """Build a snapshot at this decision point, compute equity, classify."""
    hero_seat = state.seats[rec.seat_number]
    to_call_chips = max(0, state.current_bet_to_match - hero_seat.current_bet)
    # pot_bb = pot BEFORE the bet the hero faces (oracle / required_equity
    # convention). state.pot_committed holds completed-street chips; the live
    # street's matched chips sit in current_bet. The pot the hero would win is
    # everything already in, minus the un-called portion of the bet faced.
    live_street_chips = sum(s.current_bet for s in state.seats)
    pot_before_faced = state.pot_committed + live_street_chips - to_call_chips
    pot_bb = max(0.0, pot_before_faced / bb)
    to_call_bb = to_call_chips / bb
    stack_bb = hero_seat.stack / bb

    board = _board_for_street(data.board, state.street)
    n_live_opp = len([s for s in state.live_seats() if s.seat_number != rec.seat_number])

    # Range model: solo passes per-opponent archetype ranges; multiplayer (and
    # any solo fallback) uses default_range() per live opponent.
    if data.villain_ranges is not None and len(data.villain_ranges) >= 1:
        villain_ranges = list(data.villain_ranges[: max(1, n_live_opp)])
        while len(villain_ranges) < max(1, n_live_opp):
            villain_ranges.append(default_range())
    else:
        villain_ranges = [default_range() for _ in range(max(1, n_live_opp))]

    live_equity: Optional[float] = None
    if len(hero_hole) == 2:
        live_equity = hand_equity(
            (hero_hole[0], hero_hole[1]),
            villain_ranges,
            list(board),
            seed=seed + action_index,  # stable per-action, still deterministic
            max_iters=_MAX_EQUITY_ITERS,
        )

    position = seat_position_label(rec.seat_number, data.button_seat, data.n_seats)

    snapshot = DecisionSnapshot(
        hole=(hero_hole[0], hero_hole[1]) if len(hero_hole) == 2 else (
            {"suit": "hearts", "value": "2"}, {"suit": "spades", "value": "2"}
        ),
        board=board,
        street=state.street,  # type: ignore[arg-type]
        position=position,
        hand_str=hero_hand_str,
        stack_bb=stack_bb,
        pot_bb=pot_bb,
        to_call_bb=to_call_bb,
        n_live_opponents=n_live_opp,
        seats_remaining=data.n_seats,
        is_bubble=False,  # review does not model the tournament bubble (v1)
        live_equity=live_equity,
    )

    classification = classify_decision(snapshot, _to_human_action(rec.action), "odds")

    return GradedAction(
        action_index=action_index,
        street=state.street,
        action=rec.action,
        amount_bb=rec.amount / bb,
        verdict=classification.verdict,
        confidence_tier=classification.confidence_tier,
        recommended_action=classification.recommended_action,
        equity=classification.equity,
        required_equity=classification.required_equity,
        ev_loss_bb=classification.ev_loss_bb,
        explanation=classification.explanation or classification.coach_summary,
    )


def _to_human_action(action: str) -> str:
    # The oracle's HumanAction excludes the blind/ante posts (filtered earlier).
    return action


def _finalize(
    data: ReviewHandInput,
    hero_hole: tuple[Card, ...],
    graded: list[GradedAction],
) -> HandReview:
    graded_actions = [g for g in graded if g.verdict in _GRADED_VERDICTS]
    graded_count = len(graded_actions)
    good = sum(1 for g in graded_actions if g.verdict in ("best", "good"))
    accuracy = (good / graded_count) if graded_count else 0.0
    ev_lost = sum((g.ev_loss_bb or 0.0) for g in graded_actions)

    worst_idx: Optional[int] = None
    worst_loss = -1.0
    for g in graded_actions:
        loss = g.ev_loss_bb or 0.0
        if loss > worst_loss:
            worst_loss = loss
            worst_idx = g.action_index
    if worst_loss <= 0.0:
        worst_idx = None

    return HandReview(
        hand_id=data.hand_id,
        game=data.game,
        your_hole=hero_hole,
        board=data.board,
        graded_count=graded_count,
        accuracy=accuracy,
        ev_lost_bb=ev_lost,
        worst_action_index=worst_idx,
        actions=tuple(graded),
    )


def aggregate_game_review(reviews: list[HandReview]) -> tuple[float, float, int]:
    """Aggregate per-hand reviews into (overall_accuracy, total_ev_lost_bb, graded_count).

    overall_accuracy = total (best+good) / total graded over the scope.
    """
    total_graded = sum(r.graded_count for r in reviews)
    total_ev = sum(r.ev_lost_bb for r in reviews)
    total_good = sum(round(r.accuracy * r.graded_count) for r in reviews)
    overall = (total_good / total_graded) if total_graded else 0.0
    return overall, total_ev, total_graded


def worst_verdict(review: HandReview) -> Optional[Verdict]:
    """The single worst (best→blunder) graded verdict in a hand, or None."""
    order: dict[Verdict, int] = {
        "best": 0, "good": 1, "inaccuracy": 2, "mistake": 3, "blunder": 4, "no_verdict": -1,
    }
    worst: Optional[Verdict] = None
    worst_rank = -1
    for g in review.actions:
        if g.verdict not in _GRADED_VERDICTS:
            continue
        r = order[g.verdict]
        if r > worst_rank:
            worst_rank = r
            worst = g.verdict
    return worst


__all__ = [
    "ReviewSeatRow",
    "ReviewActionRow",
    "ReviewHandInput",
    "GradedAction",
    "HandReview",
    "build_hand_review",
    "aggregate_game_review",
    "worst_verdict",
]
