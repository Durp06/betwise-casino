"""
models.py — SQLAlchemy 2.0 ORM models for BetWise Casino.

Design constraints (specs/betwise-casino.md §T3):
- Uses Mapped[...] typed columns and mapped_column(...).
- JSONB fields use generic JSON column type so SQLite (tests) and Postgres
  (production) both work.
- Python-side uuid.uuid4 defaults replace gen_random_uuid() so the test
  SQLite DB doesn't need Postgres extensions.
- streak columns (current_streak, best_streak) and game_type on GameSession
  are included per §4 additions.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─── User ─────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    chip_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=100_000)
    total_hands: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct_decisions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    best_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    # Relationships
    hands: Mapped[list["Hand"]] = relationship("Hand", back_populates="user", cascade="all, delete-orphan")
    seats: Mapped[list["TableSeat"]] = relationship("TableSeat", back_populates="user", cascade="all, delete-orphan")
    actions: Mapped[list["PlayerAction"]] = relationship("PlayerAction", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("chip_balance >= 0", name="chip_balance_non_negative"),
    )


# ─── CasinoTable ─────────────────────────────────────────────────────────────

class CasinoTable(Base):
    __tablename__ = "casino_tables"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    min_bet: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    max_bet: Mapped[int] = mapped_column(Integer, nullable=False, default=50_000)
    max_seats: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="waiting")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    # Relationships
    seats: Mapped[list["TableSeat"]] = relationship("TableSeat", back_populates="table", cascade="all, delete-orphan")
    sessions: Mapped[list["GameSession"]] = relationship("GameSession", back_populates="table", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("status IN ('waiting','playing','finished')", name="table_status_check"),
    )


# ─── TableSeat ───────────────────────────────────────────────────────────────

class TableSeat(Base):
    __tablename__ = "table_seats"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("casino_tables.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    seat_number: Mapped[int] = mapped_column(Integer, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    # Relationships
    table: Mapped["CasinoTable"] = relationship("CasinoTable", back_populates="seats")
    user: Mapped["User"] = relationship("User", back_populates="seats")

    __table_args__ = (
        CheckConstraint("seat_number BETWEEN 1 AND 3", name="seat_number_range"),
        UniqueConstraint("table_id", "seat_number", name="uq_table_seat_number"),
        UniqueConstraint("table_id", "user_id", name="uq_table_user"),
    )


# ─── GameSession ─────────────────────────────────────────────────────────────

class GameSession(Base):
    __tablename__ = "game_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("casino_tables.id", ondelete="CASCADE"), nullable=False)
    game_type: Mapped[str] = mapped_column(String(50), nullable=False, default="blackjack")
    dealer_cards: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    deck_state: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="betting")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    # Relationships
    table: Mapped["CasinoTable"] = relationship("CasinoTable", back_populates="sessions")
    hands: Mapped[list["Hand"]] = relationship("Hand", back_populates="session", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("status IN ('betting','playing','dealer_turn','finished')", name="session_status_check"),
    )


# ─── Hand ────────────────────────────────────────────────────────────────────

class Hand(Base):
    __tablename__ = "hands"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("game_sessions.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    cards: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    bet: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    outcome: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    payout: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relationships
    session: Mapped["GameSession"] = relationship("GameSession", back_populates="hands")
    user: Mapped["User"] = relationship("User", back_populates="hands")
    actions: Mapped[list["PlayerAction"]] = relationship("PlayerAction", back_populates="hand", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("bet >= 0", name="bet_non_negative"),
        CheckConstraint("status IN ('active','standing','bust','blackjack','finished')", name="hand_status_check"),
        CheckConstraint("outcome IN ('win','loss','push','blackjack','bust') OR outcome IS NULL", name="hand_outcome_check"),
        UniqueConstraint("session_id", "user_id", name="uq_session_user_hand"),
    )


# ─── PlayerAction ─────────────────────────────────────────────────────────────

class PlayerAction(Base):
    __tablename__ = "player_actions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    hand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hands.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    player_guess: Mapped[str] = mapped_column(String(10), nullable=False)
    optimal_action: Mapped[str] = mapped_column(String(10), nullable=False)
    was_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    hand_snapshot: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    dealer_upcard: Mapped[dict] = mapped_column(JSON, nullable=False)
    chipy_explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    # Relationships
    hand: Mapped["Hand"] = relationship("Hand", back_populates="actions")
    user: Mapped["User"] = relationship("User", back_populates="actions")

    __table_args__ = (
        CheckConstraint("action IN ('hit','stand','double','split')", name="action_check"),
        CheckConstraint("player_guess IN ('hit','stand','double','split')", name="player_guess_check"),
        CheckConstraint("optimal_action IN ('hit','stand','double','split')", name="optimal_action_check"),
    )
