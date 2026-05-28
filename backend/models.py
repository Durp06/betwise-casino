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

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
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


# ═════════════════════════════════════════════════════════════════════════════
# Texas Hold'em tournament models
# specs/texas-holdem.md §AC-S1..S4, brief §4.6
#
# All tournament chip amounts are integers (not money). Money flows only at
# buy-in (cents → deducted from User.chip_balance) and payout (cents →
# credited back). No reuse of blackjack hands/player_actions schema.
# ═════════════════════════════════════════════════════════════════════════════

class PokerTournament(Base):
    __tablename__ = "poker_tournaments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    bot_count: Mapped[int] = mapped_column(Integer, nullable=False)
    advice_mode: Mapped[str] = mapped_column(String(10), nullable=False, default="odds")
    buy_in_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    starting_stack_chips: Mapped[int] = mapped_column(Integer, nullable=False, default=1500)
    hands_per_level: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)  # persisted RNG seed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    button_seat: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_hand_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    seats: Mapped[list["PokerSeat"]] = relationship("PokerSeat", back_populates="tournament", cascade="all, delete-orphan")
    hands: Mapped[list["PokerHand"]] = relationship("PokerHand", back_populates="tournament", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("bot_count BETWEEN 2 AND 7", name="poker_bot_count_range"),
        CheckConstraint("advice_mode IN ('reads','odds')", name="poker_advice_mode_check"),
        CheckConstraint("status IN ('active','complete','aborted')", name="poker_tournament_status_check"),
        CheckConstraint("buy_in_cents > 0", name="poker_buy_in_positive"),
        CheckConstraint("starting_stack_chips > 0", name="poker_starting_stack_positive"),
    )


class PokerSeat(Base):
    __tablename__ = "poker_seats"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tournament_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("poker_tournaments.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )  # NULL = bot
    seat_number: Mapped[int] = mapped_column(Integer, nullable=False)
    archetype_name: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    starting_stack: Mapped[int] = mapped_column(Integer, nullable=False)
    current_stack: Mapped[int] = mapped_column(Integer, nullable=False)
    is_bust: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bust_position: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_bot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    tournament: Mapped["PokerTournament"] = relationship("PokerTournament", back_populates="seats")

    __table_args__ = (
        UniqueConstraint("tournament_id", "seat_number", name="uq_poker_seat_number"),
        CheckConstraint("starting_stack >= 0", name="poker_seat_starting_stack_nonneg"),
        CheckConstraint("current_stack >= 0", name="poker_seat_current_stack_nonneg"),
    )


class PokerHand(Base):
    __tablename__ = "poker_hands"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tournament_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("poker_tournaments.id", ondelete="CASCADE"), nullable=False
    )
    hand_number: Mapped[int] = mapped_column(Integer, nullable=False)
    button_seat: Mapped[int] = mapped_column(Integer, nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    small_blind: Mapped[int] = mapped_column(Integer, nullable=False)
    big_blind: Mapped[int] = mapped_column(Integer, nullable=False)
    ante: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    board: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    pot_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    side_pots: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    street: Mapped[str] = mapped_column(String(20), nullable=False, default="preflop")
    current_bet_to_match: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_to_act_seat: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_aggressor_seat: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    min_raise_increment: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    tournament: Mapped["PokerTournament"] = relationship("PokerTournament", back_populates="hands")
    seats: Mapped[list["PokerHandSeat"]] = relationship("PokerHandSeat", back_populates="hand", cascade="all, delete-orphan")
    actions: Mapped[list["PokerAction"]] = relationship("PokerAction", back_populates="hand", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("tournament_id", "hand_number", name="uq_poker_hand_number"),
        CheckConstraint(
            "street IN ('preflop','flop','turn','river','complete')",
            name="poker_hand_street_check",
        ),
        CheckConstraint(
            "status IN ('active','complete','aborted')",
            name="poker_hand_status_check",
        ),
    )


class PokerHandSeat(Base):
    """Per-seat per-hand state. Hole cards live here; visible only to owner
    until the hand reaches showdown."""

    __tablename__ = "poker_hand_seats"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    hand_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("poker_hands.id", ondelete="CASCADE"), nullable=False
    )
    seat_number: Mapped[int] = mapped_column(Integer, nullable=False)
    hole_cards: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    starting_stack: Mapped[int] = mapped_column(Integer, nullable=False)
    final_stack: Mapped[int] = mapped_column(Integer, nullable=False)
    contributed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_bet: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_folded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_all_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_acted_this_street: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    hand: Mapped["PokerHand"] = relationship("PokerHand", back_populates="seats")

    __table_args__ = (
        UniqueConstraint("hand_id", "seat_number", name="uq_poker_hand_seat"),
    )


class PokerAction(Base):
    """Every action by every seat across all four streets. For human seats,
    populated with player_guess + recommended_action + ev_loss for the
    oracle/replay/review system."""

    __tablename__ = "poker_actions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    hand_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("poker_hands.id", ondelete="CASCADE"), nullable=False
    )
    seat_number: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )  # NULL for bot actions
    action_index: Mapped[int] = mapped_column(Integer, nullable=False)
    street: Mapped[str] = mapped_column(String(20), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Oracle fields (humans only; NULL for bots)
    recommended_action: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    confidence_tier: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    verdict: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    ev_loss_chips: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    live_equity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    chipy_explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_human: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    hand: Mapped["PokerHand"] = relationship("PokerHand", back_populates="actions")

    __table_args__ = (
        UniqueConstraint("hand_id", "action_index", name="uq_poker_action_index"),
        CheckConstraint(
            "action IN ('fold','check','call','raise','all_in','post_blind','post_ante')",
            name="poker_action_type_check",
        ),
        CheckConstraint(
            "confidence_tier IS NULL OR confidence_tier IN ('DETERMINISTIC','HEURISTIC')",
            name="poker_action_confidence_check",
        ),
    )
