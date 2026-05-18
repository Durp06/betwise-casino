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

- **Bronze**: `backend/game/strategy.py::optimal_action` — canonical 6-deck dealer-hits-soft-17 basic-strategy table, implemented as `HARD_TOTALS`, `SOFT_TOTALS`, `PAIRS` dicts.
- **Silver**: `backend/analytics/weakness.py::get_weak_spots` — cross-session aggregation of `player_actions` bucketed by hand category × dealer upcard category with ≥5-sample filter.
- **Gold (real-time-ish)**: `frontend/src/hooks/useTablePoll.ts` — 3-second polling of `/api/tables/{id}/state`.
- **Gold custom 1**: Streak system — `backend/routers/advice.py` increments `users.current_streak/best_streak` in the same DB session as the advice response.
- **Gold custom 2**: Hand replay — `backend/routers/game.py::GET /api/hands/{hand_id}/actions` + `frontend/src/components/ReplayModal.tsx`.

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
