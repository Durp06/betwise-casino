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

from sqlalchemy import JSON, BigInteger, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─── TzDateTime ───────────────────────────────────────────────────────────────
# SQLite strips timezone info when reading DateTime values back. This subclass
# of DateTime wraps the dialect's result processor to re-attach UTC tzinfo on
# load so that hand.created_at.tzinfo is always non-None (AC-M-HIST1 / AC-R-HIST2).
# Subclassing DateTime (not TypeDecorator) ensures isinstance(col.type, DateTime)
# remains True, which is checked by test_hand_created_at_column_exists_and_is_timezone_aware.

class TzDateTime(DateTime):
    """DateTime subclass that guarantees timezone-aware datetime values on readback.

    Overrides _cached_result_processor so that after the dialect's own processor
    runs (which may return a naive datetime on SQLite), UTC tzinfo is attached.
    isinstance(col.type, DateTime) is True because TzDateTime IS a DateTime.
    """
    cache_ok = True

    def _cached_result_processor(self, dialect, coltype):  # type: ignore[override]
        base_proc = super()._cached_result_processor(dialect, coltype)

        def process(value):
            if base_proc is not None:
                value = base_proc(value)
            if value is not None and isinstance(value, datetime) and value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value

        return process


# ─── User ─────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    chip_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=100_000)
    total_hands: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct_decisions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # total_decisions: per-decision accuracy denominator (AC-M-HIST3, Decision #3).
    # Increments once per recorded decision; accuracy = correct_decisions / total_decisions.
    total_decisions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    best_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    # Relationships
    hands: Mapped[list["Hand"]] = relationship("Hand", back_populates="user", cascade="all, delete-orphan")
    seats: Mapped[list["TableSeat"]] = relationship("TableSeat", back_populates="user", cascade="all, delete-orphan")
    actions: Mapped[list["PlayerAction"]] = relationship("PlayerAction", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("chip_balance >= 0", name="chip_balance_non_negative"),
        CheckConstraint("total_decisions >= 0", name="total_decisions_non_negative"),
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
        CheckConstraint("min_bet > 0", name="min_bet_positive"),
        CheckConstraint("max_bet >= min_bet", name="max_bet_ge_min_bet"),
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
    # advice_graded_card_count: idempotency key for the streak mutation in advice.py.
    # Records len(hand.cards) at the time the streak was last graded for this hand.
    # A replay (same hand_id, same card count) is detected and skipped so the user
    # cannot pump their streak by re-requesting advice without taking an action first.
    advice_graded_card_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)
    # Absolute UTC instant this hand's 30s move clock expires, set only while it is
    # the current actor (the lowest-seat active hand). Non-null IFF on the clock;
    # enforced lazily — see game/blackjack/state.py::enforce_timeout.
    move_deadline_at: Mapped[Optional[datetime]] = mapped_column(TzDateTime(timezone=True), nullable=True, default=None)
    # created_at: used for newest-first ordering in _get_user_hands (AC-M-HIST1).
    # Uses TzDateTime to ensure tz-aware datetimes survive SQLite readback (AC-R-HIST2).
    created_at: Mapped[datetime] = mapped_column(TzDateTime(timezone=True), nullable=False, default=_now)

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


# ═════════════════════════════════════════════════════════════════════════════
# Multiplayer Texas Hold'em (cash ring game) models
# specs/holdem-multiplayer.md
#
# Mirrors the multiplayer-blackjack table conventions (CasinoTable → TableSeat →
# shared round → per-player hand) but for Hold'em, and reuses the pure poker
# brain (backend/game/poker/{cards,evaluator,state,showdown}.py). Unlike the
# solo PokerTournament trainer, every seat is a HUMAN — no bots, no escalating
# blinds, no ICM. Chips (HoldemSeat.stack) are the same integer fake-cent unit
# as User.chip_balance: a buy-in deducts the bankroll, a cash-out credits it.
# Seat numbers are 0-based to match the betting engine's seat indexing.
# ═════════════════════════════════════════════════════════════════════════════

class HoldemTable(Base):
    __tablename__ = "holdem_tables"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    small_blind: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    big_blind: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    min_buy_in: Mapped[int] = mapped_column(Integer, nullable=False, default=2_000)
    max_buy_in: Mapped[int] = mapped_column(Integer, nullable=False, default=20_000)
    max_seats: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    # Physical chair (HoldemSeat.seat_number) that held the button last hand;
    # the next deal rotates to the next occupied chair clockwise. NULL = no
    # hand dealt yet.
    button_pos: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="waiting")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    seats: Mapped[list["HoldemSeat"]] = relationship(
        "HoldemSeat", back_populates="table", cascade="all, delete-orphan"
    )
    hands: Mapped[list["HoldemHand"]] = relationship(
        "HoldemHand", back_populates="table", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("small_blind > 0", name="holdem_small_blind_positive"),
        CheckConstraint("big_blind >= small_blind", name="holdem_big_blind_gte_small"),
        CheckConstraint("max_seats BETWEEN 2 AND 9", name="holdem_max_seats_range"),
        CheckConstraint("max_buy_in >= min_buy_in", name="holdem_buy_in_range"),
        CheckConstraint("min_buy_in > 0", name="holdem_min_buy_in_positive"),
        CheckConstraint("status IN ('waiting','playing')", name="holdem_table_status_check"),
    )


class HoldemSeat(Base):
    """A player's persistent chair at a Hold'em table. The stack carries across
    hands (a ring game), unlike blackjack where bets debit the global balance."""

    __tablename__ = "holdem_seats"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("holdem_tables.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    seat_number: Mapped[int] = mapped_column(Integer, nullable=False)  # physical chair, 0-based
    stack: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    table: Mapped["HoldemTable"] = relationship("HoldemTable", back_populates="seats")

    __table_args__ = (
        CheckConstraint("seat_number >= 0", name="holdem_seat_number_nonneg"),
        CheckConstraint("stack >= 0", name="holdem_seat_stack_nonneg"),
        CheckConstraint("status IN ('active','sitting_out')", name="holdem_seat_status_check"),
        UniqueConstraint("table_id", "seat_number", name="uq_holdem_seat_number"),
        UniqueConstraint("table_id", "user_id", name="uq_holdem_seat_user"),
    )


class HoldemHand(Base):
    """One dealt hand at a table. Seat numbers in this row + its children are
    ENGINE indices (0..k-1 over the dealt-in players), not physical chairs."""

    __tablename__ = "holdem_hands"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("holdem_tables.id", ondelete="CASCADE"), nullable=False
    )
    hand_number: Mapped[int] = mapped_column(Integer, nullable=False)
    button_seat: Mapped[int] = mapped_column(Integer, nullable=False)  # engine index
    deck: Mapped[list] = mapped_column(JSON, nullable=False, default=list)  # full shuffle for this hand
    small_blind: Mapped[int] = mapped_column(Integer, nullable=False)
    big_blind: Mapped[int] = mapped_column(Integer, nullable=False)
    board: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    pot_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    side_pots: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    street: Mapped[str] = mapped_column(String(20), nullable=False, default="preflop")
    current_bet_to_match: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_to_act_seat: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_aggressor_seat: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    min_raise_increment: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Absolute UTC instant the current actor's move clock expires. Non-null IFF a
    # human is on the clock (current_to_act_seat is not None). Enforced lazily on
    # the next /state poll or /act — see routers/holdem.py::_enforce_move_timeout.
    move_deadline_at: Mapped[Optional[datetime]] = mapped_column(TzDateTime(timezone=True), nullable=True, default=None)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    table: Mapped["HoldemTable"] = relationship("HoldemTable", back_populates="hands")
    seats: Mapped[list["HoldemHandSeat"]] = relationship(
        "HoldemHandSeat", back_populates="hand", cascade="all, delete-orphan"
    )
    actions: Mapped[list["HoldemAction"]] = relationship(
        "HoldemAction", back_populates="hand", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("table_id", "hand_number", name="uq_holdem_hand_number"),
        CheckConstraint(
            "street IN ('preflop','flop','turn','river','complete')",
            name="holdem_hand_street_check",
        ),
        CheckConstraint("status IN ('active','complete')", name="holdem_hand_status_check"),
    )


class HoldemHandSeat(Base):
    """Per-seat per-hand state. Hole cards live here, visible only to their owner
    until showdown. `seat_number` is the engine index; `table_seat_number` is the
    physical chair the player occupies (for UI placement + writing the stack back)."""

    __tablename__ = "holdem_hand_seats"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    hand_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("holdem_hands.id", ondelete="CASCADE"), nullable=False
    )
    seat_number: Mapped[int] = mapped_column(Integer, nullable=False)  # engine index
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    table_seat_number: Mapped[int] = mapped_column(Integer, nullable=False)  # physical chair
    hole_cards: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    starting_stack: Mapped[int] = mapped_column(Integer, nullable=False)
    final_stack: Mapped[int] = mapped_column(Integer, nullable=False)
    contributed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_bet: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_folded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_all_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_acted_this_street: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    hand: Mapped["HoldemHand"] = relationship("HoldemHand", back_populates="seats")

    __table_args__ = (
        UniqueConstraint("hand_id", "seat_number", name="uq_holdem_hand_seat"),
    )


class ChatMessage(Base):
    """In-game player chat, polymorphic across both multiplayer games.

    `table_kind` discriminates which game's table `table_id` points at
    (blackjack → casino_tables, holdem → holdem_tables). `table_id` is NOT a
    ForeignKey because it can reference either table — the router validates
    that the caller is seated before accepting a post. `username` is
    denormalized for cheap display. `body` is stored VERBATIM (validated raw
    text, never HTML-escaped on store): the client renders it as a React text
    child so any markup is inert. See routers/chat.py::_sanitize_body."""

    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    table_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    table_id: Mapped[uuid.UUID] = mapped_column(nullable=False)  # polymorphic — not an FK
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    username: Mapped[str] = mapped_column(String(20), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        CheckConstraint("table_kind IN ('blackjack','holdem')", name="chat_table_kind_check"),
        Index("idx_chat_messages_table", "table_kind", "table_id", "created_at"),
    )


class HoldemAction(Base):
    """Append-only public action log for a hand. No oracle/coach fields — every
    action (fold/check/call/raise/all-in + blind posts) is public information."""

    __tablename__ = "holdem_actions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    hand_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("holdem_hands.id", ondelete="CASCADE"), nullable=False
    )
    seat_number: Mapped[int] = mapped_column(Integer, nullable=False)  # engine index
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )  # NULL for blind/ante posts
    action_index: Mapped[int] = mapped_column(Integer, nullable=False)
    street: Mapped[str] = mapped_column(String(20), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    hand: Mapped["HoldemHand"] = relationship("HoldemHand", back_populates="actions")

    __table_args__ = (
        UniqueConstraint("hand_id", "action_index", name="uq_holdem_action_index"),
        CheckConstraint(
            "action IN ('fold','check','call','raise','all_in','post_blind','post_ante')",
            name="holdem_action_type_check",
        ),
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
