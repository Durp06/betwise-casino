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
