# Poker Review (Game Review + Hand Review) — Design

**Status:** Design / awaiting review
**Date:** 2026-06-04
**Author:** brainstormed with Claude

## Goal

Bring the chess.com-style decision review that BetWise blackjack already has
(`SessionReviewModal` + `GET /api/sessions/{id}/review`) to **poker**, in both
of its forms:

- **Solo Poker** — SNG tournament vs bots (`PokerTournament` / `PokerAction`).
- **Multiplayer Hold'em** — human-only cash ring (`HoldemTable` / `HoldemAction`).

Two review granularities, per the product decision:

- **Hand Review** — one finished hand, decision-by-decision, with a verdict and
  EV-loss on each of *your* actions.
- **Game Review** — a session-level report card (overall accuracy, EV lost, the
  worst hands). For solo this is the whole **tournament**; for multiplayer cash
  it is your current **table visit** (the hands since you sat down).

Grading is **equity-backed**: every gradeable decision gets a real win-equity
number and an EV-loss in big blinds, bucketed into the same six-tier
classification blackjack uses.

## Guiding constraint: lightweight + low test burden

The feature must be cheap to ship and safe to ship without heavy manual QA.
Concretely that means:

1. **Compute-on-read, no persistence, no migration.** Reviews are recomputed
   from already-stored data on every read — exactly how blackjack review works
   today (it writes nothing). We do **not** extend `HoldemAction` / `PokerAction`
   with new columns and we do **not** add a background equity job. The live
   `/act` path and the deal/showdown flow are **not touched**, so the highest-risk
   code (live multiplayer gameplay) has zero new surface area.
2. **One shared grading path** for solo and multiplayer (same equity engine, same
   grader, same React modal), parameterised by data source — not two parallel builds.
3. **Modest, seeded Monte-Carlo.** Exact enumeration when ≤2 board cards remain
   (cheap); a few thousand seeded sims otherwise. Seeded from the hand id so a
   review is reproducible and tests are deterministic.
4. **Focused tests**, not exhaustive (see Testing).

## The one product call: range-based equity

To compute "your equity" the engine must assume **what opponents could have
held**. We grade **range-based** (against a plausible hand range given
position/action), *not* against the actual cards opponents turned out to hold.

- **Why:** grading vs actual cards is "results-oriented" — it would mark a correct
  fold that happened to be ahead as a mistake, which teaches the wrong lesson.
- **Bonus (multiplayer privacy):** range-based grading never needs to reveal a
  folded opponent's hole cards. Revealing them in a still-live cash ring would
  leak tendencies into future hands. So review reveals **only cards that reached
  showdown** (already public) in multiplayer; folded opponents stay masked.
- **Solo** is self-contained vs bots, so it may reveal everything and may use the
  bot's actual archetype range (`backend/game/poker/archetypes.py`) for a sharper
  equity estimate. **Multiplayer** uses a positional/action-derived default range.

## Components

### 1. Equity engine — `backend/game/poker/equity.py` (new, pure-sync)

The load-bearing new piece. `live_equity` is stubbed `None` everywhere today.

```
hand_equity(hero_hole, villain_ranges, board, *, seed, max_iters=2000) -> float
```

- Returns hero's probability of winning (ties counted as fractional) at a given
  decision point.
- **Exact enumeration** when ≤2 cards are still to come (turn: 1 card; river: 0).
- **Seeded Monte-Carlo** otherwise, sampling villain holdings from their range and
  completing the board. `random.Random(seed)` — deterministic per hand.
- Leans on the existing, correct `evaluator.best_5_of_7` for showdown ranking.
- Pure, memoizable, no DB — same architectural template as
  `backend/game/blackjack/ev.py`.

Range model lives next to the engine (small): a positional default range for
multiplayer humans, and an adapter that reads bot archetype ranges for solo.
Keep it deliberately simple in v1 (a single tightness-tunable range is fine).

### 2. Grader — extend `backend/game/poker/oracle.py`

`oracle.classify_decision` already handles two DETERMINISTIC buckets (short-stack
push/fold via `nash.py`, and pot-odds-vs-all-in). With `live_equity` now
available we extend it to grade ordinary decisions:

- **Call / check / fold:** `EV(call) = equity*(pot_if_called) - cost_to_call`,
  `EV(fold) = 0` (sunk chips excluded). Best action = argmax; the existing
  `pot_odds.required_equity` is the threshold.
- **Bet / raise:** graded with a simplified semi-bluff model using equity plus a
  default fold-equity from the existing `pot_odds` bluff break-even / MDF math.
  Genuinely contextual multi-street spots that the model can't resolve return a
  **`no_verdict`** coaching note rather than a fabricated hard verdict (this is the
  honesty boundary the brief flagged — poker has no single correct move).
- **Output per action:** `verdict` (best/good/inaccuracy/mistake/blunder/no_verdict),
  `ev_loss_bb`, `recommended_action`, `equity`, `required_equity`, short explanation,
  and `confidence_tier` (DETERMINISTIC vs HEURISTIC).
- **Bucketing:** port the blackjack EV-delta bucketing shape
  (`backend/game/blackjack/review.py::_bucket_delta`) tuned to big-blind units.
  Exact thresholds are set + pinned by tests in the plan.

### 3. Review assembly (compute-on-read) — backend

A small shared helper (pure-ish, given a hand's rows) reconstructs the hand and
produces a per-hand review:

- Deserialize `deck`, deal hole cards, iterate the `*Action` log in `action_index`
  order through `state.apply_action`, rebuilding board/pot/street at each step.
- At each action **belonging to the requesting user**, call the grader.
- Aggregate into a `HandReview` (list of graded actions + per-hand accuracy,
  EV lost, worst action).
- A `GameReview` is a thin aggregation over the hands in scope (tournament for
  solo; table-visit for multiplayer).

This helper is shared; only the *row-loading* differs by game.

### 4. Endpoints

Per project convention: thin handlers + `_`-prefixed SQL helpers, SQL centralised
per router, `GameType` validation where relevant.

| Endpoint | Game | Notes |
|---|---|---|
| `GET /api/poker/hands/{hand_id}/review` | solo | new; per-hand |
| `GET /api/poker/tournaments/{id}/review` | solo | **exists** — upgrade to equity-backed compute-on-read; keep response shape, extend fields |
| `GET /api/holdem/hands/{hand_id}/review` | multi | new; per-hand |
| `GET /api/holdem/tables/{id}/review` | multi | new; Game Review for your current table visit |

- **Access control** mirrors blackjack: caller must have been a seat in that
  hand/session (or it's finished). A user only ever sees **their own** decisions
  graded.
- **"Table visit" definition (multiplayer):** the set of hands in which the
  requesting user held the seat during their current sit. Derived from
  `HoldemHandSeat` rows joining the user within their current `HoldemSeat` tenure.
  If a clean sit-start boundary isn't available, fall back to "all hands you have a
  seat row for at this table" — pragmatic and good enough for v1 (flagged for the plan).

### 5. Frontend

- **Types** (`frontend/src/types/index.ts`): real `PokerReview` / `PokerReviewAction`
  / `PokerGameReview` replacing the `unknown` that `getPokerSessionReview` returns
  today. No `any`.
- **API** (`frontend/src/api/client.ts`): typed fetchers for the four endpoints,
  each returning `{ data, error }`; components handle **both loading and error**.
- **Component**: one `PokerReviewModal` (built on `ModalShell`), reusing the
  blackjack `ClassificationChip` colour map and `EvalBar` patterns. It renders the
  per-hand decision list (verdict chip, your action vs recommended, equity vs
  required, EV-loss, explanation) and the Game Review summary (accuracy %, EV lost,
  worst-hands list → click a hand to drill into its Hand Review).
- **Entry points:**
  - *Solo* (`PokerTablePage`): a "Review" button on the tournament-complete /
    between-hands screen → Game Review → drill into any hand.
  - *Multiplayer* (`HoldemTablePage`): a small **"Review hand"** affordance in the
    hand-result area (this requires a minimal hand-completion/result UI, which the
    table does not render today — small addition), plus a **"Session review"** entry
    (your table visit) in the table menu/header.
- All user-facing strings via `t()`. Tailwind only.

## Solo vs multiplayer — summary

| Axis | Solo Poker | Multiplayer Hold'em |
|---|---|---|
| Review scope (Game) | whole tournament | current table visit |
| Card reveal in review | reveal all (vs bots) | showdown cards only; folded holes stay masked |
| Range model | bot archetype range | positional default range |
| Backend per-hand endpoint | new | new |
| Backend game endpoint | upgrade existing | new |
| Persistence | none (recompute on read) | none (recompute on read) |
| Live-play code touched | none | none (+ small result-UI addition only) |

## Testing (focused)

- **Equity engine** (unit): pinned matchups (AA vs KK preflop ≈ 0.82; AKs vs QQ
  ≈ coin flip; made flush vs set on the turn via exact enumeration; guaranteed
  chop → 0.5); determinism (same seed → identical result); enumeration vs MC
  agreement within tolerance on a 1-card-to-come spot.
- **Grader** (unit): obvious −EV call → mistake/blunder; clearly +EV call → best;
  correct fold of trash vs a raise → best; a contextual multi-street bet →
  `no_verdict`.
- **Endpoints** (integration, in-memory SQLite, existing `seed_*` fixtures): a
  finished hand returns a review with verdicts for the caller's actions; access
  control rejects a non-participant; a hand the caller folded early still grades
  cleanly. One per game.
- **Frontend** (vitest + MSW): modal renders verdicts from a mocked response;
  loading + error branches both rendered.

## Decomposition (aim: 2 PRs)

1. **PR 1 — equity engine + grader.** Pure backend (`equity.py` + `oracle.py`
   upgrade) with unit tests. No endpoints, no UI. Self-contained and the only piece
   with interesting correctness to verify.
2. **PR 2 — review surfaces.** Compute-on-read endpoints (solo per-hand + upgraded
   tournament; multiplayer per-hand + table-visit) + the shared `PokerReviewModal`,
   typed client calls, entry points, and the minimal multiplayer hand-result UI.

   If PR 2 is too large to review comfortably it splits into 2a (backend endpoints)
   / 2b (frontend), but the target is two PRs to keep this light.

Each PR runs the project's plan → tester → implementer → oracle → verify loop.

## Explicitly out of scope (YAGNI)

- No GTO solver, no stored/cached verdicts, no schema migration, no async equity
  pipeline, no ICM rework (solo keeps its existing bubble placeholder), no
  "retry this spot" drill for poker (blackjack-only), no cross-session poker
  weakness analytics, no poker hand-history page (review is reached from the table).
  Any of these can be layered on later; the compute-on-read design composes cleanly.
