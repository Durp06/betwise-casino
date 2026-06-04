/**
 * types/index.ts — TypeScript mirrors of every Pydantic schema in
 * betwise-casino/backend/schemas.py.
 *
 * Convention (CLAUDE.md §8): no `any` anywhere.
 */

// ─── Primitives ──────────────────────────────────────────────────────────────

export type Suit = "hearts" | "diamonds" | "clubs" | "spades";
export type Value =
  | "2"
  | "3"
  | "4"
  | "5"
  | "6"
  | "7"
  | "8"
  | "9"
  | "10"
  | "J"
  | "Q"
  | "K"
  | "A";

export type Action = "hit" | "stand" | "double" | "split";

export interface Card {
  suit: Suit;
  value: Value;
}

// ─── Users ───────────────────────────────────────────────────────────────────

export interface UserOut {
  id: string;
  username: string;
  chip_balance: number;
  created_at: string;
}

export interface UserStats {
  id: string;
  username: string;
  chip_balance: number;
  total_hands: number;
  correct_decisions: number;
  accuracy: number;
  current_streak: number;
  best_streak: number;
  created_at: string;
}

// ─── Tables ──────────────────────────────────────────────────────────────────

export interface TableOut {
  id: string;
  name: string;
  min_bet: number;
  max_bet: number;
  max_seats: number;
  status: string;
  created_at: string;
}

export interface TableListRow {
  id: string;
  name: string;
  min_bet: number;
  max_bet: number;
  max_seats: number;
  status: string;
  seats_taken: number;
}

export interface Seat {
  id: string;
  user_id: string;
  seat_number: number;
  username: string | null;
  chip_balance: number | null;
}

export interface Hand {
  id: string;
  session_id: string;
  user_id: string;
  cards: (Card | null)[];
  bet: number;
  status: string;
  outcome: string | null;
  payout: number | null;
  /** Absolute UTC instant (ISO-8601) this hand's move clock expires, or null
   *  when it is not the current actor. Drives the per-seat countdown. */
  move_deadline_at: string | null;
}

export interface Session {
  id: string;
  table_id: string;
  game_type: string;
  dealer_cards: (Card | null)[];
  status: string;
  created_at: string;
}

export interface TableState {
  id: string;
  name: string;
  status: string;
  seats: Seat[];
  session: Session | null;
  hands: Hand[];
}

// ─── Analytics / Weakness ────────────────────────────────────────────────────

export interface WeakSpot {
  hand_category: string;
  dealer_upcard_category: string;
  samples: number;
  correct: number;
  accuracy: number;
}

// ─── Leaderboard ─────────────────────────────────────────────────────────────

export interface LeaderboardRow {
  rank: number;
  user_id: string;
  username: string;
  chip_balance: number;
  total_hands: number;
  accuracy_pct: number;
  best_streak: number;
}

// ─── Hand replay (gold) ──────────────────────────────────────────────────────

export interface HandReplayAction {
  id: string;
  hand_id: string;
  user_id: string;
  action: string;
  player_guess: string;
  optimal_action: string;
  was_correct: boolean;
  hand_snapshot: (Card | null)[];
  dealer_upcard: Card;
  chipy_explanation: string | null;
  created_at: string;
}

// ─── Session review (Hand Review modal) ──────────────────────────────────────

export type Classification = "best" | "good" | "inaccuracy" | "mistake" | "blunder" | "sharp";

export interface ReviewAction extends HandReplayAction {
  classification: Classification;
  ev_loss_chips: number;
  action_evs?: Record<string, number>;
  best_action?: string;
  best_ev?: number;
  ev_delta?: number;
  dealer_bust_pct?: number;
}

export interface SessionReview {
  session_id: string;
  hand_id: string;
  total_actions: number;
  optimal_count: number;
  accuracy: number;
  ev_lost_chips: number;
  worst_action_id: string | null;
  actions: ReviewAction[];
  sharp_count?: number;
  blunder_count?: number;
}

// ─── Advice streaming ────────────────────────────────────────────────────────

export interface AdviceResult {
  optimal_action: Action;
  was_correct: boolean;
  player_accuracy: number;
  current_streak: number;
  best_streak: number;
}

// ─── API result wrapper ──────────────────────────────────────────────────────

export type ApiResult<T> = { data: T; error: null } | { data: null; error: string };

// ═════════════════════════════════════════════════════════════════════════════
// Texas Hold'em — mirrors backend/schemas.py Poker* models
// ═════════════════════════════════════════════════════════════════════════════

export type PokerAdviceMode = "reads" | "odds";
export type PokerActionType = "fold" | "check" | "call" | "raise" | "all_in";
export type PokerConfidenceTier = "DETERMINISTIC" | "HEURISTIC";
export type PokerVerdict =
  | "best"
  | "good"
  | "inaccuracy"
  | "mistake"
  | "blunder"
  | "no_verdict";
export type PokerStreet = "preflop" | "flop" | "turn" | "river" | "complete";

export interface PokerCard {
  suit: Suit;
  value: Value;
}

export interface PokerTournament {
  id: string;
  bot_count: number;
  advice_mode: string;
  buy_in_cents: number;
  starting_stack_chips: number;
  hands_per_level: number;
  status: string;
  button_seat: number;
  current_hand_number: number;
  created_at: string;
}

export interface PokerSeat {
  seat_number: number;
  user_id: string | null;
  archetype_name: string | null;
  starting_stack: number;
  current_stack: number;
  is_bust: boolean;
  is_bot: boolean;
}

export interface PokerHandSeatState {
  seat_number: number;
  hole_cards: (PokerCard | null)[]; // [null, null] for opponents during play
  starting_stack: number;
  final_stack: number;
  current_bet: number;
  is_folded: boolean;
  is_all_in: boolean;
}

export interface PokerAction {
  id: string;
  seat_number: number;
  user_id: string | null;
  action_index: number;
  street: string;
  action: string;
  amount: number;
  recommended_action: string | null;
  confidence_tier: PokerConfidenceTier | null;
  verdict: PokerVerdict | null;
  ev_loss_chips: number | null;
  live_equity: number | null;
  chipy_explanation: string | null;
  is_human: boolean;
  created_at: string;
}

export interface PokerHandState {
  id: string;
  hand_number: number;
  button_seat: number;
  small_blind: number;
  big_blind: number;
  ante: number;
  board: PokerCard[];
  pot_total: number;
  side_pots: Array<{ amount: number; eligible: number[] }>;
  street: string;
  current_bet_to_match: number;
  current_to_act_seat: number | null;
  last_aggressor_seat: number | null;
  min_raise_increment: number;
  status: string;
  seats: PokerHandSeatState[];
  actions: PokerAction[];
}

export interface PokerTournamentState {
  tournament: PokerTournament;
  seats: PokerSeat[];
  current_hand: PokerHandState | null;
  your_seat_number: number | null;
}

export interface PokerAdviceResult {
  recommended_action: PokerActionType | null;
  confidence_tier: PokerConfidenceTier;
  verdict: PokerVerdict;
  ev_loss_chips: number | null;
  principle_note: string | null;
}

export interface PokerCreateTournamentPayload {
  bot_count: number;
  advice_mode: PokerAdviceMode;
  buy_in_cents: number;
  starting_stack_chips: number;
  hands_per_level?: number;
}

// ═════════════════════════════════════════════════════════════════════════════
// Multiplayer Texas Hold'em (cash ring game) — mirrors backend Holdem* schemas
// ═════════════════════════════════════════════════════════════════════════════

export interface HoldemTable {
  id: string;
  name: string;
  small_blind: number;
  big_blind: number;
  min_buy_in: number;
  max_buy_in: number;
  max_seats: number;
  status: string;
  created_at: string;
}

export interface HoldemTableListRow extends HoldemTable {
  seats_taken: number;
}

export interface HoldemSeat {
  id: string;
  user_id: string;
  seat_number: number; // physical chair
  stack: number;
  status: string;
  username: string | null;
}

export interface HoldemHandSeatState {
  seat_number: number; // engine index
  table_seat_number: number; // physical chair
  user_id: string;
  username: string | null;
  hole_cards: (PokerCard | null)[]; // [null, null] for masked opponents
  starting_stack: number;
  final_stack: number;
  current_bet: number;
  is_folded: boolean;
  is_all_in: boolean;
}

export interface HoldemActionLog {
  id: string;
  seat_number: number;
  user_id: string | null;
  action_index: number;
  street: string;
  action: string;
  amount: number;
  created_at: string;
}

export interface HoldemHandState {
  id: string;
  hand_number: number;
  button_seat: number; // engine index
  small_blind: number;
  big_blind: number;
  board: PokerCard[];
  pot_total: number;
  side_pots: Array<{ amount: number; eligible: number[] }>;
  street: string;
  current_bet_to_match: number;
  current_to_act_seat: number | null;
  last_aggressor_seat: number | null;
  min_raise_increment: number;
  /** Absolute UTC instant (ISO-8601) the current actor's move clock expires, or
   *  null when nobody is on the clock. Drives the per-seat countdown. */
  move_deadline_at: string | null;
  status: string;
  result: Record<string, unknown> | null;
  seats: HoldemHandSeatState[];
  actions: HoldemActionLog[];
}

export interface HoldemTableState {
  table: HoldemTable;
  seats: HoldemSeat[];
  current_hand: HoldemHandState | null;
  your_seat_number: number | null; // engine index in the current hand, or null
  /** The requesting user's remaining time cards (0 if not seated). Each spends to
   *  extend the current move clock by +15s. */
  your_time_cards_remaining: number;
}

export interface HoldemCreateTablePayload {
  name: string;
  small_blind: number;
  big_blind: number;
  min_buy_in: number;
  max_buy_in: number;
  max_seats: number;
}

// ═════════════════════════════════════════════════════════════════════════════
// In-game chat (both multiplayer games) — mirrors backend ChatMessageOut.
// `body` is rendered EXCLUSIVELY as a React text node so pasted markup is inert.
// ═════════════════════════════════════════════════════════════════════════════

export type ChatTableKind = "blackjack" | "holdem";

export interface ChatMessage {
  id: string;
  table_kind: string;
  table_id: string;
  user_id: string;
  username: string;
  body: string;
  created_at: string;
}

// ─── Practice grade (Pillar 4/6) ─────────────────────────────────────────────

export interface PracticeGrade {
  optimal_action: string;
  action_evs: Record<string, number>;
  best_ev: number;
  ev_delta: number;
  classification: Classification;
  dealer_bust_pct: number;
  explanation: string;
}

export interface PracticeGradeRequest {
  hand: Card[];
  dealer_upcard: Card;
  action: Action;
}

// ─── Pai Gow Poker (additive — separate type surface) ───────────────────────

/** Pai Gow card type — accepts the joker sentinel alongside the standard
 *  suits/values. Backend serializes joker as `{ suit: "joker", value: "JK" }`.
 */
export type PaiGowSuit = Suit | "joker";
export type PaiGowValue = Value | "JK";
export interface PaiGowCard {
  suit: PaiGowSuit;
  value: PaiGowValue;
}

export type PaiGowRoundStatus = "betting" | "playing" | "dealer_turn" | "finished";
export type PaiGowActionStatus = "dealt" | "set" | "auto_set" | "resolved";
export type PaiGowSideCompare = "player" | "banker" | "copy";
export type PaiGowHandResult = "win" | "push" | "lose";

export interface PaiGowTableOut {
  id: string;
  name: string;
  min_bet_cents: number;
  max_bet_cents: number;
  min_fortune_bet_cents: number;
  max_fortune_bet_cents: number;
  max_seats: number;
  created_at: string;
}

export interface PaiGowTableListItem {
  id: string;
  name: string;
  min_bet_cents: number;
  max_bet_cents: number;
  max_seats: number;
  seats_taken: number;
  active_round_status: PaiGowRoundStatus | null;
}

export interface PaiGowTableCreateIn {
  name: string;
  min_bet_cents?: number;
  max_bet_cents?: number;
  min_fortune_bet_cents?: number;
  max_fortune_bet_cents?: number;
  max_seats?: number;
}

export interface PaiGowSeat {
  id: string;
  user_id: string;
  seat_number: number;
  username: string | null;
  chip_balance: number | null;
}

export interface PaiGowRound {
  id: string;
  table_id: string;
  round_number: number;
  dealer_dealt_cards: PaiGowCard[] | null;
  dealer_front: PaiGowCard[] | null;
  dealer_back: PaiGowCard[] | null;
  status: PaiGowRoundStatus;
  playing_started_at: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface PaiGowPlayerHand {
  id: string;
  round_id: string;
  user_id: string;
  dealt_cards: PaiGowCard[] | null;
  front_cards: PaiGowCard[] | null;
  back_cards: PaiGowCard[] | null;
  bet_cents: number;
  fortune_bet_cents: number;
  front_compare: PaiGowSideCompare | null;
  back_compare: PaiGowSideCompare | null;
  hand_result: PaiGowHandResult | null;
  ante_payout_cents: number | null;
  fortune_payout_cents: number | null;
  action_status: PaiGowActionStatus;
  created_at: string;
  resolved_at: string | null;
}

export interface PaiGowTableState {
  id: string;
  name: string;
  min_bet_cents: number;
  max_bet_cents: number;
  min_fortune_bet_cents: number;
  max_fortune_bet_cents: number;
  max_seats: number;
  seats: PaiGowSeat[];
  round: PaiGowRound | null;
  hands: PaiGowPlayerHand[];
  fortune_pool_amount_cents: number;
}

export interface PaiGowDealIn {
  bet_cents: number;
  fortune_bet_cents?: number;
}

export interface PaiGowSetIn {
  front: PaiGowCard[];
  back: PaiGowCard[];
}

export interface PaiGowReplayAction {
  id: string;
  hand_id: string;
  user_id: string;
  action_type: "set" | "auto_set";
  player_front: PaiGowCard[] | null;
  player_back: PaiGowCard[] | null;
  optimal_front: PaiGowCard[];
  optimal_back: PaiGowCard[];
  was_optimal: boolean;
  chipy_explanation: string | null;
  created_at: string;
}

export interface FortunePool {
  amount_cents: number;
  seed_cents: number;
  last_updated_at: string;
}

export interface PaiGowStrategyStreak {
  user_id: string;
  current_streak: number;
  longest_streak: number;
  total_optimal: number;
  total_played: number;
  last_played_at: string | null;
}

/** SSE summary event payload — what Chipy's pre/post advice streams emit as
 *  the final `data:` event after the streamed text chunks. */
export interface PaiGowAdvicePreSummary {
  optimal_front: PaiGowCard[];
  optimal_back: PaiGowCard[];
  reasoning_key: string;
  phase: "pre";
}

export interface PaiGowAdvicePostSummary {
  is_optimal: boolean;
  ev_loss_unit_cents: number;
  optimal_front: PaiGowCard[];
  optimal_back: PaiGowCard[];
  reasoning_key: string;
  phase: "post";
}
