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

from sqlalchemy import BigInteger, JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
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


# ─── Pai Gow Poker (round-6 architectural shift — fully separate container) ──
# PG owns its container schema. Mirrors poker_tournaments/poker_seats/poker_hands.
# Zero reuse of CasinoTable / TableSeat / GameSession. See specs/pai-gow.md §8.

FORTUNE_POOL_SINGLETON_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class PaiGowTable(Base):
    __tablename__ = "pai_gow_tables"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    min_bet_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    max_bet_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=50_000)
    min_fortune_bet_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    max_fortune_bet_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=10_000)
    max_seats: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        CheckConstraint("min_bet_cents > 0", name="pai_gow_table_min_bet_positive"),
        CheckConstraint("max_bet_cents >= min_bet_cents", name="pai_gow_table_max_bet_ge_min"),
        CheckConstraint("min_fortune_bet_cents >= 0", name="pai_gow_table_min_fortune_nonneg"),
        CheckConstraint(
            "max_fortune_bet_cents >= min_fortune_bet_cents",
            name="pai_gow_table_max_fortune_ge_min",
        ),
        CheckConstraint(
            "max_seats BETWEEN 1 AND 3",
            name="pai_gow_table_max_seats_range",
        ),
    )


class PaiGowSeat(Base):
    __tablename__ = "pai_gow_seats"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pai_gow_tables.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    seat_number: Mapped[int] = mapped_column(Integer, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        CheckConstraint("seat_number BETWEEN 1 AND 3", name="pai_gow_seat_number_range"),
        UniqueConstraint("table_id", "seat_number", name="uq_pai_gow_table_seat"),
        UniqueConstraint("table_id", "user_id", name="uq_pai_gow_table_user"),
    )


class PaiGowRound(Base):
    """One row per round of play. Multiple rounds per table over time.

    playing_started_at is the AUTHORITATIVE timeout reference (spec §9.4).
    UNIQUE(table_id, round_number) is what makes the round-creation race fix B
    in spec §9.2 deterministic.
    """
    __tablename__ = "pai_gow_rounds"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pai_gow_tables.id", ondelete="CASCADE"), nullable=False
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    dealer_dealt_cards: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    dealer_front: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    dealer_back: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    deck_state: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="betting")
    playing_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('betting','playing','dealer_turn','finished')",
            name="pai_gow_round_status_check",
        ),
        UniqueConstraint("table_id", "round_number", name="uq_pai_gow_table_round_number"),
    )


class PaiGowPlayerHand(Base):
    """One row per (round, user). Stores dealt 7 cards + chosen 2/5 split.

    created_at is for audit/replay only — NOT a timeout source (round-level
    PaiGowRound.playing_started_at is authoritative per spec §9.4).
    """
    __tablename__ = "pai_gow_player_hands"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    round_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pai_gow_rounds.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    dealt_cards: Mapped[list] = mapped_column(JSON, nullable=False)
    front_cards: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    back_cards: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    bet_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    fortune_bet_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    front_compare: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    back_compare: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    hand_result: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    ante_payout_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fortune_payout_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    action_status: Mapped[str] = mapped_column(String(20), nullable=False, default="dealt")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("bet_cents > 0", name="pai_gow_player_hand_bet_positive"),
        CheckConstraint("fortune_bet_cents >= 0", name="pai_gow_player_hand_fortune_nonneg"),
        CheckConstraint(
            "front_compare IS NULL OR front_compare IN ('player','banker','copy')",
            name="pai_gow_player_hand_front_compare_check",
        ),
        CheckConstraint(
            "back_compare IS NULL OR back_compare IN ('player','banker','copy')",
            name="pai_gow_player_hand_back_compare_check",
        ),
        CheckConstraint(
            "hand_result IS NULL OR hand_result IN ('win','push','lose')",
            name="pai_gow_player_hand_result_check",
        ),
        CheckConstraint(
            "action_status IN ('dealt','set','auto_set','resolved')",
            name="pai_gow_player_hand_action_status_check",
        ),
        UniqueConstraint("round_id", "user_id", name="uq_pai_gow_round_user"),
    )


class PaiGowPlayerAction(Base):
    """Replay audit. One row per set/auto_set. No 'forfeit' in v1 (spec §15)."""
    __tablename__ = "pai_gow_player_actions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    hand_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pai_gow_player_hands.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    action_type: Mapped[str] = mapped_column(String(20), nullable=False)
    player_front: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    player_back: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    optimal_front: Mapped[list] = mapped_column(JSON, nullable=False)
    optimal_back: Mapped[list] = mapped_column(JSON, nullable=False)
    was_optimal: Mapped[bool] = mapped_column(Boolean, nullable=False)
    chipy_explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        CheckConstraint(
            "action_type IN ('set','auto_set')",
            name="pai_gow_player_action_type_check",
        ),
    )


class PaiGowStrategyStreak(Base):
    """Per-user PG-specific streak. Separate from users.current_streak/best_streak
    which stay blackjack-owned. Documented inconsistency in README; v2 may unify
    under generic strategy_streak(user_id, game_type) table.
    """
    __tablename__ = "pai_gow_strategy_streaks"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    current_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    longest_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_optimal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_played_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class FortunePool(Base):
    """Singleton row. Exactly one row exists, identified by FORTUNE_POOL_SINGLETON_ID.

    All concurrent updates serialize on this row via SELECT … FOR UPDATE
    (spec §11.4). amount_cents is BigInteger because the pool can grow large.
    """
    __tablename__ = "fortune_pool"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=100_000)
    seed_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=100_000)
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    __table_args__ = (
        CheckConstraint("amount_cents >= seed_cents", name="fortune_pool_amount_ge_seed"),
    )


class FortunePoolEvent(Base):
    """Audit ledger. Concurrency tests assert ledger-based invariants (spec §11.6)."""
    __tablename__ = "fortune_pool_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    hand_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("pai_gow_player_hands.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    contribution_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    payout_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    post_balance_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('seed','contribute','fixed_payout','grand_payout','major_payout')",
            name="fortune_pool_event_type_check",
        ),
    )
