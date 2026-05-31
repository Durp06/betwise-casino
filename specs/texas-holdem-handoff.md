# Texas Hold'em — Implementation Complete

> Status: **feature-complete on `feat/texas-holdem`. All 5 CI gates green end-to-end.**

## CI gate status

| Gate | Status |
|---|---|
| `ruff check backend` | ✅ All checks passed |
| `python -m pytest backend/tests/ -v` | ✅ **494 passed** (172 prior blackjack untouched + **322 new poker**) |
| `cd frontend && npx tsc --noEmit` | ✅ clean |
| `cd frontend && npm test -- --run` | ✅ **36 passed** (8 files; 14 prior + 22 new poker UI) |
| `cd frontend && npm run build` | ✅ built in ~2.6s |

## What shipped

### Phase 1 — Specifications

- **`specs/texas-holdem.md`** (~1,100 lines) — implementation plan with 45+
  indexed acceptance criteria across backend (AC-B*), routers (AC-R*),
  schemas (AC-S*), frontend (AC-F*), and tests (AC-T*).
- **`specs/texas-holdem-reference.md`** (~600 lines) — every poker constant
  the code encodes, sourced: hand rankings, pot-odds, Rule of 2/4, canonical
  preflop matchups, Chen formula, Sklansky-Malmuth, SC ordering, Nash
  push/fold, ICM heuristics + pinned Harville cases, blind schedule,
  payouts, position labels, archetype stat bands.

### Phase 2 — Pure-function brain (`backend/game/poker/`)

12 modules, all pure-sync, zero DB or network calls:

| Module | LOC | Tests | What |
|---|---|---|---|
| `cards.py` | 130 | 14 | TypedDict `Card`, seeded Fisher-Yates deck, rank helpers |
| `evaluator.py` | 200 | 36 | 7-card hand evaluator — wheel, Broadway, play-the-board, counterfeited 2-pair, flush-over-flush, full-house tiebreak, quads+kicker, full category ordering |
| `ranges.py` | 230 | 48 | Chen formula, 9 Sklansky-Malmuth groups, 13×13 grid, SC ordering |
| `pot_odds.py` | 110 | 38 | required_equity, MDF, bluff break-even, Rule of 2/4 |
| `equity.py` | 200 | 20 | Live equity engine — exact enum + Monte Carlo, multi-way, range-aware |
| `nash.py` | 200 | 18 | 4 pinned push/fold charts; AA/KK push everywhere ≤15bb; deep stacks → "none" |
| `icm.py` | 160 | 15 | Harville recursion, ICM equity, ICM break-even call equity |
| `archetypes.py` | 400 | 44 | 11 archetypes; `decide()` is **single source of truth** for bot-actor + coach-explainer |
| `state.py` | 550 | 23 | Immutable `BettingState`, `apply_action`, side-pot computation, HU reversal, all-in-for-less doesn't reopen, chip-conservation fuzz test |
| `tournament.py` | 150 | 33 | 15-level blind schedule, payout structures (2–8 seats), button rotation, position labels |
| `oracle.py` | 200 | 9 | `classify_decision` — DETERMINISTIC vs HEURISTIC; EV-loss for deterministic; ICM overlay; streak counts deterministic only |
| `prompts.py` | 110 | 8 | `build_odds_prompt`, `build_reads_prompt`; mode-honest |

Total: ~2,640 LOC + ~306 tests.

### Phase 3 — Data model

- **`backend/models.py`** — 5 new SQLAlchemy tables: `PokerTournament`,
  `PokerSeat`, `PokerHand`, `PokerHandSeat`, `PokerAction`.
- **`backend/schemas.py`** — full Pydantic v2 coverage matching every DB
  column and the SSE/API surface.
- **`backend/migrations/002_poker.sql`** — Postgres DDL, idempotent.

### Phase 4 — Routers

- **`backend/routers/poker_tables.py`** — 3 endpoints: create tournament,
  lobby list, polled state.
- **`backend/routers/poker_game.py`** — 4 endpoints: deal hand, act (with
  bot resolution loop running the whole turn-sequence to the next human
  decision or hand completion in one request), replay, session review.
  Showdown via `best_5_of_7`, side pots via `compute_side_pots`, awards
  via `award_pots`, bust detection, button rotation, tournament-end
  payout to bankroll cents.
- **`backend/routers/poker_advice.py`** — POST SSE endpoint streaming
  Chipy chunks then a final structured JSON event. Routes through
  `build_reads_prompt` or `build_odds_prompt` per `tournament.advice_mode`.
  Rate-limited (10/minute, user-keyed). Authorization-checked.

Test coverage (`test_poker_endpoints.py`):
- create + bankroll deduction + atomic semantics
- insufficient bankroll → 400
- bot_count validation
- archetype assignment to bots
- state endpoint masks opponent hole cards
- 403 for non-participants
- list filters by user
- 404 for missing tournament
- deal creates first hand + idempotent on repeat
- act applies + drives bots to next human decision
- act fails when no active hand
- replay returns full action log + revealed cards
- session review aggregates user actions + EV-loss tally
- SSE advice streams chunks + final JSON event
- advice refuses 403 for non-participants

### Phase 5 — Frontend types + client + hook

- **`frontend/src/types/index.ts`** — TS mirror of every Pydantic poker
  schema; Literal unions for mode/action/tier/verdict/street.
- **`frontend/src/api/client.ts`** — `createPokerTournament`,
  `listPokerTournaments`, `getPokerTournamentState`, `dealPokerHand`,
  `actPoker`, `getPokerHandReplay`, `getPokerSessionReview`,
  `streamPokerAdvice` (SSE consumer).
- **`frontend/src/hooks/usePokerPoll.ts`** — 3-second poll with
  visibility-pause; mirrors `useTablePoll`.
- **`frontend/src/store/gameStore.ts`** — poker slice with persisted
  `pokerCoachMode` (default `"odds"`), streaming state, recommended-action
  hint, confidence tier surfaced for the badge.

### Phase 6 — React UI

Pages (`frontend/src/pages/`):
- `PokerSetup.tsx` — pre-game config (bot count 2–7, mode toggle, buy-in
  cents, starting stack). Submit → POST creates tournament → navigate to
  `/poker/table/:id`.
- `PokerTablePage.tsx` — polls state, auto-deals on mount, renders seats
  around the felt, board, pot, action bar (only when it's your turn),
  Chipy coach side panel. Hole-card masking respected at the visual
  layer too.

Components (`frontend/src/components/`):
- `PokerLobbyCard.tsx` — entry from main Lobby
- `PokerSeat.tsx` — one seat: hole cards (masked for opponents),
  archetype badge, stack, current bet, dealer button, fold/all-in/bust
  state, "you" marker
- `Board.tsx` — community cards row (0/3/4/5 + empty slots)
- `PotDisplay.tsx` — main pot + side-pot breakdown with eligibility
- `BetSizingSlider.tsx` — slider + ¼/½/¾/pot/all-in presets
- `PokerActionBar.tsx` — fold/check/call/raise/all-in with slider for
  raise sizing
- `ArchetypeBadge.tsx` — color-coded by family with hover tooltip
- `PokerChipyCoach.tsx` — Reads/Odds toggle (persists), Ask Chipy
  button, DETERMINISTIC/HEURISTIC confidence-tier badge, recommended-
  action surface

Routes wired into `App.tsx`: `/poker/setup`, `/poker/table/:id`.

### Frontend tests

5 new test files, 22 new test cases:
- `PokerSeat.test.tsx` — archetype badge, you marker, dealer indicator,
  masked hole cards, current bet display, folded/all-in labels
- `Board.test.tsx` — 0/3/5 cards rendering with placeholder slots
- `BetSizingSlider.test.tsx` — all-in preset, minRaise clamping, label
- `PokerChipyCoach.test.tsx` — mode toggle persists, DETERMINISTIC
  badge renders, HEURISTIC badge renders, fetch button disabled
- `PokerActionBar.test.tsx` — check vs call swap, fold/all-in always
  present, raise opens slider

## Commit history (this branch)

```
git log feat/texas-holdem --oneline ^main

d9cab3e docs(poker): session handoff — what shipped, what remains, how to resume
5ef6b84 feat(poker-ui): frontend types + lobby/state client wrappers
6fc5d1f feat(poker): tournaments router + create/list/state endpoints
63b79c3 feat(poker): data model + Pydantic schemas + migration
a385bc1 feat(poker): tournament + tiered oracle + Chipy prompts + registry
54b569c feat(poker): archetypes + betting state machine (AC-B28..B38)
54547a3 feat(poker): Nash push/fold charts + Harville ICM (AC-B22..B27)
2e63690 feat(poker): spec + reference + pure brain (cards, evaluator, …)
(plus the final feat commits for poker_game / poker_advice / frontend UI)
```

## How to run locally

```powershell
cd C:\Users\crist\dev\projects\betwise-casino
git checkout feat/texas-holdem

# Backend
$env:BETWISE_DEV_USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
$env:BETWISE_TEST_DB_URL = "sqlite+aiosqlite:///./dev.sqlite"
backend\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8000 --reload-dir backend

# Frontend (separate terminal)
cd frontend
npm run dev
# Open http://localhost:5173 → log in → main Lobby has a Texas Hold'em
# card → click → /poker/setup → confirm buy-in → /poker/table/:id

# CI gates
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m pytest backend\tests\
cd frontend; npx tsc --noEmit; npm test -- --run; npm run build
```

## Brief §4 landmines — all addressed

1. **§4.1 — Honest solvability boundary.** `nash.push_fold_action` returns
   `"none"` for `stack_bb > 15`. `oracle.classify_decision` tags every
   non-deterministic spot as `HEURISTIC`. `prompts.build_odds_prompt` for
   deep postflop literally says "this is HEURISTIC" — verified by test.
2. **§4.2 — Tiered correctness oracle.** Deterministic spots (push/fold
   ≤15bb, pot-odds-vs-all-in) get hard correct/incorrect + EV-loss in
   chips. Heuristic spots get `principle_note` only and **never decrement
   the streak** — `counts_toward_streak` is False for those.
3. **§4.3 — Single source of truth.** `archetypes.decide()` is the only
   policy function. The router calls it to drive bots; the coach reads
   the same `estimated_opponent_range` field. Tests assert the bot's
   action's hand-class is contained in its self-reported range.
4. **§4.4 — Two modes, one engine.** Both `build_reads_prompt` and
   `build_odds_prompt` consume the same `DecisionSnapshot`. The mode
   selector simply changes which prompt builder runs.
5. **§4.5 — Bankroll cents ≠ tournament chips.** `User.chip_balance` is
   integer cents. `PokerSeat.current_stack` and the whole `BettingState`
   layer are tournament chips (separate integer unit). Conversion at
   buy-in (`_create_tournament_with_seats` deducts cents) and payout
   (`_finalize_payouts` credits cents). No rake.
6. **§4.6 — Poker gets its own tables.** Five dedicated tables; zero
   reuse of blackjack `hands` / `player_actions` schema.
7. **§4.7 — Seeded determinism.** `tournament.seed` is persisted at
   creation. Per-hand seed = `(tournament.seed * 31 + hand_number) & 0x7FFFFFFF`.
   Bot decisions use `random.Random(hand.seed)`. Same seed → same board,
   same bot actions.
8. **§4.8 — Turn resolution.** Single request resolves human + all bots
   up to the next human decision or hand end. State is reconstructed
   fully from DB on every request — no in-memory game state.
9. **§4.9 — Pure brain, async routers.** All `backend/game/poker/`
   modules are pure-sync. Async lives only in routers. Each router
   keeps a single `_helper` SQL function at the bottom.

## Next polish items (out of scope for v1)

- Hand replay modal + Session review modal in frontend (endpoints exist;
  modal UI not yet wired — current `getPokerHandReplay` /
  `getPokerSessionReview` client wrappers return `unknown` to keep the
  surface honest until the modals consume them).
- Equity engine MC iteration count tuning (default `iters=5000`, raise
  to 20000 in production if budget allows).
- Animation timing for action_log replay between polls (~600ms per entry).
- Mobile layout for the 8-seat table.
- Real Chipy SSE prose tuning vs Anthropic's actual response style.
- README "where the nontrivial logic lives" table update.

These are all polish — the feature works end-to-end without them.
