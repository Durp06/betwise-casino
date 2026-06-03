# BetWise Study — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. The repo workflow is plan → tests (failing) → implement → oracle review → verify. Steps use checkbox (`- [ ]`) syntax for tracking. Do not expand scope; if the plan is wrong, stop and say so.

---

## Goal

Bring Chess.com's **Game Review / analysis** experience to BetWise blackjack. Today the codebase has a heuristic `EV_LOSS_TABLE` that approximates per-decision EV loss, a 5-bucket move classifier, a session-review endpoint/modal, and a hand-replay flow. **BetWise Study** replaces the heuristic with a *rigorous expected-value engine*, upgrades the classifier to grade by real EV delta, adds a "Sharp" tier for counterintuitive optimal plays, enriches the review payload with per-action EV breakdowns + what-if lines, adds a stateless "retry this spot" drill endpoint + UI, and ships a browsable hand-history page backed by a real `created_at` ordering.

The user chose **"Analysis-deep"** scope: lean hard into review/analysis depth; in-play flow changes are deliberately light (one CTA + two tooltips).

## CRITICAL merge-safety constraint

A separate open PR (**#6**, branch `feat/texas-holdem`) adds poker + multiplayer and **rewrites several shared frontend files**. To minimize merge conflicts:

- Edits to `frontend/src/api/client.ts`, `frontend/src/types/index.ts`, `frontend/src/i18n.ts`, and `frontend/src/store/gameStore.ts` MUST be **small and append-only** — add new exports/fields at the end of the relevant section, never reorder or rewrite existing code.
- Do **NOT** touch any poker files or `backend/game/poker/` (they don't exist on `main` and must not be created here).
- Everything in this plan is **blackjack-only, on `main`, purely additive**. No router refactor through `GAME_REGISTRY` (that's deferred until a second game lands per `CLAUDE.md`).

## Conventions (from `CLAUDE.md`, repeated for the implementer)

- All API routes prefixed `/api`. Cards are `{suit, value}`. Money is **integer fake-cents** ($10.00 = 1000).
- **Async SQLAlchemy everywhere**; game logic is **pure sync** — never `await` inside `ev.py`/`review.py`/`strategy.py`/`engine.py`, never do sync DB calls.
- Pydantic v2 with `model_config = ConfigDict(from_attributes=True)`. Literal types match DB CHECK constraints.
- **Never `datetime.utcnow()`** — always `datetime.now(timezone.utc)` (use the existing `_now` helper in `models.py`).
- **Per-router SQL `_helpers`** — no inline SQL in route handlers; handlers stay thin.
- `from __future__ import annotations` at the top of every new Python file; type hints + return types on every function. Line length 120, `ruff check backend` green. No `print()` — use `logging.getLogger(__name__)`. Route handlers raise `HTTPException`.
- Frontend: **no `any`** (use `unknown` + narrow). Tailwind only (inline styles only for dynamic numeric values like `style={{ width: \`${pct}%\` }}`). Every fetch shows **loading + error** branches. All user-facing strings through `t()` from `frontend/src/i18n.ts`. Components PascalCase, hooks `use*`.
- Tests: backend pytest-asyncio + in-memory SQLite using `seed_user/seed_table/seed_session/seed_hand/seed_actions` from `backend/tests/conftest.py`. Frontend Vitest + jsdom + MSW (`setupServer` pattern in `frontend/tests/ChipyPanel.test.tsx` / `SessionReviewModal.test.tsx`). Don't mock the DB; don't mock React Query/Zustand.

---

## Architecture

### The EV engine (new centerpiece)

A new pure-sync module `backend/game/blackjack/ev.py` models blackjack EV under an **infinite-deck, dealer-hits-soft-17 (H17)** assumption. Infinite-deck is chosen (over a finite 6-deck composition-dependent model) because:

- It is **pure, deterministic, and dependency-free** — every draw is rank `r` with probability `1/13` for A and 2..9, and `4/13` for ten-valued (10/J/Q/K). No deck state, no `deck_state` plumbing, trivially unit-testable.
- It is **fast** — recursion depth is bounded by total ≤ 21, and the dealer distribution is memoizable per upcard.
- It is **accurate enough to pin orderings and decisions**, which is all the classifier and drill need. It will not exactly match published 6-deck composition-dependent charts, so tests pin *orderings and the argmax decision* with tolerances, not exact published EV cents.

The engine exposes EV in **units of the initial bet** (win = +1, push = 0, loss = −1; blackjack and double scale accordingly).

The classifier (`review.py`) is rewired to grade by `ev_best - ev_played` computed from `ev.py`, replacing the heuristic table lookup while preserving the public `(classification, ev_loss_chips)` contract. A new `"sharp"` tier is added for counterintuitive optimal plays via a deterministic curated pattern set.

### Data flow

```
ev.py (pure)  ──►  review.classify_action (pure)  ──►  sessions._get_session_review (async, per-action enrichment)
   │                       ▲                                      │
   │                       │                                      ▼
   ├──► practice router (pure grading, stateless)          SessionReviewOut → SessionReviewModal (eval bars + what-if + Sharp chip)
   │                                                              │
strategy.optimal_action (existing)  ── cross-checked against ev.action_evs argmax (test only)
odds.dealer_bust_pct (existing)  ──► what-if line ("dealer's 6 busts ~42%")
```

### Schema

`Hand.created_at` is added (models + a clean `003_study.sql` migration) so `/users/{id}/hands` can order newest-first instead of by random `session_id` UUID. The same migration adds `User.total_decisions` so accuracy becomes the honest per-decision ratio `correct_decisions / total_decisions` (never >100%) rather than the current `correct_decisions / total_hands`. The existing 001-vs-models drift (e.g. `username` length check) is **explicitly out of scope** — `003_study.sql` is a clean additive migration only.

---

## File structure

### Files to create (backend)

- `backend/game/blackjack/ev.py` — pure-sync EV engine (Pillar 1).
- `backend/routers/practice.py` — stateless `POST /api/practice/grade` endpoint (Pillar 4).
- `backend/migrations/003_study.sql` — idempotent migration adding `hands.created_at` + `users.total_decisions` (Pillars 5 & 0).
- `backend/tests/test_ev_engine.py` — exhaustive EV unit tests + strategy cross-check (Pillar 1).
- `backend/tests/test_strategy_soft18.py` — soft-18 grader regression (Pillar 0).
- `backend/tests/test_game_accuracy_counters.py` — `total_hands`/`correct_decisions` increment tests (Pillar 0).
- `backend/tests/test_review_ev_classifier.py` — classifier-by-EV + Sharp tier tests (Pillar 2).
- `backend/tests/test_practice_grade.py` — practice endpoint validation + correctness (Pillar 4).
- `backend/tests/test_hand_history_order.py` — newest-first ordering test (Pillar 5).

### Files to create (frontend)

- `frontend/src/pages/HandHistory.tsx` — browsable hand-history route (Pillar 6).
- `frontend/src/components/EvalBar.tsx` — per-action horizontal EV readout, best highlighted in gold (Pillar 6).
- `frontend/src/components/RetrySpot.tsx` — "retry this spot" drill control (Pillar 6).
- `frontend/tests/EvalBar.test.tsx` — EvalBar render test.
- `frontend/tests/RetrySpot.test.tsx` — retry-spot MSW-mocked test.
- `frontend/tests/HandHistory.test.tsx` — hand-history page MSW-mocked test (loading/error/list).

### Files to modify (backend)

- `backend/game/blackjack/strategy.py` — fix the soft-18 `can_double=False` downgrade (Pillar 0).
- `backend/game/blackjack/review.py` — rewire `classify_action` to EV-delta grading + Sharp tier; widen `Classification` (Pillar 2).
- `backend/routers/game.py::_take_action` — increment `total_hands`/`correct_decisions` in the locked transaction (Pillar 0).
- `backend/routers/sessions.py::_get_session_review` — enrich each `ReviewActionOut` + add aggregates (Pillar 3).
- `backend/routers/users.py::_get_user_hands` — order by `Hand.created_at desc` (Pillar 5).
- `backend/models.py` — add `Hand.created_at` (Pillar 5) and `User.total_decisions` (Pillar 0).
- `backend/schemas.py` — widen `Classification`; extend `ReviewActionOut`; add `PracticeGradeIn`/`PracticeGradeOut`; extend `SessionReviewOut` aggregates; expose `total_decisions` + per-decision `accuracy` in the user-stats schemas (Pillars 0/2/3/4).
- `backend/routers/users.py`, `backend/routers/leaderboard.py`, `backend/routers/advice.py` — switch the accuracy readers to `correct_decisions / total_decisions` (Pillar 0).
- `backend/main.py` — register `practice.router` (Pillar 4).

### Files to modify (frontend — APPEND-ONLY where shared)

- `frontend/src/types/index.ts` — **append**: widen `Classification` with `"sharp"`; extend `ReviewAction`/`SessionReview` with new optional fields; add `ActionEv`, `PracticeGrade`, `PracticeGradeRequest` types (Pillar 6). Append-only.
- `frontend/src/api/client.ts` — **append**: `gradePractice(...)` function (Pillar 4/6). Append-only.
- `frontend/src/components/SessionReviewModal.tsx` — add eval bars, what-if line, Sharp chip color, Retry control (Pillar 6). This is **not** a shared/poker file — full edits OK.
- `frontend/src/pages/Table.tsx` — add a prominent "Review this hand" CTA + tooltips (Pillar 6). Keep edits minimal; Table.tsx IS touched by PR #6, so keep the diff small and localized.
- `frontend/src/App.tsx` — **append** a `/history` route (Pillar 6). Append-only (one `<Route>` + one import).

### Files explicitly NOT touched

- Anything under `backend/game/poker/` (does not exist on `main`).
- `frontend/src/store/gameStore.ts` — no store changes are required by this plan (the review modal and history page own their own local React state). If the implementer finds a genuine need, it must be a single append-only field and flagged to the user first.
- `backend/migrations/001_initial.sql` — left as-is (drift is out of scope).

---

## Decisions made (and why)

1. **Infinite-deck H17 EV model.** Pure, deterministic, fast, dependency-free. Tolerances pin orderings/decisions, not published 6-deck cents. (See Architecture.)
2. **Split EV is OMITTED in v1.** Split is currently HTTP 501 (`game.py` rejects it), `ActionBar` hides it server-validates it away, and modeling split EV correctly requires post-split rules (DAS, resplit, split-aces-one-card) that the engine doesn't model. `action_evs` returns EV only for legal **non-split** actions; when `can_split=True` we still grade the *played* action against the best non-split action. `review.py` keeps its existing pair-bucket handling for split-optimal spots (Aces/8s) via the curated Sharp set and a documented fallback (see Pillar 2). This is noted as a follow-up in Out of Scope.
3. **Per-decision accuracy via a NEW `User.total_decisions` column.** Inside `_take_action`: `total_decisions` increments **once per recorded decision**; `correct_decisions` increments **once per correct decision** (every action where `was_correct`); `total_hands` increments **once per resolved hand** (terminal status `bust`/`blackjack`/`standing`/`finished`) and remains a separate "hands played" stat. **`accuracy = correct_decisions / total_decisions`** (zero-guarded → 0.0), applied at every reader. Rationale: this is the honest, Chess.com-style per-move accuracy and can never exceed 100% (the previous `correct_decisions / total_hands` could exceed 100% for multi-decision hands). It is a strict improvement with no regression risk because accuracy was permanently 0% before (no counter ever incremented), so there is no prior behavior to preserve. Documented inline. (See Pillar 0 / AC-R-ACC*.)
4. **EV-delta bucket thresholds** (delta = `ev_best - ev_played`, in bet units, always ≥ 0):
   - `delta <= 0.005` → `"best"` (effectively the optimal action, or a tie within noise)
   - `0.005 < delta <= 0.02` → `"good"`
   - `0.02 < delta <= 0.05` → `"inaccuracy"`
   - `0.05 < delta <= 0.12` → `"mistake"`
   - `delta > 0.12` → `"blunder"`
   These thresholds are chosen to keep the existing anchor tests green (hit hard 20 → blunder; stand hard 8 → blunder; double hard 17 → blunder; hit hard 12 vs 4 → inaccuracy; stand hard 16 vs 10 → inaccuracy). The tester must verify each anchor lands in the right bucket under real EV; if a published-EV anchor lands one bucket off, adjust the boundary (not the anchor) and document it. `ev_loss_chips = round(bet * delta)` preserves the existing contract.
5. **Sharp tier definition** is a deterministic curated pattern set keyed by `(hand_category, dealer_category, optimal_action)` — see Pillar 2 / AC-B-EV5 for the exact list. A play is `"sharp"` iff: the player chose the optimal action AND `(hand_category, dealer_category, optimal_action)` is in the curated counterintuitive set. A plain/forced obvious optimal play (e.g. stand hard 20, hit hard 5) is `"best"`, never `"sharp"`. Sharp is a strict refinement of "best" (the player was correct).
6. **`Classification` literal is widened to add `"sharp"`** in both `backend/schemas.py`, `backend/game/blackjack/review.py`, and `frontend/src/types/index.ts`. This is an additive widening of a shared TS type — append `"sharp"` to the union, add a chip-color entry; do not reorder.
7. **Legacy `EV_LOSS_TABLE` is removed** from `review.py` (replaced wholesale by EV math). It is dead once `classify_action` no longer reads it; keeping it would invite drift between two sources of truth. The `_categorize_hand`/`_categorize_dealer` helpers are **kept** (the Sharp curated set and the existing weakness analytics use those category strings).
8. **Hand-history UI is a route (`/history`)**, not a Profile rewrite, to avoid heavy edits to `Profile.tsx` and keep the diff append-only on `App.tsx`.

---

## Acceptance Criteria

Each AC is concrete and testable; the tester writes one failing test per AC before implementation.

### Pillar 0 — Correctness (Bronze fix + real accuracy)

- **AC-B-STRAT1**: `strategy.optimal_action([A,7], dealer, can_double=False)` returns `"stand"` for dealer upcards 2,3,4,5,6 (soft 18, no-double fallback is stand, not hit).
- **AC-B-STRAT2**: `strategy.optimal_action([A,7], dealer 9/10/A, can_double=False)` returns `"hit"` (soft 18 vs strong upcards still hits).
- **AC-B-STRAT3**: `strategy.optimal_action([A,7], dealer 7/8, can_double=True or False)` returns `"stand"` (table already stands; unaffected by the fix).
- **AC-B-STRAT4**: Soft 17 (`[A,6]`) is unaffected — `can_double=False` vs 3..6 downgrades to `"hit"` (correct: soft 17 has no stand fallback).
- **AC-B-STRAT5**: Soft 19+ (`[A,8]`, `[A,9]`) with `can_double=False` returns `"stand"` (already true; regression guard).
- **AC-R-ACC1**: After a `POST /api/tables/{id}/action` that ends a hand (stand/bust/blackjack/double), the acting user's `total_hands` increases by exactly 1 and `total_decisions` increases by at least 1; `GET /api/users/me` reflects the new totals.
- **AC-R-ACC2**: A non-terminal `hit` (hand stays `active`) does **not** increment `total_hands`, but **does** increment `total_decisions` by 1.
- **AC-R-ACC3**: Each action whose server-computed `was_correct` is true increments `correct_decisions` by 1 and `total_decisions` by 1; a wrong action increments only `total_decisions`.
- **AC-R-ACC4**: After a sequence of actions, `GET /api/users/me`'s `accuracy` and `GET /api/leaderboard`'s `accuracy_pct` both equal `correct_decisions / total_decisions` (zero-guarded). A user with 3 correct of 4 decisions reads 75% and never exceeds 100%.
- **AC-R-ACC5**: The per-decision denominator (`correct_decisions / total_decisions`) is applied consistently across **all** accuracy readers: `GET /users/me` (and the other user endpoints), `leaderboard.py` `accuracy_pct`, `advice.py` `player_accuracy`, and the `SessionReviewOut` summary if it derives from user stats. `total_decisions` is exposed in the user-stats schemas alongside the existing `total_hands`/`correct_decisions`.

### Pillar 1 — EV engine (`backend/game/blackjack/ev.py`)

- **AC-B-EV1**: `ev.py` is pure-sync — no `import sqlalchemy`, no `async def`, no `import random`, no network. (Test asserts module has no `async` callables and importing it does no IO.)
- **AC-B-EV2**: `dealer_outcome_distribution(upcard)` returns a dict over keys `{17,18,19,20,21,"bust"}` whose values sum to `1.0` (within `1e-9`) for every upcard 2..A. Dealer hits hard ≤16 and soft 17; stands hard 17+/soft 18+.
- **AC-B-EV3**: `ev_stand(player_total, is_soft, upcard)` returns a float in `[-1, 1]`. Pinned orderings: `ev_stand(20, False, X)` strongly positive (> 0.4) for every upcard; `ev_stand(16, False, ten)` strongly negative (< −0.4).
- **AC-B-EV4**: `action_evs(hand_cards, upcard, can_double, can_split)` returns a dict containing exactly the legal non-split actions: always `hit` and `stand`; `double` only when `len(cards) == 2`; never a `split` key (split EV omitted in v1). A companion `best_action_ev(...)` (or equivalent) returns `(action, ev)` for the argmax over the returned dict.
- **AC-B-EV5 (Sharp set anchors)**: The following decisions are correctly *ordered* by `action_evs` (the named action is the argmax), pinning that the engine agrees with basic strategy on the counterintuitive spots that define the Sharp tier:
  - hard 16 (`[10,6]`) vs 10 → `hit` > `stand`
  - hard 12 (`[7,5]`) vs 4/5/6 → `stand` > `hit`
  - hard 11 (`[6,5]`) vs any upcard 2..A → `double` is the argmax
  - soft 18 (`[A,7]`) vs 6 → `double` is the argmax; vs 9/10/A → `hit` > `stand`
  - hard 10 (`[6,4]`) vs 9 → `double` is the argmax
- **AC-B-EV6 (strategy cross-check)**: For a broad sweep of `(hand, upcard)` over all hard totals 5..20, soft totals 13..20, and upcards 2..A, the argmax of `action_evs(...)` agrees with `strategy.optimal_action(...)` **for non-split, non-double-restricted decisions** within the model's known divergences. The test enumerates the sweep and asserts agreement, listing any documented exceptions explicitly (e.g. a handful of marginal cells where infinite-deck flips a published 6-deck call — these are enumerated in the test as an allow-list with a comment, and the allow-list must be small, < 5 cells).
- **AC-B-EV7**: `ev_double(hand_cards, upcard)` returns `2 ×` the expected `ev_stand` over one drawn rank, with bust → `-2`. `ev_double([5,6], X)` (hard 11) > `ev_hit([5,6], X)` and > `ev_stand(11, False, X)` for every upcard.
- **AC-B-EV8**: `ev_hit(hand_cards, upcard)` expects over the next drawn rank: bust → `-1`, else `max(ev_stand(...), ev_hit(...))` with recursion bounded by total ≤ 21. `ev_hit` of a hard 5 is > `ev_stand(5,...)` for every upcard (you never stand on 5).
- **AC-B-EV9**: Determinism — `action_evs` called twice with identical args returns identical dicts (pure function, memoization must not leak per-call state).

### Pillar 2 — Classifier upgrade + Sharp tier (`review.py`)

- **AC-B-CLS1**: `classify_action(hand, upcard, player_action, optimal_action, bet)` still returns `(classification, ev_loss_chips)`; when `player_action == optimal_action` and the spot is NOT in the Sharp set, returns `("best", 0)`.
- **AC-B-CLS2**: When `player_action == optimal_action` AND the spot is in the curated Sharp set, returns `("sharp", 0)`.
- **AC-B-CLS3 (EV-delta buckets)**: For wrong actions, classification follows the thresholds in Decision #4 using `delta = ev_best - ev_played` from `ev.py`. `ev_loss_chips = round(bet * delta)`.
- **AC-B-CLS4 (anchors preserved)**: hit on hard 20 → `blunder`; stand on hard 8 → `blunder`; double on hard 17 → `blunder`; hit hard 12 vs 4 → `inaccuracy`; stand hard 16 vs 10 → `inaccuracy`; hit on hard 11 vs ace (optimal=double) → `inaccuracy`. (These map 1:1 to the existing `test_session_review.py` assertions, which must still pass.)
- **AC-B-CLS5 (split fallback)**: For split-optimal pairs where split EV is not modeled (A,A and 8,8), missing the split (e.g. stand) still classifies as `blunder` (preserving `test_split_aces_still_uses_pair_bucket` / `test_split_88_still_uses_pair_bucket`). `4,4 vs 2` with optimal=hit and player stand still classifies as `blunder` (preserving `test_stand_on_44_vs_2_is_blunder_treated_as_hard_8`).
- **AC-B-CLS6 (Sharp curated set)**: The Sharp set is exactly: stand hard 12 vs {4,5,6}; hit hard 16 vs {10,A}; double soft 13–18 vs weak (the soft-double cells); hit soft 18 vs {9,10,A}; split 8s vs {9,10,A}; split aces (any upcard). A plain obvious optimal play (stand hard 20, hit hard 5, stand hard 19) returns `"best"`, never `"sharp"`.
- **AC-B-CLS7**: `classify_action` is pure & deterministic — same inputs → same outputs; no DB/network.
- **AC-B-CLS8**: Per-action bet pricing regression preserved — a pre-double wrong stand is priced at the initial bet, not the doubled stake (preserves `test_review_uses_per_action_bet_when_hand_doubled`).

### Pillar 3 — Review enrichment (schema + router)

- **AC-S-REV1**: `ReviewActionOut` gains additive optional fields: `action_evs: dict[str, float]` (per legal non-split action), `best_action: str`, `best_ev: float`, `ev_delta: float`, `dealer_bust_pct: float`. Existing fields unchanged; `model_config = ConfigDict(from_attributes=True)`.
- **AC-S-REV2**: `SessionReviewOut` gains additive aggregate fields: `sharp_count: int`, `blunder_count: int`. Existing fields (`accuracy`, `ev_lost_chips`, `worst_action_id`, ...) unchanged.
- **AC-R-REV1**: `GET /api/sessions/{id}/review` populates `action_evs`, `best_action`, `best_ev`, `ev_delta`, and `dealer_bust_pct` (from `odds.dealer_bust_pct`) for each action, and the new aggregates, computed via `ev.py` + `review.classify_action` + `odds.py`. SQL stays in `_get_session_review`/helpers.
- **AC-R-REV2**: For a session containing one Sharp decision and one blunder, `sharp_count == 1` and `blunder_count == 1`.
- **AC-R-REV3**: Existing review behavior (accuracy, owner/finished access rules, worst_action ordering, empty-actions → zero accuracy) is unchanged — all current `test_session_review.py` endpoint tests pass.

### Pillar 4 — Practice grading endpoint (`backend/routers/practice.py`)

- **AC-S-PR1**: `PracticeGradeIn` validates `{hand: list[CardOut], dealer_upcard: CardOut, action: Action}`. `PracticeGradeOut` returns `{optimal_action, action_evs, best_ev, ev_delta, classification, dealer_bust_pct, explanation}`.
- **AC-R-PR1**: `POST /api/practice/grade` requires auth (`CurrentUser`); returns 200 with a correct grade for a valid body. Registered under `/api` in `main.py`. Stateless — does not create/read sessions, hands, or player_actions.
- **AC-R-PR2**: Grading correctness — `{hand:[10,6], dealer_upcard:10, action:"stand"}` → `optimal_action == "hit"`, `classification == "inaccuracy"` (matches the session-review anchor), `dealer_bust_pct == 0.23`.
- **AC-R-PR3 (Sharp via practice)**: `{hand:[10,6], dealer_upcard:10, action:"hit"}` → `optimal_action == "hit"`, `classification == "sharp"`.
- **AC-R-PR4 (validation)**: A malformed body (missing `dealer_upcard`, bad card value, illegal `action` literal) returns `422`. A body with `hand: []` (empty) returns `400` (handler-level guard) — not a 500.
- **AC-R-PR5**: `explanation` is a non-empty human-readable string (reuses `strategy.explain_decision` or equivalent).

### Pillar 5 — Hand history ordering (model + migration + router)

- **AC-M-HIST1**: `Hand.created_at: Mapped[datetime]` is `DateTime(timezone=True)`, `nullable=False`, `default=_now` in `models.py`. (Test: `Hand.__table__.columns["created_at"]` exists and is timezone-aware.)
- **AC-M-HIST2**: `backend/migrations/003_study.sql` is idempotent (`ADD COLUMN IF NOT EXISTS`), adds `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()` to `hands`, adds `CREATE INDEX IF NOT EXISTS idx_hands_user_created ON hands(user_id, created_at DESC)`, and adds `users.total_decisions INTEGER NOT NULL DEFAULT 0`.
- **AC-M-HIST3**: `User.total_decisions` exists (`Integer`, `nullable=False`, `default=0`, `CHECK (total_decisions >= 0)`) in `models.py`; existing rows default to 0. (Test: `User.__table__.columns["total_decisions"]` exists with default 0.)
- **AC-R-HIST1**: `_get_user_hands` orders by `Hand.created_at DESC` with `Hand.id` as a stable tiebreaker; `GET /api/users/{id}/hands` returns the user's hands newest-first. (Test seeds three hands with distinct `created_at` and asserts the returned order.)
- **AC-R-HIST2**: `_deal_hand` in `game.py` sets `created_at=datetime.now(timezone.utc)` on new `Hand` rows (so live-dealt hands order correctly). Existing deal tests still pass.

### Pillar 6 — Frontend (Analysis-deep)

- **AC-F-TYPE1**: `frontend/src/types/index.ts` — `Classification` union includes `"sharp"`; `ReviewAction` has the new optional fields (`action_evs?`, `best_action?`, `best_ev?`, `ev_delta?`, `dealer_bust_pct?`); `SessionReview` has optional `sharp_count?`/`blunder_count?`; new `ActionEv`, `PracticeGrade`, `PracticeGradeRequest` types exist. `npx tsc --noEmit` clean, no `any`.
- **AC-F-EVAL1**: `EvalBar.tsx` renders one row per entry in `action_evs`, the best action highlighted with a gold class, EV shown as a number; width is a dynamic numeric inline style only. Renders nothing/gracefully when `action_evs` is undefined.
- **AC-F-REV1**: `SessionReviewModal` renders an `EvalBar` per decision when `action_evs` is present, a what-if line for non-best decisions ("You {action}. Best was {best_action} — dealer's {upcard} busts ~{pct}%."), and a gold `"sharp"` chip color in `CLASSIFICATION_CLASS`. Loading/error states preserved; all strings via `t()`; no `any`.
- **AC-F-REV2**: For a `"sharp"` action the modal shows the Sharp chip; for a `"best"` action it shows the existing Best chip — they are visually distinct (different Tailwind classes).
- **AC-F-RETRY1**: `RetrySpot.tsx` takes a `hand`, `dealer_upcard`, re-presents the spot with action buttons, calls `gradePractice(...)` on selection, and renders the returned eval + verdict. Shows loading while the request is in flight and an error branch on failure. MSW-mocked.
- **AC-F-RETRY2**: SessionReviewModal shows a "Retry this spot" control for any decision that is not `best`/`sharp`; clicking it mounts `RetrySpot` for that decision's `(hand_snapshot, dealer_upcard)`.
- **AC-F-CLIENT1**: `client.ts` exports `gradePractice(req: PracticeGradeRequest): Promise<ApiResult<PracticeGrade>>` POSTing to `/api/practice/grade`. Append-only addition.
- **AC-F-HIST1**: `HandHistory.tsx` fetches `getUserHands(currentUserId)`, shows a loading state (`role="status"`/`aria-busy`), an error state (`role="alert"`), and a list of hands (outcome, accuracy/bet, date) newest-first; clicking a hand opens the session review (`SessionReviewModal` for that hand's session). Empty state handled.
- **AC-F-HIST2**: `/history` route is wired in `App.tsx` behind `AuthGate` (append-only: one import + one `<Route>`).
- **AC-F-TABLE1**: `Table.tsx` post-hand area shows a prominent "Review this hand" CTA (it may reuse the existing "Review session" button styling/wiring) and plain-language tooltips (`title` attribute via `t()`) on the Accuracy / EV-Lost labels surfaced in the review. Edits localized; existing post-hand buttons and flow unchanged.

### Tests (cross-cutting)

- **AC-T-CI1**: `ruff check backend` green.
- **AC-T-CI2**: `python -m pytest backend/tests/ -v` green (existing 118+ tests **plus** every new test). No existing test is deleted; any existing test that changes behavior (e.g. if an EV bucket shifts a non-anchor case) is updated by the tester with a comment explaining why.
- **AC-T-CI3**: `cd frontend && npx tsc --noEmit` clean.
- **AC-T-CI4**: `cd frontend && npm test -- --run` green.
- **AC-T-CI5**: `cd frontend && npm run build` succeeds.

---

## Plan (task-by-task, dependency order)

> Order: EV engine + tests first (everything depends on it), then the small correctness fixes, then classifier, then schema/migration, then routers/schemas, then frontend. Each task is ~one commit. Run the relevant tests after each task; run the full suite at the milestones noted.

### Task 1 — Soft-18 grader fix (Pillar 0, independent quick win)

**Files:** modify `backend/game/blackjack/strategy.py`; create `backend/tests/test_strategy_soft18.py`.

- [ ] Write failing tests for AC-B-STRAT1..5 in `test_strategy_soft18.py` (parametrize dealer upcards; build `[A,7]`, `[A,6]`, `[A,8]`, `[A,9]` hands).
- [ ] Run them; confirm AC-B-STRAT1 fails (`[A,7]` vs 2..6, `can_double=False` currently returns `"hit"`).
- [ ] Fix the downgrade block (lines ~178–186): when `action == "double" and not can_double`, if `soft and total >= 18` return `"stand"`, else return `"hit"`. Update the misleading comment.
- [ ] Run `pytest backend/tests/test_strategy_soft18.py -v` → green. Run full backend suite to confirm no strategy regression. Commit `fix(strategy): soft-18 no-double fallback is stand`.

### Task 2 — EV engine (Pillar 1, the centerpiece)

**Files:** create `backend/game/blackjack/ev.py`; create `backend/tests/test_ev_engine.py`.

- [ ] Write the failing tests for AC-B-EV1..EV9 in `test_ev_engine.py`, including the strategy cross-check sweep (AC-B-EV6) with a small documented allow-list.
- [ ] Run them; confirm `ImportError` for `backend.game.blackjack.ev`.
- [ ] Implement `ev.py` (pure, `from __future__ import annotations`, full type hints):
  - `RANK_PROBS` mapping (A and 2..9 → 1/13, ten-valued → 4/13). Decide representation (use numeric ranks 2..11 with prob, treating 10 with 4/13).
  - `dealer_outcome_distribution(upcard_rank) -> dict[int|str, float]` — recursion over the H17 rule, memoized per upcard (module-level cache keyed by an immutable dealer-state tuple, never per-call mutable state — AC-B-EV9).
  - `ev_stand(player_total, is_soft, upcard) -> float`.
  - `ev_hit(hand_cards, upcard) -> float` (recursion bounded by total ≤ 21).
  - `ev_double(hand_cards, upcard) -> float`.
  - `action_evs(hand_cards, upcard, can_double, can_split) -> dict[str, float]` (legal non-split actions only; split omitted).
  - `best_action_ev(hand_cards, upcard, can_double, can_split) -> tuple[str, float]`.
  - Accept card dicts (`{suit,value}`) and reuse `engine.card_rank`/`hand_value`/`is_soft` for hand math; `upcard` is a card dict, convert via `card_rank`.
- [ ] Run `pytest backend/tests/test_ev_engine.py -v` → green. Commit `feat(ev): infinite-deck H17 expected-value engine`.

**Milestone:** EV engine green and cross-checked against `strategy.optimal_action`.

### Task 3 — Real accuracy counters (Pillar 0)

**Files:** modify `backend/routers/game.py::_take_action`; create `backend/tests/test_game_accuracy_counters.py`.

- [ ] Write failing tests for AC-R-ACC1..5 (seed user+table+session+hand via fixtures, POST actions, assert counters via `/api/users/me` and `/api/leaderboard`; assert accuracy = correct/total_decisions and never >100%).
- [ ] Run them; confirm they fail (counters never move today).
- [ ] In `_take_action`, inside the existing locked transaction: increment `User.total_decisions` by 1 on every recorded decision; increment `User.correct_decisions` by 1 when `was_correct`; increment `User.total_hands` by 1 once when the hand reaches a terminal status (not on a still-`active` hit). Reuse the row-locked `User` fetch where it already exists for `double`; otherwise add a `with_for_update()` user fetch. Document the increment timing in a comment matching Decision #3.
- [ ] Switch every accuracy READER to `correct_decisions / total_decisions` (zero-guarded): `users.py` (GET /users/me + the other user endpoints), `leaderboard.py` `accuracy_pct`, `advice.py` `player_accuracy`, and the review summary if it derives from user stats. Expose `total_decisions` in the user-stats schemas.
- [ ] Run the new tests + full backend suite → green (existing leaderboard/users tests may need the denominator updated — do so with a comment). Commit `feat(game): per-decision accuracy via total_decisions counter`.

### Task 4 — Classifier upgrade + Sharp tier (Pillar 2)

**Files:** modify `backend/game/blackjack/review.py`; modify `backend/schemas.py` (widen `Classification`); create `backend/tests/test_review_ev_classifier.py`.

- [ ] Write failing tests for AC-B-CLS1..8 plus the Sharp curated set (AC-B-CLS6). Keep the existing `test_session_review.py` classify_action assertions as the anchor set (do not modify them).
- [ ] Widen `Classification = Literal["best","good","inaccuracy","mistake","blunder","sharp"]` in both `review.py` and `schemas.py`.
- [ ] Rewire `classify_action`: compute `ev_played` and `ev_best` from `ev.py` (`action_evs` + `best_action_ev`); `delta = max(0.0, ev_best - ev_played)`; bucket per Decision #4; `ev_loss_chips = round(bet * delta)`. Add the Sharp check (curated set keyed off `_categorize_hand`/`_categorize_dealer` + `optimal_action`). Handle the split fallback (AC-B-CLS5) — when the optimal action is `"split"` (not in `action_evs`), keep the deterministic blunder grading for missed always-split pairs.
- [ ] Remove `EV_LOSS_TABLE`; keep `_categorize_hand`/`_categorize_dealer`/`_bucket` (repurpose `_bucket` for the EV-delta thresholds, or replace with a new `_bucket_delta`).
- [ ] Run new tests + `test_session_review.py` (classify_action unit tests) → green. Commit `feat(review): grade by real EV delta + add Sharp tier`.

**Milestone:** classifier green; existing review unit tests preserved.

### Task 5 — Schema: `Hand.created_at` + `User.total_decisions` + migration (Pillars 5 & 0)

**Files:** modify `backend/models.py`, `backend/routers/game.py::_deal_hand`, `backend/routers/users.py::_get_user_hands`; create `backend/migrations/003_study.sql`, `backend/tests/test_hand_history_order.py`.

> Note: `User.total_decisions` is added here (the schema task) but is *consumed* by Task 3. If Task 3 runs first, add the column to `models.py` as part of Task 3 and keep the migration creation here — either way both columns ship in the single `003_study.sql`.

- [ ] Write failing tests for AC-M-HIST1, AC-M-HIST3 (User.total_decisions column exists, default 0, CHECK >= 0), AC-R-HIST1 (seed three hands with explicit distinct `created_at`, assert newest-first), AC-R-HIST2.
- [ ] Add `created_at` to the `Hand` model (`DateTime(timezone=True)`, `default=_now`) and `total_decisions` to the `User` model (`Integer`, `nullable=False`, `default=0`, with a `CheckConstraint("total_decisions >= 0")`).
- [ ] Update `seed_hand` in `backend/tests/conftest.py` to accept an optional `created_at` kwarg (defaulting to `datetime.now(timezone.utc)`) so ordering tests can seed distinct timestamps. (This is a test fixture, not production — additive.)
- [ ] Set `created_at` explicitly in `_deal_hand`'s `Hand(...)` construction.
- [ ] Change `_get_user_hands` ordering from `desc(Hand.session_id)` to `Hand.created_at.desc(), Hand.id.desc()`.
- [ ] Write `003_study.sql` — idempotent (`ADD COLUMN IF NOT EXISTS`) adding `hands.created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`, the `idx_hands_user_created` index, AND `users.total_decisions INTEGER NOT NULL DEFAULT 0` (with its `>= 0` check).
- [ ] Run new tests + full backend suite → green. Commit `feat(schema): Hand.created_at + User.total_decisions + 003 migration`.

### Task 6 — Review enrichment (Pillar 3)

**Files:** modify `backend/schemas.py` (extend `ReviewActionOut`/`SessionReviewOut`), `backend/routers/sessions.py::_get_session_review`; extend `backend/tests/test_session_review.py` (or a new `test_review_enrichment.py`).

- [ ] Write failing tests for AC-S-REV1/2, AC-R-REV1/2/3.
- [ ] Extend the schemas additively (optional fields with defaults so existing serialization stays valid).
- [ ] In `_get_session_review`, for each action compute `action_evs`/`best_action`/`best_ev`/`ev_delta` via `ev.py` and `dealer_bust_pct` via `odds.py`; tally `sharp_count`/`blunder_count`. Keep SQL in helpers; the EV math is pure-sync called from the async helper (no `await` on it).
- [ ] Run tests + full backend suite → green. Commit `feat(review): per-action EV breakdown + what-if data in session review`.

### Task 7 — Practice grading endpoint (Pillar 4)

**Files:** create `backend/routers/practice.py`; modify `backend/schemas.py` (`PracticeGradeIn`/`PracticeGradeOut`), `backend/main.py` (register router); create `backend/tests/test_practice_grade.py`.

- [ ] Write failing tests for AC-S-PR1, AC-R-PR1..5.
- [ ] Add the Pydantic schemas (use the existing `CardOut`/`Action` types; `PracticeGradeIn.hand: list[CardOut]`).
- [ ] Implement `practice.py` with a thin handler + `_grade` helper (pure call into `ev.py`/`strategy.py`/`review.py`/`odds.py`). Validate empty hand → `HTTPException(400)`. `CurrentUser` dependency for auth. No DB access.
- [ ] Register `app.include_router(practice.router, prefix="/api")` in `main.py` and add `practice` to the import line (append).
- [ ] Run tests + full backend suite → green. Commit `feat(practice): POST /api/practice/grade stateless drill grader`.

**Milestone:** full backend green; `ruff check backend` clean (AC-T-CI1/CI2).

### Task 8 — Frontend types + client (Pillar 6, append-only shared files)

**Files:** modify `frontend/src/types/index.ts`, `frontend/src/api/client.ts` (both APPEND-ONLY).

- [ ] Append to `types/index.ts`: widen `Classification` with `"sharp"`; add the new optional fields to `ReviewAction`/`SessionReview`; add `ActionEv`, `PracticeGrade`, `PracticeGradeRequest`.
- [ ] Append `gradePractice(...)` to `client.ts`.
- [ ] `cd frontend && npx tsc --noEmit` → clean. Commit `feat(types): sharp tier + practice-grade types (append-only)`.

### Task 9 — EvalBar + SessionReviewModal upgrade (Pillar 6)

**Files:** create `frontend/src/components/EvalBar.tsx`, `frontend/tests/EvalBar.test.tsx`; modify `frontend/src/components/SessionReviewModal.tsx`.

- [ ] Write failing `EvalBar.test.tsx` (AC-F-EVAL1) and extend `SessionReviewModal.test.tsx` for AC-F-REV1/2 (MSW-mock `getSessionReview` returning enriched actions incl. a `"sharp"` one).
- [ ] Implement `EvalBar.tsx`.
- [ ] Add `"sharp"` to `CLASSIFICATION_CLASS` (gold class), render `EvalBar` + the what-if line in `ActionRow`. Preserve loading/error/`t()`/no-`any`.
- [ ] Run `npm test -- --run` + `tsc --noEmit` → green. Commit `feat(review-ui): eval bars + what-if line + Sharp chip`.

### Task 10 — RetrySpot drill control (Pillar 6)

**Files:** create `frontend/src/components/RetrySpot.tsx`, `frontend/tests/RetrySpot.test.tsx`; modify `frontend/src/components/SessionReviewModal.tsx`.

- [ ] Write failing `RetrySpot.test.tsx` (AC-F-RETRY1: MSW-mock `/api/practice/grade`; assert loading → eval/verdict; assert error branch).
- [ ] Implement `RetrySpot.tsx`.
- [ ] Wire the "Retry this spot" control into `SessionReviewModal` for non-best/non-sharp decisions (AC-F-RETRY2).
- [ ] Run `npm test -- --run` + `tsc --noEmit` → green. Commit `feat(drill): retry-this-spot control via /api/practice/grade`.

### Task 11 — Hand History page + route (Pillar 6)

**Files:** create `frontend/src/pages/HandHistory.tsx`, `frontend/tests/HandHistory.test.tsx`; modify `frontend/src/App.tsx` (append `/history` route).

- [ ] Write failing `HandHistory.test.tsx` (AC-F-HIST1: loading/error/list/empty; clicking opens review).
- [ ] Implement `HandHistory.tsx` (fetch `getUserHands`, three-branch render, click → `SessionReviewModal`).
- [ ] Append the `/history` route + import in `App.tsx`.
- [ ] Run `npm test -- --run` + `tsc --noEmit` → green. Commit `feat(history): browsable hand-history page at /history`.

### Task 12 — Table CTA + tooltips (Pillar 6, light touch)

**Files:** modify `frontend/src/pages/Table.tsx`.

- [ ] Add a prominent "Review this hand" CTA in the post-hand area and `title` tooltips (via `t()`) on Accuracy / EV-Lost where surfaced. Keep the diff minimal and localized (Table.tsx is touched by PR #6).
- [ ] If a Table.tsx test exists, extend it; otherwise a focused render assertion is sufficient. Run `npm test -- --run` + `tsc --noEmit` → green. Commit `feat(table): review-this-hand CTA + plain-language tooltips`.

### Task 13 — Full-suite verification (all pillars)

- [ ] `ruff check backend` → clean (AC-T-CI1).
- [ ] `python -m pytest backend/tests/ -v` → green (AC-T-CI2).
- [ ] `cd frontend && npx tsc --noEmit` → clean (AC-T-CI3).
- [ ] `cd frontend && npm test -- --run` → green (AC-T-CI4).
- [ ] `cd frontend && npm run build` → succeeds (AC-T-CI5).
- [ ] Walk the AC list; anything red is a follow-up, not a silent skip. No commit unless a check surfaced a fix.

---

## CI gates (must stay green)

- `ruff check backend`
- `python -m pytest backend/tests/ -v` (118+ existing + all new)
- `cd frontend && npx tsc --noEmit`
- `cd frontend && npm test -- --run`
- `cd frontend && npm run build`

See `.github/workflows/ci.yml`.

---

## Out of scope (deliberately deferred)

- **Split EV modeling.** `action_evs` omits split; split remains HTTP 501. Modeling split EV (DAS, resplits, split-aces-one-card) is a follow-up that should land alongside actually implementing split play (which needs the `(session_id, user_id, hand_index)` schema change noted in `CLAUDE.md`).
- **Composition-dependent / finite 6-deck EV.** The engine is infinite-deck. A finite-deck refinement is a future accuracy pass; the current model is "accurate enough to pin decisions."
- **Router dispatch through `GAME_REGISTRY`.** Deferred until a second game exists (per `CLAUDE.md`); routers stay blackjack-hardcoded.
- **Fixing the 001-vs-models migration drift.** Out of scope; `003` is a clean additive migration only.
- **Persisting Sharp/streak/drill stats to new DB columns.** The only new column is `User.total_decisions` (for honest per-decision accuracy); no Sharp-count / streak / drill columns are added — those stay derived/local.
- **Any poker / multiplayer work** (owned by PR #6).
- **Gamifying the drill** (XP, daily puzzle, leaderboards for Sharp count) — analysis depth only this slice.
- **`gameStore.ts` changes** — the review modal and history page own local React state; no Zustand additions planned.
- **Insurance / surrender / even-money** decisions — not modeled by the engine.

---

## Resolved decisions (the five former open questions — confirmed by the user 2026-05-31)

1. **EV-delta thresholds (Decision #4).** ACCEPTED as written (tuned to keep all anchor tests green under real EV).
2. **Sharp curated set (Decision #5 / AC-B-CLS6).** ACCEPTED as written (stand 12 vs 4–6, hit 16 vs 10/A, soft doubles, hit soft 18 vs 9/10/A, split 8s vs 9/10/A, split aces).
3. **Hand-history surface.** ACCEPTED: a new `/history` route (not a `Profile.tsx` rewrite), to keep the diff small and append-only.
4. **What-if line wording.** ACCEPTED as written: "You {action}. Best was {best}. Dealer's {upcard} busts ~{pct}%."
5. **Accuracy denominator (Decision #3).** CHANGED → **per-decision accuracy via a new `User.total_decisions` column**: `accuracy = correct_decisions / total_decisions` (zero-guarded), applied across all readers. `total_hands` stays as a separate "hands played" stat. This avoids the >100% bug and matches Chess.com per-move accuracy; it is a strict improvement (accuracy was 0% before). Threaded through Decision #3, AC-R-ACC1..5, AC-M-HIST3, Task 3, Task 5, and the `003_study.sql` migration.
