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

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ─── Card ─────────────────────────────────────────────────────────────────────

CardSuit = Literal["hearts", "diamonds", "clubs", "spades"]
CardValue = Literal["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
Action = Literal["hit", "stand", "double", "split"]


class CardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    suit: str
    value: str


class CardIn(BaseModel):
    """Strictly validated card for input endpoints (enforces valid suit + value literals)."""
    suit: CardSuit
    value: CardValue


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
    # total_decisions: per-decision accuracy denominator (AC-R-ACC5, Decision #3).
    # accuracy = correct_decisions / total_decisions (zero-guarded → 0.0).
    total_decisions: int
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
    total_decisions: int
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

Classification = Literal["best", "good", "inaccuracy", "mistake", "blunder", "sharp"]


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
    # EV enrichment fields (AC-S-REV1, Task 6) — optional with defaults.
    action_evs: dict[str, float] = {}
    best_action: str = ""
    best_ev: float = 0.0
    ev_delta: float = 0.0
    dealer_bust_pct: float = 0.0


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
    # Aggregate fields (AC-S-REV2, Task 6) — optional with defaults.
    sharp_count: int = 0
    blunder_count: int = 0


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


# ─── Multiplayer Texas Hold'em (cash ring game) ──────────────────────────────
# specs/holdem-multiplayer.md. Reuses PokerActionType / PokerStreet above.


class HoldemTableCreateIn(BaseModel):
    name: str
    small_blind: int = 50
    big_blind: int = 100
    min_buy_in: int = 2_000
    max_buy_in: int = 20_000
    max_seats: int = 6


class HoldemJoinIn(BaseModel):
    buy_in: int


class HoldemActIn(BaseModel):
    action: PokerActionType
    amount: int = 0  # raise-to chip level for 'raise'; ignored otherwise


class HoldemTableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    small_blind: int
    big_blind: int
    min_buy_in: int
    max_buy_in: int
    max_seats: int
    status: str
    created_at: datetime


class HoldemTableListOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    small_blind: int
    big_blind: int
    min_buy_in: int
    max_buy_in: int
    max_seats: int
    status: str
    seats_taken: int


class HoldemSeatOut(BaseModel):
    """A persistent chair at the table (physical seat_number)."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    user_id: uuid.UUID
    seat_number: int
    stack: int
    status: str
    username: Optional[str] = None


class HoldemHandSeatStateOut(BaseModel):
    """Per-seat per-hand state in the polled /state payload. `seat_number` is the
    engine index; `table_seat_number` places the player at their physical chair.
    `hole_cards` is [null, null] for opponents until showdown."""

    model_config = ConfigDict(from_attributes=True)
    seat_number: int
    table_seat_number: int
    user_id: uuid.UUID
    username: Optional[str] = None
    hole_cards: list                 # [Card, Card] or [None, None]
    starting_stack: int
    final_stack: int
    current_bet: int
    is_folded: bool
    is_all_in: bool


class HoldemActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    seat_number: int
    user_id: Optional[uuid.UUID] = None
    action_index: int
    street: str
    action: str
    amount: int
    created_at: datetime


class HoldemHandStateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    hand_number: int
    button_seat: int
    small_blind: int
    big_blind: int
    board: list
    pot_total: int
    side_pots: list
    street: str
    current_bet_to_match: int
    current_to_act_seat: Optional[int] = None
    last_aggressor_seat: Optional[int] = None
    min_raise_increment: int
    status: str
    result: Optional[dict] = None
    seats: list[HoldemHandSeatStateOut]
    actions: list[HoldemActionOut]


class HoldemTableStateOut(BaseModel):
    """The polled endpoint payload: table summary + persistent seats + the
    current hand (board, pot, per-seat state, action log)."""

    model_config = ConfigDict(from_attributes=True)
    table: HoldemTableOut
    seats: list[HoldemSeatOut]
    current_hand: Optional[HoldemHandStateOut] = None
    your_seat_number: Optional[int] = None


# ─── In-game chat (both multiplayer games) ───────────────────────────────────
# specs: polymorphic chat across blackjack CasinoTable + multiplayer HoldemTable.
# Body is stored verbatim (validated raw text) and rendered as an inert React
# text node client-side — see routers/chat.py for the stored-XSS defense.

ChatTableKind = Literal["blackjack", "holdem"]


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    table_kind: str
    table_id: uuid.UUID
    user_id: uuid.UUID
    username: str
    body: str
    created_at: datetime


class ChatPostIn(BaseModel):
    body: str


# ─── Practice grading (Task 7) ────────────────────────────────────────────────

class PracticeGradeIn(BaseModel):
    # CardIn enforces valid suit + value literals → 422 on invalid card (AC-R-PR4).
    # max_length=11: a real blackjack hand cannot exceed ~11 cards (4×A + 4×2 + 3×3 = 21),
    # so we cap here to prevent O(n) DoS amplification on huge input arrays.
    # min_length is intentionally absent — the handler guards against empty hands
    # with a 400 (test_practice_grade_empty_hand_is_400 relies on handler, not 422).
    hand: list[CardIn] = Field(max_length=11)
    dealer_upcard: CardIn
    action: Action


class PracticeGradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    optimal_action: str
    action_evs: dict[str, float]
    best_ev: float
    ev_delta: float
    classification: Classification
    dealer_bust_pct: float
    explanation: str


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

def _validate_pai_gow_split(front: list[dict], back: list[dict]) -> None:
    """Shared shape check for a Pai Gow split: front=2 cards, back=5, each a
    {suit, value} dict. Raises ValueError (→ Pydantic 422) on any violation, so
    malformed input is rejected at the request boundary instead of blowing up
    deep inside an SSE generator after the 200 headers have been sent.
    Not typed as CardIn because Pai Gow includes the joker sentinel
    ({"suit":"joker","value":"JK"}), which is outside the blackjack CardValue
    literal set.
    """
    if len(front) != 2:
        raise ValueError(f"front must be exactly 2 cards, got {len(front)}")
    if len(back) != 5:
        raise ValueError(f"back must be exactly 5 cards, got {len(back)}")
    for label, cards in (("front", front), ("back", back)):
        for c in cards:
            if not isinstance(c, dict) or "suit" not in c or "value" not in c:
                raise ValueError(f"{label} cards must be {{'suit','value'}} objects")


class PaiGowAdviceIn(BaseModel):
    """Player's submitted split for post-hand evaluation. Sent with POST
    /api/pai-gow/advice/{hand_id} so Chipy can compare against optimal_set.
    """
    front: list[dict]
    back: list[dict]

    @field_validator("back")
    @classmethod
    def _check_split(cls, back: list[dict], info) -> list[dict]:  # noqa: ANN001
        # Validate the whole split once `back` is bound (front is already parsed).
        front = info.data.get("front")
        if front is not None:
            _validate_pai_gow_split(front, back)
        return back
