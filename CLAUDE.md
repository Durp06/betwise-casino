# BetWise Casino — Conventions

## Project conventions (from source spec Step 1)

1. All API routes prefixed `/api`.
2. Cards represented as `{ suit: "hearts"|"diamonds"|"clubs"|"spades", value: "2"-"10"|"J"|"Q"|"K"|"A" }`.
3. Hand state stored as JSONB arrays of card objects.
4. All monetary values are integers (fake cents, so $10.00 = 1000).
5. User always starts with 100000 (= $1,000.00).
6. Async SQLAlchemy everywhere — no sync DB calls.
7. Pydantic v2 models with `model_config = ConfigDict(from_attributes=True)`.
8. Frontend: no `any` types — everything typed.
9. Zustand for client state, React Query for server state.
10. Tailwind only — no inline styles except dynamic values (e.g. `style={{ width: \`${pct}%\` }}`).
11. Component files: PascalCase. Utility files: camelCase.
12. All user-facing text goes through a `t()` helper (future i18n hook).
13. **Never call `datetime.utcnow()` — always `datetime.now(timezone.utc)`.** (Grader anti-pattern.)
14. **Centralize each SQL query in one module — do not re-implement the same SELECT across routers.** Each router has its own SQL helper functions; route handlers call helpers, never inline raw SQL or duplicate queries.
15. **Every fetch must show loading + error states.** No happy-path-only components. The typed `client.ts` returns `{ data, error }` so React components always have both branches.

## Dev bypass variables

- `BETWISE_DEV_USER_ID` — UUID string. When set, `backend/auth.py`'s `get_current_user` skips JWT verification and returns this UUID. Used for local dev and all tests. **Never set in production.**
- `BETWISE_TEST_DB_URL` — SQLAlchemy URL. When set, `database.get_engine()` uses this instead of `DATABASE_URL`. Defaults to `sqlite+aiosqlite:///:memory:` for in-memory test DB.

## Where the nontrivial pieces live

> **Note**: blackjack-specific code now lives at `backend/game/blackjack/`. The historical paths (`backend/game/engine.py`, `strategy.py`, `state.py`, `review.py`) still work — they're re-exported by `backend/game/__init__.py`. New blackjack-specific code goes in `backend/game/blackjack/`, not at the root.

- **Bronze**: `backend/game/blackjack/strategy.py::optimal_action` — canonical 6-deck dealer-hits-soft-17 basic-strategy table, implemented as `HARD_TOTALS`, `SOFT_TOTALS`, `PAIRS` dicts.
- **Silver**: `backend/analytics/weakness.py::get_weak_spots` — cross-session aggregation of `player_actions` bucketed by hand category × dealer upcard category with ≥5-sample filter.
- **Gold (real-time-ish)**: `frontend/src/hooks/useTablePoll.ts` — 3-second polling of `/api/tables/{id}/state`.
- **Gold custom 1**: Streak system — `backend/routers/advice.py` increments `users.current_streak/best_streak` in the same DB session as the advice response.
- **Gold custom 2**: Hand replay — `backend/routers/game.py::GET /api/hands/{hand_id}/actions` + `frontend/src/components/ReplayModal.tsx`.
- **Hand Review (educational)**: `backend/routers/sessions.py::GET /api/sessions/{id}/review` + `backend/game/blackjack/review.py::classify_action` + `frontend/src/components/SessionReviewModal.tsx`. Inspired by Chess.com's Game Review — classifies every decision in a session as Best / Good / Inaccuracy / Mistake / Blunder with EV-loss math.

## Why polling over WebSockets

Polling (3s interval) was chosen over WebSockets because:
- No reconnect logic needed
- Simpler server-side implementation (stateless GET)
- Fits the "real-time-ish" gold requirement
- Easier to debug and test

## Hole card visibility rule

During `playing` session status, the **dealer's second card** (index 1 of `session.dealer_cards`) is the hole card and is hidden with `null` in the GET `/api/tables/{id}/state` response. All player hands are fully visible to everyone. At `dealer_turn` and `finished`, all dealer cards are revealed.

- Implementation: `backend/routers/tables.py::_get_table_state` masks `dealer_cards_out[1]` when `session.status == "playing"`.
- The `test_other_players_hole_cards_hidden_during_play` test asserts this corrected behavior.

## Known limitations

- **Split returns 501**: `POST /api/tables/{id}/action` with `action="split"` always returns HTTP 501. The current schema has an implicit `UNIQUE(session_id, user_id)` constraint on hands (one hand per user per session). Implementing split properly requires a follow-up migration to add a `(session_id, user_id, hand_index)` unique constraint. This is tracked as a future enhancement.

## Test isolation note

The `backend/conftest.py` monkeypatches `AsyncSession.commit()` → `flush()` for every test. This ensures the session-scoped SQLite in-memory engine can properly roll back per-test data via the `db` fixture's `rollback()` call. The `tests/conftest.py`'s `seed_*` helpers call `commit()` explicitly; without this patch, committed data would persist across tests and cause UNIQUE constraint failures.

---

## Code standards

These apply to every PR. They are not preferences — they are the conventions reviewers will block on.

### Backend (Python)

- **Line length 120, formatter is your choice** as long as ruff stays green. `ruff check backend` runs in CI; rules are in `pyproject.toml`.
- **Type hints on every function.** Use `from __future__ import annotations` at the top of every file so forward references work without quoting. Return types are not optional.
- **Async everywhere or sync everywhere — no mixing.** Database access is async (SQLAlchemy 2.0 `AsyncSession`). Game logic is sync (pure functions). Don't `await` inside `engine.py`-style modules; don't write sync DB calls.
- **Imports inside route handlers are fine** for lazy loading (you'll see `from backend.models import ...  # noqa: PLC0415` inside helpers). This is intentional — keeps `main.py` import-time cheap so the health endpoint can answer before the DB engine is built.
- **One responsibility per module.** `routers/foo.py` has handlers + `_helper` SQL functions. Logic that's reused across routers belongs in `backend/game/`, `backend/analytics/`, or a new top-level package — not stuffed sideways into a router.
- **No `print()` in production code.** Use the `logger = logging.getLogger(__name__)` pattern.
- **Exceptions in route handlers raise `HTTPException`**, never bare exceptions that leak to the client. The global handler in `main.py` catches anything that escapes and returns `{"detail": "Internal server error"}` — that's a last-resort net, not a substitute for handling.

### Frontend (TypeScript)

- **No `any` — no exceptions.** If you can't type something, use `unknown` and narrow at the boundary.
- **`npx tsc --noEmit` must be clean.** CI runs it.
- **Components are PascalCase files**, utilities are camelCase. Hooks start with `use`.
- **Tailwind for everything visual.** Inline styles only for dynamic numeric values (`style={{ width: \`${pct}%\` }}`). No CSS modules, no styled-components.
- **Every fetch shows loading + error states.** The API client returns `{ data, error }` — handle both branches. No `if (data)` and silently swallowing errors.
- **State separation**: Zustand for client state (the game store, modal visibility), React Query for server state when caching matters. Most BetWise UI uses Zustand directly because the polling hook is the source of truth, not React Query.
- **User-facing strings go through `t()`** from `frontend/src/i18n.ts`. Even when there's only one locale — it's a hook for the future and grades will look for it.

### Tests

- **Backend**: pytest-asyncio + in-memory SQLite. Use `seed_user`, `seed_table`, `seed_session`, `seed_hand`, `seed_actions` from `backend/tests/conftest.py`. Each test gets a clean DB via the `db` fixture's rollback.
- **Frontend**: Vitest + jsdom + `@testing-library/react`. Mock HTTP with MSW (`setupServer` pattern in `frontend/tests/ChipyPanel.test.tsx`). Don't mock React Query / Zustand — render real components and assert on the DOM.
- **Tests live next to acceptance criteria.** A spec lists ACs; the tester writes one test per AC; the implementer makes them pass. See `~/.claude/CLAUDE.md` for the planner→tester→implementer subagent loop.
- **Don't mock the DB.** Mock-vs-prod divergence has burned this codebase before — see `feedback_workflow.md`.

### Naming + commits

- **Branch names**: `<area>/<short-kebab-summary>` — `feat/`, `fix/`, `chore/`, `refactor/`, `docs/`, `test/`.
- **Commit subjects**: `<area>(scope): imperative summary`. Examples:
  - `feat(review): GET /api/sessions/{id}/review endpoint`
  - `fix(table): drop Split until schema supports it`
  - `chore(ci): add ruff lint step`
- **Body when warranted**: explain the *why*, not the *what*. The diff is the what.
- **One coherent change per PR.** Refactors and feature work split across separate PRs.

### Where new code goes

| Adding... | Lives in |
|---|---|
| A new API route | New file `backend/routers/<area>.py` (or extend an existing one) with thin handlers + `_` helpers. Register in `backend/main.py`. |
| A new SQLAlchemy table | `backend/models.py` (one file, all models). Add a Pydantic `Out` schema in `backend/schemas.py`. Migration goes in `backend/migrations/`. |
| A new pure helper | The right `backend/<package>/` — `game/blackjack/` for blackjack logic, `analytics/` for cross-session aggregation, etc. Don't create a `utils.py`. |
| A new game | `backend/game/<game_name>/` subpackage. See "Adding a new game" below (added once the multi-game scaffold lands). |
| A new React page | `frontend/src/pages/<Page>.tsx`. Wire into `App.tsx` Routes. |
| A new reusable component | `frontend/src/components/<Component>.tsx`. |
| A new typed API call | `frontend/src/api/client.ts` — keep all server I/O in this file. |
| A new TS type | `frontend/src/types/index.ts`. |

### What CI gates

A PR cannot merge unless:

- `ruff check backend` is green
- `python -m pytest backend/tests/ -v` is green (currently 118+ tests)
- `cd frontend && npx tsc --noEmit` is clean
- `cd frontend && npm test -- --run` is green
- `cd frontend && npm run build` succeeds

See `.github/workflows/ci.yml`.

---

## Adding a new game

BetWise is built to host multiple games. The scaffold lives at `backend/game/`. Today's only entry is blackjack at `backend/game/blackjack/`. To add a second game (poker, baccarat, gin rummy, etc.), follow these steps.

The goal: **a new game is a localized contribution**. You should not need to edit routers, models, or any blackjack code to add poker. The only files that change are inside `backend/game/<your_game>/`, plus a one-line addition to the registry and one literal addition to the type alias.

### Step-by-step

1. **Create the package.**

   ```
   backend/game/<your_game>/
   ├── __init__.py     # exposes GAME_TYPE = "<your_game>"; re-exports submodules
   ├── engine.py       # pure functions: create_deck, deal_card, hand-value math
   ├── strategy.py     # optional: optimal-play lookup (the equivalent of basic strategy)
   ├── state.py        # turn machine: whose turn, advance_turn, resolve outcomes
   └── review.py       # optional: classify_action for the Hand Review feature
   ```

   The submodule names are conventions, not requirements. Add only what your game needs — baccarat has no "optimal strategy" the same way blackjack does, so `strategy.py` might be a no-op or absent. Don't pad files for symmetry.

   Inside `__init__.py`:

   ```python
   """backend.game.<your_game> — <your_game>-specific game module."""
   from __future__ import annotations

   GAME_TYPE = "<your_game>"

   from . import engine  # noqa: F401,E402
   # ...other submodules you actually have
   ```

2. **Register the package in the game registry.**

   Edit `backend/game/registry.py`:

   ```python
   from backend.game import blackjack
   from backend.game import <your_game>   # ← add this

   GAME_REGISTRY: Mapping[str, ModuleType] = {
       blackjack.GAME_TYPE: blackjack,
       <your_game>.GAME_TYPE: <your_game>,   # ← add this
   }
   ```

3. **Add the literal to `backend/game/types.py`.**

   ```python
   GameType = Literal["blackjack", "<your_game>"]
   ```

   Any router or schema that wants to validate the game_type field can now use `GameType` as a Pydantic field type to get automatic enum-style validation.

4. **Don't add submodules at the root of `backend/game/`.** The flat-looking files there (`engine.py`, `strategy.py`, `state.py`, `review.py`) are re-exports from blackjack for historical compatibility. Adding a new game-flavored file at the root would collide. Keep every per-game module inside its package directory.

5. **Tests.** Add `backend/tests/test_<your_game>_engine.py`, etc. The existing fixtures in `backend/tests/conftest.py` (`seed_user`, `seed_table`, `seed_session`) are game-agnostic and will work for any game. Pass `game_type=<your_game>` when calling `seed_session`.

6. **Frontend.** The frontend is currently 100% blackjack-shaped (`/table/:id` shows a felt with blackjack actions). Adding poker means a new page set and a new ActionBar variant. This is a much bigger change than the backend side; design it as a separate spec before starting.

### What the registry does NOT do (yet)

The router layer (`backend/routers/game.py`, `backend/routers/tables.py`) still imports `backend.game.engine` and `backend.game.strategy` directly — meaning it's hardcoded for blackjack. When the second game lands, dispatching by `session.game_type` through `GAME_REGISTRY` is the natural cleanup. That refactor is deferred until a second game actually exists, to avoid building the wrong abstraction.

If you're the contributor adding the second game, expect to split your work across two PRs:

- **PR 1**: add `backend/game/<your_game>/` + registry entry + tests. Blackjack still works exactly as before. CI green.
- **PR 2**: refactor routers to dispatch through `GAME_REGISTRY`. Both games callable from the same API surface.

### Don't speculate the Protocol

`GameModule` in `backend/game/__init__.py` declares only `GAME_TYPE: str` right now. If your new game shares useful runtime methods with blackjack (e.g. both have an `apply_action(state, action) -> new_state` shape), promote that into the Protocol *as part of your PR*. Don't add Protocol methods that no caller will use.

The discipline is "two examples before an abstraction." Blackjack alone is not two examples.
