# Pai Gow Poker — Locked Spec (v1, round-6)

> **For implementers / future Claude sessions:** this file is the single source of truth for the Pai Gow Poker feature. Conventions from `CLAUDE.md` still apply. Decisions in this file override anything earlier in chat history. Format mirrors `specs/drill-mode.md` and `specs/texas-holdem.md`.

**Tier contribution**: gold polish. The team is already at gold via blackjack + hold'em; Pai Gow is an additive third game owned by **halynk21**. Net-positive only if shipped polished (the professor's double-penalty rule).

**Owner**: halynk21 (Pai Gow + Chipy-for-PG + Fortune progressive pool).

---

## 1. Goal

Add **house-banked, multiplayer Pai Gow Poker** as a third game in BetWise Casino. Players sit at a table, place ante bets and an optional **Fortune** progressive side bet, receive seven cards each, and split them into a **2-card front** and **5-card back** to beat the dealer's house-way split. **Chipy-for-PG** coaches the optimal split with house-way + published deviation table and tracks strategy adherence as a PG-specific streak. A **cross-table Fortune progressive pool** grows from every fortune bet placed across every PG table; payouts are bet-proportional for fixed tiers and flat pool-shares for pool-funded tiers with row-level locking.

Banker rotation is explicitly deferred to v2 (see §15 Out of Scope). The data model does NOT carry a `banker_user_id` column in v1 (no dead schema); v2 adds it additively.

---

## 2. Architecture

**Backend**: parallel-router pattern matching `routers/poker_*.py` and `routers/holdem.py`. Three new router files (`pai_gow_tables.py`, `pai_gow_game.py`, `pai_gow_advice.py`), one new game subpackage (`backend/game/pai_gow/`), one additive migration (`005_pai_gow.sql`).

**Storage**: PG owns its full container schema — `pai_gow_tables`, `pai_gow_seats`, `pai_gow_rounds`, `pai_gow_player_hands`, `pai_gow_player_actions`, `pai_gow_strategy_streaks`, `fortune_pool`, `fortune_pool_events`. **Zero reuse** of `casino_tables` / `table_seats` / `game_sessions` — this matches poker's actual pattern (`poker_tournaments`, `poker_seats`, `poker_hands`) and eliminates the entire class of cross-game read-contamination bugs. The only existing table PG touches at all is `users`, and only its `chip_balance` column (no streak columns — PG has its own streak table).

**Frontend**: parallel page set (`PaiGowLobby`, `PaiGowTablePage`) + new components (`HandSetter`, `ChipyPaiGowCoach`, `FortunePoolTicker`, `PaiGowSeat`, `PaiGowReplayModal`) + one polling hook (`usePaiGowPoll`). Adds a PG slice to `gameStore.ts` and PG types to `types/index.ts`. Mobile-first CSS at 375px — **only** for PG pages.

**State machine** lives in the DB (`pai_gow_rounds.status` + `pai_gow_player_hands.action_status`) so it survives restarts and supports the existing polling-based multiplayer pattern. All status transitions use compare-and-set SQL (`UPDATE … WHERE status=:old RETURNING …`) so concurrent timeout fires or double submits resolve as one transition.

**Money discipline**: integer cents throughout (CLAUDE.md rule 4). Escrow at deal: ante and fortune bets deducted from `chip_balance` at deal time, returned (or not) at resolve. This makes double-spend prevention structural, not a runtime check.

---

## 3. Tech Stack

- Backend: FastAPI + async SQLAlchemy 2.0 + Pydantic v2 (`ConfigDict(from_attributes=True)`).
- Tests: pytest-asyncio + in-memory SQLite via the existing `BETWISE_TEST_DB_URL` bypass.
- DB: Postgres in production, SQLite in tests. JSON columns (not JSONB on definitions) so both work.
- Auth: existing `CurrentUser = Annotated[uuid.UUID, Depends(get_current_user)]` dependency. Supabase JWT in prod, `BETWISE_DEV_USER_ID` bypass in dev/tests.
- Frontend: React + TypeScript + Vite + Zustand + Tailwind (no `any`, no inline styles except dynamic values, all UI strings via `t()`).
- Chipy: Anthropic SSE streaming via the existing `_stream_anthropic` shimmable helper pattern.
- Rate limiting: existing slowapi `ADVICE_RATE_LIMIT` applied to PG advice endpoints.

---

## 4. Context

**Why Pai Gow**: blackjack and hold'em are both already taught by Chipy. PG completes the "skill coaching" thesis on a third game with a genuinely different decision surface — hand-setting under house-way deviation rather than action-per-turn. PG also has a built-in cross-table multi-user hook (the Fortune progressive pool) that's load-bearing for the demo story.

**Why house-banked v1**: banker rotation requires bankroll-sufficiency checks, cap rules when banker can't cover all wins, concurrency on deal-passing, and a "no one banking" UI dead state. That's a feature on top of a feature. The team's existing multiplayer hook (blackjack tables + leaderboards) already satisfies the spec's `#6 multi-user interaction` invariant at the app level — PG doesn't need to re-satisfy it solo. Fortune pool gives PG its own multi-user hook within the game surface. Banker rotation is forward-design-aware (no dead column carried; v2 adds it) but explicitly out of scope.

**Why fully separate tables** (not reuse `casino_tables`/etc): the existing blackjack queries on `game_sessions` aren't all game-type-filtered (e.g., `tables.py::_get_table_state` reads "active or latest session" without a game_type predicate). Even if we added the filter everywhere, future blackjack work could re-introduce unfiltered queries and silently break PG. Poker handles this by owning its full container schema (`poker_tournaments`/`poker_seats`/`poker_hands`). PG mirrors. This is the only durable fix.

**Why parallel routers, not registry dispatch**: CLAUDE.md describes a "PR 2 router refactor via `GAME_REGISTRY`" that was abandoned in practice. The team chose parallel per-game routers (`poker_*.py`, `holdem.py`). PG follows.

**What's NOT changing**: existing `Hand`, `PlayerAction`, `GameSession`, `CasinoTable`, `TableSeat` tables stay untouched. Their CHECK constraints stay blackjack-shaped. PG uses PG-specific tables for everything game-specific including the table/seat/round container.

---

## 5. File structure

### Files to create — backend

```
backend/game/pai_gow/__init__.py        # GAME_TYPE="pai_gow", re-export submodules
backend/game/pai_gow/cards.py           # Card + deck (52+joker), seeded shuffle, deal_card helper
backend/game/pai_gow/evaluator.py       # 5-card + 2-card hand strength, joker semi-wild,
                                        # unified-comparison protocol, total ordering
backend/game/pai_gow/house_way.py       # Foxwoods house way (~20-rule table)
backend/game/pai_gow/optimal_set.py     # house_way + published deviation table +
                                        # unit-EV-cents-per-bet table (Chipy's authority)
backend/game/pai_gow/fortune.py         # qualifying hand detection, payout schedule
backend/game/pai_gow/resolver.py        # pure: (front_compare, back_compare) -> hand_result
backend/game/pai_gow/state.py           # async DB helpers: deal, set, auto-set on timeout,
                                        # resolve_round (escrow refund / pay out)
backend/game/pai_gow/prompts.py         # Chipy-for-PG prompt templates (pre + post)
backend/game/pai_gow/canonical.py       # canonical hand form for Chipy cache key

backend/routers/pai_gow_tables.py       # prefix=/pai-gow/tables (list/create/join/leave/state)
backend/routers/pai_gow_game.py         # prefix=/pai-gow (deal, set-hand, replay, fortune-pool)
backend/routers/pai_gow_advice.py       # prefix=/pai-gow/advice (pre + post Chipy SSE)

backend/migrations/005_pai_gow.sql      # additive: creates all PG tables. No ALTER on existing.
```

### Files to create — frontend

```
frontend/src/pages/PaiGowLobby.tsx
frontend/src/pages/PaiGowTablePage.tsx
frontend/src/components/HandSetter.tsx
frontend/src/components/ChipyPaiGowCoach.tsx
frontend/src/components/FortunePoolTicker.tsx
frontend/src/components/PaiGowSeat.tsx
frontend/src/components/PaiGowReplayModal.tsx
frontend/src/hooks/usePaiGowPoll.ts

frontend/tests/HandSetter.test.tsx
frontend/tests/ChipyPaiGowCoach.test.tsx
frontend/tests/FortunePoolTicker.test.tsx
```

### Files to create — backend tests

```
backend/tests/test_pai_gow_evaluator.py      # ~10 tests
backend/tests/test_pai_gow_house_way.py      # ~10 tests (incl. quad-split foul-pass)
backend/tests/test_pai_gow_resolver.py       # exactly 9 tests (truth table; 3 copy cases)
backend/tests/test_pai_gow_optimal_set.py    # ~3 tests
backend/tests/test_pai_gow_endpoints.py      # ~5 tests (deal idempotency, multi-player join,
                                             # set, foul rejection, auth gate)
backend/tests/test_pai_gow_fortune.py        # 2 concurrency tests
backend/tests/test_pai_gow_canonical.py      # 1 test (equivalence/non-equivalence)
backend/tests/test_pai_gow_round_flow.py     # ~3 tests (round-level state machine, timeout,
                                             # multi-player deal concurrency)
```

### Files to create — specs

```
specs/pai-gow.md                        # THIS FILE
```

### Files to modify (all additive — no behavior changes on existing surfaces)

```
backend/main.py                         # +3 lines: register pai_gow_tables/_game/_advice routers
backend/models.py                       # +PG models (additive; no existing-model edits)
backend/schemas.py                      # +PG Pydantic schemas (additive)
backend/game/registry.py                # +1 line: pai_gow.GAME_TYPE entry
backend/game/types.py                   # GameType literal: add "pai_gow"
backend/conftest.py                     # IF needed: seed_pai_gow_* helpers (additive)

frontend/src/App.tsx                    # +2 routes: /pai-gow/lobby, /pai-gow/table/:id
frontend/src/pages/Lobby.tsx            # +1 link to PaiGowLobby (additive; tiny diff)
frontend/src/store/gameStore.ts         # +PG slice (additive; no existing-slice edits)
frontend/src/api/client.ts              # +PG API wrappers (additive)
frontend/src/types/index.ts             # +PG types (additive)

README.md                               # +PG to nontrivial-logic table, fill halynk21 row,
                                        # document v1 limitations (no commission, no rotation,
                                        # max_seats=6 etc.)
```

---

## 6. Conventions (cheatsheet from CLAUDE.md)

These apply to every file we touch. Listed here so the implementer doesn't have to re-read CLAUDE.md mid-flow.

- All API routes prefixed `/api` (handled by `app.include_router(..., prefix="/api")`).
- Cards: `{ suit: "hearts"|"diamonds"|"clubs"|"spades", value: "2"-"10"|"J"|"Q"|"K"|"A" }`. **Joker** uses `{ suit: "joker", value: "JK" }`.
- Monetary values are integers in fake cents (`$10.00 = 1000`).
- Async SQLAlchemy everywhere (DB); sync pure functions in `pai_gow/cards|evaluator|house_way|optimal_set|fortune|resolver|canonical`.
- Pydantic v2 with `model_config = ConfigDict(from_attributes=True)`.
- `from __future__ import annotations` at the top of every Python file.
- **Never `datetime.utcnow()`** — always `datetime.now(timezone.utc)`.
- Per-router SQL helpers prefixed `_`, at the bottom of the router file. No inline SQL in handlers.
- Lazy imports inside handlers with `# noqa: PLC0415`.
- Frontend: no `any`, Tailwind only, all UI strings via `t()`, every fetch shows loading + error states.
- Branch naming: `feat/pai-gow` (already done).
- Commit subjects: `<area>(scope): imperative summary`.
- Tests: pytest-asyncio + in-memory SQLite; never mock the DB. Use existing seed helpers + add `seed_pai_gow_*` if needed.

---

## 7. Rule decisions (LOCKED)

### 7.1 Joker semantics

53-card deck (52 + 1 joker). Joker is **semi-wild**:
- Completes a straight (fills any rank gap)
- Completes a flush (matches any suit)
- Completes a straight flush
- Otherwise counts as an **Ace**

Joker representation: `{ suit: "joker", value: "JK" }`. Evaluator inspects suit/value to detect the joker and applies semi-wild logic during hand-strength computation. Joker never participates in pair/three-of-a-kind/full-house/four-of-a-kind unless via Ace fallback.

### 7.2 Hand rankings

**5-card hand**, high to low: straight flush > four of a kind > full house > flush > straight > three of a kind > two pair > one pair > high card.

- **A-K-Q-J-10** is the **highest** straight (royal flush at the straight-flush rank).
- **A-2-3-4-5** ("wheel") is the **second-highest** straight (standard US Pai Gow rule). Divergence from some poker variants.
- Within the same category, rank-tuple comparison breaks ties (kings-and-fours beats queens-and-anything in two-pair).

**2-card hand**: pair > high card only. No straights or flushes in 2 cards. Within category, higher pair / higher first card beats lower; second card breaks ties.

### 7.3 Unified comparison protocol

Both 2-card and 5-card hands compare under a unified total ordering:

1. **Category rank** first (high card < one pair < two pair < three of a kind < straight < flush < full house < four of a kind < straight flush). Two-card categories project as: "pair" → one pair; "high card" → high card.
2. **Within category**: rank-tuple comparison (pair rank, then kickers from highest down).
3. **Two-card hands have no kickers** beyond the two cards themselves. When comparing a 2-card hand to a 5-card hand in the same category, the 5-card hand's extra cards act as additional kickers; the 2-card hand effectively has "zero kickers below any real card." So a 5-card pair-of-kings with kickers beats a 2-card pair-of-kings.

This protocol is what makes the foul rule (§7.4) work cleanly without false rejections of legal house-way outputs.

### 7.4 Foul rule (LOCKED)

**Foul = front strictly outranks back** under the unified comparison protocol of §7.3. Equality is **NOT** foul. Back-greater-than-front is legal.

Examples:
- Four kings split as `KK | KK + 3 kickers`: front = pair of kings, back = pair of kings + 3 kickers. Under §7.3, back > front (kicker tiebreak). **Legal**, not foul.
- Player puts `AA | KQJ10 9` (pair of aces front, no-pair back): front > back. **Foul, auto-loss.**

Foul is detected **client-side before submit** (HandSetter shows the foul warning) **and** server-side on set submission (defense in depth). Server response: HTTP 400 with `{"detail": "Foul: front rank exceeds back rank"}`. House way is deterministic and never produces fouls.

### 7.5 Tie / copy rule (LOCKED)

When player's front equals dealer's front (or back equals back) under §7.3 ordering, the dealer wins ("copy" in PG terminology). This is the standard house rule.

Sides resolve as binary: from the player's perspective, each side is either "player strictly higher" or "not" (where "not" includes both banker-higher and copy). There is no push at the side level.

**Hand result** is derived from the count of strict-player-win sides:
- 2 strict wins → **WIN**
- 1 strict win → **PUSH**
- 0 strict wins (incl. copy+copy, banker+copy, copy+banker) → **LOSE**

See §10 for the truth table.

### 7.6 Commission

The standard 5% commission on PG winning hands is **dropped in v1** for simplicity. Documented in README. Chipy's EV tables are recomputed against no-commission ruleset (so the coach teaches correct EV for our rules; see §12).

### 7.7 Hands per round per user

One hand per user per round (`UNIQUE(round_id, user_id)` on `pai_gow_player_hands`).

### 7.8 Ante + Fortune bet ranges

- **Ante bet** within table's `min_bet_cents` / `max_bet_cents`. Default table: `min=500`, `max=50000`.
- **Fortune bet** is optional. Range when placed: `min_fortune_bet_cents=100` ($1), `max_fortune_bet_cents=10000` ($100). If 0, no Fortune side play.
- **Pool-tier qualifying bet**: `fortune_bet_cents >= 500` ($5). Below this, hand qualifies only for fixed-tier multipliers even if it would otherwise pay GRAND or MAJOR (royal/SF7 falls back to "straight flush" multiplier).

### 7.9 No forfeit in v1

`action_status` is `{'dealt', 'set', 'auto_set', 'resolved'}`. There is no `'forfeit'` state. Auto-set on timeout is the only non-player-driven transition. Surrender/forfeit is v2 if ever.

---

## 8. Data model (LOCKED)

### 8.1 Reused tables (no schema changes)

- **`users`** — read `chip_balance` only. PG streak is on its own table (§8.2). Blackjack streak columns stay blackjack-owned.

That's it. PG owns its full container schema; no other reuse of existing tables.

### 8.2 New tables (additive — `migrations/005_pai_gow.sql`)

#### `pai_gow_tables`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | `gen_random_uuid()` Postgres / `uuid.uuid4()` Python in tests |
| `name` | TEXT NOT NULL | |
| `min_bet_cents` | INTEGER NOT NULL DEFAULT 500 | CHECK `> 0` |
| `max_bet_cents` | INTEGER NOT NULL DEFAULT 50000 | CHECK `>= min_bet_cents` |
| `min_fortune_bet_cents` | INTEGER NOT NULL DEFAULT 100 | CHECK `>= 0` |
| `max_fortune_bet_cents` | INTEGER NOT NULL DEFAULT 10000 | CHECK `>= min_fortune_bet_cents` |
| `max_seats` | INTEGER NOT NULL DEFAULT 3 | CHECK `BETWEEN 1 AND 3` (v1 limitation per user direction; ≥2 sufficient for multi-demo, can be lifted to 6 in v2) |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT `now()` | |

#### `pai_gow_seats`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `table_id` | UUID NOT NULL REFERENCES `pai_gow_tables(id)` ON DELETE CASCADE | |
| `user_id` | UUID NOT NULL REFERENCES `users(id)` ON DELETE CASCADE | |
| `seat_number` | INTEGER NOT NULL | CHECK `BETWEEN 1 AND 3` (matches `pai_gow_tables.max_seats` v1 cap) |
| `joined_at` | TIMESTAMPTZ NOT NULL DEFAULT `now()` | |

Constraints: `UNIQUE(table_id, seat_number)`, `UNIQUE(table_id, user_id)`. Indexes: `(table_id)`, `(user_id)`.

#### `pai_gow_rounds`

One row per round of play. Multiple rounds per table over time.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `table_id` | UUID NOT NULL REFERENCES `pai_gow_tables(id)` ON DELETE CASCADE | |
| `round_number` | INTEGER NOT NULL | Per-table monotonically increasing |
| `dealer_dealt_cards` | JSON NOT NULL DEFAULT `[]` | Dealer's 7 cards; populated on first player's deal |
| `dealer_front` | JSON | NULL until comparing; 2 cards |
| `dealer_back` | JSON | NULL until comparing; 5 cards |
| `deck_state` | JSON NOT NULL DEFAULT `[]` | Residual deck after dealing |
| `status` | TEXT NOT NULL DEFAULT `'betting'` | CHECK in `('betting','playing','dealer_turn','finished')` |
| `playing_started_at` | TIMESTAMPTZ | NULL until CAS `betting→playing`; stamped at that instant. **Timeout reference** (`now() - playing_started_at > 60s` triggers auto-set + transition). |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT `now()` | |
| `resolved_at` | TIMESTAMPTZ | Set when status reaches `finished` |

Constraints: `UNIQUE(table_id, round_number)`. Index: `(table_id, status)` for "find active round on this table" queries.

#### `pai_gow_player_hands`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `round_id` | UUID NOT NULL REFERENCES `pai_gow_rounds(id)` ON DELETE CASCADE | |
| `user_id` | UUID NOT NULL REFERENCES `users(id)` ON DELETE CASCADE | |
| `dealt_cards` | JSON NOT NULL | List of 7 cards (one may be the joker) |
| `front_cards` | JSON | NULL until set; list of exactly 2 |
| `back_cards` | JSON | NULL until set; list of exactly 5 |
| `bet_cents` | INTEGER NOT NULL | CHECK `> 0`. App-validates against table.min/max. |
| `fortune_bet_cents` | INTEGER NOT NULL DEFAULT 0 | CHECK `>= 0` |
| `front_compare` | TEXT | NULL until compared; CHECK NULL OR IN (`'player','banker','copy'`) |
| `back_compare` | TEXT | NULL until compared; CHECK NULL OR IN (`'player','banker','copy'`) |
| `hand_result` | TEXT | NULL until resolved; CHECK NULL OR IN (`'win','push','lose'`) |
| `ante_payout_cents` | INTEGER | NULL until resolved. Net delta to chip_balance: WIN=+bet, PUSH=0, LOSE=-bet. |
| `fortune_payout_cents` | INTEGER | NULL until resolved. The fortune winnings credited; NULL if no fortune bet or non-qualifying. |
| `action_status` | TEXT NOT NULL DEFAULT `'dealt'` | CHECK IN (`'dealt','set','auto_set','resolved'`) |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT `now()` | Audit/replay timestamp. **NOT** the timeout reference — round-level `pai_gow_rounds.playing_started_at` is authoritative (see §9.4). Per-hand timing isn't used for state decisions in v1. |
| `resolved_at` | TIMESTAMPTZ | |

Constraints: `UNIQUE(round_id, user_id)`. Indexes: `(round_id, action_status)` for "are all hands set yet" queries; `(user_id)`.

#### `pai_gow_player_actions` (replay audit trail)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `hand_id` | UUID NOT NULL REFERENCES `pai_gow_player_hands(id)` ON DELETE CASCADE | |
| `user_id` | UUID NOT NULL REFERENCES `users(id)` ON DELETE CASCADE | |
| `action_type` | TEXT NOT NULL | CHECK IN (`'set','auto_set'`) |
| `player_front` | JSON | NULL on auto_set (filled with house-way result for replay) |
| `player_back` | JSON | NULL on auto_set |
| `optimal_front` | JSON NOT NULL | Chipy's optimal_set output at this moment |
| `optimal_back` | JSON NOT NULL | |
| `was_optimal` | BOOLEAN NOT NULL | True iff canonically-sorted player split matches canonically-sorted optimal split (see §12.5) |
| `chipy_explanation` | TEXT | Optional captured explanation for replay |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT `now()` | |

#### `pai_gow_strategy_streaks`

| Column | Type | Notes |
|---|---|---|
| `user_id` | UUID PK REFERENCES `users(id)` ON DELETE CASCADE | One row per user |
| `current_streak` | INTEGER NOT NULL DEFAULT 0 | |
| `longest_streak` | INTEGER NOT NULL DEFAULT 0 | |
| `total_optimal` | INTEGER NOT NULL DEFAULT 0 | Lifetime optimal player-driven sets |
| `total_played` | INTEGER NOT NULL DEFAULT 0 | Lifetime player-driven sets (auto-set NOT counted) |
| `last_played_at` | TIMESTAMPTZ | |

Profile UI reads from this table for PG; from `users.current_streak/best_streak` for blackjack. Frontend batches both reads into one round-trip.

#### `fortune_pool` (singleton row)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | Fixed sentinel `'00000000-0000-0000-0000-000000000001'`. Only one row ever exists. Migration seeds it. |
| `amount_cents` | BIGINT NOT NULL DEFAULT 100000 | Starts at `seed_cents`. CHECK `>= seed_cents`. BIGINT because the pool can grow large. |
| `seed_cents` | BIGINT NOT NULL DEFAULT 100000 | Pool floor. Default `$1000`. |
| `last_updated_at` | TIMESTAMPTZ NOT NULL DEFAULT `now()` | |

#### `fortune_pool_events` (audit ledger)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `hand_id` | UUID REFERENCES `pai_gow_player_hands(id)` ON DELETE SET NULL | NULL allowed (seed event has no hand) |
| `event_type` | TEXT NOT NULL | CHECK IN (`'seed','contribute','fixed_payout','grand_payout','major_payout'`) |
| `contribution_cents` | BIGINT NOT NULL DEFAULT 0 | |
| `payout_cents` | BIGINT NOT NULL DEFAULT 0 | |
| `post_balance_cents` | BIGINT NOT NULL | Pool balance AFTER this event |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT `now()` | |

Every contribution and every payout writes a row. Demo can show the ledger to prove the math.

### 8.3 GameType + registry additions

```python
# backend/game/types.py
GameType = Literal["blackjack", "poker", "pai_gow"]
```

```python
# backend/game/registry.py
from backend.game import blackjack, poker, pai_gow
GAME_REGISTRY = {
    blackjack.GAME_TYPE: blackjack,
    poker.GAME_TYPE: poker,
    pai_gow.GAME_TYPE: pai_gow,
}
```

```python
# backend/game/pai_gow/__init__.py
from __future__ import annotations
GAME_TYPE = "pai_gow"
from . import engine, evaluator, house_way, optimal_set, fortune, resolver, state  # noqa: F401
```

(Adjust for hold'em-branch reality if `poker` import has changed by the time we apply this.)

---

## 9. Round state machine + multiplayer round flow (LOCKED — round-6 fix)

### 9.1 Round lifecycle

```
betting --(first deal)--> playing --(all set/auto-set OR timeout)--> dealer_turn --(resolve)--> finished
```

A round is created when the **first** player at the table calls `deal` and no active round exists. Subsequent deals on the same round add more players. Once a round reaches `dealer_turn`, no further players can join — they wait for the next round.

### 9.2 Multiplayer deal flow (the round-6 fix)

**`POST /api/pai-gow/tables/{table_id}/deal`** — per-player endpoint. Idempotent on `(round_id, user_id)`.

Algorithm (LOCKED — round-6 fixes A and B baked in):

1. Verify caller is seated (`pai_gow_seats` row exists for this user + table).
2. Validate `bet_cents` against `pai_gow_tables.min_bet_cents/max_bet_cents` and chip_balance.
3. Validate `fortune_bet_cents` against `pai_gow_tables.min_fortune_bet_cents/max_fortune_bet_cents` (if > 0) and chip_balance.
4. **Find or create the active round — race-safe (round-6 fix B)**:
   a. `SELECT … FROM pai_gow_rounds WHERE table_id=:tid AND status IN ('betting','playing')` ordered by `round_number DESC LIMIT 1`.
   b. If found: use it; jump to step 5.
   c. If not: attempt to INSERT a new round with `round_number = COALESCE((SELECT MAX(round_number) FROM pai_gow_rounds WHERE table_id=:tid), 0) + 1`, `status='betting'`, empty `dealer_dealt_cards`, freshly shuffled `deck_state` (52 cards + joker).
   d. On `IntegrityError` from `UNIQUE(table_id, round_number)` (another simultaneous first-deal won the create): rollback the insert, re-execute the SELECT in (a), proceed. **Retry exactly once.** Second-race surfacing as 500 is acceptable; not retrying at all means two simultaneous first deals at a 2-seat table get a visible 500 in the demo. **This retry is mandatory in implementation — call out in Phase 4 acceptance criteria.**
5. **Check if caller already has a hand in this round** (`pai_gow_player_hands` UNIQUE on `(round_id, user_id)`): if yes, return existing hand (idempotent — survives client double-fire / network retry).
6. Escrow: `users.chip_balance -= (bet_cents + fortune_bet_cents)`. Hard floor at 0; transaction aborts if would underflow.
7. **Lock the round row before mutating `deck_state` / `dealer_dealt_cards` (round-6 fix A)**:
   ```sql
   SELECT id, dealer_dealt_cards, deck_state
     FROM pai_gow_rounds
    WHERE id = :rid
      FOR UPDATE;
   ```
   Without this lock, two concurrent deals on the same round both `SELECT` a 52-card deck, each pop 7+7 cards independently, and the later `UPDATE` overwrites the earlier — same card dealt to two players, or cards silently vanishing. Read-committed isolation alone does NOT prevent this (the two SELECTs both happen before either UPDATE). **Same locking discipline as `fortune_pool`'s row lock in §11.4. This lock is mandatory in implementation — call out in Phase 4 acceptance criteria.**
8. **Deal dealer cards if not yet dealt** on this round (`dealer_dealt_cards == []` after the locked read): pop 7 cards from `deck_state` into `dealer_dealt_cards`.
9. **Deal this player's cards**: pop 7 cards from `deck_state` into `dealt_cards`.
10. `UPDATE pai_gow_rounds SET deck_state = :new_deck, dealer_dealt_cards = :new_dealer WHERE id = :rid;` — the `FOR UPDATE` lock from step 7 holds until transaction commit, so step 10's write cannot race with another deal's step 7.
11. Insert `pai_gow_player_hands` row with `action_status='dealt'`, `created_at=now()`.
12. **CAS round status `betting → playing`**:
    ```sql
    UPDATE pai_gow_rounds
       SET status='playing', playing_started_at=now()
     WHERE id=:rid AND status='betting'
    RETURNING id;
    ```
    Empty RETURNING means another deal already transitioned (not an error — second+ player on this round).
13. Contribute to Fortune pool if `fortune_bet_cents > 0`:
    ```sql
    UPDATE fortune_pool SET amount_cents = amount_cents + 25, last_updated_at = now()
     WHERE id = '00000000-0000-0000-0000-000000000001'
    RETURNING amount_cents;
    ```
    Plus one `fortune_pool_events` row `event_type='contribute'`.
14. Return the `pai_gow_player_hands` row.

**Why this resolves the "409 second player" class**: status is never required to be `'betting'` on entry; the round is selected by `status IN ('betting','playing')` so both first and subsequent deals find it. The CAS is **only** for transitioning, not for validation. Second deal silently observes empty RETURNING and continues.

**Why fixes A and B were needed (round-6 critique)**: §11 correctly applies `FOR UPDATE` to the fortune pool row but the original §9.2 left the deck row write read-then-write. Same concurrency surface, same fix. The IntegrityError retry handles the symmetric race at round creation time — without it the second of two simultaneous first-deals crashes with 500.

### 9.3 Set flow

**`POST /api/pai-gow/hands/{hand_id}/set`** — per-player endpoint. CAS-protected against double submit.

1. Load hand, verify caller owns it (`user_id == current_user`).
2. Verify split: exactly 2 cards in `front`, exactly 5 in `back`, both subsets of `dealt_cards` (no card reuse, no foreign cards).
3. Verify foul rule (§7.4): `front strictly > back` → HTTP 400 without DB write.
4. **CAS hand status `dealt → set`**:
   ```sql
   UPDATE pai_gow_player_hands
      SET action_status='set', front_cards=:front, back_cards=:back
    WHERE id=:hid AND action_status='dealt'
   RETURNING id;
   ```
   Empty RETURNING → already set/auto-set by another request or timeout. Return HTTP 409 with current state.
5. Insert `pai_gow_player_actions` row with the optimal split from `optimal_set` and `was_optimal` per §12.5 canonical comparison.
6. **Eager round-state check**: read all hands in this round. If every `action_status` is non-`'dealt'`, attempt `playing → dealer_turn` CAS and run resolution inline (§9.5). If round transitions, also update `pai_gow_strategy_streaks` for this user in the same transaction (§12.5).
7. Return the updated hand.

### 9.4 Lazy timeout fallback (called from `_get_state` poll)

On every `GET /api/pai-gow/tables/{id}/state`:

1. Find the active round on this table.
2. If `status == 'playing'` and `playing_started_at + 60s < now()`:
   a. For each hand with `action_status='dealt'`: compute house-way split, CAS-update to `action_status='auto_set'` with the house-way cards. Insert `pai_gow_player_actions` row `action_type='auto_set'`.
   b. Attempt `playing → dealer_turn` CAS.
   c. If CAS succeeds, run resolution (§9.5).
3. Return state.

This ensures abandoned tables don't hang and a single slow player can't grief the others.

### 9.5 Resolution (when round transitions `playing → dealer_turn`)

In a single DB transaction:

1. Compute dealer's split via house_way on `dealer_dealt_cards`. Store as `dealer_front`, `dealer_back`.
2. For each hand:
   a. If fouled (shouldn't happen — fouls are rejected at set-time): `front_compare=back_compare=None`, `hand_result='lose'`, `ante_payout_cents = -bet_cents`. Refund: no chip_balance change (already escrowed).
   b. Else: compute `front_compare = compare_side(player_front, dealer_front)`, `back_compare = compare_side(player_back, dealer_back)`. Resolve via §10 truth table.
3. Apply ante payouts:
   - WIN: `chip_balance += 2 * bet_cents` (escrow refund + win).
   - PUSH: `chip_balance += bet_cents` (escrow refund only).
   - LOSE: nothing (escrow stays with the house).
4. For each hand with `fortune_bet_cents > 0`, evaluate Fortune via `fortune.classify_fortune(seven_cards, fortune_bet_cents)` (§11.1).
   - **No qualification**: nothing happens. The fortune_bet escrow stays with the house (this is the "lose" case for the side bet).
   - **FIXED tier**: `chip_balance += fortune_bet_cents + fortune_payout_cents` where `fortune_payout_cents = fortune.fixed_payout_cents(category, fortune_bet_cents)`. The `fortune_bet_cents` term is the **escrow refund** (the bet was deducted at deal); the `fortune_payout_cents` term is the multiplier × bet winnings. Net delta over deal→resolve cycle: **+fortune_payout_cents** ("X to 1" odds).
   - **GRAND / MAJOR (pool tier)**: inside the `SELECT ... FOR UPDATE` row lock on `fortune_pool` (§11.4), compute `(payout, new_amount) = fortune.pool_payout_cents(tier, current_amount, seed_cents)`. Then `chip_balance += fortune_bet_cents + payout` (same escrow-refund + payout pattern). `UPDATE fortune_pool SET amount_cents = :new_amount`. INSERT `fortune_pool_events` row recording the payout.

   **Critical**: Skipping the `fortune_bet_cents` refund term underpays the player by exactly one bet (`fortune_payout` alone is the winnings, not the gross return). The pattern mirrors the ante's "WIN = +2*bet" structure: escrow comes back AND winnings are added. Same discipline.
5. Update `pai_gow_strategy_streaks` for each player based on `was_optimal` from their player_action row.
6. Mark each hand `action_status='resolved'`, `resolved_at=now()`.
7. CAS `dealer_turn → finished` on the round, stamp `resolved_at`.

Single transaction guarantees: chip_balance, pool, ledger, hands, and streaks all advance together or roll back together. No partial states.

### 9.6 Leave during an active round (escrow refund — round-6 minor fix)

`POST /api/pai-gow/tables/{table_id}/leave` semantics depend on round status. The original "delete the active round if last to leave" rule leaked escrowed chips when CASCADE deleted in-progress player_hand rows. Corrected:

| Round status | Behavior |
|---|---|
| No active round, OR `'finished'` | Remove seat. No refund (nothing escrowed for this user). |
| `'betting'` or `'playing'`, user HAS a hand on the round | (1) `chip_balance += player_hand.bet_cents + player_hand.fortune_bet_cents` (full escrow refund). (2) DELETE the `pai_gow_player_hands` row. (3) Count remaining hands on the round: if zero, DELETE the round (cascade-clean); if non-zero, leave the round alive — the eager-resolution check (§9.3) fires because the remaining players may now all be set. (4) Remove seat. |
| `'dealer_turn'` | Resolution is in progress / imminent. Remove seat but do NOT touch the round or refund — the resolution transaction (§9.5) handles payouts. |

This closes the chip-leak path that the round-6 review flagged. **Implementation note**: leave-during-betting/playing is a multi-step DB write — wrap in one transaction so a crash mid-refund doesn't leave the player double-debited.

---

## 10. Hand resolution truth table (VERBATIM — round 4)

Side comparisons under §7.3 unified ordering (copy = dealer wins per §7.5):

| front \\ back | back=player | back=banker | back=copy |
|---|---|---|---|
| **front=player** | WIN | PUSH | PUSH |
| **front=banker** | PUSH | LOSE | LOSE |
| **front=copy** | PUSH | LOSE | **LOSE** ← the round-4 catch |

Rule compressed: count sides where player strictly higher. 2 → WIN; 1 → PUSH; 0 → LOSE.

Pure resolver (`backend/game/pai_gow/resolver.py`):

```python
from enum import Enum

class SideCompare(str, Enum):
    PLAYER = "player"
    BANKER = "banker"
    COPY   = "copy"

class HandResult(str, Enum):
    WIN = "win"
    PUSH = "push"
    LOSE = "lose"

def compare_side(player_rank, banker_rank) -> SideCompare:
    # rank is a totally-ordered tuple produced by evaluator.score_hand(...)
    if player_rank > banker_rank: return SideCompare.PLAYER
    if player_rank < banker_rank: return SideCompare.BANKER
    return SideCompare.COPY

def resolve_hand(front: SideCompare, back: SideCompare) -> HandResult:
    wins = int(front is SideCompare.PLAYER) + int(back is SideCompare.PLAYER)
    return (HandResult.WIN if wins == 2
            else HandResult.PUSH if wins == 1
            else HandResult.LOSE)

def ante_payout_cents(result: HandResult, bet_cents: int) -> int:
    """Net delta to chip_balance. v1 has no 5% commission (see §7.6)."""
    return {HandResult.WIN: bet_cents,
            HandResult.PUSH: 0,
            HandResult.LOSE: -bet_cents}[result]
```

---

## 11. Fortune pool design (LOCKED — round-6 redesign for points 6 + 8)

### 11.1 Qualifying criterion

**Best 5-card poker hand among the 7 dealt cards** (round-4 unification). Plus the 7-card-straight-flush special case for GRAND. No other mixed criteria. Evaluator exposes `best_five_card_hand(seven_cards)`.

### 11.2 Payout schedule

**Fixed tier — house-funded, bet × multiplier, no pool touch, no lock**:

| Hand category | Multiplier | Example payout on $5 bet |
|---|---|---|
| Straight flush in best-5 (non-royal, e.g., 9-10-J-Q-K of hearts) | 200× | $1,000 |
| Four of a kind | 50× | $250 |
| Full house | 5× | $25 |
| Flush | 4× | $20 |
| Straight | 3× | $15 |
| Three of a kind | 2× | $10 |

Tier classification is exclusive: a hand qualifying for a higher tier doesn't also fire lower tiers.

**Pool tier — pool-funded, requires `fortune_bet_cents >= 500` ($5)**:

| Hand | Payout |
|---|---|
| 7-card straight flush (all seven cards form a straight flush, joker allowed) | full pool drains to seed (`amount - seed`); pool resets to `seed` (GRAND) |
| Royal flush in best 5-card | `(amount - seed) // 2`, floors at 0 if pool is at seed (MAJOR) |

If `fortune_bet_cents < 500` and the hand qualifies for pool tier: pay the highest applicable fixed-tier multiplier instead (royal flush → "straight flush" multiplier 200×). 7-card SF with bet < $5 → 200× too. Documented as a fairness boundary; matches real casino "qualifying bet" semantics.

### 11.3 Contribution

Every deal where `fortune_bet_cents > 0` contributes a **fixed 25 cents** to the pool, independent of bet size. The rest of the fortune bet funds the fixed-tier payouts (house margin).

Atomic, single SQL statement:

```sql
UPDATE fortune_pool
   SET amount_cents = amount_cents + 25,
       last_updated_at = now()
 WHERE id = '00000000-0000-0000-0000-000000000001'
RETURNING amount_cents;
```

Same transaction writes one `fortune_pool_events` row `event_type='contribute'`, `contribution_cents=25`, `payout_cents=0`, `post_balance_cents=<returned>`.

### 11.4 Pool-proportional payout (row-locked)

Wrapped in the same DB transaction as the hand resolution:

```sql
SELECT amount_cents, seed_cents
  FROM fortune_pool
 WHERE id = '00000000-0000-0000-0000-000000000001'
   FOR UPDATE;     -- serializes all concurrent winners + contributors
```

Then compute in app:

```python
available = amount_cents - seed_cents
if event_type == "grand_payout":
    payout = max(available, 0)
    new_amount = seed_cents
elif event_type == "major_payout":
    payout = max(available // 2, 0)
    new_amount = amount_cents - payout
```

Then:

```sql
UPDATE fortune_pool
   SET amount_cents = :new_amount, last_updated_at = now()
 WHERE id = '00000000-0000-0000-0000-000000000001';
```

Plus one `fortune_pool_events` row with the appropriate `event_type`, `payout_cents`, `post_balance_cents`.

**Why this is correct**: `FOR UPDATE` holds a row-level lock until transaction commit. Concurrent contribute-`UPDATE`s wait on the same lock (same row). So no lost-updates mid-payout. Two simultaneous GRAND winners: second reads `amount = seed_cents`, computes `payout=0`. Correct casino behavior — only the first to acquire the lock collects.

### 11.5 Transaction boundary

Single DB transaction wraps: ante refund/loss, fortune fixed-tier payout (if applicable), fortune pool-proportional payout (if applicable), `fortune_pool_events` writes, `pai_gow_player_hands` resolve, `pai_gow_strategy_streaks` update. Crash mid-resolution rolls back to consistent state — never "pool drained but player not credited."

### 11.6 Concurrency tests (round-4 method — ledger-based invariants)

Test A — contribute-only (deterministic):
- N parallel deals with `fortune_bet > 0`, no qualifying hands.
- Assert: `final_pool == initial + 25 * N`, ledger has N `contribute` rows.

Test B — mixed contributes + K simulated GRAND winners:
- Force `K` rounds to have a 7-card SF outcome via seeded deck fixtures.
- Order-dependent → don't pre-compute final. Assert:
  - `final_pool == initial + Σ(ledger.contribution_cents) - Σ(ledger.payout_cents)` (read from actual ledger rows)
  - At every recorded `post_balance_cents`, value `>= seed_cents`
  - Among the K grand attempts, at most one has `payout_cents > 0` (others observed pool already at seed)

---

## 12. Chipy-for-PG surface (LOCKED — round-4 precisions)

### 12.1 Endpoints

```
POST /api/pai-gow/advice/{hand_id}/pre    # SSE — pre-set suggestion + optimal split
POST /api/pai-gow/advice/{hand_id}        # SSE — post-set explanation + streak update
```

Both gated by the existing `slowapi` `ADVICE_RATE_LIMIT`. PG **duplicates** `_stream_anthropic` into `backend/routers/pai_gow_advice.py` rather than extracting to a shared module (LOCKED — avoids touching blackjack's `advice.py` for merge safety; API credit billing is per-call, not per-code-copy; v2 can extract to a shared `_chipy.py` in a small follow-up PR).

### 12.2 Tool calls (Python-side helpers)

- `pai_gow_optimal_split(cards) -> {front, back, ev_unit_cents, reasoning_key}` — calls `optimal_set.find_optimal(cards)`.
- `pai_gow_evaluate_split(cards, front, back) -> {is_optimal, ev_loss_unit_cents, why}` — for post-hand replay.
- `pai_gow_house_way(cards) -> {front, back}` — dealer's algorithm + auto-set on timeout.

### 12.3 Unit EV (bet-independent)

Chipy returns EV as **cents per unit bet** (`ev_unit_cents`). UI multiplies by actual `bet_cents` for display. Cache key is bet-independent.

### 12.4 Canonical hand form (Chipy cache key)

Algorithm in `backend/game/pai_gow/canonical.py`:

```python
def canonical_form(cards: list[dict]) -> tuple:
    joker_present = any(c["suit"] == "joker" for c in cards)
    suited = [c for c in cards if c["suit"] != "joker"]

    RANK_ORDER = {"2":2,"3":3,"4":4,"5":5,"6":6,"7":7,"8":8,"9":9,"10":10,"J":11,"Q":12,"K":13,"A":14}
    SUIT_ORDER = {"clubs":1,"diamonds":2,"hearts":3,"spades":4}
    suited.sort(key=lambda c: (-RANK_ORDER[c["value"]], SUIT_ORDER[c["suit"]]))

    label_map = {}
    next_label = 0
    canonical_cards = []
    for c in suited:
        s = c["suit"]
        if s not in label_map:
            label_map[s] = chr(ord("A") + next_label)
            next_label += 1
        canonical_cards.append((c["value"], label_map[s]))

    return (joker_present, tuple(canonical_cards))
```

**Why rank-sort first**: input order varies between callers; sorting puts equivalent hands in the same order before suit relabeling. **Why joker as a distinct boolean**: joker changes optimal split + EV; without an explicit marker, joker-bearing and joker-free hands with the same rank multiset would collide.

Cache key includes a **commission-ruleset version** (`"no_commission_v1"`) so future commission rule changes don't return stale EVs.

### 12.5 `was_optimal` comparison (round-6 fix — canonical-sorted equality)

Comparing raw lists is order-sensitive: `[Kh,Ks] != [Ks,Kh]` even though same hand. Fix: canonical-sort both halves before equality:

```python
def card_sort_key(c: dict):
    return (-RANK_ORDER[c["value"]], SUIT_ORDER.get(c["suit"], 0))

def hands_equivalent(player_front, player_back, optimal_front, optimal_back) -> bool:
    pf = sorted(player_front, key=card_sort_key)
    pb = sorted(player_back,  key=card_sort_key)
    of = sorted(optimal_front, key=card_sort_key)
    ob = sorted(optimal_back,  key=card_sort_key)
    return pf == of and pb == ob
```

v1 simplification: assumes a single optimal split per dealt hand. If `optimal_set` ever returns one of multiple EV-tied splits, v1 may flag legitimate alternative-optimal plays as suboptimal. Documented as a known v1 limitation — v2 would compare by resulting `(front_score, back_score)` instead of card identity.

### 12.6 Strategy streak

Updated inside the post-set advice endpoint **and** inline at `set` time (when the round resolves eagerly), in the same DB session as the response. Writes to `pai_gow_strategy_streaks`:

```python
was_opt = hands_equivalent(player_front, player_back, optimal_front, optimal_back)
if was_opt:
    streak.current_streak += 1
    streak.longest_streak = max(streak.longest_streak, streak.current_streak)
    streak.total_optimal += 1
else:
    streak.current_streak = 0
streak.total_played += 1   # incremented ONLY on player-driven sets, NOT on auto_set
streak.last_played_at = datetime.now(timezone.utc)
```

### 12.7 Prompt template (sketch)

System prompt: warm, plain-text-only (no markdown), 1–2 sentences, always names the reason.

Pre-set:
> "I just got dealt these 7 cards: {cards}. The house-way split would be {hw_front}/{hw_back}. Basic strategy suggests {opt_front}/{opt_back}. {If different: explain why the deviation is worth it in EV terms.} In one or two short sentences, plain prose, tell me what split to make and why."

Post-set:
> "I split my hand as {player_front}/{player_back}. The optimal split was {opt_front}/{opt_back}. {If matched: 'I played it optimally.'} {If deviated: 'I gave up about {ev_loss_unit_cents}¢ per unit bet on this hand.'} In one or two short sentences, plain prose, tell me whether my call was right and the dealer-strength reasoning."

Prompt strings in `backend/game/pai_gow/prompts.py` so the test suite can assert contracts (parallel to `test_advice_drill.py`).

---

## 13. Endpoint catalog (LOCKED)

| Method | Path | Auth | Rate-limit | Purpose |
|---|---|---|---|---|
| POST | `/api/pai-gow/tables` | required | none | Create a PG table |
| GET | `/api/pai-gow/tables` | required | none | List PG tables with seat counts |
| POST | `/api/pai-gow/tables/{table_id}/join` | required | none | Take the lowest open seat (idempotent if already seated) |
| POST | `/api/pai-gow/tables/{table_id}/leave` | required | none | Release seat. Refund escrow + clean up round per §9.6. |
| GET | `/api/pai-gow/tables/{table_id}/state` | required | none | Full polled state (3s) |
| POST | `/api/pai-gow/tables/{table_id}/deal` | required | none | Place ante + optional fortune bet, deal 7 cards (idempotent per round per user) |
| POST | `/api/pai-gow/hands/{hand_id}/set` | required | none | Submit player split (front, back); CAS on `action_status='dealt'` |
| GET | `/api/pai-gow/hands/{hand_id}/replay` | required | none | Hand replay (owner during play; anyone after round.status='finished') |
| GET | `/api/pai-gow/fortune-pool` | required | none | Current pool amount + last_updated_at |
| POST | `/api/pai-gow/advice/{hand_id}/pre` | required | ADVICE_RATE_LIMIT | Chipy pre-set SSE |
| POST | `/api/pai-gow/advice/{hand_id}` | required | ADVICE_RATE_LIMIT | Chipy post-set SSE + streak update |

**11 endpoints**, all `/api/pai-gow/...` prefix.

`state` response masks: each player's `front`/`back` is hidden from other players until `round.status == 'dealer_turn'`. Sentinel for hidden split is `null`. Same goes for `dealt_cards` of other players — only visible to owner until `dealer_turn`.

---

## 14. Acceptance criteria

### Backend

- **AC-B1**: `backend/game/pai_gow/__init__.py::GAME_TYPE == "pai_gow"`, registered in `backend.game.registry.GAME_REGISTRY`, literal in `backend.game.types.GameType`.
- **AC-B2**: `evaluator.score_hand(cards)` returns a totally-ordered comparable value. Joker semi-wild: joker + 4 hearts = flush; joker alone = ace-high.
- **AC-B3**: A-K-Q-J-10 > A-2-3-4-5; A-2-3-4-5 > K-Q-J-10-9 (second-highest straight pin).
- **AC-B4**: `house_way.foxwoods(cards) -> (front, back)` returns a legal split (back >= front under §7.3) for every legal input. Specifically passes for **high quads (KK | KK+kickers)**, three pairs, full house variants, joker-bearing hands.
- **AC-B5**: `resolver.resolve_hand(front, back)` returns the §10 truth-table value for all 9 cells. **`(COPY,COPY) == LOSE`, `(BANKER,COPY) == LOSE`, `(COPY,BANKER) == LOSE`** are non-negotiable.
- **AC-B6**: `optimal_set.find_optimal(cards)` returns `{front, back, ev_unit_cents, reasoning_key}`. Output matches `house_way.foxwoods` for non-deviation inputs; for documented Wong deviation cases, returns the deviated split with positive `ev_unit_cents`.
- **AC-B7**: `fortune.qualifying_hand(seven_cards)` returns `None` or `{"tier", "category"}` based on best-5-card criterion. Plain straight flush returns `{"tier":"fixed","category":"straight_flush"}` (200× multiplier). 7-card SF returns `{"tier":"pool","category":"grand"}` if `fortune_bet >= 500`, else fallback to fixed straight_flush.
- **AC-B8**: `POST /api/pai-gow/tables/{id}/deal` with `bet > balance` returns 400; with `bet < table.min_bet_cents` returns 400; with `fortune_bet < table.min_fortune_bet_cents` and `> 0` returns 400; without auth returns 401.
- **AC-B9**: First successful deal creates `pai_gow_rounds` row in `'betting'`, inserts `pai_gow_player_hands` with `action_status='dealt'`, deals dealer's 7 cards, CASes round `betting→playing` stamping `playing_started_at`, deducts `(bet + fortune_bet)` from chip_balance, contributes 25 cents to pool if fortune_bet > 0, writes one `fortune_pool_events` `event_type='contribute'`.
- **AC-B10**: Second successful deal on the same round (different user, status now `'playing'`) succeeds — silent empty RETURNING on the betting→playing CAS is not an error. Player gets cards from existing `deck_state`, pool contributes another 25 if their fortune_bet > 0.
- **AC-B11**: `POST /api/pai-gow/tables/{id}/deal` called twice by the SAME user on the SAME round returns the existing hand (idempotent, no double-deal, no double-escrow).
- **AC-B12**: `POST /api/pai-gow/hands/{id}/set` with fouled split (front strictly > back under §7.3) returns 400 without DB write. Legal split CAS-updates `action_status` `dealt→set`. Second concurrent submit observes empty RETURNING and returns 409.
- **AC-B13**: Eager resolution: when the last `dealt` hand becomes `set`/`auto_set` via a `set` request, the same transaction CASes round `playing→dealer_turn`, runs dealer house-way, resolves all hands, fires fortune payouts, updates streaks, CASes `dealer_turn→finished`.
- **AC-B14**: Lazy timeout: `GET /api/pai-gow/tables/{id}/state` with `round.status='playing'` and `now() - playing_started_at > 60s` auto-sets each `dealt` hand via house-way (`action_status='auto_set'`, `action_type='auto_set'` in player_actions row), then runs resolution. `was_optimal=True` for auto_set rows since player == optimal == house_way by construction. `total_played` is NOT incremented for auto_set (per §12.6).
- **AC-B15**: Pool-proportional payout uses `SELECT ... FOR UPDATE` on `fortune_pool`. Two concurrent GRAND wins (forced via fixture) result in exactly one positive payout; second writes `payout_cents=0`. Pool never below `seed_cents`.
- **AC-B16**: Strategy streak: optimal set increments `current_streak`, updates `longest_streak` if new max; suboptimal set resets `current_streak`. `total_played` increments only on player-driven sets. Comparison uses canonical sort per §12.5 — `[Kh,Ks]` and `[Ks,Kh]` are equivalent.
- **AC-B17**: Chipy advice endpoints return `text/event-stream`. Both stream prompt text via `_stream_anthropic`. Both end with a final JSON summary event containing `optimal_front`, `optimal_back`, `was_optimal` (post-set only), `ev_unit_cents` (post-set only), `current_streak`, `longest_streak`.
- **AC-B18**: Fortune payout bet-proportionality: 4-of-a-kind on $5 fortune bet returns 25000 cents; on $10 returns 50000 cents. Pool tier (royal flush, 7-card SF) pays flat `(amount-seed)/2` and `amount-seed` regardless of bet size, but only if `fortune_bet >= 500`; below 500, royal flush pays 200× as straight flush.
- **AC-B19**: Leave behavior (per §9.6): leaving while round is `'betting'` or `'playing'` refunds escrow (`bet_cents + fortune_bet_cents`) to chip_balance, deletes the player_hand, then deletes the round only if no other hands remain. Leaving while round is `'dealer_turn'` or `'finished'` just removes the seat; resolution transaction handles its own payouts. Crash mid-refund must roll back cleanly (single transaction).
- **AC-B20**: Deal concurrency — round creation race (round-6 fix B): two simultaneous first-deals at a 2-seat empty-round table both succeed. First wins the INSERT; second catches `IntegrityError` on `UNIQUE(table_id, round_number)`, retries the SELECT, joins the existing round. Neither returns 500.
- **AC-B21**: Deal concurrency — deck integrity (round-6 fix A): two concurrent deals on the same round serialize via `SELECT … FOR UPDATE` on the round row. Test forces simultaneous deals via threadpool; asserts (a) `dealer_dealt_cards` populated exactly once, (b) `len(deck_state) == 52 + 1 - 7 - 7 - 7 = 32` (joker + 52 deck − dealer 7 − 2 players × 7), (c) every dealt card appears in exactly one hand.

### Frontend

- **AC-F1**: `/pai-gow/lobby` route shows list of PG tables with name + seat count + min/max bet. "Create table" button opens form. Loading + error states visible.
- **AC-F2**: `/pai-gow/table/:id` polls every 3s via `usePaiGowPoll`. Shows seats + dealer area + your hand + Fortune ticker. Visibility-pause + in-flight guard (A4 pattern).
- **AC-F3**: `HandSetter` shows the 7 dealt cards. User taps to **assign exactly 2 cards to the front**; remaining 5 auto-populate the back. Submit disabled until exactly 2 in front. Foul preview surfaces if current selection is fouled.
- **AC-F4**: `ChipyPaiGowCoach` panel streams pre-set suggestion immediately on `action_status='dealt'`. After submit, streams post-set explanation. Plain-text (no markdown). Strategy streak counter visible.
- **AC-F5**: `FortunePoolTicker` shows current pool as `$X,XXX.XX`. Updates within one poll cycle on change.
- **AC-F6**: Mobile width 375px: PG lobby + table + HandSetter + Chipy + Fortune ticker render cleanly, no horizontal scroll, tap targets ≥ 44px.
- **AC-F7**: Bookmarkable URLs: `/pai-gow/lobby` and `/pai-gow/table/:id` survive refresh; back button works.
- **AC-F8**: No `any`, Tailwind only, all UI strings through `t()`, every fetch has visible loading + error states.

### Tests

- **AC-T1**: `test_pai_gow_evaluator.py` — ≥10 tests covering every 5-card category, every 2-card category, joker semi-wild branches, A-2-3-4-5 second-highest pin, A-K-Q-J-10 highest pin, tied-category kicker tiebreaks.
- **AC-T2**: `test_pai_gow_house_way.py` — ≥10 tests including: **high-quad split (KK|KK+kickers) passes foul check**, three pairs, full-house variants, joker handling.
- **AC-T3**: `test_pai_gow_resolver.py` — exactly 9 tests covering all 9 truth-table cells. **(copy,copy)→LOSE, (banker,copy)→LOSE, (copy,banker)→LOSE** are mandatory.
- **AC-T4**: `test_pai_gow_optimal_set.py` — ≥3 tests: canonical-form roundtrip, joker vs joker-free distinct keys, ≥1 documented Wong deviation returns the deviated split with positive `ev_unit_cents`.
- **AC-T5**: `test_pai_gow_endpoints.py` — ≥5 tests: deal happy path (DB + chip balance + pool contribution), **second-player deal succeeds while round.status='playing'** (the round-6 regression test), idempotent same-user double deal, foul rejection, auth gate.
- **AC-T6**: `test_pai_gow_fortune.py` — Test A (contribute-only deterministic invariant); Test B (mixed + grand, ledger-based invariants). Plus: 4-of-a-kind at $5 vs $10 fortune bet → bet-proportional payouts. Plus: royal flush at $4 fortune bet → falls back to 200× straight flush multiplier (pool qualifying bet boundary).
- **AC-T7**: `test_pai_gow_canonical.py` — ≥1 test: equivalent hands collapse to same key; joker-bearing vs free distinct.
- **AC-T8**: `test_pai_gow_round_flow.py` — ≥3 tests: lazy timeout auto-sets all dealt hands after 60s and transitions round, eager resolution on last-set fires inline, leave during 'playing' as last player deletes round.
- **AC-T-demo-prep** (manual, Phase 9): a dev/test fixture exists that deterministically produces a qualifying Fortune hand (e.g., seeded shuffle that yields a four-of-a-kind for player 1 on round 1). The live demo can fire this fixture and the grader sees an actual payout + ledger entry on the Fortune ticker.
- **AC-T9**: Frontend Vitest — `HandSetter.test.tsx` covers tap-to-assign, exactly-2 enforcement, submit disable, foul preview.
- **AC-T10**: All existing 172 backend tests still pass (no regressions). All existing 14 frontend tests still pass. CI green: ruff + pytest + tsc + vitest + build.

---

## 15. Out of scope (LOCKED)

- **Banker rotation** (v2). v1 has no `banker_user_id` column at all.
- **5% commission** on winning hands (§7.6).
- **Forfeit / surrender** (§7.9). `action_status` does not include `'forfeit'` in v1.
- **Push 22 or similar PG variants** — standard rule only.
- **Multi-hand per user per round** (UNIQUE constraint).
- **Cross-team mobile sweep** — only PG pages get the 375px pass.
- **Generic `strategy_streak(user_id, game_type, ...)` table** — PG has its own; blackjack keeps `users.current_streak`. Documented inconsistency.
- **WebSocket / SSE for state polling** — reuse 3s polling.
- **Image generation for cards / Chipy poses** — reuse existing assets.
- **In-game chat for PG tables** — revisit after hold'em merge.
- **Refactor of existing `_stream_anthropic`** — see §17 Q1.
- **`max_seats > 3`** — we own our own `CHECK BETWEEN 1 AND 3` on `pai_gow_tables`. Real PG seats 6 but v1 caps at 3 (≥2 is enough for the multi-player demo; lifting to 6 is purely additive in v2).

---

## 16. Test budget (qualitative, not vanity)

~38 PG-specific backend tests + ~6 frontend tests + 1 optional Playwright e2e.

| Bucket | Count | Load-bearing tests |
|---|---|---|
| Evaluator | ~10 | joker as wild AND ace; A-2-3-4-5 second-highest; tied-category kickers |
| House way | ~10 | **high-quad split passes foul check**; three pairs; full-house |
| Resolver | exactly 9 | **the 3 copy cases** |
| Optimal-set | ~3 | canonical-form roundtrip; joker; ≥1 Wong deviation |
| Endpoints | ~5 | **second-player deal works**; idempotent same-user deal; foul; auth |
| Fortune | ~4 | contribute-only invariant; mixed-with-grand ledger invariant; **bet-proportional fixed tier**; **pool-qualifying-bet boundary** |
| Round flow | ~3 | lazy timeout auto-set; eager resolution; leave-while-active deletes round |
| Canonical | 1 | equivalence + joker distinct |
| Frontend | ~6 | HandSetter (3), ChipyPaiGowCoach (2), FortunePoolTicker (1) |
| E2E (optional) | 1 | sign in → join PG table → deal → set → see result + Fortune advance |

Count is not the target. Coverage of the listed load-bearing cases IS.

---

## 17. Open questions — RESOLVED (Phase 1 sign-off)

1. **Shared `_stream_anthropic`** — **RESOLVED: duplicate.** PG ships its own copy in `pai_gow_advice.py`. No edits to blackjack's `advice.py` → zero merge-conflict surface with hold'em branches. API credit billing is per-call, not per-code-copy. v2 extract to shared `_chipy.py` is a one-line follow-up.
2. **Lobby integration** — **RESOLVED: add the card.** One additive line to `Lobby.tsx`. Games missing from the lobby are invisible at the demo.
3. **Fortune pool seed** — **RESOLVED: $1000 (100,000 cents).** Plus a demo-prep requirement: a seeded qualifying hand fixture must exist so the live demo can fire a Fortune payout (see Phase 9 walkthrough checklist).
4. **Fortune contribution model** — **RESOLVED: flat 25¢** per qualifying deal regardless of bet size. Keeps test invariants deterministic.
5. **PG table `max_seats`** — **RESOLVED: 3.** `pai_gow_tables.max_seats DEFAULT 3, CHECK BETWEEN 1 AND 3`. ≥2 is sufficient for the multi-player demo. (Note: round-6 architectural shift means we own the CHECK ourselves on `pai_gow_tables` — the original "avoid touching shared `casino_tables` CHECK" rationale is moot post-round-6, but the bottom-line decision still applies for demo scope.)
6. **PR splitting** — **RESOLVED: one PR, with two work-cadence constraints**:
   - **(a) Incremental commits during the build, not a single giant "final commit."** Single-hero monolithic commits are a red flag for the professor's git-log review.
   - **(b) PR opened by Wednesday daytime** before submission so there's buffer for merge + deploy + live smoke. No giant PR opened at night.
7. **Pool-tier qualifying bet minimum at $5** — **RESOLVED: keep.** Bets below $5 get the 200× straight flush fallback even on royal/SF7. Matches real casino "qualifying bet" semantics; makes the $1–$100 fortune range meaningful. AC-B18 / AC-T6 stand.

---

## 18. Verification commands

Once implemented, all of these must pass before Phase 9 manual walkthrough:

```bash
# Backend
ruff check backend                                       # must be clean
python -m pytest backend/tests/test_pai_gow_evaluator.py -v
python -m pytest backend/tests/test_pai_gow_house_way.py -v
python -m pytest backend/tests/test_pai_gow_resolver.py -v
python -m pytest backend/tests/test_pai_gow_optimal_set.py -v
python -m pytest backend/tests/test_pai_gow_endpoints.py -v
python -m pytest backend/tests/test_pai_gow_fortune.py -v
python -m pytest backend/tests/test_pai_gow_canonical.py -v
python -m pytest backend/tests/test_pai_gow_round_flow.py -v
python -m pytest backend/tests -v                        # full: 172 existing + ~38 new

# Frontend
npx --prefix frontend tsc --noEmit                       # type-check clean
npm --prefix frontend test -- --run                      # all vitest specs green
npm --prefix frontend run build                          # vite build succeeds
```

---

## 19. Plan (Phase-by-Phase — BLOCKED on this spec being signed off)

(Mirrors task list created by Claude Code in session.)

- **Phase 2 — Data model + migration** — write `005_pai_gow.sql`, add SQLAlchemy models (8 new) + Pydantic schemas + `GAME_REGISTRY`/`GameType` updates.
- **Phase 3 — Core game modules (pure)** — `cards.py`, `evaluator.py`, `house_way.py`, `optimal_set.py`, `fortune.py`, `resolver.py`, `canonical.py`. TDD per drill-mode.md.
- **Phase 4 — Parallel routers + state machine** — three router files, per-player deal + eager/lazy round resolution, escrow at deal, atomic fortune updates, auto-set on timeout.
- **Phase 5 — Frontend** — pages + components + hook. Mobile-first CSS at 375px on PG pages only.
- **Phase 6 — Tests + CI** — fill out the test buckets in §16. CI already runs everything.
- **Phase 7 — Chipy-for-PG** — prompts.py, advice endpoints, canonical-form caching, streak integration.
- **Phase 8 — README + docs** — root README updates, fill halynk21 row, document v1 limitations.
- **Phase 9 — Manual walkthrough** — A4-style edge-case checklist. **Includes Fortune demo-prep**: seeded fixture for a qualifying hand so the live demo can show a real payout firing.
- **Phase 10 — Commit cadence + PR** — only on explicit user go-ahead. **Constraints from §17 Q6 (calendar locked)**: (a) build via incremental commits, never one giant final commit (git-log review is part of grading); (b) **PR opens by Wednesday 2026-06-03 daytime** — leaves buffer Wed afternoon for merge + deploy + live smoke + phone-width verification before Thursday 2026-06-04 lecture 10.2 demo. Working backwards from today Mon 6/1: Mon night + Tue 6/2 = build window; Wed 6/3 = PR + integration + deploy; Thu 6/4 = demo. **No PR opens at night.**

---

## 20. Provenance

- **Round 1** = initial 10-phase plan.
- **Round 2** feedback corrected: copy/push side model, Fortune atomicity claim, cross-table CHECK, optimal_set scope trap, strategic surplus framing, hold'em verification, routing convention, Fortune criterion mixing, test budget weighting, state-transition concurrency, Chipy cache key + canonical form, streak parallel claim, foul rule precision, commission/EV consistency, HandSetter UX, deck_seed redundancy.
- **Round 3** = round 2 corrections accepted with one nuance (house_way + optimal_set both nontrivial).
- **Round 4** feedback corrected: foul rule must be strictly front > back (high-quad split case), streak storage best as separate PG table (additive, lowest teammate risk), canonical form must rank-sort before relabel + joker as distinct token.
- **Round 5 (Phase 0 discovery)** folded in: parallel-router pattern, `/api/pai-gow/...` URL prefix, `005_pai_gow.sql` migration numbering, **attempted** semantic remapping of `GameSession.status` (later reverted in round 6).
- **Round 6 (this spec)** = the architectural shift. PG owns its full container schema (`pai_gow_tables`, `pai_gow_seats`, `pai_gow_rounds`, etc.), mirroring poker's actual `poker_tournaments`/`poker_seats`/`poker_hands` pattern. Round-5's reuse-with-semantic-remapping of `casino_tables`/`table_seats`/`game_sessions` was abandoned because (a) it created a cross-game read-contamination class of bugs (existing blackjack queries on `game_sessions` aren't all game_type-filtered), (b) it didn't match the team's actual practice. Plus six bug fixes: separate `pai_gow_round` table (point 3 — session=round, multiple per table), `playing_started_at` column for timeout (point 4), canonical-sort `was_optimal` comparison (point 5), straight-flush tier added + fixed tier becomes bet-proportional + pool tier flat with qualifying minimum (points 6+8), multiplayer round flow with per-player deal that doesn't require `status='betting'` (point 7, the load-bearing fix), no `'forfeit'` in v1 (point 9).
