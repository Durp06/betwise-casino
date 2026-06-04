# Move Timer + Hold'em Time Cards

Status: design approved 2026-06-03. Split across two PRs.

## Goal

1. **Move timer (all multiplayer games).** Every player gets ~30 seconds to make a
   move. When the clock runs out, the server makes the safest legal move for them
   and play continues. In scope: **Blackjack tables** and **multiplayer Hold'em**.
   Out of scope: the solo Poker SNG trainer (human-vs-bots — no opponent waiting)
   and Pai Gow (simultaneous action; has its own round timeout).
2. **Hold'em time cards (Hold'em only).** Each player is granted **5 time cards**
   when they sit at a table. Using one extends the current move clock by **+15s**.
   Cards do **not** regenerate during play. A fresh 5 is granted each time a player
   takes a seat (cards live on the seat).

## Decisions (locked)

| # | Decision | Choice |
|---|----------|--------|
| 1 | Game scope | Blackjack + Hold'em only |
| 2 | Enforcement | Lazy, on the next `/state` poll or `/act` — **no** background worker (matches the repo's polling-only doctrine and the Pai Gow `auto_set_round_if_timed_out` precedent) |
| 3 | Time-card lifetime | Fresh 5 per seat; standing up and re-buying-in grants a new 5 |
| 4 | Blackjack StrictMode leave | Re-verify the current `Table.tsx` leave path; it already uses a StrictMode-safe `pagehide` listener. Make the new countdown effect StrictMode-clean; only touch the leave path if a genuine bug remains. |

## Core mechanism — server-authoritative absolute deadline

Store an **absolute UTC instant** on the row that already holds the per-turn
pointer, set at the exact moment a human becomes next-to-act, serialized to the
client as ISO-8601 so it renders a countdown against its own wall clock. The
deadline is enforced **lazily**: whoever next polls `/state` or POSTs `/act` for
that table triggers the auto-action.

**The load-bearing invariant: `move_deadline_at` is non-null iff a human is on the
clock.** When everyone is all-in (`current_to_act_seat is None`) or the hand is
complete, the deadline MUST be null, or a stale clock would auto-act for a player
who has no decision to make.

### Constant

`backend/game/timer.py`:
- `MOVE_TIMER_SECONDS = 30`
- `TIME_CARD_BONUS_SECONDS = 15` (PR2)
- `STARTING_TIME_CARDS = 5` (PR2)
- `move_deadline(now)` → `now + timedelta(seconds=MOVE_TIMER_SECONDS)` (pure)
- `is_expired(deadline, now)` → `deadline is not None and now > deadline` (pure)

All timestamps use `datetime.now(timezone.utc)` (CLAUDE.md rule #13) and the
`TzDateTime` column type (tz-aware on SQLite readback).

## Timeout semantics (the auto-action)

- **Hold'em**: check if the player faces no outstanding bet
  (`current_bet == current_bet_to_match`), otherwise fold. This is the universal
  poker timeout and never forfeits chips the player didn't have to. Synthesized via
  `apply_action(state, seat, "check"|"fold")`, then `_advance_until_human_or_complete`.
  Logged as a normal `fold`/`check` `HoldemAction` with the actor's `user_id` (it is
  their forced action; keeps replay chip-sums correct).
- **Blackjack**: auto-**stand** (lock the current total). Auto-hit could bust the
  player; stand is the only chip-safe default. Sets `hand.status = "standing"`, then
  `advance_turn`.

Expiry is **final**: a player who acts after their deadline passed is auto-resolved
first (the enforcement runs before the turn guard), so their late action hits a
"not your turn" 400.

---

# PR1 — `feat/move-timer`

Per-player 30s move timer for Blackjack + Hold'em. Ships and is fully functional
alone.

### Backend
- **Migration** `008_move_deadlines.sql` (additive, idempotent):
  `ALTER TABLE holdem_hands ADD COLUMN IF NOT EXISTS move_deadline_at TIMESTAMPTZ;`
  `ALTER TABLE hands ADD COLUMN IF NOT EXISTS move_deadline_at TIMESTAMPTZ;`
- **Models** (`models.py`): `HoldemHand.move_deadline_at`, `Hand.move_deadline_at`
  (both `Mapped[Optional[datetime]]`, `TzDateTime(timezone=True)`, nullable).
- **Schemas** (`schemas.py`): `move_deadline_at: Optional[datetime] = None` on
  `HoldemHandStateOut` and `HandOut`.
- **`backend/game/timer.py`**: constants + pure helpers above.
- **Hold'em** (`routers/holdem.py`):
  - `_set_move_deadline(hand)` — `hand.move_deadline_at = move_deadline(now) if
    hand.current_to_act_seat is not None else None`. Called immediately after every
    `current_to_act_seat` write: in `_advance_until_human_or_complete` (the human-waiting
    exit and the no-actor break) and in `_complete_hand`.
  - `_enforce_move_timeout(table, db) -> bool` — double-checked: cheap read of the
    active hand; if `current_to_act_seat is not None and is_expired(deadline)`, take
    the table lock, re-read, re-check, then synthesize check/fold + re-advance.
    Called at the top of `_act` (before the turn guard) and inside
    `_build_state_payload` (the poll path).
- **Blackjack** (`game/blackjack/state.py` + `routers/game.py`):
  - `stamp_current_deadline(session_id, db)` in `state.py` — find the current actor
    (lowest-seat `active` hand), set its deadline `now+30s`, clear every other hand's
    deadline in the session. Called from `_deal_hand` (first actor), from
    `advance_turn` (new actor), and re-stamped in `_take_action` when the acting hand
    stays `active` (per-decision reset). Cleared when the session goes to `dealer_turn`.
  - `_enforce_blackjack_timeout(session, db) -> bool` — if the current actor hand's
    deadline is expired, auto-stand it then `advance_turn`. Called at the top of
    `_take_action` and inside `_get_table_state` (poll path, session-row double-checked
    lock).

### Frontend
- **Types** (`types/index.ts`): `move_deadline_at: string | null` on `Hand` and
  `HoldemHandState`.
- **`hooks/useCountdown.ts`**: `useCountdown(deadlineIso: string | null): number | null`
  — seconds remaining, ticks every 250ms, clean interval cleanup (StrictMode-safe),
  returns `null` when no deadline.
- **`components/MoveTimer.tsx`**: `{ deadlineAt: string | null }` → a countdown badge,
  green→amber→red as it nears zero, `null` when no deadline.
- **Hold'em** (`HoldemTablePage.tsx` → `HoldemSeat.tsx`): thread
  `moveDeadlineAt={isCurrentToAct ? hand.move_deadline_at : null}`; mount `<MoveTimer>`
  in the seat.
- **Blackjack** (`Table.tsx`): mount `<MoveTimer deadlineAt={hand.move_deadline_at}>`
  in the active hand's header row.

### Tests
- Backend Hold'em (`tests/test_holdem_timer.py`): deadline set on deal; deadline
  moves with the turn; expired → auto-fold (facing a bet); expired → auto-check (no
  bet); all-in → deadline null; complete → deadline null; deadline surfaced in `/state`.
- Backend Blackjack (`tests/test_blackjack_timer.py`): deadline on the first actor at
  deal; only the current actor carries a deadline (waiting hands null); re-stamp on
  hit; expired → auto-stand + advance; deadline surfaced in `/state` and cleared at
  dealer turn.
- Frontend (`useCountdown.test.ts`, `MoveTimer.test.tsx`): decrement, zero-floor,
  null-deadline → no render, cleanup.

---

# PR2 — `feat/holdem-time-cards` (stacked on PR1)

Hold'em-only layer. Strictly additive: reads/decrements a new `HoldemSeat` column
and only *extends* the `move_deadline_at` PR1 owns. Zero changes to blackjack or the
shared poker engine. Depends on PR1.

### Backend
- **Migration** `009_holdem_time_cards.sql`:
  `ALTER TABLE holdem_seats ADD COLUMN IF NOT EXISTS time_cards_remaining INTEGER NOT NULL DEFAULT 5;`
  (+ a `CHECK (time_cards_remaining >= 0)` constraint).
- **Model**: `HoldemSeat.time_cards_remaining: Mapped[int]` default 5, CHECK ≥ 0.
- **Grant**: in `_join_seat`, set `time_cards_remaining = STARTING_TIME_CARDS`.
- **Endpoint** `POST /api/holdem/tables/{table_id}/use-time-card` → `_use_time_card`:
  lock table; load caller's seat + active hand; guard (it's your turn,
  `time_cards_remaining > 0`, deadline not already expired); `seat.time_cards_remaining
  -= 1`; `hand.move_deadline_at += TIME_CARD_BONUS_SECONDS`; commit; return state.
- **Schema**: `your_time_cards_remaining: int = 0` on `HoldemTableStateOut`, populated
  in `_build_state_payload` from the requesting user's seat.

### Frontend
- **Types**: `your_time_cards_remaining: number` on `HoldemTableState`.
- **Client**: `useHoldemTimeCard(tableId)` → `POST .../use-time-card`.
- **UI**: a "Time cards n/5 · +15s" control beside `HoldemActionBar`, shown only when
  it's your turn; disabled at 0; calls the endpoint then refreshes.

### Tests (`tests/test_holdem_time_cards.py`)
- Granted 5 on join; using one decrements and extends the deadline +15s; using at 0 →
  400; not-your-turn → 400; no regen mid-hand; expired deadline can't be extended;
  `your_time_cards_remaining` surfaced in `/state`.

## Risks
- **deadline-iff-actor invariant** (see above) — the single most important test.
- **Concurrent poll enforcement** — mutating read path must take the table/session
  lock (double-checked) so two `/state` polls can't double-resolve.
- **Migration/ORM divergence** — tests use `Base.metadata.create_all`, not the `.sql`;
  keep the model column and the migration in sync by hand. Use `008_`/`009_` (the repo
  already has a duplicate `006_`).
- **No-worker enforcement** — an abandoned table self-heals on the next visit; an
  all-closed table stays put (acceptable per the polling doctrine).
- **Parallel-session hazard** — this work is built in an isolated worktree
  (`betwise-casino-move-timer`) because a concurrent session sharing the main
  checkout switched branches out from under it and ate untracked files. Commit early.

## As-built notes / adversarial-review remediation (PR1, 2026-06-03)

A multi-agent adversarial review (22 agents, 11 confirmed findings) drove these
as-built deltas vs. the design above:

- **Enforcement is gated on the caller being SEATED.** `GET /state` is viewable by
  spectators, so running enforcement (a mutation) on every poll let a non-seated
  user drive another table's game (IDOR). Fixed: `_build_state_payload` (holdem) /
  `_get_table_state` (blackjack) only call enforcement when the caller has a seat;
  the holdem `/act` enforcement was moved *after* its seat check; the blackjack
  `/action` enforcement is gated on the caller's `TableSeat`. Tests:
  `test_spectator_poll_does_not_enforce_timeout` (both games).
- **Blackjack enforcement function is `state.py::enforce_timeout(table_id, db)`**
  (not the spec's tentative `_enforce_blackjack_timeout(session, db)`) — it mirrors
  holdem's `table_id`-keyed `_enforce_move_timeout` and looks the session up itself.
- **GET-mutates-state is an intentional design choice** (the Pai Gow precedent;
  `get_db` commits on GET). Documented; mitigated by the seating gate + the
  double-checked lock. Not a background worker.
- **Refuted finding:** the `/deal` response already carries `move_deadline_at`
  correctly (the SQLAlchemy identity map updates the router's `hand` ref); no
  defensive `refresh` needed. Locked in by `test_deal_response_carries_move_deadline`.
- **Out of scope / follow-up:** `HoldemHand.created_at` uses `DateTime` rather than
  the `TzDateTime` used elsewhere — a pre-existing inconsistency, NOT touched here
  (the new `move_deadline_at` columns correctly use `TzDateTime`).
