# BetWise Casino

A fake-money casino **trainer** for three table games — **Blackjack**, **Texas Hold'em**, and **Pai Gow Poker** — where an AI coach named **Chipy** explains every decision against game theory instead of just telling you "wrong." Sit at a shared table with other players, place a bet, and as you play, BetWise tells you the *optimal* move and *why* (expected value, pot odds, house-way), then grades the hand afterward chess.com-style (Best / Good / Inaccuracy / Mistake / Blunder). The chip leaderboard is the hook; walking away a measurably better player is the point.

> **Live URL:** https://betwise-casino-production.up.railway.app
> **GitHub:** https://github.com/Durp06/betwise-casino

## Tier targeted

**Gold.** Three games live and deployed, real-time-ish multiplayer **and** an end-to-end test suite (two of the gold "pick one" options), phone-friendly, a visual design with a point of view, and well more than two custom nontrivial features. Details below.

## Team members

- **Myles — [@Durp06](https://github.com/Durp06)** — blackjack end-to-end (basic-strategy engine, the EV engine + Hand Review classifier, Chipy coaching flow), the multi-game platform scaffold, multiplayer polling + table state, the auto-migration runner, and Railway/Docker deploy plumbing.
- **[@halynk21](https://github.com/halynk21)** — Pai Gow Poker end-to-end (the pure house-way/evaluator/foul-rule game logic, its three routers, the Fortune side-bet pool, and the Pai Gow frontend pages).
- **[@cristpierce](https://github.com/cristpierce)** — Texas Hold'em + multiplayer (cash-ring betting state machine, showdown/side-pots, in-game chat) and the Balatro-grade UX/motion overhaul.

## Where the nontrivial logic lives

Every game contributes a genuinely-designed piece — none of these are CRUD-from-a-one-line-prompt.

| Piece | File · function | What it does (and the design problem) |
|---|---|---|
| **Blackjack basic strategy** (bronze) | `backend/game/blackjack/strategy.py:136` · `optimal_action` | Canonical 6-deck dealer-hits-soft-17 table as `HARD_TOTALS`/`SOFT_TOTALS`/`PAIRS` dicts. Pure function — called from both the live game and ~30 unit tests with no DB. |
| **Blackjack EV engine** (silver) | `backend/game/blackjack/ev.py:165,322` · `dealer_outcome_distribution`, `best_action_ev` | Infinite-deck H17 expected-value recursion: computes the true EV of stand/hit/double for any hand vs upcard, cross-checked against the strategy table. Powers the Hand Review grade and the "Sharp" tier in `review.py:258 classify_action`. Design problem: dealer-distribution recursion + ace demotion + the peek (no-blackjack) conditioning. |
| **Cross-table weakness analytics** | `backend/analytics/weakness.py:86` · `get_weak_spots` | Aggregates `player_actions` by `(hand_category, dealer_upcard_category)`, filters to ≥5-sample buckets, sorts worst-accuracy-first. The ≥5 filter is load-bearing — without it one rare mistake reads as a 0%-accuracy "weakness." |
| **Hold'em betting state machine** | `backend/game/poker/state.py:189,504` · `apply_action`, `compute_side_pots` | Real multi-step poker engine: street progression, min-raise / all-in-doesn't-reopen rules, and side-pot construction when players are all-in for different amounts. The side-pot ladder + showdown award (`poker/showdown.py:23 decide_winners_per_pot`) is the classic chips-at-stake correctness trap. |
| **Hold'em equity engine + equity-backed review** | `backend/game/poker/equity.py:367` · `hand_equity` | Win-equity for a hero hand vs villain *ranges*: **exact enumeration** when ≤2 board cards remain (villain-combo × board-runout cross-product, dead-card removal, fractional tie splits) and **seeded Monte-Carlo** preflop or when the combo space explodes — same seed → identical float, so reviews reproduce. Powers a chess.com-style **equity-backed poker Game/Hand Review** (`routers/poker_review.py`, grades each decision against its true equity, never needs opponents' cards) plus the on-felt "Ask Chipy" win/tie/lose odds. Design problem: the enumerate-vs-sample dispatch, reproducibility, and multiway dead-card bookkeeping. |
| **Pai Gow house way + foul rule** | `backend/game/pai_gow/house_way.py:50` · `foxwoods`; `pai_gow/resolver.py:56` · `resolve_hand` | Splits 7 cards into a legal 5-card/2-card set under the Foxwoods house way (with joker semi-wild handling), enforces the "low hand can't outrank high hand" foul rule, and resolves copies-to-dealer across the 9-cell truth table. Verified by a 300-seed full-deck fuzz invariant. |

## Design decisions

1. **Supabase Auth, not our own JWT.** Real identity that survives refresh (email/password), verified in `backend/auth.py` with `python-jose` against Supabase's JWKS. A `BETWISE_DEV_USER_ID` bypass keeps the test suite off Supabase's critical path. Rolling our own would have burned a week on the login page.
2. **Polling, not WebSockets (the gold real-time pick).** A 3-second `setInterval` against each game's `/state` endpoint (`useTablePoll`, `usePokerPoll`, `useHoldemPoll`, `usePaiGowPoll`). Table turns last ≥5s, so worst-case staleness is ~3s — well inside the rubric's 5s bar — without a reconnect state machine, session pinning, or deploy-time connection draining.
3. **Money is integer fake-cents, everywhere.** `chip_balance`, `bet`, `payout`, pots, and the Fortune pool are all integers ($50.00 = `5000`); floating-point money never enters the system. Payout math (blackjack 3:2, side pots, Pai Gow commission) is all integer division with documented rounding.
4. **Migrations auto-apply on deploy.** The Dockerfile runs `python -m backend.migrate` before uvicorn — it discovers `backend/migrations/*.sql`, applies pending files once (tracked in a `schema_migrations` ledger), and **fails the deploy** if a migration errors. We added this after poker's tables shipped in code but 500'd in prod because a hand-run migration step got forgotten.

## Where the agents helped most and where we pushed back

Claude was reliably strong on the well-specified, math-heavy cores: the basic-strategy table (every cell right first pass), the 7-card poker evaluator and Pai Gow house-way (both pinned by exhaustive/fuzz tests), and the EV-recursion engine. Where we had to lean in was, every time, the unhappy path and the seams. It shipped a multiplayer table page that called `leaveTable` from a React effect *cleanup*, so `StrictMode`'s dev double-invoke un-seated the player the instant they sat down (caught only by driving the real browser, not by green unit tests). It serialized poker's per-hand RNG seed to the client, making hole-card masking cosmetic — a player could recompute the deck. It computed a tournament prize pool as `buy_in × (1 + bot_count)` while the bots paid nothing, minting chips from thin air. And it liked opening a second `AsyncSession` for cross-cutting writes, which silently broke streak updates until we forced them onto the dependency-injected session. The pattern held across all three games: agents nail the specified algorithm, then assume the happy path holds everywhere — concurrency, auth, money-conservation, and lifecycle edges are where the humans had to push hardest.

## How to run locally and run tests

```bash
# Backend (from repo root)
cd backend && python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest tests/ -q            # full backend suite, in-memory SQLite, mocked Anthropic

# Frontend
cd ../frontend && npm install
npx tsc --noEmit && npm test -- --run # typecheck + Vitest component tests
npm run build                         # emits frontend/dist/

# End-to-end (Playwright drives a headless browser; its config boots the
# backend + a no-bypass backend + the vite dev server automatically)
npx playwright install chromium
npm run e2e                           # frontend/e2e/*.e2e.ts — 3 flows

# Run the whole app (one service: FastAPI serves the built React bundle at / and /api/*)
cd .. && uvicorn backend.main:app --reload --port 8000   # -> http://localhost:8000
```

The app boots with no env vars (tests use in-memory SQLite). For an end-to-end copy against real Supabase + Anthropic, set `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET`, `ANTHROPIC_API_KEY`, and `DATABASE_URL` (a cloud Postgres, e.g. Supabase `postgresql+asyncpg://...`). For local dev without Supabase: `BETWISE_DEV_USER_ID=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa` and `BETWISE_TEST_DB_URL=sqlite+aiosqlite:///:memory:`.

## Gold: the "pick one" and the custom features

- **Pick one (we ship two of the three) → real-time-ish multiplayer (polling).** Other players' actions, seats, and the dealer/board appear in your open view within ~3s, no manual refresh, across all three games. Polling fits because turn cadence (≥5s) is slower than the poll interval — see Design Decision #2.
- **Pick one (also) → an end-to-end test suite (Playwright).** Specs in `frontend/e2e/` cover three distinct flows — authenticated landing/onboarding, the full sit → bet → deal → play blackjack action, and an unauthorized-401 edge — each driving the real React app against a live FastAPI backend in a headless browser. `frontend/playwright.config.ts` boots the backend (plus a no-bypass instance so the auth check can't be masked) and the vite frontend, and the suite runs in CI (the `e2e` job in `.github/workflows/ci.yml`) alongside pytest + Vitest, so the whole pipeline must go green before deploy. The browser flows authenticate through the same `BETWISE_DEV_USER_ID` / `VITE_DEV_USER_ID` bypass the pytest suite uses (deterministic, no Supabase round-trip); real Supabase email sign-up is verified manually.
- **Custom feature — chess.com-style Hand Review (blackjack).** Every decision in a session is graded Best/Good/Inaccuracy/Mistake/Blunder with the real EV cost in chips and a "what-if" line, plus a "retry this spot" drill. `backend/routers/sessions.py` + `backend/game/blackjack/review.py`.
- **Custom feature — equity-backed poker Hand/Game Review.** The poker analogue of the blackjack Hand Review: every decision in a solo or multiplayer hold'em hand is graded against its *true equity* (from the enumeration/Monte-Carlo engine above), recomputed on read with no migration and never exposing opponents' hole cards. `backend/routers/poker_review.py` + `backend/game/poker/review.py` + `backend/game/poker/equity.py`.
- **Custom feature — Pai Gow Fortune side-bet pool.** A shared, progressive bonus pool that every Fortune bet contributes to and that pays out (with a seeded floor + ledgered draws) when a player hits a qualifying hand — real shared state across players. `backend/game/pai_gow/fortune.py`.
- **Custom feature — in-game chat + multiplayer presence.** A polymorphic chat table shared across blackjack and Hold'em tables, server-validated and rendered as inert text (stored-XSS-safe). `backend/routers/chat.py`.
- **Plus:** Texas Hold'em (solo-vs-bots trainer **and** multiplayer cash rings), per-decision skill ratings, streaks, and a multi-game leaderboard.

## What's where

Three games as parallel router stacks under `backend/routers/` (blackjack: `tables`/`game`/`advice`/`sessions`; poker: `poker_*`; Hold'em: `holdem`; Pai Gow: `pai_gow_*`; shared: `users`/`leaderboard`/`analytics`/`chat`/`practice`) — **50+ endpoints**. Pure game logic lives in `backend/game/{blackjack,poker,pai_gow}/` (no DB, fully unit-tested). Data model in `backend/models.py`; schema in `backend/migrations/*.sql` (real FKs + NOT NULL/UNIQUE/CHECK constraints, hosted on Supabase Postgres). Frontend pages per game under `frontend/src/pages/`, Zustand stores with optimistic updates, React Router for bookmarkable URLs. Tests: `backend/tests/` (~1,200 pytest cases across ~800 test functions) + `frontend/tests/` (Vitest) + `frontend/e2e/` (Playwright, 3 flows), gated in `.github/workflows/ci.yml` on every push to `main`; Railway is configured to "Wait for CI", so deploy is gated on a green pipeline.
