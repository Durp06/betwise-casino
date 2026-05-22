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
