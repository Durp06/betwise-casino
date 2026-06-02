# Texas Hold'em (Educational) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Companion file: `specs/texas-holdem-reference.md` (every poker constant the code encodes).

**Goal:** Add an educational, single-table No-Limit Hold'em **Sit-and-Go tournament** game. One human plays against 2–7 fictional bots, each assigned a random archetype from a fixed registry. Chipy coaches every human decision in two switchable modes — **Reads mode** (archetype-aware, range-grounded prose) and **Odds mode** (deterministic-only: pot odds, live equity, short-stack push/fold Nash). The feature ships full parity with blackjack: replay, chess.com-style session review, streak (deterministic spots only), and analytics-compatible logging.

**Architecture:** New `backend/game/poker/` package holds the entire pure-function brain — card primitives, 7-card evaluator, equity engine (exact enum + Monte Carlo), pot-odds math, push/fold Nash charts, Harville ICM, range tables (Chen / Sklansky-Malmuth / 169-grid), archetype engine (single source of truth for bot-actor AND coach-explainer per brief §4.3), betting state machine (min-raise, all-in-for-less, side pots, chip conservation, heads-up reversal), and tiered correctness oracle (DETERMINISTIC vs HEURISTIC confidence tag on every classification). Poker registers in `backend.game.registry.GAME_REGISTRY` and the `GameType` literal grows `"poker"`. Persistence uses five new tables (`poker_tournaments`, `poker_seats`, `poker_hands`, `poker_hand_seats`, `poker_actions`) — *no* reuse of blackjack's `hands` / `player_actions` schema. Three new routers mirror the blackjack split: `routers/poker_tables.py` (lobby, create, join, state), `routers/poker_game.py` (deal, act, resolve — server runs all bot actions up to the next human decision point in one request), `routers/poker_advice.py` (Chipy SSE stream, mode-switched). Frontend: new `usePokerPoll` hook polling `/api/poker/tournaments/{id}/state` on the same 3-s rhythm as `useTablePoll`; new types mirror Pydantic; new `pages/PokerTable.tsx` + supporting components (PokerSeat, Board, PotDisplay, BetSizingSlider, ArchetypeBadge); replay + review modals adapt the existing patterns to poker's hand log. All hand state is fully persisted; the polled endpoint reconstructs in-progress hands from the DB.

**Tech Stack:** FastAPI + async SQLAlchemy 2.0 + Pydantic v2 on the backend; pure-sync poker brain (no async leak); pytest-asyncio + pytest-mock + in-memory SQLite for backend tests; React 18 + TypeScript + Zustand + Tailwind + React Query (only where caching matters; polling is source of truth) on the frontend; Vitest + jsdom + MSW + `@testing-library/react` for frontend tests. No new external libraries (the hand evaluator and equity engine are hand-rolled per brief §3.6 — the test suite neutralizes the usual case for a library).

---

## Context

BetWise Casino is an educational fake-money casino. Today the only game is blackjack, with a coach (Chipy) explaining each decision against the canonical basic-strategy table. The Drill Mode feature (specs/drill-mode.md) is the closest precedent for what this slice ships: pure-Python helper drives both Chipy's prompt and the test suite, and the coach gets a mode toggle.

Poker is dramatically more complex than blackjack along seven dimensions:

1. **No single oracle.** Blackjack has a published correct action for every state. Poker has a published correct action **only** for: short-stack push/fold (Nash), pot-odds-call vs all-in (equity ≥ required equity), and chip-EV preflop all-in spots. Everything else is heuristic. The brief mandates an honest **tiered classifier** — `DETERMINISTIC` spots get hard correct/incorrect + EV-loss; `HEURISTIC` spots get principle-based notes only, never streak penalties.
2. **Multi-way state.** Up to 8 seats per table, each with hole cards / stack / archetype / position / fold-state / current-bet, plus a community board (0/3/4/5 cards) and a pot (main + 0+ side pots).
3. **Many actions per hand.** Each player can act up to 4 times per hand (one per street), so a single hand can produce 20+ action rows across all seats.
4. **Bots.** 2–7 seats are server-controlled, with a per-seat archetype. The server resolves all bot actions up to the next human decision point in *one* request (brief §4.8).
5. **Tournament dynamics.** Equal starting stacks, escalating blinds + antes, eliminations, payouts. The **money unit is two integer scales**: cents (bankroll, blackjack-compatible) and tournament chips (a separate unit, brief §4.5).
6. **ICM.** Chip equity ≠ $ equity in tournaments. Harville recursion applied near the bubble + final table.
7. **Coach must match bots.** The brief's §4.3 landmine: the engine that decides a bot's action and the engine the coach uses to *explain* "what that action means" must be the same. Otherwise the game teaches false patterns.

This is the largest single feature in the project. The plan is decomposed strictly along brief §4.9: pure-sync brain (`backend/game/poker/`), then async routers split into three to keep the "single SQL helper per router" rule intact, then frontend.

---

## File Structure

### Files to create

#### Backend — pure brain (`backend/game/poker/`)
- `__init__.py` — exposes `GAME_TYPE = "poker"`; re-exports submodules.
- `cards.py` — Suit, Rank, Card TypedDict, ranks, deck factory, seeded Fisher-Yates shuffle.
- `evaluator.py` — 7-card hand evaluator: `best_5_of_7(cards)`, `rank_hand(hand)`, `compare(a, b)`. Returns `(Category, kicker_tuple)`.
- `equity.py` — `equity(hero_hole, opp_holes_or_ranges, board, iters=20000)` — exact enumeration when ≤2 cards remain across players; Monte Carlo otherwise. Multi-way aware. Accepts uniform/random or archetype-range opponent specs.
- `pot_odds.py` — `required_equity(pot_before, opp_bet)`, `bluff_breakeven(pot_before, bet)`, `mdf(pot_before, bet)`, `equity_from_outs(outs, streets_to_come)`.
- `ranges.py` — `chen_score(hand)`, `SKLANSKY_GROUPS`, `HAND_GRID`, `hand_to_str(c1, c2)`, `hand_to_grid(hand_str)`, `grid_to_hand(r, c)`, `combos_for(hand_str)`, `SC_RANK_ORDER`.
- `nash.py` — `push_fold_action(hand, stack_bb, position, ante_pct, seats)` against pinned `PUSH_FOLD_CHART`.
- `icm.py` — `harville_finish_distribution(stacks)`, `icm_equity(stacks, payouts)`, `icm_breakeven_call_equity(stacks, payouts, hero_seat, opp_seat, pot_before, opp_bet)`.
- `archetypes.py` — `ARCHETYPE_REGISTRY: dict[str, ArchetypeSpec]`, `decide(spec, hole, board, position, history, stack_bb, rng) -> ArchetypeDecision` returning `(action, sizing, intent, estimated_opponent_range)`. Single source of truth (brief §4.3).
- `state.py` — `BettingState` immutable dataclass; `apply_action(state, seat, action, amount) -> BettingState`; `next_to_act(state)`; `street_closed(state)`; `compute_side_pots(state)`; `award_pots(state, winners_per_pot)`; full chip-conservation invariant.
- `tournament.py` — `BLIND_SCHEDULE_DEFAULT`, `PAYOUT_STRUCTURE_BY_SEATS`, `current_level(hand_number)`, `effective_bb(stack_chips, level)`, `seat_assignments(seats, button_seat)`, `next_button(button_seat, live_seats)`.
- `oracle.py` — `classify_decision(snapshot, human_action, mode) -> DecisionClassification` with `confidence_tier`, `recommended_action`, `ev_loss_chips`, `principle_note`. Drives the streak and session-review.
- `prompts.py` — Chipy prompt builders for Reads + Odds modes. Pure functions that take a `BettingSnapshot` and the engine outputs, return `(system_prompt, user_message)`. The advice router calls these so the prompt logic is testable without hitting Anthropic.

#### Backend — registry + types
- `backend/game/poker/__init__.py` (above)
- Modify `backend/game/registry.py` — add poker.
- Modify `backend/game/types.py` — widen `GameType = Literal["blackjack", "poker"]`.

#### Backend — models + schemas + migration
- Modify `backend/models.py` — add `PokerTournament`, `PokerSeat`, `PokerHand`, `PokerHandSeat`, `PokerAction`.
- Modify `backend/schemas.py` — add poker Pydantic schemas (see §AC-S* below).
- `backend/migrations/002_poker.sql` — idempotent CREATE TABLE / INDEX for the five new tables (Postgres-only; tests use `Base.metadata.create_all` so SQLite is automatic).

#### Backend — routers
- `backend/routers/poker_tables.py` — `POST /api/poker/tournaments` (create+buy-in), `GET /api/poker/tournaments` (lobby), `GET /api/poker/tournaments/{id}/state` (the polled endpoint, with hole-card masking).
- `backend/routers/poker_game.py` — `POST /api/poker/tournaments/{id}/act` (human submits action; server resolves bots to next human decision point or hand end; returns updated state + action log).
- `backend/routers/poker_advice.py` — `POST /api/poker/hands/{hand_id}/advice` (SSE Chipy stream; reads `mode` query param; routes Reads/Odds through `prompts.py`).
- Modify `backend/main.py` — `app.include_router(poker_tables.router, prefix="/api/poker")` and the other two.

#### Backend — tests
- `backend/tests/test_poker_cards.py`
- `backend/tests/test_poker_evaluator.py`  *(the largest test file)*
- `backend/tests/test_poker_equity.py`
- `backend/tests/test_poker_pot_odds.py`
- `backend/tests/test_poker_ranges.py`
- `backend/tests/test_poker_nash.py`
- `backend/tests/test_poker_icm.py`
- `backend/tests/test_poker_archetypes.py`
- `backend/tests/test_poker_state.py`  *(state machine + side pots + chip conservation)*
- `backend/tests/test_poker_oracle.py`
- `backend/tests/test_poker_prompts.py`
- `backend/tests/test_poker_endpoints.py`  *(integration: full hand via HTTP, including SSE advice)*
- Modify `backend/tests/conftest.py` — add `seed_poker_tournament`, `seed_poker_seats(archetypes=...)`, `seed_poker_hand(board=..., hole_cards={...})`, `seed_poker_actions(...)`.

#### Frontend — types + client + hook
- Modify `frontend/src/types/index.ts` — add `PokerSuit`, `PokerRank`, `PokerCard`, `Archetype`, `PokerSeatView`, `PokerTournamentState`, `PokerHandState`, `PokerAction`, `PokerActionLogEntry`, `PokerAdviceMode`, `PokerCoachConfidenceTier`, `PokerAdviceChunk`, `PokerHandReplay`, `PokerSessionReview`, `PokerWeakness` (the analytics-compatible shape).
- Modify `frontend/src/api/client.ts` — add `createPokerTournament`, `listPokerTournaments`, `getPokerTournamentState`, `actPoker`, `streamPokerAdvice`, `getPokerHandReplay`, `getPokerSessionReview`.
- `frontend/src/hooks/usePokerPoll.ts` — 3-s poll of `/api/poker/tournaments/{id}/state`, reconcile into Zustand. Mirrors `useTablePoll` exactly.

#### Frontend — store + i18n
- Modify `frontend/src/store/gameStore.ts` — add a `poker` slice: `pokerTournamentState`, `pokerHandReplay`, `pokerSessionReview`, `pokerCoachMode` (`"reads" | "odds"`, persisted to `localStorage`), `pokerCoachConfidenceTier`, `setPokerCoachMode`, `setPokerTournamentState`, etc. Reuse the existing Chipy slice for streaming.
- Modify `frontend/src/i18n.ts` — add poker strings: action labels (fold/check/call/raise/all-in), 10 hand-rank names, archetype names + descriptions, coach templates, confidence-tier labels, pre-game config labels, payout-structure labels.

#### Frontend — pages + components
- `frontend/src/pages/PokerLobby.tsx` — or extend `Lobby.tsx` with a "Texas Hold'em" card alongside blackjack tables.
- `frontend/src/pages/PokerTablePage.tsx` — the table page (separate from blackjack `Table.tsx` because UI shape differs significantly).
- `frontend/src/pages/PokerSetup.tsx` — pre-game config (bot count, advice mode, buy-in confirm).
- `frontend/src/components/PokerLobbyCard.tsx` — entry point card in Lobby.
- `frontend/src/components/PokerSeat.tsx` — single seat: archetype badge, stack, current bet, fold/all-in state, dealer-button indicator.
- `frontend/src/components/Board.tsx` — community cards row (0/3/4/5 cards).
- `frontend/src/components/PotDisplay.tsx` — main pot + side pots if any.
- `frontend/src/components/BetSizingSlider.tsx` — slider + preset fractions (¼ / ½ / ¾ / pot / all-in).
- `frontend/src/components/PokerActionBar.tsx` — fold/check/call/raise/all-in buttons; submits to `/api/poker/.../act`.
- `frontend/src/components/ArchetypeBadge.tsx` — pill showing archetype name + Hellmuth-animal tooltip.
- `frontend/src/components/PokerChipyCoach.tsx` — reuses `Chipy` sprite + `ChipyPanel` but with a Reads/Odds toggle and a confidence-tier badge on each coach output.
- `frontend/src/components/PokerReplayModal.tsx` — step through hand street-by-street using the persisted action log + seed.
- `frontend/src/components/PokerSessionReviewModal.tsx` — chess.com-style classified-action list, deterministic spots only get EV-loss.

#### Frontend — tests
- `frontend/tests/PokerSeat.test.tsx` — renders archetype + stack.
- `frontend/tests/Board.test.tsx` — renders 0/3/4/5 cards.
- `frontend/tests/PotDisplay.test.tsx` — main + side pots layout.
- `frontend/tests/BetSizingSlider.test.tsx` — preset clicks, bound min/max, ¼/½/¾/pot/all-in math.
- `frontend/tests/PokerActionBar.test.tsx` — fold/check/call/raise/all-in legality wiring.
- `frontend/tests/PokerChipyCoach.test.tsx` — mode toggle persists, confidence-tier badge renders.
- `frontend/tests/PokerReplayModal.test.tsx` — step forward/back through a seeded replay.
- `frontend/tests/PokerSessionReviewModal.test.tsx` — verdict + EV-loss for deterministic, principle-note for heuristic.

#### Specs (this file + reference)
- `specs/texas-holdem.md` — this file.
- `specs/texas-holdem-reference.md` — vetted poker constants + sources (already written).

### Files to modify (recap)
- `backend/game/registry.py`
- `backend/game/types.py`
- `backend/models.py`
- `backend/schemas.py`
- `backend/main.py`
- `backend/tests/conftest.py`
- `frontend/src/types/index.ts`
- `frontend/src/api/client.ts`
- `frontend/src/store/gameStore.ts`
- `frontend/src/i18n.ts`
- `frontend/src/pages/Lobby.tsx` (or new `PokerLobby.tsx`)
- `frontend/src/App.tsx` (add the two new routes — `/poker/setup` and `/poker/table/:id`)
- `README.md` (add Texas Hold'em to the gold-features section once green)

---

## Conventions (verbatim applicable subset of CLAUDE.md, repeated for the implementer)

**Backend (Python):**
- All bankroll money in **integer cents**.
- **Tournament chips are a separate integer unit**, never converted to cents except at buy-in (deduct from bankroll) and payout (credit to bankroll). No rake.
- Async SQLAlchemy 2.0 only in routers and DB code. `Mapped[...]` typed columns. JSON columns for board / hole-card / action-log / side-pot snapshots (SQLite-tests + Postgres-prod compatibility).
- Pure-sync game logic in `backend/game/poker/`. No `await`, no DB access. The hand evaluator, equity engine, archetype decisions, push/fold lookups, ICM math, side-pot computation, and state-machine transitions all run as sync pure functions.
- Pydantic v2 with `model_config = ConfigDict(from_attributes=True)`.
- `datetime.now(timezone.utc)` — never `datetime.utcnow()` (grader anti-pattern).
- **Single SQL helper per router, prefixed `_`, at the bottom of the file.** Hence the router split: `poker_tables.py`, `poker_game.py`, `poker_advice.py` each have their own `_helper`.
- Lazy imports inside handlers with `# noqa: PLC0415` for cheap module-import time.
- Errors → `raise HTTPException(...)`; the global handler in `main.py` catches anything that escapes.
- `logger = logging.getLogger(__name__)` — no `print()`.
- Every endpoint returning user data takes `current_user: CurrentUser` and checks ownership. **Hole cards** are user data: every seat except the current viewer's own seat returns `cards: [null, null]` during a hand. Replay-after-finish is the only public carve-out.
- Ruff line length 120 stays green.

**Frontend (TypeScript):**
- **No `any` — no exceptions.** Use `unknown` and narrow at the boundary.
- Tailwind for everything visual; inline styles only for dynamic numeric values.
- Components PascalCase, utilities camelCase, hooks `useXxx`.
- Every fetch handles `{ data, error }` and both branches are rendered.
- All user-facing strings through `t()` from `frontend/src/i18n.ts` — including the ten hand-rank names, the eleven archetype names + descriptions, every action label, every coach template.
- Zustand for client state; polling hook is the source of truth.

**Tests:**
- Backend pytest-asyncio + in-memory SQLite. **Do not mock the DB.** Use the new `seed_poker_*` helpers in `tests/conftest.py`.
- Frontend Vitest + jsdom + `@testing-library/react`. Mock HTTP with MSW.
- Acceptance criterion → failing test → implementation. Via the planner→tester→implementer subagent loop.

**CI gates (all must stay green):**
- `ruff check backend`
- `python -m pytest backend/tests/ -v`
- `cd frontend && npx tsc --noEmit`
- `cd frontend && npm test -- --run`
- `cd frontend && npm run build`

---

## Acceptance Criteria

### Backend — engine (pure)

- **AC-B1** *(cards)* — `cards.py::create_deck(seed)` returns 52 distinct `Card` dicts; same seed → identical order. `deal(deck) -> (card, remaining)` does not mutate.
- **AC-B2** *(evaluator categories)* — `evaluator.rank_hand` correctly returns each of the 10 categories with at least one test per category.
- **AC-B3** *(evaluator wheel)* — `A-2-3-4-5` evaluates as a straight (ace low), category 6, top kicker 5.
- **AC-B4** *(evaluator Broadway)* — `A-K-Q-J-T` evaluates as a straight, top kicker A.
- **AC-B5** *(evaluator play-the-board)* — when the best 5 are entirely community cards (e.g. board is A-K-Q-J-T rainbow), all live seats tie regardless of hole cards.
- **AC-B6** *(evaluator counterfeited 2-pair)* — hand `99 + 88` with board `KK22 + 4`: best 5 = `KK 99 + something` — but if board pairs higher (e.g. `KKQQ + 4`), the two pair becomes counterfeited (KKQQ + K kicker, not KK 99). Pinned scenario.
- **AC-B7** *(evaluator flush-over-flush)* — two players holding the same suit; comparison is by highest non-board flush card down the kickers.
- **AC-B8** *(evaluator full-house tiebreak)* — full house with same trips uses the pair as tiebreak; same trips + same pair = chop.
- **AC-B9** *(evaluator quads + kicker)* — same quads → high kicker wins.
- **AC-B10** *(evaluator category ordering)* — straight flush > quads > full house > flush > straight > trips > two pair > pair > high card. Parametrized.
- **AC-B11** *(equity heads-up canonical)* — `equity(AA, KK, board=[])` between 81.5% and 82.5% over 50k iterations. Test parametrizes the canonical matchups from reference §4 with ±1.5% tolerance.
- **AC-B12** *(equity multi-way)* — `equity(AA, [random, random], board=[])` returns ~73% ±2%.
- **AC-B13** *(equity board-aware)* — `equity(AKs of hearts, KQo, board=2h-5h-9c)` reflects the flush draw — AKs > 50%.
- **AC-B14** *(equity range-aware)* — `equity(hero=87s, opp_range=top_15_pct(SC), board=[])` returns higher than `equity(87s, opp_range=top_5_pct, board=[])` — the wider range gives 87s more equity.
- **AC-B15** *(pot odds)* — `required_equity(pot=100, opp_bet=50) == 0.25`. Pinned table values match §2.
- **AC-B16** *(MDF + bluff break-even)* — pinned values from §2 match.
- **AC-B17** *(rule of 2/4)* — `equity_from_outs(9, streets=2) ≈ 0.35` ±0.04; `outs=15` clamps the overestimate down per the comment in §3.
- **AC-B18** *(Chen formula)* — `chen_score("AKs") == 12`, `chen_score("AKo") == 10`, `chen_score("JTs") == 9`, `chen_score("55") == 5`, `chen_score("22") == 5`. Parametrized worked examples.
- **AC-B19** *(Sklansky-Malmuth groups)* — group sets together total all 169 hands exactly once; Group 1 contains exactly `{AA, KK, QQ, JJ, AKs}`; Group 9 = everything outside Groups 1–8.
- **AC-B20** *(SC ordering monotonic)* — AA top, 32o bottom; for any two hands `a`, `b` in `SC_RANK_ORDER`, `chen_score(a) >= chen_score(b)` is *not* guaranteed (orderings differ), but pairs beat same-high-card offsuit (e.g. SC(22) < SC(J2o) is false — pair beats J2o).
- **AC-B21** *(169-hand grid completeness)* — `HAND_GRID` flattened has 169 distinct entries; `combos_for` returns 6 for pairs, 4 for suited, 12 for offsuit; total combos sum to 1326.
- **AC-B22** *(Nash chart pinning — HU 10bb)* — `push_fold_action("AA", 10, "SB", ante_pct=0, seats=2) == "push"`; `push_fold_action("32o", 10, "SB", 0, 2) == "fold"`; `push_fold_action("A2s", 10, "SB", 0, 2) == "push"`. Parametrized.
- **AC-B23** *(Nash chart pinning — HU ≤1.7bb shoves any-two)* — `push_fold_action("32o", 1.5, "SB", 0, 2) == "push"`.
- **AC-B24** *(Nash chart pinning — CO 12bb +ante widens)* — `push_fold_action("Q8s", 12, "CO", 0.125, 9) == "push"`; without ante, that same hand folds.
- **AC-B25** *(Nash refuses out-of-bounds)* — `push_fold_action("AA", 25, "BTN", 0, 9)` returns `"none"` or raises with a clear message; the contract is "Nash is short-stack only; deep-stacked is not push/fold."
- **AC-B26** *(Harville ICM)* — pinned cases from reference §9 match within ±$0.05.
- **AC-B27** *(ICM break-even tighter than chip-EV)* — `icm_breakeven_call_equity` for a bubble-style spot returns ≥0.36 (vs the chip-EV 0.333 for a pot-sized all-in).
- **AC-B28** *(archetype determinism)* — `decide(spec=TAG, hole=AKs, board=[], ...)` with `rng=Random(42)` always returns the same `ArchetypeDecision`. Parametrized across all 10+ archetypes.
- **AC-B29** *(archetype-coach single source of truth — brief §4.3)* — for every archetype × spot in a pinned test matrix, `decide(...)` returns an `estimated_opponent_range` that contains the bot's actually-chosen action's range. Asserts the coach can't say "this bot only raises premium" while the bot raises with non-premium.
- **AC-B30** *(archetype roster ≥ 10)* — `ARCHETYPE_REGISTRY` has at least 10 distinct entries with the exact names from reference §12.
- **AC-B31** *(state machine min-raise)* — a raise that increases the bet by less than the previous raise increment is rejected (except when the raiser is going all-in for less, in which case the action is legal but does not reopen betting for already-acted players).
- **AC-B32** *(state machine all-in-for-less)* — Player A bets 100; Player B all-ins for 130 (raise of 30, less than the 100 increment); previously-acted Player C cannot re-raise — can only call 130 or fold.
- **AC-B33** *(state machine street closing)* — once action returns to the last aggressor (or all live players check through), the street closes and the next street is dealt.
- **AC-B34** *(state machine heads-up reversal)* — preflop in HU: BTN posts SB and acts first preflop; postflop: BB acts first.
- **AC-B35** *(side pots)* — three all-ins at different stack sizes (e.g. 30, 60, 100) produce a main pot eligible to all 3 plus a side pot eligible to the back two plus a side pot eligible to only the deepest. Tested against worked examples.
- **AC-B36** *(chip conservation)* — for every transition `apply_action(state, ...)`: `sum(stacks) + sum(pots) + sum(current_street_bets) == initial_total_chips`. Tested at every action in a fuzz test (100 random hands).
- **AC-B37** *(all-in run-out)* — when all live players are all-in, remaining streets deal automatically with no further action; showdown awards the pots.
- **AC-B38** *(everyone folds to BB)* — preflop, every seat folds before the BB. BB wins the dead money; no flop dealt.
- **AC-B39** *(seeded determinism end-to-end)* — given the same `tournament.seed`, the same human action sequence produces the same board, the same bot actions, the same winners.
- **AC-B40** *(oracle DETERMINISTIC ≤15bb push/fold)* — `classify_decision(short_stack_jam_spot, "push", "odds")` for an in-Nash-chart push returns `{tier: "DETERMINISTIC", correct: True}`; pushing a clear fold hand returns `{tier: "DETERMINISTIC", correct: False, ev_loss_chips: > 0}`.
- **AC-B41** *(oracle DETERMINISTIC pot-odds call)* — facing a pot-sized all-in with `equity > 0.34` and `equity > required_equity` returns `{tier: "DETERMINISTIC", correct: action == "call"}`.
- **AC-B42** *(oracle HEURISTIC deep postflop)* — a deep-stacked postflop spot returns `{tier: "HEURISTIC", correct: None, principle_note: <non-empty string>}`. Never decrements the streak.
- **AC-B43** *(oracle ICM overlay)* — near the bubble (the second-to-last seat shoving into the chip leader), the break-even equity to call rises above the chip-EV value by ≥3 percentage points.
- **AC-B44** *(prompts Odds mode is deterministic-grounded only)* — `build_odds_prompt(snapshot)` for a deep postflop spot mentions "heuristic" or "principle" and does **not** assert a single correct action.
- **AC-B45** *(prompts Reads mode names archetypes)* — `build_reads_prompt(snapshot, archetypes_by_seat)` for a multi-opponent spot mentions at least one archetype name from `ARCHETYPE_REGISTRY` and at least one estimated range descriptor.

### Backend — routers + persistence

- **AC-R1** *(create tournament + buy-in)* — `POST /api/poker/tournaments` with `{bot_count, advice_mode, buy_in_cents, starting_stack_chips}`: creates a `PokerTournament` row + `PokerSeat` rows (1 human + N bots, archetypes randomly assigned), deducts `buy_in_cents` from `user.chip_balance` atomically. Returns the tournament row.
- **AC-R2** *(insufficient bankroll)* — `POST /api/poker/tournaments` when `user.chip_balance < buy_in_cents` returns 400.
- **AC-R3** *(buy-in cents conservation)* — across creation and payout, the sum `bankroll_user + bankroll_others + prize_pool_cents` is invariant.
- **AC-R4** *(state endpoint masks hole cards)* — `GET /api/poker/tournaments/{id}/state` returns the current viewer's own seat's hole cards but `[null, null]` for every other live seat, until showdown (status `"showdown"` or beyond). Tested with two clients.
- **AC-R5** *(state endpoint reconstructs in-progress hand from DB)* — kill the server (drop the in-process state); `GET /state` rebuilds the current `BettingState` from the persisted `PokerHand` + `PokerHandSeat` + `PokerAction` rows. No in-memory game state.
- **AC-R6** *(act resolves bots to next human decision)* — `POST /api/poker/tournaments/{id}/act` with a human action: the server applies the human's action, then loops `archetypes.decide` for each bot until the next human decision point or hand end, persisting every bot action. Returns the updated state + an action log the frontend animates through.
- **AC-R7** *(SSE Chipy stream Reads mode)* — `POST /api/poker/hands/{hand_id}/advice?mode=reads`: streams text chunks; final SSE event carries a JSON shape `{"recommended_action", "confidence_tier", "ev_loss_chips"}`.
- **AC-R8** *(SSE Chipy stream Odds mode)* — same endpoint with `mode=odds`: the final JSON event carries the same fields; for deep postflop the `confidence_tier` is `"HEURISTIC"` and `recommended_action` is `null`.
- **AC-R9** *(advice authorization)* — only the seat that owns the hand can request advice for it (returns 403 for any other user).
- **AC-R10** *(replay endpoint)* — `GET /api/poker/hands/{hand_id}/replay` returns the ordered action log + per-seat hole cards (for finished hands only — authorization rule mirrors blackjack: owner during play, public after showdown).
- **AC-R11** *(session review endpoint)* — `GET /api/poker/tournaments/{id}/review` returns a `PokerSessionReview` with: `total_actions`, `deterministic_actions`, `optimal_count`, `ev_lost_chips` (sum over DETERMINISTIC spots only), per-action classifications.
- **AC-R12** *(rate limits)* — Chipy SSE endpoint is `@limiter.limit("10/minute")` keyed by `user_id` (mirrors blackjack advice).
- **AC-R13** *(streak counts deterministic only)* — after a series of mixed deterministic / heuristic decisions, `current_streak` increases on deterministic-correct and resets on deterministic-incorrect; heuristic decisions are never counted.
- **AC-R14** *(blackjack untouched)* — every existing blackjack test still passes.

### Backend — Pydantic schemas

- **AC-S1** — `PokerTournamentCreateIn` validates `bot_count ∈ [2, 7]`, `advice_mode ∈ {"reads", "odds"}`, `buy_in_cents > 0`, `starting_stack_chips > 0`.
- **AC-S2** — `PokerTournamentOut`, `PokerSeatOut`, `PokerHandOut`, `PokerHandSeatOut`, `PokerActionOut` all have `ConfigDict(from_attributes=True)` and exact-match the SQLAlchemy column types.
- **AC-S3** — `PokerTournamentStateOut` exposes: tournament metadata, seats (with masked hole cards per AC-R4), current hand (board, pot, side pots, status, current_to_act_seat), action_log (the new actions the client must animate through).
- **AC-S4** — `PokerActIn` validates `action ∈ {"fold","check","call","raise","all_in"}` and `amount ≥ 0`.

### Frontend

- **AC-F1** *(types-mirror-Pydantic)* — every backend schema has a TS interface in `types/index.ts` with matching field names + types. `npx tsc --noEmit` is clean. No `any`.
- **AC-F2** *(client functions)* — every poker endpoint has a typed wrapper in `client.ts` returning `Promise<ApiResult<T>>`. Both `data` and `error` branches handled at every call site.
- **AC-F3** *(usePokerPoll)* — polls `/state` every 3s; reconciles to `gameStore.pokerTournamentState`. Detects "turn is now ours" and surfaces it for the coach.
- **AC-F4** *(PokerLobbyCard)* — renders in `Lobby.tsx` alongside blackjack tables; click → `/poker/setup`.
- **AC-F5** *(PokerSetup)* — bot-count select (2–7), advice-mode radio (Reads/Odds), starting-stack input, buy-in input. Confirm button calls `createPokerTournament`. Surfaces both `error` and the deducted balance on success.
- **AC-F6** *(PokerTablePage)* — renders seats around the table with `PokerSeat`, the `Board`, `PotDisplay`, `PokerActionBar` + `BetSizingSlider`, `PokerChipyCoach`. Animates the action log between polls.
- **AC-F7** *(hole-card masking)* — opponent cards always render as card-backs until showdown. Visual test asserts no `data-card-value` attribute appears for non-self seats during play.
- **AC-F8** *(coach mode toggle persists)* — `PokerChipyCoach` renders Reads/Odds pills, persists choice to `localStorage` key `betwise.pokerCoachMode`.
- **AC-F9** *(confidence-tier badge)* — every coach output shows `DETERMINISTIC` (green) or `HEURISTIC` (orange) badge, label via `t()`.
- **AC-F10** *(replay parity)* — `PokerReplayModal` steps through the persisted action log + seed; revealed hole cards appear at showdown.
- **AC-F11** *(session review parity)* — `PokerSessionReviewModal` classifies each deterministic action and totals EV-loss; lists heuristic actions with their principle notes and no verdict.
- **AC-F12** *(every fetch handles loading + error)* — both branches visible in the UI. Tested via MSW error injection.
- **AC-F13** *(i18n coverage)* — every user-facing string goes through `t()`. Grep test: no string literals in poker .tsx files for action labels / archetype names / hand-rank names.

### Tests / CI

- **AC-T1** — `seed_poker_tournament`, `seed_poker_seats(archetypes=[...])`, `seed_poker_hand(board=..., hole_cards={seat_id: [...]})`, `seed_poker_actions(...)` exist in `backend/tests/conftest.py` alongside the existing seed helpers.
- **AC-T2** — full `pytest backend/tests/ -v` passes — both new poker tests AND every prior blackjack test (AC-R14 stronger form).
- **AC-T3** — `ruff check backend` is green.
- **AC-T4** — `cd frontend && npx tsc --noEmit` is clean.
- **AC-T5** — `cd frontend && npm test -- --run` passes including all new `PokerXxx.test.tsx` files.
- **AC-T6** — `cd frontend && npm run build` succeeds.
- **AC-T7** *(end-to-end smoke)* — `backend/tests/test_poker_endpoints.py` runs a full hand via HTTP: create tournament, deal hand, human acts, bots respond, showdown, payouts updated. Assertions on the persisted action log + chip conservation.

---

## Out of scope (for v1)

- Multi-table tournaments. Single SNG only.
- Live human-vs-human multiplayer. Bots only.
- Real money. Fake-cents bankroll only.
- Rebuys / add-ons. Freezeout only.
- Run-it-twice / insurance.
- Acting clock for the human (no timer).
- Adaptive / learning bots that adjust across hands. Static archetypes; deterministic by seed.
- A dedicated poker-specific analytics dashboard. Logging is compatible with the existing analytics surface but no new UI for it in v1.
- Solver-grade GTO advice. The "Odds" mode is deterministic-only-where-it's-actually-deterministic; brief §4.1 explicitly forbids fake-oracle behavior for deep postflop.
- A "tournament history" view. Replay + review per-hand only.
- WebSocket transport for the table. 3-s polling per existing convention.
- Heads-up display (HUD) stats over time.
- Sound / music for the poker table beyond what blackjack uses.

---

## Plan

The build proceeds in nine task groups. Each task is a planner→tester→implementer slice:
- The **planner** decomposes the task into specific files + AC mappings.
- The **tester** writes the failing tests.
- The **implementer** writes the minimal code that makes the tests pass.
- After every task: `ruff check backend` + `pytest backend/tests/<new_file> -v` + (where applicable) `tsc --noEmit` + `npm test -- --run`.

### Task 1: Card primitives and seeded deck

**Files:** create `backend/game/poker/cards.py`, `backend/tests/test_poker_cards.py`.

**ACs covered:** AC-B1.

- [ ] Write `test_poker_cards.py` covering: `create_deck()` length 52; `create_deck(seed=42)` == `create_deck(seed=42)`; `deal` does not mutate; suits + ranks complete.
- [ ] Run test → fail (import error).
- [ ] Write `cards.py` minimal implementation.
- [ ] Run test → pass.
- [ ] `ruff check backend/game/poker/cards.py` clean.
- [ ] Commit: `feat(poker): card primitives + seeded deck`.

### Task 2: 7-card evaluator

**Files:** create `backend/game/poker/evaluator.py`, `backend/tests/test_poker_evaluator.py`.

**ACs covered:** AC-B2 through AC-B10.

- [ ] Write `test_poker_evaluator.py` with at least one test per category (royal flush, straight flush, quads, full house, flush, straight, trips, two pair, pair, high card), plus the wheel, Broadway, play-the-board, counterfeited 2-pair, flush-over-flush by kicker, full-house tiebreak, quads + kicker.
- [ ] Run → fail.
- [ ] Implement evaluator. Use 5-of-7 enumeration (21 combos) — simpler than a lookup table and fast enough at scale tested by the equity engine.
- [ ] Run → pass.
- [ ] Commit: `feat(poker): 7-card hand evaluator with kicker logic`.

### Task 3: Ranges (Chen, Sklansky-Malmuth, 169 grid, SC ordering)

**Files:** create `backend/game/poker/ranges.py`, `backend/tests/test_poker_ranges.py`.

**ACs covered:** AC-B18–AC-B21.

- [ ] Write `test_poker_ranges.py` parametrized over the worked Chen examples + the Sklansky-Malmuth group completeness + 169-hand grid completeness + SC ordering monotonic.
- [ ] Run → fail.
- [ ] Implement `chen_score`, `SKLANSKY_GROUPS`, `HAND_GRID`, helpers, `SC_RANK_ORDER` (drawing from `specs/texas-holdem-reference.md` §5–§7 + §11).
- [ ] Run → pass.
- [ ] Commit: `feat(poker): starting-hand ranges + Chen + Sklansky tiers`.

### Task 4: Pot odds, MDF, Rule of 2/4

**Files:** create `backend/game/poker/pot_odds.py`, `backend/tests/test_poker_pot_odds.py`.

**ACs covered:** AC-B15–AC-B17.

- [ ] Write `test_poker_pot_odds.py` with the pinned table values from reference §2 and §3.
- [ ] Run → fail.
- [ ] Implement pure functions.
- [ ] Run → pass.
- [ ] Commit: `feat(poker): pot odds + MDF + Rule of 2/4`.

### Task 5: Equity engine

**Files:** create `backend/game/poker/equity.py`, `backend/tests/test_poker_equity.py`.

**ACs covered:** AC-B11–AC-B14.

- [ ] Write `test_poker_equity.py` covering canonical matchups (parametrized from reference §4), multi-way equity, board-aware equity, range-aware equity. Tolerance ±1.5%.
- [ ] Run → fail.
- [ ] Implement `equity` — exact enumeration when remaining cards ≤ ~5; Monte Carlo otherwise with `iters=20000` default. Use `evaluator` for showdown.
- [ ] Run → pass (may be slow; set `iters=5000` in tests to keep total runtime <10s).
- [ ] Commit: `feat(poker): live equity engine (enum + MC)`.

### Task 6: Push/fold Nash charts

**Files:** create `backend/game/poker/nash.py`, `backend/tests/test_poker_nash.py`.

**ACs covered:** AC-B22–AC-B25.

- [ ] Write `test_poker_nash.py` parametrized over the pinned HU-10bb + HU-≤1.7bb + CO-12bb+ante + UTG-10bb-A3o-fold cases.
- [ ] Run → fail.
- [ ] Implement `PUSH_FOLD_CHART` per reference §8 — bucketed by `(seats, ante_pct, stack_bb_bucket, position)`. Out-of-bounds (stack_bb > 15) returns `"none"`.
- [ ] Run → pass.
- [ ] Commit: `feat(poker): short-stack push/fold Nash charts`.

### Task 7: ICM (Harville)

**Files:** create `backend/game/poker/icm.py`, `backend/tests/test_poker_icm.py`.

**ACs covered:** AC-B26, AC-B27.

- [ ] Write `test_poker_icm.py` with the pinned Harville cases from reference §9.
- [ ] Run → fail.
- [ ] Implement `harville_finish_distribution` (Malmuth recursion), `icm_equity`, `icm_breakeven_call_equity`.
- [ ] Run → pass.
- [ ] Commit: `feat(poker): Harville ICM calculator`.

### Task 8: Archetype engine

**Files:** create `backend/game/poker/archetypes.py`, `backend/tests/test_poker_archetypes.py`.

**ACs covered:** AC-B28–AC-B30, AC-B45 (partial).

- [ ] Write `test_poker_archetypes.py` with: registry has ≥10 named archetypes per reference §12; `decide(...)` is deterministic given the same RNG; for every archetype, the bot's chosen action is contained in its self-reported `estimated_opponent_range`.
- [ ] Run → fail.
- [ ] Implement `ArchetypeSpec`, `ArchetypeDecision` (action / sizing / intent / estimated_opponent_range), `ARCHETYPE_REGISTRY` with TAG, LAG, Nit, CallingStation, Maniac, SetMiner, ABC, TAGFish, Whale, Trapper, Shark + optional Tilt overlay (11+ total). Each archetype is a pure-function decision policy keyed off `(VPIP, PFR, AF, sizing-policy, reaction-to-aggression-policy, hole, board, position, history, stack_bb)`.
- [ ] Run → pass.
- [ ] Commit: `feat(poker): archetype engine — bot policies & coach reads`.

### Task 9: Betting state machine + side pots + chip conservation

**Files:** create `backend/game/poker/state.py`, `backend/tests/test_poker_state.py`.

**ACs covered:** AC-B31–AC-B38.

- [ ] Write `test_poker_state.py` covering: min-raise legality, all-in-for-less not reopening, street closing, heads-up reversal, blind + ante posting, button rotation, side-pot math (3 all-ins at different stack sizes), chip conservation (fuzz test 100 hands), all-in run-out, everyone-folds-to-BB.
- [ ] Run → fail.
- [ ] Implement immutable `BettingState` dataclass + `apply_action` + helpers. The state machine is the largest single module — budget 600-800 LOC.
- [ ] Run → pass.
- [ ] Commit: `feat(poker): betting state machine + side pots + chip conservation`.

### Task 10: Tournament glue (blinds, payouts, button rotation, seed)

**Files:** create `backend/game/poker/tournament.py`, `backend/tests/test_poker_tournament.py`.

**ACs covered:** part of AC-B36, AC-B39; supports AC-R1–R3.

- [ ] Write `test_poker_tournament.py` covering: default blind schedule pins; payout structure sums to 100% per seat count; button rotation across hands; `effective_bb` math.
- [ ] Run → fail.
- [ ] Implement.
- [ ] Run → pass.
- [ ] Commit: `feat(poker): tournament glue — blinds, payouts, button rotation`.

### Task 11: Tiered correctness oracle

**Files:** create `backend/game/poker/oracle.py`, `backend/tests/test_poker_oracle.py`.

**ACs covered:** AC-B40–AC-B43.

- [ ] Write `test_poker_oracle.py` covering: deterministic ≤15bb push/fold; deterministic pot-odds call; heuristic deep postflop; ICM overlay tightens break-even.
- [ ] Run → fail.
- [ ] Implement `classify_decision(snapshot, human_action, mode) -> DecisionClassification`. Spec types: `confidence_tier: "DETERMINISTIC" | "HEURISTIC"`, `recommended_action: Optional[str]`, `correct: Optional[bool]`, `ev_loss_chips: Optional[int]`, `principle_note: Optional[str]`.
- [ ] Run → pass.
- [ ] Commit: `feat(poker): tiered correctness oracle with confidence tags`.

### Task 12: Chipy prompt builders

**Files:** create `backend/game/poker/prompts.py`, `backend/tests/test_poker_prompts.py`.

**ACs covered:** AC-B44, AC-B45.

- [ ] Write `test_poker_prompts.py` covering Reads-mode prompt names archetypes + estimated ranges; Odds-mode prompt for deep postflop mentions "heuristic"/"principle" and does NOT assert a single correct action.
- [ ] Run → fail.
- [ ] Implement `build_reads_prompt(snapshot, archetypes_by_seat) -> (system, user)`, `build_odds_prompt(snapshot) -> (system, user)`.
- [ ] Run → pass.
- [ ] Commit: `feat(poker): Chipy prompts for Reads and Odds modes`.

### Task 13: Register poker in the registry + types

**Files:** modify `backend/game/__init__.py`, `backend/game/registry.py`, `backend/game/types.py`, create `backend/game/poker/__init__.py`.

- [ ] Edit `backend/game/poker/__init__.py` → `GAME_TYPE = "poker"` + submodule re-exports.
- [ ] Edit `backend/game/registry.py` → add poker.
- [ ] Edit `backend/game/types.py` → widen `GameType = Literal["blackjack", "poker"]`.
- [ ] Run: `pytest backend/tests/test_poker_*.py` — all still pass.
- [ ] Run: `pytest backend/tests/test_endpoints.py` — blackjack untouched (AC-R14).
- [ ] Commit: `feat(poker): register in multi-game scaffold`.

### Task 14: Data model + Pydantic schemas + migration

**Files:** modify `backend/models.py`, `backend/schemas.py`; create `backend/migrations/002_poker.sql`.

**ACs covered:** AC-S1–AC-S4.

- [ ] Add `PokerTournament`, `PokerSeat`, `PokerHand`, `PokerHandSeat`, `PokerAction` to `models.py`. JSON columns for board / hole_cards / side_pots / action_log / archetype_params. UUID PKs. `datetime.now(timezone.utc)` defaults. UNIQUE constraints: `(tournament_id, seat_number)`, `(tournament_id, user_id) WHERE user_id IS NOT NULL` (i.e. one human per tournament, but bots can share NULL user_id), `(hand_id, seat_id)`, `(hand_id, street, action_index)`.
- [ ] Add Pydantic schemas to `schemas.py`. Use `Literal` types for `advice_mode`, `confidence_tier`, `action`, `tournament_status`.
- [ ] Write `002_poker.sql` (Postgres syntax) idempotent. (Tests don't read this file — they use `Base.metadata.create_all`.)
- [ ] Add seed helpers to `backend/tests/conftest.py`: `seed_poker_tournament`, `seed_poker_seats(archetypes=...)`, `seed_poker_hand(board=..., hole_cards={seat_id: [...]})`, `seed_poker_actions(...)`.
- [ ] Run: `pytest backend/tests/ -v` — every prior test still green.
- [ ] Commit: `feat(poker): data model + Pydantic schemas + migration`.

### Task 15: Routers (tables, game, advice)

**Files:** create `backend/routers/poker_tables.py`, `backend/routers/poker_game.py`, `backend/routers/poker_advice.py`; create `backend/tests/test_poker_endpoints.py`.

**ACs covered:** AC-R1–AC-R13, AC-T7.

- [ ] Write `test_poker_endpoints.py` covering: AC-R1, R2, R3 (cents conservation), R4 (mask), R5 (reconstruct from DB), R6 (act → bots resolved), R7 (SSE Reads mode), R8 (SSE Odds mode), R9 (advice authorization), R10 (replay), R11 (review), R12 (rate limits), R13 (streak deterministic-only).
- [ ] Run → fail.
- [ ] Implement the three routers. Each keeps one `_helper` SQL function at the bottom.
- [ ] Wire into `main.py`.
- [ ] Run → pass.
- [ ] Commit: `feat(poker): routers — tables, game, advice (SSE)`.

### Task 16: Frontend types + client + poll hook

**Files:** modify `frontend/src/types/index.ts`, `frontend/src/api/client.ts`; create `frontend/src/hooks/usePokerPoll.ts`.

**ACs covered:** AC-F1–AC-F3.

- [ ] Mirror every backend schema in `types/index.ts`. No `any`.
- [ ] Add typed wrappers to `client.ts`.
- [ ] Implement `usePokerPoll`.
- [ ] Run: `tsc --noEmit` → clean.
- [ ] Commit: `feat(poker): frontend types + client + poll hook`.

### Task 17: Store + i18n

**Files:** modify `frontend/src/store/gameStore.ts`, `frontend/src/i18n.ts`.

- [ ] Add `poker` slice to `gameStore.ts` (state + actions). Persist `pokerCoachMode` to `localStorage` (default `"odds"` for new users — odds is the safer default for an educational tool).
- [ ] Add all poker strings to `i18n.ts`.
- [ ] Run: `tsc --noEmit` → clean.
- [ ] Commit: `feat(poker): store slice + i18n strings`.

### Task 18: UI components

**Files:** create `frontend/src/components/PokerLobbyCard.tsx`, `PokerSeat.tsx`, `Board.tsx`, `PotDisplay.tsx`, `BetSizingSlider.tsx`, `PokerActionBar.tsx`, `ArchetypeBadge.tsx`, `PokerChipyCoach.tsx`, `PokerReplayModal.tsx`, `PokerSessionReviewModal.tsx`; corresponding tests in `frontend/tests/`.

**ACs covered:** AC-F4–AC-F13.

- [ ] One component at a time: write the Vitest test → run (fail) → implement → run (pass).
- [ ] Reuse existing `PlayingCard`, `Chipy`, `ChipyPanel` shapes.
- [ ] Commit each component individually: `feat(poker-ui): <ComponentName>`.

### Task 19: Pages + routes

**Files:** create `frontend/src/pages/PokerLobby.tsx` (or extend `Lobby.tsx`), `PokerSetup.tsx`, `PokerTablePage.tsx`; modify `frontend/src/App.tsx`.

**ACs covered:** AC-F4–AC-F12 (wiring).

- [ ] Add routes `/poker/setup` and `/poker/table/:tournamentId` to `App.tsx`.
- [ ] Implement pages. Animate the action log between polls via `pokerTournamentState.action_log` consumed by `PokerTablePage`.
- [ ] Run: `tsc --noEmit` + `npm test -- --run` + `npm run build` → all green.
- [ ] Commit: `feat(poker-ui): lobby, setup, and table pages`.

### Task 20: Full CI + cleanup

- [ ] `ruff check backend` → green.
- [ ] `pytest backend/tests/ -v` → all tests pass (existing 172 + ~150 new).
- [ ] `tsc --noEmit` → clean.
- [ ] `npm test -- --run` → green.
- [ ] `npm run build` → succeeds.
- [ ] Update `README.md` to add Texas Hold'em to the "where the nontrivial logic lives" table.
- [ ] Commit: `docs(readme): Texas Hold'em educational tournament feature`.
- [ ] Open PR against `main`.

---

## Verification commands

- Backend single-module: `pytest backend/tests/test_poker_evaluator.py -v`
- Backend full: `cd backend && BETWISE_TEST_DB_URL="sqlite+aiosqlite:///:memory:" BETWISE_DEV_USER_ID="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" pytest tests/ -v`
- Ruff: `ruff check backend`
- Frontend single-file: `cd frontend && npx vitest run PokerActionBar`
- Frontend full: `cd frontend && npm test -- --run`
- TS typecheck: `cd frontend && npx tsc --noEmit`
- Production build: `cd frontend && npm run build`

End-to-end smoke (manual, after launch):
- Start backend on `:8000`, frontend on `:5173`.
- Lobby → "Texas Hold'em (Educational)" card → Setup → confirm buy-in.
- At the poker table: act through a full hand, switching coach mode mid-hand.
- After the hand, open Replay and Session Review.
- Play until either you bust or you win the tournament; confirm cents bankroll is debited at buy-in and credited at payout.

---

## Open questions

1. **Equity engine MC iteration count.** Default in implementation is `iters=20000`. Tests use `iters=5000` for speed. Confirm the tolerance budget the grader applies and tune if needed.
2. **Bot timing.** The brief §4.8 specifies the server runs all bot actions up to the next human decision point in one request. UI animation between polls is driven by the persisted `action_log`. Do we want a configurable per-bot delay (e.g. 800ms) to feel realistic, or instant? Default: 600ms client-side delay between consecutive bot actions in the same poll batch.
3. **Coach mode default for new users.** The brief is silent. Plan defaults to **Odds** — it's the safer / more honest mode for an educational tool. Confirm.
4. **Side-pot odd-chip rule.** Default per common SNG convention: odd chip to the first seat left of the button. Confirm.
5. **Heads-up vs full-ring archetype tunings.** The brief says VPIP/PFR bands run "several points tighter in full-ring." Should each archetype carry both 6-max and full-ring stat blocks, or scale on the fly from a single block? Plan: single block + a `tighten_for_full_ring(spec, seats)` modifier (saves table size).
6. **Tournament hand history persistence beyond replay.** Out of scope for v1, but design `PokerHand` and `PokerAction` to remain queryable for a future history page.
7. **Mobile layout for 8-seat table.** Skipped in plan. Existing blackjack layout is mobile-tolerant; the 8-seat poker table is meaningfully tighter. Defer to a follow-up polish PR.
8. **Anthropic model for Chipy in poker context.** Default to whatever blackjack uses (`CHIPY_MODEL` env var, currently `claude-sonnet-4-6`). Confirm — `claude-sonnet-4-7` may be preferable for the longer reasoning required by Reads mode.
9. **Animation timing for `action_log` replay between polls.** Default: 600ms per entry, configurable via a Zustand action. The "polling hook is source of truth" rule keeps this safe — if a poll comes in with a later state, the in-flight animation jumps to the new state.

---

*End of plan.*
