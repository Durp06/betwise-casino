# BetWise Casino

A fake-money multiplayer blackjack lounge with an AI coaching buddy named **Chipy** who explains every decision against the canonical basic-strategy table. Sit down at a table with friends, place a bet, and before you confirm a Hit / Stand / Double / Split, Chipy tells you what the correct play is and *why* — using probability and expected-value reasoning, not just "wrong, try again." The point is that you walk away from the session a measurably better blackjack player; the chip leaderboard is the side effect.

> **Live URL:** https://betwise-casino-production.up.railway.app
> **GitHub:** https://github.com/Durp06/betwise-casino

## Tier targeted

**Gold.** See "Where the nontrivial logic lives" below for the bronze + silver + gold-pick pieces, and "Custom gold features" for the two custom features.

## Team members

- **Myles ([@Durp06](https://github.com/Durp06))** — backend (FastAPI + SQLAlchemy + Supabase), frontend (React/TS + Cuphead design pivot), the basic-strategy engine, the Chipy coaching flow (proactive pre/post advice with markdown stripping), multiplayer polling + table state, deploy plumbing (Railway + Dockerfile).
- _Teammate #2 — [name, GitHub handle, one-line summary of their owned area]_
- _Teammate #3 — [name, GitHub handle, one-line summary of their owned area]_

## Where the nontrivial logic lives

| Tier | File | Function | What it does |
|---|---|---|---|
| **Bronze** | `backend/game/strategy.py:136` | `optimal_action(player_cards, dealer_upcard, can_double, can_split)` | Canonical 6-deck, dealer-hits-soft-17 basic-strategy table. Implemented as three nested dicts — `HARD_TOTALS`, `SOFT_TOTALS`, `PAIRS` — so the file reads as the published table itself, not a heuristic. Returns one of `hit`/`stand`/`double`/`split`. Pure function, no DB, fully unit-testable. **Design decision:** keeping this as a pure function (no DB access) is what lets us hit it from both the advice endpoint and the test suite without a fixture. |
| **Bronze (helper)** | `backend/game/strategy.py:193` | `explain_decision(...)` | Returns the natural-language explanation that Chipy embeds in its prompt to Claude. Names the hand category (`"hard 16"`, `"soft 18"`, `"pair of aces"`) and the dealer upcard. |
| **Silver** | `backend/analytics/weakness.py:75` (`_categorize`), endpoint at `backend/routers/analytics.py` | `get_weak_spots(user_id, db)` | Cross-table aggregation of `player_actions` bucketed by `(hand_category, dealer_upcard_category)`, filtered to buckets with ≥ 5 samples, sorted worst-accuracy-first. Tells the player which situations they keep losing. **Design decision:** the ≥ 5-sample filter is non-negotiable — without it, one mistake at a rare hand looks like a 0 %-accuracy "weakness" and ruins the signal. |
| **Gold pick** (real-time-ish) | `frontend/src/hooks/useTablePoll.ts:16` | `useTablePoll(tableId, currentUserId)` | 3-second poll of `GET /api/tables/{id}/state` driving the multiplayer view. Reconciles into the Zustand store, detects when the turn becomes ours, and auto-opens Chipy. **Design decision:** polling over WebSockets — see "Design decisions" below. |
| **Gold custom #1** | `backend/routers/advice.py:111` | streak update inside `/api/advice/{hand_id}` | Increments `users.current_streak` on every correct guess and resets to zero on a wrong guess, tracking `best_streak` as a max. Surfaced on `/profile` and `/leaderboard`. |
| **Gold custom #2** | `backend/routers/game.py:51` (`GET /api/hands/{hand_id}/actions`) + `frontend/src/components/ReplayModal.tsx` | hand replay | After a hand finishes, the player can step through every decision they made — what they did, what was optimal, what Chipy said. Pulls ordered rows from `player_actions`. Authorization rule: only the owning user can read it during play; once the session is finished, anyone can. |

## Design decisions

1. **Supabase Auth over rolling our own JWT.** The PDF rubric explicitly calls out "X-Username header is not enough" and warns against burning three weeks on the login page. Supabase Auth + the `python-jose` JWT verifier in `backend/auth.py` gets us signed-and-verified identity that survives refresh, with email/password and OAuth options, in about a day of setup. The local `BETWISE_DEV_USER_ID` bypass keeps tests off the Supabase critical path.
2. **Polling, not WebSockets.** A 3-second `setInterval` against `GET /api/tables/{id}/state` is more than fast enough for blackjack — table turns last ≥ 5 s in practice, so the worst-case staleness any player sees is ~ 3 s. WebSockets would add a reconnect state machine, server-side session pinning, and connection draining on deploy — three problems we don't actually have. The PDF rubric explicitly says polling is fine for the gold real-time pick; we took that at face value.
3. **Chips stored as integer cents.** All monetary values in the schema (`chip_balance`, `bet`, `payout`, `min_bet`, `max_bet`) are integers — `$10.00` is `1000`. Floating-point money never enters the system. Blackjack 3:2 is `bet * 5 // 2` (round half-down toward the bet); documented in `backend/game/state.py::resolve_hand`.
4. **Strategy engine as a pure function — no DB access.** `optimal_action` takes only the cards and the dealer upcard. It is called from the advice endpoint and from ~ 20 unit tests; both call sites use the same code path with no DB or HTTP shimming. If we ever swap from 6-deck-H17 to 8-deck-S17, the change is a constant in one file.

## Where the agents helped most and where we pushed back

Claude was reliably good at the well-specified pieces — the basic-strategy table (HARD_TOTALS / SOFT_TOTALS / PAIRS dicts, every cell right on the first pass including the 9-9 split-vs-2-6/8-9/stand-vs-7/10/A edge cases), the SSE streaming endpoint, and the Zustand optimistic-with-rollback reducer. The patterns where we had to push back recurred: it loved opening a second `AsyncSession` for cross-cutting writes (which broke `test_advice_correct_increments_streak` until we forced the streak update onto the dependency-injected session); it wrote test helpers that silently masked impossible inputs (`hand_cards_for(22)` returning a 19-value 2-card hand instead of failing loudly that 22 isn't representable with two cards); and it shipped happy-path code that ignored every failure mode — a hard-coded `claude-sonnet-4-20250514` model alias that crashed silently when Anthropic deprecated it (we added a `CHIPY_MODEL` env var + try/except that emits graceful fallback chunks), a 409 "Round already in progress" guard on the deal endpoint that blocked the second player at a multiplayer table (caught during a two-user live test and removed), and a button-driven ChipyPanel quiz that interrupted actual play (redesigned as an always-visible side panel that streams pre-play suggestions and post-play critiques automatically). The pattern across all of these: agents nail the well-specified piece on the first try, then quietly assume the happy path holds everywhere — loading + error + concurrency + deprecation surface is where the human has to lean in hardest.

## How to run locally

```bash
# Backend
cd betwise-casino/backend
python -m venv .venv
.venv\Scripts\activate              # PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Tests run against in-memory SQLite — no real Postgres needed.
python -m pytest tests/ -v

# Frontend
cd ../frontend
npm install
npm test -- --run                   # 6 Vitest tests
npm run build                       # produces frontend/dist/

# Run the whole app locally (FastAPI serves the built React bundle at /)
cd ../backend
uvicorn main:app --reload --port 8000
# Open http://localhost:8000 in a browser.
```

### Environment variables

The app boots without any env vars set (great for tests). To run end-to-end against real Supabase + Anthropic you need:

```
SUPABASE_URL=                       # https://<project>.supabase.co
SUPABASE_ANON_KEY=                  # Supabase anon public key (frontend reads this as VITE_SUPABASE_ANON_KEY)
SUPABASE_JWT_SECRET=                # Supabase JWT secret — Settings → API → JWT Settings
ANTHROPIC_API_KEY=                  # sk-ant-...
DATABASE_URL=                       # postgresql+asyncpg://... (Supabase connection string, port 5432)
```

For local dev without Supabase, set:

```
BETWISE_DEV_USER_ID=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa
BETWISE_TEST_DB_URL=sqlite+aiosqlite:///:memory:
```

The frontend additionally reads `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` from a `frontend/.env.local` file (Vite picks these up automatically).

## Gold features summary

- **Gold pick:** real-time-ish multiplayer via 3-second polling — see `frontend/src/hooks/useTablePoll.ts`. Reason: polling fits because blackjack turns last ≥ 5 s, the staleness budget tolerates ~ 3 s, and WebSockets would add reconnect + session-pinning complexity we don't need.
- **Custom feature #1 — strategy streak.** Every correct call against `optimal_action` adds 1 to `users.current_streak`; one wrong call resets it; `users.best_streak` tracks the all-time max. Visible on `/profile` and on the leaderboard row. Tracked atomically in the same DB session as the advice response (`backend/routers/advice.py:111`).
- **Custom feature #2 — hand replay.** After a hand finishes, "Review Hand" opens a modal (`frontend/src/components/ReplayModal.tsx`) that steps through every action the player took, with Chipy's optimal call beside it. Pulls ordered rows from `player_actions` via `GET /api/hands/{hand_id}/actions`. Authorization: owner-only during play, everyone after the session is finished.

## Repo layout

```
betwise-casino/
├── CLAUDE.md                      # team conventions (also used by Claude Code)
├── README.md                      # this file
├── railway.json                   # single-service Railway deploy
├── .github/workflows/ci.yml       # backend pytest + frontend Vitest, gates merge to main
├── backend/
│   ├── main.py                    # FastAPI app, mounts frontend/dist at /
│   ├── database.py                # lazy async engine factory (no module-level connect)
│   ├── models.py                  # SQLAlchemy 2.0 Mapped[] columns
│   ├── schemas.py                 # Pydantic v2 (ConfigDict(from_attributes=True))
│   ├── auth.py                    # Supabase JWT verification, lazy JWKS cache, dev bypass
│   ├── game/
│   │   ├── engine.py              # deck, hand_value, is_blackjack, deal_card
│   │   ├── strategy.py            # BRONZE nontrivial piece (basic-strategy table)
│   │   └── state.py               # turn machine, dealer auto-play, resolve_hand
│   ├── analytics/
│   │   └── weakness.py            # SILVER nontrivial piece (cross-table aggregation)
│   ├── routers/                   # users, tables, game, advice, leaderboard, analytics
│   ├── migrations/001_initial.sql # idempotent CREATE TABLE / CREATE INDEX
│   └── tests/                     # 100 pytest tests, in-memory SQLite, mocked Anthropic
└── frontend/
    ├── src/
    │   ├── api/client.ts          # typed fetch wrapper, never throws to components
    │   ├── auth/supabase.ts       # Supabase client singleton + useSession hook
    │   ├── store/gameStore.ts     # Zustand store + optimistic Hit reducer
    │   ├── hooks/
    │   │   ├── useTablePoll.ts    # GOLD: 3-s polling
    │   │   └── useChipy.ts        # SSE consumer for /api/advice
    │   ├── components/            # PlayingCard, CardHand, ChipyPanel, ReplayModal, …
    │   └── pages/                 # Login, Lobby, Table, Profile, Leaderboard
    └── tests/ChipyPanel.test.tsx  # contract test for the Chipy flow
```
