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

from pydantic import BaseModel, ConfigDict, Field

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


# ─── Pai Gow Poker (round-6 architectural shift — see specs/pai-gow.md §13) ──

PaiGowRoundStatus = Literal["betting", "playing", "dealer_turn", "finished"]
PaiGowActionStatus = Literal["dealt", "set", "auto_set", "resolved"]
PaiGowSideCompare = Literal["player", "banker", "copy"]
PaiGowHandResult = Literal["win", "push", "lose"]


# ── Tables ───────────────────────────────────────────────────────────────────

class PaiGowTableCreateIn(BaseModel):
    """Field bounds give clean 422 on obvious bad input; cross-field validation
    (max >= min) is enforced at the handler layer per spec §9.2.
    """
    name: str = Field(min_length=1, max_length=100)
    min_bet_cents: int = Field(default=500, ge=1)
    max_bet_cents: int = Field(default=50_000, ge=1)
    min_fortune_bet_cents: int = Field(default=100, ge=0)
    max_fortune_bet_cents: int = Field(default=10_000, ge=0)
    max_seats: int = Field(default=3, ge=1, le=3)


class PaiGowTableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    min_bet_cents: int
    max_bet_cents: int
    min_fortune_bet_cents: int
    max_fortune_bet_cents: int
    max_seats: int
    created_at: datetime


class PaiGowTableListItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    min_bet_cents: int
    max_bet_cents: int
    max_seats: int
    seats_taken: int
    active_round_status: Optional[PaiGowRoundStatus] = None


class PaiGowSeatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    user_id: uuid.UUID
    seat_number: int
    username: Optional[str] = None
    chip_balance: Optional[int] = None


# ── Deal / Set / Hand ────────────────────────────────────────────────────────

class PaiGowDealIn(BaseModel):
    bet_cents: int = Field(ge=1)
    fortune_bet_cents: int = Field(default=0, ge=0)


class PaiGowSetIn(BaseModel):
    """Player's chosen split. front must be exactly 2 cards; back exactly 5."""
    front: list[dict]
    back: list[dict]


class PaiGowPlayerHandOut(BaseModel):
    """Hand state. Card visibility is masked at the router layer based on
    round.status and viewer identity (see spec §13).
    """
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    round_id: uuid.UUID
    user_id: uuid.UUID
    dealt_cards: Optional[list] = None  # masked for non-owner during 'playing'
    front_cards: Optional[list] = None  # masked until 'dealer_turn'
    back_cards: Optional[list] = None
    bet_cents: int
    fortune_bet_cents: int
    front_compare: Optional[PaiGowSideCompare] = None
    back_compare: Optional[PaiGowSideCompare] = None
    hand_result: Optional[PaiGowHandResult] = None
    ante_payout_cents: Optional[int] = None
    fortune_payout_cents: Optional[int] = None
    action_status: PaiGowActionStatus
    created_at: datetime
    resolved_at: Optional[datetime] = None


class PaiGowRoundOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    table_id: uuid.UUID
    round_number: int
    dealer_dealt_cards: Optional[list] = None  # masked until 'dealer_turn'
    dealer_front: Optional[list] = None
    dealer_back: Optional[list] = None
    status: PaiGowRoundStatus
    playing_started_at: Optional[datetime] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None


class PaiGowTableStateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    min_bet_cents: int
    max_bet_cents: int
    min_fortune_bet_cents: int
    max_fortune_bet_cents: int
    max_seats: int
    seats: list[PaiGowSeatOut]
    round: Optional[PaiGowRoundOut] = None
    hands: list[PaiGowPlayerHandOut]
    fortune_pool_amount_cents: int  # current pool snapshot inline for one round-trip


# ── Streak ───────────────────────────────────────────────────────────────────

class PaiGowStrategyStreakOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: uuid.UUID
    current_streak: int
    longest_streak: int
    total_optimal: int
    total_played: int
    last_played_at: Optional[datetime] = None


# ── Fortune Pool ─────────────────────────────────────────────────────────────

class FortunePoolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    amount_cents: int
    seed_cents: int
    last_updated_at: datetime


# ── Replay ───────────────────────────────────────────────────────────────────

class PaiGowReplayActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    hand_id: uuid.UUID
    user_id: uuid.UUID
    action_type: Literal["set", "auto_set"]
    player_front: Optional[list] = None
    player_back: Optional[list] = None
    optimal_front: list
    optimal_back: list
    was_optimal: bool
    chipy_explanation: Optional[str] = None
    created_at: datetime


# ── Chipy advice ─────────────────────────────────────────────────────────────

class PaiGowAdviceIn(BaseModel):
    """Player's submitted split for post-hand evaluation. Sent with POST
    /api/pai-gow/advice/{hand_id} so Chipy can compare against optimal_set.
    """
    front: list[dict]
    back: list[dict]
