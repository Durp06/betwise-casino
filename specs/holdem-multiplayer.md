# Multiplayer Texas Hold'em — Implementation Plan

> Multi-human cash-ring Hold'em, mirroring the **multiplayer blackjack** conventions
> (`CasinoTable` → `TableSeat` → shared session → per-player hand, 3-second polling,
> server-side hole-card masking, join/leave) — *not* the existing solo-vs-bots
> tournament trainer (`PokerTournament`). Reuses the proven pure poker brain
> (`backend/game/poker/{cards,evaluator,state}.py`).

## What this is vs. the existing poker

| | Existing (`poker_*`) | This PR (`holdem_*`) |
|---|---|---|
| Players | 1 human + 2–7 **bots** | 2–9 **humans** |
| Format | Sit-n-go **tournament** (escalating blinds, bust, ICM payouts) | **Cash ring** (fixed blinds, buy-in / cash-out) |
| Driver | one request resolves human + all bots | each human acts on their own turn; poll syncs |
| Coach | Chipy / Nash / ICM / oracle | none (live multi-human; advice would be unfair) |
| Tables | `poker_tournaments/seats/hands/hand_seats/actions` | `holdem_tables/seats/hands/hand_seats/actions` |

Shared, reused unchanged: `cards.py`, `evaluator.py`, `state.py` (the betting engine).
New pure module: `backend/game/poker/showdown.py` (`decide_winners_per_pot`).

## Hold'em rule canon (from `specs/texas-holdem-reference.md`)

Streets: post SB → post BB → deal 2 hole cards → preflop → flop(3) → turn(1) → river(1)
→ showdown (best-5-of-7 per live seat, side pots, rotate button). Actions:
fold / check / call / raise / all-in (a "bet" into an unraised pot is `raise` to a level).
Min-raise = previous raise increment; all-in-for-less does **not** reopen. Heads-up:
button posts SB, acts first preflop, acts last postflop. Side pots by commitment level;
folded chips contribute but can't win. Odd chip → first seat left of button.
All of this is already encoded in `state.py` + `evaluator.py`.

## Data model (`backend/models.py` + `migrations/003_holdem.sql`)

Money unit = integer fake-cents (same as `User.chip_balance`, like blackjack). Buy-in
moves cents → `HoldemSeat.stack`; cash-out moves the remaining stack back. Seat numbers
are **0-based** to match the engine.

- **HoldemTable**: `id, name, small_blind, big_blind, min_buy_in, max_buy_in, max_seats(2–9), button_pos(nullable physical chair), status('waiting'|'playing'), created_at`.
- **HoldemSeat** (persistent chair): `id, table_id, user_id, seat_number(physical 0..max-1), stack, status('active'|'sitting_out'), joined_at`; UNIQUE(table,seat), UNIQUE(table,user).
- **HoldemHand** (one round): `id, table_id, hand_number, button_seat(engine idx), deck(JSON full shuffle), board, pot_total, side_pots, small_blind, big_blind, street, current_bet_to_match, current_to_act_seat(engine idx), last_aggressor_seat, min_raise_increment, status('active'|'complete'), result, created_at`; UNIQUE(table,hand_number).
- **HoldemHandSeat** (per-hand seat): `id, hand_id, seat_number(engine idx 0..k-1), user_id, table_seat_number(physical), hole_cards, starting_stack, final_stack, contributed, current_bet, is_folded, is_all_in, has_acted_this_street`; UNIQUE(hand,seat).
- **HoldemAction** (append-only log): `id, hand_id, seat_number, user_id(nullable), action_index, street, action, amount, created_at`; UNIQUE(hand,action_index).

## API (`backend/routers/holdem.py`, prefix `/holdem`, mounted under `/api`)

1. `POST /api/holdem/tables` — create. → `HoldemTableOut`
2. `GET  /api/holdem/tables` — lobby list w/ seats_taken. → `[HoldemTableListOut]`
3. `POST /api/holdem/tables/{id}/join` `{buy_in}` — lowest open seat, deduct bankroll, set stack. Idempotent. 409 full. → `HoldemSeatOut`
4. `POST /api/holdem/tables/{id}/leave` — fold out of any active hand, cash out stack, free seat. → `{status:"ok"}`
5. `GET  /api/holdem/tables/{id}/state` — polled; **per-viewer** hole-card masking. → `HoldemTableStateOut`
6. `POST /api/holdem/tables/{id}/deal` — start next hand (≥2 chipped players, no active hand; idempotent). Rotates button, compacts dealt set → engine, posts blinds, deals hole cards, sets current_to_act. → state
7. `POST /api/holdem/tables/{id}/act` `{action, amount}` — turn-guarded; applies, logs, advances streets / runs out all-ins / showdown. → state

## Orchestration (router helpers, mirror `poker_game.py` minus bots/oracle)

- `_reconstruct_betting_state(hand, hand_seats)` / `_persist_state_to_hand` — DB↔engine bridge (n = len(hand_seats)).
- `_advance_until_human_or_complete(state, hand, hand_seats, table, db)`: while `street_closed` → if complete or ≤1 live → `_complete_hand`; else `advance_street` + `_deal_community_cards` + continue. Else stop at `next_to_act` (always a human). Runs out the board when all live are all-in.
- `_deal_community_cards`: `remaining = remove_cards(hand.deck, board+all_holes)`; flop=3 / turn=1 / river=1.
- `_complete_hand`: fast-forward to complete, fill board to 5 if needed, `compute_side_pots`, winners via `decide_winners_per_pot` (or sole live seat), `award_pots`, write final stacks back to `HoldemSeat` by physical chair, mark complete + `result`, table → 'waiting'.
- `_build_state_payload(..., viewer_user_id)`: physical seats + current hand; mask every seat whose `user_id != viewer` to `[null,null]` while active; at showdown reveal non-folded, keep folded mucked; `your_seat_number` = viewer's engine idx or null.

## Frontend (`frontend/src/...`)

- `types/index.ts`: `HoldemTable, HoldemSeat, HoldemHandSeatState, HoldemHandState, HoldemTableState, HoldemTableListRow, HoldemAction` (reuse `PokerActionType`, `PokerCard`).
- `api/client.ts`: `createHoldemTable, listHoldemTables, joinHoldemTable, leaveHoldemTable, getHoldemTableState, dealHoldemHand, actHoldem` (all `ApiResult<T>`).
- `hooks/useHoldemPoll.ts`: 3 s poll + visibility pause (mirror `useTablePoll`).
- `store/gameStore.ts`: `holdemTableState` + `setHoldemTableState`.
- Components: reuse `Board`, `PotDisplay`, `BetSizingSlider` as-is; new `HoldemSeat` (username, masked holes, button/turn/fold/all-in), `HoldemActionBar` (fold/check/call/raise/all-in + slider, gated on turn).
- Pages: `HoldemLobby` (`/holdem` — list/create/join-with-buy-in), `HoldemTablePage` (`/holdem/table/:id` — poll, deal, act, leave-on-unmount, loading+error). `HoldemLobbyCard` on main Lobby → `/holdem`. Routes in `App.tsx`. All strings via `t()`, no `any`.

## Acceptance criteria

- **AC-S1** showdown `decide_winners_per_pot`: high-card→straight-flush ordering, kickers, split pots, side-pot eligibility excludes folded, sole-live shortcut, play-the-board chop.
- **AC-E1** create table validates blinds (`bb≥sb>0`), buy-in range, seats 2–9.
- **AC-E2** join: lowest open seat, deduct bankroll, set stack; idempotent; 409 when full; 400 insufficient bankroll / out-of-range buy-in.
- **AC-E3** leave: cash out remaining stack to bankroll; folds out of an active hand; frees seat.
- **AC-E4** deal: ≥2 chipped players; blinds posted (pot = sb+bb+antes); 2 hole cards each; `current_to_act` = first to act; idempotent; button rotates between hands.
- **AC-E5** act: turn-guarded (400 not-your-turn); fold/check/call/raise/all-in apply; betting advances to next live seat; chip conservation holds.
- **AC-E6** streets advance only when closed; community cards dealt 3/1/1; all-in run-out completes the board.
- **AC-E7** showdown awards correct side pots; winners' stacks credited; `HoldemSeat.stack` updated; hand → complete.
- **AC-E8** masking: opponents' hole cards `[null,null]` while active for every viewer; revealed (non-folded) at showdown; 403 for non-participant state? (state is public read like blackjack — participants get their own holes).
- **AC-F1** HoldemSeat renders username/button/turn/fold/all-in + masked holes.
- **AC-F2** HoldemActionBar swaps check↔call, always shows fold/all-in, raise opens slider, gated on turn.
- **AC-F3** lobby lists tables with seats_taken + blinds, join with buy-in navigates to table; loading+error branches.

## Known limitations (v1)

- A player must be dealt-in with `stack > 0`; a 0-stack seat sits out until they leave + rejoin (rebuy). No in-place top-up.
- No hand-replay / session-review UI (those are educational extras tied to the solo coach).
- Tables are not auto-garbage-collected when empty (a future janitor; blackjack deletes the session on last-leave — holdem leaves the empty table in the lobby).
