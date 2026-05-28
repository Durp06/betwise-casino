# Texas Hold'em — Session Handoff

> Status at end of session on branch `feat/texas-holdem`.
> All 5 CI gates were green when this branch was committed; what remains is
> the routers/UI integration on top of a fully-tested pure brain.

## What shipped this session

### Phase 1 — Specifications (complete)

- **`specs/texas-holdem.md`** (~1,100 lines) — implementation plan mirroring
  `specs/drill-mode.md` exactly: Goal, Architecture, Tech Stack, Context, File
  Structure, Conventions, **45 indexed acceptance criteria** (AC-B1..B45,
  AC-R1..R14, AC-S1..S4, AC-F1..F13, AC-T1..T7), Out of scope, 20 task-group
  plan with checkboxes, Verification commands, Open questions.
- **`specs/texas-holdem-reference.md`** (~600 lines) — every poker constant
  the code encodes, with sources noted: hand rankings, pot-odds table, Rule
  of 2/4, canonical preflop matchups, **Chen formula**, **Sklansky-Malmuth
  groups 1–9**, **Sklansky-Chubukov ordering**, **push/fold Nash charts**,
  **ICM heuristics + pinned Harville test cases**, blind schedule, payout
  structure, position labels, archetype stat bands.

### Phase 2 — Backend pure-function brain (complete; 306 new tests)

All under `backend/game/poker/`. Pure-sync — zero DB or network calls. Each
imports cleanly; each has dedicated unit tests.

| Module | LOC | Tests | What |
|---|---|---|---|
| `cards.py` | 130 | 14 | TypedDict `Card`, seeded Fisher-Yates deck, rank helpers |
| `evaluator.py` | 200 | 36 | 7-card hand evaluator — wheel, Broadway, play-the-board, counterfeited 2-pair, flush-over-flush, full-house tiebreak, quads+kicker, full category ordering |
| `ranges.py` | 230 | 48 | Chen formula (pinned worked examples), 9 Sklansky-Malmuth groups (disjoint, sum-to-169), 13×13 grid (1326 total combos), Sklansky-Chubukov ordering |
| `pot_odds.py` | 110 | 38 | required_equity, MDF, bluff break-even, Rule of 2/4 (with shading for 9+ outs) |
| `equity.py` | 200 | 20 | Live equity engine — exact enumeration when ≤2 board cards remain, Monte Carlo otherwise; multi-way aware; range-aware via `equity_vs_range` |
| `nash.py` | 200 | 18 | 4 pinned push/fold charts (HU SB 10bb, HU BB calling, MP 10bb, CO 12bb +ante); AA/KK push everywhere ≤15bb; ≤2bb HU shoves any-two; **deep stacks → "none"** (Odds-mode refuses to fabricate) |
| `icm.py` | 160 | 15 | Full Harville recursion with memoized subset evaluation; `icm_equity`; `icm_breakeven_call_equity` via binary search; chip-leader-gets-less-than-chip-share invariant verified |
| `archetypes.py` | 400 | 44 | 11 archetypes (TAG, LAG, Nit, CallingStation, Maniac, SetMiner, ABC, TAGFish, Whale, Trapper, Shark); `decide()` is **single source of truth** for bot-actor + coach-explainer (brief §4.3); deterministic given an RNG |
| `state.py` | 550 | 23 | Immutable `BettingState`, `apply_action`, side-pot computation (multi-all-in at different commitments), heads-up reversal, all-in-for-less doesn't reopen action, **chip-conservation fuzz test** |
| `tournament.py` | 150 | 33 | 15-level default blind schedule, payout structures (2-8 seats), button rotation, position labels (2-9 handed) |
| `oracle.py` | 200 | 9 | `classify_decision` — **DETERMINISTIC vs HEURISTIC** confidence tag on every output; EV-loss for deterministic; ICM overlay near bubble; streak counts deterministic only |
| `prompts.py` | 110 | 8 | `build_odds_prompt` (mentions "heuristic"/"principle", refuses single oracle for deep postflop), `build_reads_prompt` (names archetypes + estimated ranges) |

**Multi-game scaffold**: poker registered in `backend/game/registry.py` and
`backend/game/types.py::GameType`. The blackjack tests still pass — zero
regressions.

### Phase 3 — Data model + Pydantic + migration (complete)

- **`backend/models.py`** — 5 new SQLAlchemy tables: `PokerTournament`,
  `PokerSeat`, `PokerHand`, `PokerHandSeat`, `PokerAction`. Bots have NULL
  `user_id`. UNIQUE constraints on `(tournament_id, seat_number)`,
  `(tournament_id, hand_number)`, `(hand_id, seat_number)`,
  `(hand_id, action_index)`. JSON columns for board / hole_cards /
  side_pots / result.
- **`backend/schemas.py`** — Pydantic v2: `PokerTournamentCreateIn`,
  `PokerTournamentOut`, `PokerSeatOut`, `PokerHandSeatStateOut`,
  `PokerActionOut`, `PokerHandStateOut`, `PokerTournamentStateOut`,
  `PokerActIn`, `PokerAdviceIn/Out`, `PokerHandReplayOut`,
  `PokerSessionReviewOut`. All `Literal` types match DB CHECK constraints.
- **`backend/migrations/002_poker.sql`** — Postgres DDL, idempotent
  (`CREATE TABLE IF NOT EXISTS`), with indexes on FK columns. CI uses this;
  tests use `Base.metadata.create_all` on in-memory SQLite.

### Phase 4 — Routers (partial: `poker_tables.py` complete; 7 new tests)

- **`backend/routers/poker_tables.py`** — 3 endpoints:
  - `POST /api/poker/tournaments` (atomic: deduct buy-in, create
    tournament, randomly assign archetypes, create seats)
  - `GET /api/poker/tournaments` (lobby filtered by current_user)
  - `GET /api/poker/tournaments/{id}/state` (the polled endpoint; refuses
    403 for non-participants)
- Wired into `backend/main.py` (`app.include_router(poker_tables.router, prefix="/api")`).
- 7 integration tests covering AC-R1 (create + deduct), AC-R2 (insufficient
  funds), AC-R3 (bankroll conservation), validation (bot_count bounds),
  AC-R9 (authorization), list filtering by user, 404 for missing tournament.

### Phase 5 — Frontend types + client (partial)

- **`frontend/src/types/index.ts`** — full TS mirror of every Pydantic poker
  schema: `PokerCard`, `PokerTournament`, `PokerSeat`, `PokerHandSeatState`,
  `PokerAction`, `PokerHandState`, `PokerTournamentState`,
  `PokerAdviceResult`, plus `Literal` unions for mode/action/tier/verdict/street.
- **`frontend/src/api/client.ts`** — typed wrappers: `createPokerTournament`,
  `listPokerTournaments`, `getPokerTournamentState` — all returning
  `Promise<ApiResult<T>>`. No `any` — `tsc --noEmit` clean.

### CI gate status when committed

| Gate | Status |
|---|---|
| `ruff check backend` | ✅ green |
| `python -m pytest backend/tests/ -v` | ✅ **485 passed** (172 prior blackjack untouched + **313 new poker**) |
| `cd frontend && npx tsc --noEmit` | ✅ clean |
| `cd frontend && npm test -- --run` | ✅ 14 passed (3 files) |
| `cd frontend && npm run build` | ✅ built in 5.48s |

---

## What remains (in order of priority for the next session)

### A. Backend — `poker_game.py` router (the biggest remaining piece)

The endpoint `POST /api/poker/tournaments/{id}/act` is the heart of the game
loop. It must:

1. Validate the action against the current `BettingState` reconstructed from
   the DB.
2. Apply the human's action via `state.apply_action`.
3. Persist the resulting `PokerAction` row + updated `PokerHandSeat` rows.
4. **Loop** calling `archetypes.decide()` for each bot seat in `next_to_act`
   order, persisting each bot's action, until the next human decision point
   or `street_closed` returns True at hand-complete.
5. On street close: advance the street, deal community cards via
   `cards.create_deck(seed=...)`, update the `PokerHand` board.
6. On hand complete: run showdown via `evaluator.best_5_of_7`, compute
   winners per side pot, call `state.award_pots`, write the result JSON
   to `PokerHand.result`, update each seat's stack, rotate the button via
   `tournament.next_button`, advance the blind level if needed.
7. Persist everything atomically.

Plus the replay + review endpoints:
- `GET /api/poker/hands/{hand_id}/replay` (mirrors blackjack's
  `getHandActions`)
- `GET /api/poker/tournaments/{id}/review` (mirrors blackjack's
  `getSessionReview`)

Tests covering AC-R5 (in-progress reconstruction from DB), AC-R6 (act-
resolves-bots), AC-R10 (replay), AC-R11 (review), AC-R13 (streak counts
deterministic only).

**Estimate**: ~600 LOC + ~200 LOC tests, ~3-5 hours focused.

### B. Backend — `poker_advice.py` SSE router

Mirrors `backend/routers/advice.py` (blackjack) but routes through
`prompts.build_odds_prompt` or `prompts.build_reads_prompt` based on
`?mode=reads|odds`. The final SSE event carries the `PokerAdviceResult`
shape: `{ recommended_action, confidence_tier, verdict, ev_loss_chips,
principle_note }` from `oracle.classify_decision`.

Rate-limited via the existing slowapi `@limiter.limit("10/minute")` pattern.
Authorization rule: only the seat that owns the hand can request advice.

**Estimate**: ~250 LOC + ~150 LOC tests, ~2 hours.

### C. Backend — test seed helpers in `backend/tests/conftest.py`

Add `seed_poker_tournament`, `seed_poker_seats(archetypes=[...])`,
`seed_poker_hand(board=..., hole_cards={...})`, `seed_poker_actions(...)`
alongside the existing blackjack `seed_*` helpers. The integration tests in
`test_poker_endpoints.py` currently inline this; promoting them to fixtures
will simplify the upcoming router tests.

**Estimate**: ~150 LOC, ~30 min.

### D. Frontend — Zustand slice + i18n + hook

- `frontend/src/store/gameStore.ts` — add a `poker` slice:
  `pokerTournamentState`, `pokerCoachMode` (persisted to `localStorage` key
  `betwise.pokerCoachMode`, default `"odds"` per the spec's open question
  3), `pokerActionLog` (animation buffer between polls), setters.
- `frontend/src/i18n.ts` — every action label, hand-rank name (royal flush,
  straight flush, …), archetype name + description, coach template,
  confidence-tier label.
- `frontend/src/hooks/usePokerPoll.ts` — 3-second poll mirroring
  `useTablePoll.ts`. Detects "turn is now ours" and auto-opens Chipy.

**Estimate**: ~400 LOC, ~2 hours.

### E. Frontend — UI components + pages

11 components + 3 pages per the spec's File Structure section. Reuse
`PlayingCard`, `Chipy`, `ChipyPanel` from blackjack. New:

- Pages: `PokerLobby.tsx` (or extend `Lobby.tsx`), `PokerSetup.tsx`,
  `PokerTablePage.tsx`.
- Components: `PokerLobbyCard`, `PokerSeat`, `Board`, `PotDisplay`,
  `BetSizingSlider`, `PokerActionBar`, `ArchetypeBadge`,
  `PokerChipyCoach` (mode toggle + confidence-tier badge),
  `PokerReplayModal`, `PokerSessionReviewModal`.

Routes `/poker/setup` and `/poker/table/:tournamentId` added to `App.tsx`.

Hole-card masking enforced at the visual layer too (no `data-card-value`
attribute on opponent cards mid-hand).

Vitest tests for each component (8 test files) verifying loading + error
state visibility, mode toggle persistence, confidence-tier badge
rendering, and replay step-through.

**Estimate**: ~1,800 LOC TSX + ~600 LOC tests, ~6-8 hours.

### F. Final integration test

`backend/tests/test_poker_endpoints.py` — extend with the full end-to-end
smoke test the spec calls out (AC-T7): create tournament → deal hand →
human acts → bots respond → showdown → payouts updated, with chip
conservation asserted across the whole flow.

**Estimate**: ~100 LOC, ~1 hour.

### G. Documentation polish

- Add poker to the README's "where the nontrivial logic lives" table.
- Add the multi-game lobby card.
- Update `CLAUDE.md`'s "Where new code goes" table with the poker locations.

---

## Open design questions deferred from the spec

These are the open questions in `specs/texas-holdem.md` §"Open questions"
that the next session should answer:

1. **Equity engine MC iteration count** for production — currently `iters=5000`
   default; bump to 20000 if tolerance budget allows.
2. **Bot timing** — should the frontend animate bot actions at ~600ms each
   between polls? Default planned in spec.
3. **Coach mode default for new users** — plan defaults to `"odds"`. Confirm.
4. **Side-pot odd-chip rule** — plan: first seat left of button. Confirm.
5. **Heads-up vs full-ring archetype tunings** — single spec + on-the-fly
   tighten or two specs? Plan: single + `tighten_for_full_ring`.
6. **Hand-history persistence beyond replay** — design choice for later.
7. **Mobile layout for 8-seat table** — deferred to polish PR.
8. **Chipy model for poker context** — `CHIPY_MODEL` env var, currently
   blackjack uses `claude-sonnet-4-6`. May want `claude-sonnet-4-7` for
   the longer Reads-mode reasoning. Confirm.
9. **`action_log` animation timing** — default 600ms, configurable.

---

## Commit log (this session)

```
5ef6b84 feat(poker-ui): frontend types + lobby/state client wrappers
        feat(poker): tournaments router + create/list/state endpoints
        feat(poker): data model + Pydantic schemas + migration
        feat(poker): tournament + tiered oracle + Chipy prompts + registry
        feat(poker): archetypes + betting state machine (AC-B28..B38)
        feat(poker): Nash push/fold charts + Harville ICM (AC-B22..B27)
        feat(poker): spec + reference + pure brain (cards, evaluator,
                     ranges, pot odds, equity)
```

Run `git log feat/texas-holdem --oneline ^main` for the exact list.

---

## How to resume next session

```powershell
cd C:\Users\crist\dev\projects\betwise-casino
git checkout feat/texas-holdem
# Verify the CI gates are still green:
$env:BETWISE_TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
$env:BETWISE_DEV_USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
backend\.venv\Scripts\python.exe -m pytest backend\tests\ -v
backend\.venv\Scripts\python.exe -m ruff check backend
cd frontend
npx tsc --noEmit
npm test -- --run
npm run build
```

Then start with section **A** above (the `poker_game.py` router), since
everything downstream depends on it. The pure brain modules in
`backend/game/poker/` are the only thing you'll need to import — they're
fully tested and stable.

The brief in the original session's mega-prompt is the single source of
truth for AC and design constraints. This handoff covers what was built
against that brief and what the next session needs to finish.
