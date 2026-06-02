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

export type Classification = "best" | "good" | "inaccuracy" | "mistake" | "blunder";

export interface ReviewAction extends HandReplayAction {
  classification: Classification;
  ev_loss_chips: number;
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
