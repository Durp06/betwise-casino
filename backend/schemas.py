"""
schemas.py — Pydantic v2 request/response schemas for BetWise Casino.

Design constraints (specs/betwise-casino.md §T4):
- All schemas use model_config = ConfigDict(from_attributes=True).
- Literal types match DB CHECK constraints exactly.
- Includes streak fields (current_streak, best_streak) per gold feature.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

# ─── Card ─────────────────────────────────────────────────────────────────────

CardSuit = Literal["hearts", "diamonds", "clubs", "spades"]
CardValue = Literal["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
Action = Literal["hit", "stand", "double", "split"]


class CardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    suit: str
    value: str


# ─── Users ────────────────────────────────────────────────────────────────────

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    username: str
    chip_balance: int
    created_at: datetime


class UserStatsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    username: str
    chip_balance: int
    total_hands: int
    correct_decisions: int
    accuracy: float
    current_streak: int
    best_streak: int
    created_at: datetime


class UserCreateIn(BaseModel):
    username: str


# ─── Tables ───────────────────────────────────────────────────────────────────

class TableCreateIn(BaseModel):
    name: str
    min_bet: int = 500
    max_bet: int = 50_000
    game_type: str = "blackjack"


class TableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    min_bet: int
    max_bet: int
    max_seats: int
    status: str
    created_at: datetime


class TableListOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    min_bet: int
    max_bet: int
    max_seats: int
    status: str
    seats_taken: int


class SeatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    user_id: uuid.UUID
    seat_number: int
    username: Optional[str] = None
    chip_balance: Optional[int] = None


class HandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    session_id: uuid.UUID
    user_id: uuid.UUID
    cards: list
    bet: int
    status: str
    outcome: Optional[str] = None
    payout: Optional[int] = None


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    table_id: uuid.UUID
    game_type: str
    dealer_cards: list
    status: str
    created_at: datetime


class TableStateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    status: str
    seats: list[SeatOut]
    session: Optional[SessionOut] = None
    hands: list[HandOut]


# ─── Game actions ─────────────────────────────────────────────────────────────

class DealIn(BaseModel):
    bet: int


class ActionIn(BaseModel):
    action: Action


# ─── Advice ───────────────────────────────────────────────────────────────────

class AdviceIn(BaseModel):
    player_guess: Action


class AdviceOut(BaseModel):
    optimal_action: Action
    was_correct: bool
    player_accuracy: float
    current_streak: int
    best_streak: int


# ─── Analytics / Weakness ─────────────────────────────────────────────────────

class WeakSpotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    hand_category: str
    dealer_upcard_category: str
    samples: int
    correct: int
    accuracy: float


# ─── Leaderboard ─────────────────────────────────────────────────────────────

class LeaderboardRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    rank: int
    user_id: uuid.UUID
    username: str
    chip_balance: int
    total_hands: int
    accuracy_pct: float
    best_streak: int


# ─── Hand replay (gold) ───────────────────────────────────────────────────────

class HandReplayActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    hand_id: uuid.UUID
    user_id: uuid.UUID
    action: str
    player_guess: str
    optimal_action: str
    was_correct: bool
    hand_snapshot: list
    dealer_upcard: dict
    chipy_explanation: Optional[str] = None
    created_at: datetime


# ─── Session review (Hand Review modal) ──────────────────────────────────────

Classification = Literal["best", "good", "inaccuracy", "mistake", "blunder"]


class ReviewActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    hand_id: uuid.UUID
    user_id: uuid.UUID
    action: str
    player_guess: str
    optimal_action: str
    was_correct: bool
    hand_snapshot: list
    dealer_upcard: dict
    chipy_explanation: Optional[str] = None
    created_at: datetime
    classification: Classification
    ev_loss_chips: int


class SessionReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    session_id: uuid.UUID
    hand_id: uuid.UUID
    total_actions: int
    optimal_count: int
    accuracy: float
    ev_lost_chips: int
    worst_action_id: Optional[uuid.UUID] = None
    actions: list[ReviewActionOut]


# ═════════════════════════════════════════════════════════════════════════════
# Texas Hold'em schemas (specs/texas-holdem.md §AC-S1..S4)
# ═════════════════════════════════════════════════════════════════════════════

PokerAdviceMode = Literal["reads", "odds"]
PokerActionType = Literal["fold", "check", "call", "raise", "all_in"]
PokerConfidenceTier = Literal["DETERMINISTIC", "HEURISTIC"]
PokerVerdict = Literal["best", "good", "inaccuracy", "mistake", "blunder", "no_verdict"]
PokerStreet = Literal["preflop", "flop", "turn", "river", "complete"]


class PokerCardOut(BaseModel):
    """Card as JSON object. Same shape as blackjack CardOut. None values for
    masked opponent hole cards."""

    model_config = ConfigDict(from_attributes=True)
    suit: str
    value: str


class PokerTournamentCreateIn(BaseModel):
    bot_count: int                     # 2..7
    advice_mode: PokerAdviceMode = "odds"
    buy_in_cents: int
    starting_stack_chips: int = 1500
    hands_per_level: int = 10


class PokerTournamentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    bot_count: int
    advice_mode: str
    buy_in_cents: int
    starting_stack_chips: int
    hands_per_level: int
    seed: int
    status: str
    button_seat: int
    current_hand_number: int
    created_at: datetime


class PokerSeatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    seat_number: int
    user_id: Optional[uuid.UUID] = None
    archetype_name: Optional[str] = None
    starting_stack: int
    current_stack: int
    is_bust: bool
    is_bot: bool


class PokerHandSeatStateOut(BaseModel):
    """Per-seat per-hand visible state in the polled /state endpoint.

    Hole cards are masked ([null, null]) for opponents during the hand.
    The router populates them only for the requesting user's own seat
    until showdown.
    """

    model_config = ConfigDict(from_attributes=True)
    seat_number: int
    hole_cards: list                 # [Card, Card] or [None, None]
    starting_stack: int
    final_stack: int
    current_bet: int
    is_folded: bool
    is_all_in: bool


class PokerActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    seat_number: int
    user_id: Optional[uuid.UUID] = None
    action_index: int
    street: str
    action: str
    amount: int
    recommended_action: Optional[str] = None
    confidence_tier: Optional[str] = None
    verdict: Optional[str] = None
    ev_loss_chips: Optional[int] = None
    live_equity: Optional[float] = None
    chipy_explanation: Optional[str] = None
    is_human: bool
    created_at: datetime


class PokerHandStateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    hand_number: int
    button_seat: int
    small_blind: int
    big_blind: int
    ante: int
    board: list
    pot_total: int
    side_pots: list
    street: str
    current_bet_to_match: int
    current_to_act_seat: Optional[int] = None
    last_aggressor_seat: Optional[int] = None
    min_raise_increment: int
    status: str
    seats: list[PokerHandSeatStateOut]
    actions: list[PokerActionOut]


class PokerTournamentStateOut(BaseModel):
    """The polled endpoint payload. Holds the tournament summary + the seats
    + the current hand state (board, pot, action log)."""

    model_config = ConfigDict(from_attributes=True)
    tournament: PokerTournamentOut
    seats: list[PokerSeatOut]
    current_hand: Optional[PokerHandStateOut] = None
    your_seat_number: Optional[int] = None


class PokerActIn(BaseModel):
    action: PokerActionType
    amount: int = 0  # raise-to chip level for 'raise'; ignored otherwise


class PokerAdviceIn(BaseModel):
    mode: PokerAdviceMode = "odds"


class PokerAdviceOut(BaseModel):
    """Final SSE event payload for /api/poker/hands/{hand_id}/advice."""

    recommended_action: Optional[PokerActionType] = None
    confidence_tier: PokerConfidenceTier
    verdict: PokerVerdict
    ev_loss_chips: Optional[int] = None
    principle_note: Optional[str] = None


# ─── Replay + review ─────────────────────────────────────────────────────────


class PokerHandReplayOut(BaseModel):
    """Step-through replay of a finished hand."""

    model_config = ConfigDict(from_attributes=True)
    hand_id: uuid.UUID
    hand_number: int
    seed: int
    button_seat: int
    board: list
    seats: list[PokerHandSeatStateOut]
    actions: list[PokerActionOut]
    result: Optional[dict] = None


class PokerReviewActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    hand_number: int
    street: str
    action: str
    recommended_action: Optional[str] = None
    confidence_tier: Optional[str] = None
    verdict: Optional[str] = None
    ev_loss_chips: Optional[int] = None
    principle_note: Optional[str] = None


class PokerSessionReviewOut(BaseModel):
    """Per-tournament chess.com-style review. Only DETERMINISTIC spots get
    EV-loss; HEURISTIC spots get principle notes."""

    model_config = ConfigDict(from_attributes=True)
    tournament_id: uuid.UUID
    total_actions: int
    deterministic_actions: int
    optimal_count: int
    ev_lost_chips: int
    actions: list[PokerReviewActionOut]
