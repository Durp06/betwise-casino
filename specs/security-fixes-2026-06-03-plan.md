# BetWise Casino — Security-Audit Remediation Plan (2026-06-03)

**One-line summary:** Remediate the verified findings from `specs/security-audit-2026-06-03.md` — one critical path-traversal, the poker buy-in double-spend, the blackjack seat-grab 500, streak-replay inflation, a dealer-natural payout bug, the infinite-spinner poll hooks, and four cheap info-leak/validation hardenings — one task per finding, each with 1:1 testable acceptance criteria.

**Branch:** `fix/security-audit-2026-06-03` (already created).

**Source of findings:** `specs/security-audit-2026-06-03.md` (the audit report). This is the *remediation* plan — do not re-audit; every finding below is confirmed with exact locations.

---

## Context

A 63-agent adversarial audit produced 27 verified findings, deduplicated to the set below. The findings map directly to the grader's stated attack plan (no-token / forged-JWT / id-swap / double-submit races / cross-user access / missing loading+error states / explain-your-logic). The constraint behind this slice: ship the security fixes *only*, each as one commit's worth of work, with a test that actually pins the fix — not a test that passes vacuously under the SQLite test harness.

### Test-harness facts that shape every task (READ FIRST)

- Backend tests: `pytest-asyncio` + in-memory SQLite (`StaticPool`), fixtures in `backend/tests/conftest.py`: `client` (auth = `TEST_USER_ID`), `other_client` (auth = `OTHER_USER_ID`), `db`, and `seed_user/seed_table/seed_session/seed_hand`. Import these from `tests.conftest` (see existing tests, e.g. `backend/tests/test_chat.py:27`).
- `backend/conftest.py` monkeypatches `AsyncSession.commit()` → `flush()`. **SQLite treats `with_for_update()` as a NO-OP.** Therefore "fire two concurrent requests and watch the balance" does **not** reproduce the H1/M1 races. Each race fix gets the three-pronged test strategy spelled out in its task: (1) STRUCTURAL lock-presence test, (2) BEHAVIORAL IntegrityError→409/400 test (works because SQLite *does* enforce UNIQUE), (3) SEQUENTIAL correctness test. Pattern to mirror: `backend/tests/test_action_race.py` (structural via `inspect.getsource(...).count("with_for_update")`, plus behavioral sequential).
- The ORM builds the test schema via `Base.metadata.create_all` (`backend/tests/conftest.py:58`), **not** the SQL migration files (which are Postgres-only and exercised only by the CI Postgres job). **Consequence for L2:** the `CheckConstraint`s added to the `CasinoTable` ORM model are what the SQLite tests pick up automatically; the new SQL migration file is for prod/Postgres parity and is *not* what the pytest assertions run against.
- Frontend tests: Vitest + jsdom + MSW (`setupServer`), pattern in `frontend/tests/ChipyPanel.test.tsx` / `frontend/tests/HoldemTablePage.test.tsx`. No `any`; `npx tsc --noEmit` must stay clean. `ApiResult<T> = { data: T; error: null } | { data: null; error: string }` (`frontend/src/types/index.ts:190`).

---

## Acceptance criteria → tests (1 AC = 1 test)

Each task below lists its ACs. The tester writes exactly one test per AC; the implementer makes them pass without expanding scope.

---

## Tasks (ordered; most are independent — see Sequencing note)

### T1 — C1: Path traversal in SPA catch-all  [P0]

**Files:** `backend/main.py` (the `spa_fallback` route at `:148-159`, and the `_frontend_dist`/`_index_html` module-level vars at `:127-146`).

**Change:**
1. Extract a pure, unit-testable helper `_safe_static_path(dist: str, full_path: str) -> str | None` (module level, defined whether or not `frontend/dist` exists at import time so tests can import it without the mount). Logic:
   - Reject early and return `None` if `full_path` is empty, starts with `/`, contains a backslash, contains a `..` path segment, or looks like an absolute/drive path (`os.path.isabs(full_path)` or a Windows drive letter).
   - `candidate = os.path.join(dist, full_path)`; `real = os.path.realpath(candidate)`; `root = os.path.realpath(dist)`.
   - Return `real` only if `os.path.commonpath([real, root]) == root` **and** `os.path.isfile(real)`; otherwise `None`.
2. Rewrite `spa_fallback` to: keep the existing `api/` rejection; compute `safe = _safe_static_path(_frontend_dist, full_path)`; `return FileResponse(safe)` if `safe is not None`, else `return FileResponse(_index_html)` (the SPA shell). Never feed `full_path` to `FileResponse` directly.

**ACs:**
- **AC-1.1** `_safe_static_path(dist, "../../backend/auth.py")` returns `None` (traversal via `..` segments rejected). Build a temp `dist` dir with an `index.html` and a sibling secret file *outside* `dist`; assert the helper does not resolve to the secret.
- **AC-1.2** `_safe_static_path(dist, "favicon.ico")` returns the real path to a legit top-level file that exists inside `dist` (favicon.ico written into the temp dist); a normal route like `_safe_static_path(dist, "lobby")` (no such file) returns `None` (so the route serves the SPA shell).
- **AC-1.3** End-to-end via the ASGI `client`: `GET /%2e%2e/<secret>` and `GET /..%2f<secret>` return the SPA shell (`index.html` body) or a 404 — **never** the secret file's contents. *(Test note: the SPA route only mounts when `frontend/dist` exists at import time. Prefer pinning AC-1.1/1.2 on the extracted pure helper, which needs no import-time gymnastics. For AC-1.3 the route-level test must arrange a temp dist + secret and exercise the real transport; if the harness can't re-import `main` cleanly, AC-1.3 may be expressed against the helper that the route provably calls, with a comment that the route delegates 100% to `_safe_static_path`.)*

**Test strategy:** pure-helper unit tests (AC-1.1, AC-1.2) are the load-bearing guarantee; the route delegates entirely to the helper, so a structural assertion that `spa_fallback`'s source calls `_safe_static_path` backs AC-1.3 where full transport re-import is awkward.

---

### T2 — H1: Poker buy-in non-atomic debit + missing rate-limit  [P1]

**Files:** `backend/routers/poker_tables.py` — `_create_tournament_with_seats` (`:85-164`, the User read at `:97`, debit at `:124`, commit at `:161`) and the `create_tournament` endpoint (`:43-59`).

**Change (mirror `holdem._join_seat:330-372` and `holdem.create_table:68-78`):**
1. Lock the user row: `select(User).where(User.id == current_user).with_for_update()` at `:97`.
2. Wrap the final `await db.commit()` in `try/except IntegrityError: await db.rollback(); raise HTTPException(status_code=409, detail="…") from None`. Import `IntegrityError` lazily inside the helper (`from sqlalchemy.exc import IntegrityError  # noqa: PLC0415`).
3. Add `@limiter.limit(MUTATION_RATE_LIMIT)` to `create_tournament`, add a `request: Request` parameter (first param), and set `request.state.user_id = str(current_user)` in the handler body. Add the imports: `from backend.ratelimit import MUTATION_RATE_LIMIT, limiter` and `from starlette.requests import Request` (mirror `holdem.py:33,43`).

**ACs:**
- **AC-2.1 (structural lock)** `inspect.getsource(_create_tournament_with_seats)` contains `with_for_update` on the `User` SELECT (assert `"with_for_update" in source`). Regression guard mirroring `test_action_race.py:38`.
- **AC-2.2 (structural rate-limit + key)** The `create_tournament` handler is decorated with the mutation limiter and stuffs the per-user key: assert `inspect.getsource(create_tournament)` contains `request.state.user_id = str(current_user)`, and that `create_tournament` carries a `request: Request` parameter (inspect its signature).
- **AC-2.3 (behavioral IntegrityError→409)** Exercise the IntegrityError→rollback→409 path. *Strategy:* the cleanest SQLite-enforceable collision is the `PokerSeat` `UNIQUE(tournament_id, seat_number)` constraint — monkeypatch `random.randint` / patch the tournament id is brittle, so instead pre-insert a `PokerSeat` row that will collide, **or** patch `assign_random_archetypes`/seat construction so two seats share `seat_number=0`, forcing the commit to raise `IntegrityError`; assert the endpoint returns **409 (not 500)** and that the user's `chip_balance` is unchanged (no debit leaked through). The tester picks whichever collision the schema actually enforces under SQLite and documents it in a test comment.
- **AC-2.4 (sequential correctness)** Seed a user with `chip_balance == 10_000`. First `POST /api/poker/tournaments` with `buy_in_cents=10_000` succeeds (201) and debits exactly once (`GET /api/users/me` → `chip_balance == 0`). A second create with the same buy-in is rejected with 400 ("Insufficient bankroll"), and the balance stays `0` (debited exactly once across both calls). Mirrors `test_poker_endpoints.py` balance assertions.

**Test strategy note (race):** SQLite ignores `FOR UPDATE`, so the lock is pinned structurally (AC-2.1). The *consequence* of the missing lock — a second buy-in passing the balance check and double-spending — is pinned behaviorally by the sequential correctness test (AC-2.4), and the 500→409 hardening by AC-2.3.

---

### T3 — M1: Blackjack seat-grab race → 409 not 500  [P1]

**Files:** `backend/routers/tables.py` — `_join_seat` (`:152-230`, table read at `:172`, seat insert/flush at `:215-224`).

**Change (mirror `holdem._join_seat`):**
1. Lock the table row before computing the open seat: `select(CasinoTable).where(CasinoTable.id == table_id).with_for_update()` at `:172`.
2. Wrap the seat insert + commit/flush in `try/except IntegrityError: await db.rollback(); raise HTTPException(status_code=409, detail="Seat just taken — please retry") from None`. Import `IntegrityError` lazily. (Note: this handler currently `flush()`es; under conftest's `commit→flush` patch the UNIQUE violation surfaces on `flush`. Wrap whichever write triggers the constraint so a real concurrent collision returns a clean 409.)

**ACs:**
- **AC-3.1 (structural lock)** `inspect.getsource(_join_seat)` (the blackjack one in `backend/routers/tables.py`) contains `with_for_update` on the `CasinoTable` SELECT.
- **AC-3.2 (behavioral IntegrityError→409)** Pre-seed a `TableSeat` that collides on the table's UNIQUE constraint (`UNIQUE(table_id, seat_number)` — or `UNIQUE(table_id, user_id)` if that's what the schema enforces) so the join insert raises `IntegrityError`; assert `POST /api/tables/{id}/join` returns **409**, not 500. The tester confirms the actual UNIQUE constraint on `TableSeat` in `backend/models.py` and constructs the collision accordingly.
- **AC-3.3 (sequential correctness preserved)** A normal first join still returns its seat (200/idempotent existing behavior), and a second join by the *same* user is idempotent (returns the same seat number) — i.e. the fix doesn't regress the existing "one seat per user / lowest open seat" semantics.

**Test strategy note (race):** identical rationale to T2 — lock pinned structurally, collision-handling pinned behaviorally via SQLite's real UNIQUE enforcement.

---

### T4 — M2: Streak inflation via advice replay  [P1]

**Files:** `backend/routers/advice.py` — the streak mutation inside `get_advice`'s `_sse_stream` (`:135-160`); `backend/models.py` — `Hand` (add one nullable column); `backend/migrations/` — add the column for prod/Postgres parity.

**Decision (state explicitly) — why NOT a status gate or boolean flag:** `POST /api/advice/{hand_id}` grades **one decision** of a hand against the hand's *current* `cards`, and a single hand legitimately receives **multiple** advice calls (hit→hit→stand) while it stays `status == "active"`, with `hand.cards` growing by one card between consecutive decisions (confirmed by reading `advice.py:126-147` — it recomputes `optimal_action(hand.cards, …)` each call). Therefore:
- A **`hand.status == "active"` gate does NOT work** — both a legit replay-spaced decision *and* the abusive replay see `active`, so it fails to block the pump (AC-4.2).
- A **boolean "already advised" flag does NOT work** — it would cap a hand at a single streak bump ever, silently breaking real multi-decision play (and it would *pass* AC-4.1/4.2 while regressing the feature — caught only by AC-4.4 below).

**The correct idempotency key is `(hand_id, len(hand.cards))`.** In legitimate play every decision occurs at a distinct card count (hit/double append a card; stand ends the turn — no two decisions share a count). A replay keeps `hand.cards` frozen, so the count repeats. Grade-the-streak-once-per-(hand, card-count):

**Change:**
1. `backend/models.py` — add `advice_graded_card_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)` to `Hand`.
2. `backend/routers/advice.py` — inside the streak block (`:138-147`), before mutating: `card_count = len(hand.cards)`; if `hand.advice_graded_card_count == card_count` → this decision was already graded (a replay): **skip the entire streak mutation** (neither bump nor reset), set the summary's `current_streak`/`best_streak` to the user's *current* values, and still stream Chipy + the final event. Otherwise grade as today (bump on correct / reset to 0 on wrong) **and** set `hand.advice_graded_card_count = card_count`, then `flush`. (Reuse the `hand` already loaded at `:108-113`.)
3. `backend/migrations/007_hand_advice_graded.sql` — `ALTER TABLE hands ADD COLUMN IF NOT EXISTS advice_graded_card_count INTEGER;` (idempotent; prod/Postgres only — the ORM `create_all` path carries the column for tests, same rationale as T7).

**ACs:**
- **AC-4.1 (happy path preserved)** A first, legitimate `POST /api/advice/{hand_id}` with a *correct* guess increments `current_streak` by exactly 1 (and `best_streak` tracks it). (SSE: parse the final summary event; or assert the persisted `User` row.)
- **AC-4.2 (replay blocked)** Two sequential `POST /api/advice/{hand_id}` calls for the *same* `hand_id` **with `hand.cards` unchanged** and a correct guess increase `current_streak` by **at most 1 total** (the replay does not pump it to 2). Assert the streak after the second call equals the streak after the first.
- **AC-4.3 (ownership unchanged)** Requesting advice for another user's hand still returns 403 (regression guard on the existing ownership check at `:99-100`).
- **AC-4.4 (legit multi-decision NOT over-blocked — the regression a boolean flag would cause)** Two advice calls on the same `hand_id` where `hand.cards` **changes between them** (simulate a real hit: update the seeded hand's `cards` from 2→3 cards, both guesses correct) increment `current_streak` by **2** (once per distinct decision). This proves the fix keys on card-count, not hand identity.

---

### T5 — M3: Dealer natural blackjack pushes player 3-card 21  [P1]

**Files:** `backend/game/blackjack/state.py` — `resolve_hand` (`:22-65`).

**Change:** Before the generic value compare (i.e. before `:53`, after the player-blackjack branch at `:47-51`), add:
```python
if eng.is_blackjack(dealer_cards):
    return ("push", bet) if eng.is_blackjack(cards) else ("loss", 0)
```
`eng.is_blackjack` is confirmed in `backend/game/blackjack/engine.py:109-111` as `len(cards) == 2 and hand_value(cards) == 21`, so a 3-card 21 is correctly *not* a blackjack and loses to a dealer natural. Pure function — no DB change.

**ACs (pure-function unit tests on `resolve_hand`, no DB):**
- **AC-5.1** Player `[9,5,7]` (3-card 21) vs dealer `[A,K]` → `("loss", 0)` (was incorrectly `("push", bet)`).
- **AC-5.2** Player blackjack `[A,K]` vs dealer `[A,K]` → `("push", bet)` (two-natural push still holds).
- **AC-5.3** Player 20 (`[10,10]`) vs dealer non-natural 20 (e.g. `[10,5,5]`) → `("push", bet)` (equal non-natural totals still push when the dealer is *not* natural — the new branch must not over-fire).

---

### T6 — M4: Poll hooks swallow errors → infinite spinner  [P1]

**Files:**
- Hooks: `frontend/src/hooks/useTablePoll.ts` (`:24-32`), `frontend/src/hooks/useHoldemPoll.ts` (`:20-26`), `frontend/src/hooks/usePokerPoll.ts` (`:23-31`).
- Pages: `frontend/src/pages/Table.tsx` (loading guard at `:239-247`), `frontend/src/pages/HoldemTablePage.tsx` (loading guard at `:93-101`), `frontend/src/pages/PokerTablePage.tsx` (analogous loading guard).

**Change (minimal, typed, no `any`):** Each hook currently early-returns on `result.error || result.data === null`, so a failing `/state` fetch leaves the page in a permanent spinner. Add an error surface:
1. Hooks accept an optional `onError?: (msg: string) => void` callback and, after **N consecutive failures** (suggest N = 3 to ride out transient blips on the 3 s cadence), invoke `onError(result.error ?? "…")`; reset the counter to 0 on any successful poll. Keep the existing store-reconcile on success. Type the callback parameter explicitly (`string`); no `any`.
2. Each consuming page holds a `pollError` state (`useState<string | null>(null)`), passes `setPollError` as `onError`, and — when `pollError` is set and there's still no state to render — renders an **error panel** (`role="alert"`) with a "Back to lobby" navigation and a "Retry" affordance (Retry clears `pollError` and re-invokes the existing `refresh()` where one exists, e.g. `HoldemTablePage.refresh` at `:41-49`; for `Table.tsx`, Retry clears the error so the next poll tick re-attempts). Replace the unconditional spinner branch with: if `pollError` → error panel; else if no state yet → spinner.

**ACs (Vitest + jsdom + MSW; one test per page, mock the `/state` route to 500):**
- **AC-6.1** `Table.tsx`: with `GET /api/tables/:id/state` mocked to fail, after the failure threshold the page renders an element with `role="alert"` (the error panel) and a control to return to the lobby / retry — **not** a permanent `role="status"` spinner.
- **AC-6.2** `HoldemTablePage.tsx`: same assertion against `GET /api/holdem/tables/:id/state` mocked to 500 — error panel + Back-to-lobby/Retry, no infinite `aria-busy` spinner.
- **AC-6.3** `PokerTablePage.tsx`: same assertion against `GET /api/poker/tournaments/:id/state` mocked to 500.

*(Mirror the MSW `setupServer` wiring in `frontend/tests/HoldemTablePage.test.tsx`. `tsc --noEmit` must stay clean — the new `onError` param is optional so existing call sites compile unchanged.)*

---

### T7 — L2: Negative-bet & table-bound validation  [P2]

**Files:**
- `backend/schemas.py` — `DealIn` (`:141-143`): change `bet: int` → `bet: int = Field(gt=0)`.
- `backend/models.py` — `CasinoTable` (`:89-106`): add `CheckConstraint("min_bet > 0", name="min_bet_positive")` and `CheckConstraint("max_bet >= min_bet", name="max_bet_ge_min_bet")` to `__table_args__` (`:104-106`).
- **Migration:** add `backend/migrations/006_table_bet_constraints.sql` (next number after `005_study.sql`). Idempotent Postgres DDL: add the two CHECK constraints via a `DO $$ … IF NOT EXISTS … $$` guard (mirror the constraint-add pattern in `005_study.sql:34-47`, checking `pg_constraint.conname`). This is for prod/Postgres parity; **the ORM `create_all` path already enforces the new constraints in tests** (per the harness facts above) — no test depends on the SQL file.

**ACs:**
- **AC-7.1** `POST /api/tables/{id}/deal` with `{"bet": 0}` and with `{"bet": -100}` is rejected with **422** (Pydantic `gt=0`), not accepted.
- **AC-7.2** Constructing/committing a `CasinoTable` with `min_bet <= 0` (e.g. `min_bet=0`) raises an integrity/constraint error under the test DB (the ORM `CheckConstraint` is honored by `create_all`). *(Tester: assert the insert fails — `IntegrityError` / `sqlite3.IntegrityError` — at `flush`/`commit`.)*
- **AC-7.3** Constructing/committing a `CasinoTable` with `max_bet < min_bet` raises the same constraint error; a valid `0 < min_bet <= max_bet` table still commits cleanly (no false positive).

---

### T8 — L3: Leaderboard requires auth  [P2]

**Files:** `backend/routers/leaderboard.py` — `get_leaderboard` (`:21-27`).

**Decision (state explicitly):** Require authentication at minimum — add the `CurrentUser` dependency so the endpoint is no longer anonymously reachable. **Keep** the existing response shape (`chip_balance`, `user_id`/UUIDs) unchanged for this slice: the leaderboard is an intentionally public-within-the-app ranking, and changing the payload would ripple into `frontend/src/pages/Leaderboard.tsx` and `LeaderboardRowOut`. Trimming exact balances / internal UUIDs is deferred (see Out of scope). The minimal, grader-probe-satisfying change is "no longer unauthenticated."

**Change:** Add `current_user: CurrentUser` to the handler signature (import `from backend.auth import CurrentUser`). The handler body is otherwise unchanged.

**ACs:**
- **AC-8.1** `GET /api/leaderboard` with a valid auth (the `client` fixture) still returns 200 and the existing top-N rows (regression: shape unchanged).
- **AC-8.2** `GET /api/leaderboard` with **no** authenticated user is rejected (401/403). *(Tester: hit the app via a transport with the auth dependency override removed / returning no user, mirroring how the suite exercises unauthenticated paths; assert non-200.)*

---

### T9 — L4: Session-review enumeration oracle → uniform 404  [P2]

**Files:** `backend/routers/sessions.py` — `_get_session_review` (`:34-69`, specifically the 404 vs 403 branching at `:51-69`).

**Change:** Collapse the distinguishable responses into a **uniform 404** so a caller cannot tell "session does not exist" from "exists but you don't own a hand in it." Specifically:
- Session not found → `404 "Session not found"` (keep).
- `caller_hand is None` (whether the session is finished or in progress) → return the **same** `404` with the **same** detail string as not-found (replace the current `403`/distinct-detail branch at `:62-69`). Do not leak existence via status code *or* detail text.

**ACs:**
- **AC-9.1** `GET /api/sessions/{id}/review` for a non-existent session id → 404.
- **AC-9.2** `GET /api/sessions/{id}/review` for a session that exists but where the caller owns no hand (in-progress) → **404 with the identical status and detail** as AC-9.1 (no 403, no distinguishing detail string). Assert both `status_code` and `json()["detail"]` match the not-found case.
- **AC-9.3** A caller who *does* own a hand in the session still gets their review (200) — owner path unregressed.

---

### T10 — L7: Chat readable by non-seated users  [P2]

**Files:** `backend/routers/chat.py` — `get_messages` handler (`:97-107`) and `_get_messages` helper (`:172-192`). The seated check `_is_seated` already exists (`:113-127`) and is used by the POST path (`:146-147`).

**Change:** Apply the same seated-membership gate to the GET path. Add `current_user: CurrentUser` is already present on `get_messages` (`:101`) — thread it down: before fetching messages, call `_is_seated(table_kind, table_id, current_user, db)` and raise `403 "You must be seated at this table to chat"` when false (matching the POST path's behavior at `:146-147`). Keep the `table_kind not in _VALID_TABLE_KINDS → 404` guard. The simplest implementation: move/duplicate the `_is_seated` check into `_get_messages` (passing `current_user`), or guard in the handler before delegating.

**ACs:**
- **AC-10.1** A seated user can `GET /api/chat/{kind}/{table_id}/messages` and read the scrollback (200) — regression on the existing read path.
- **AC-10.2** A *non-seated* authenticated user (`other_client`, never seated at that table) gets **403** from the GET, matching the POST path's gate. (Seed a table + seat `TEST_USER_ID`; `OTHER_USER_ID` reads → 403.)
- **AC-10.3** An unknown `table_kind` still returns 404 (guard unregressed).

---

## Test strategy summary (race fixes only)

For **T2 (H1)** and **T3 (M1)** the SQLite harness no-ops `with_for_update()`, so a literal two-coroutine balance race cannot reproduce the bug. Each race fix is therefore pinned by three tests:

1. **Structural** — `inspect.getsource(handler)` asserts the `with_for_update` lock is present on the right SELECT (regression guard against silent removal; mirrors `test_action_race.py:38`).
2. **Behavioral** — pre-insert a row that collides on a real UNIQUE constraint so the second write raises `IntegrityError`; assert the response is a clean **409** (not 500). SQLite *does* enforce UNIQUE, so this path runs for real.
3. **Sequential correctness** — drive the handler twice in sequence; assert the money/seat invariant (debited/seated exactly once; second call cleanly rejected when it should be).

T1 (C1) is pinned by pure-helper unit tests; T5 (M3) by pure-function unit tests on `resolve_hand`; T6 (M4) by MSW-mocked failed-fetch frontend tests; T7–T10 by ordinary HTTP-endpoint and ORM-constraint tests.

---

## Migration task (called out per deliverable §4)

T7 includes a single new migration file `backend/migrations/006_table_bet_constraints.sql` adding the two `CasinoTable` CHECK constraints, written idempotently (`DO $$ … IF NOT EXISTS … $$` guarding on `pg_constraint.conname`, mirroring `005_study.sql:34-47`). `backend/migrate.py` auto-discovers `*.sql` lexicographically and applies pending files once at boot, so no code wiring is needed beyond dropping the file in. **The pytest suite does not exercise this file** — it builds the schema from the ORM via `Base.metadata.create_all`, which already carries the new `CheckConstraint`s; the SQL file exists for prod/Postgres parity and is verified by the CI Postgres job.

---

## Risk / sequencing note

- **All ten tasks are independent** and touch disjoint files — they can be implemented (and committed) in any order, or in parallel. The only soft coupling is conceptual (T2/T3 share the race-test pattern; T9/T10 share the auth-gate pattern), not code-level.
- T1 (critical, anonymous) and T6 (the one user-visible "missing error state" the grader probes) are the highest-value; do them first if prioritizing.
- T7's migration file changes nothing the test suite asserts against (ORM path), so it carries the least regression risk; its ORM `CheckConstraint` change is the part tests pin.
- **Definition of done — the full suite must be green at the end:**
  - `python -m pytest backend/tests/ -v` (currently 118+ tests; all pass, including the new ones)
  - `ruff check backend` clean
  - `cd frontend && npx tsc --noEmit` clean
  - `cd frontend && npm test -- --run` green
  - `cd frontend && npm run build` succeeds
- Per the project workflow: tests are written first (mapped 1:1 to the ACs above) and expected to fail; the implementer makes them pass task-by-task; the oracle review fires on the branch vs `main` before the work is declared done.

---

## Out of scope (this slice)

- Trimming the leaderboard payload (hiding exact `chip_balance` / internal UUIDs). T8 only adds auth; payload redaction is a separate, frontend-rippling change.
- Implementing true Postgres concurrency integration tests (a real Postgres harness firing genuinely concurrent requests). The structural + behavioral + sequential trio is the agreed substitute under the SQLite suite.
- Blackjack split (still 501 by design — see project CLAUDE.md "Known limitations").
- Any of the audit's INFO-level items not in the P0–P2 scope above, and the refuted/cleared candidate findings.
- Refactoring routers to dispatch through `GAME_REGISTRY`. Untouched here.

---

## Open questions

1. **M2 guard choice (T4):** the plan defaults to gating the streak increment on `hand.status` being live/active. If the legitimate advice call actually fires *after* the hand resolves (so the hand is already terminal at advice time), the status gate would break the happy path (AC-4.1) — in which case switch to a per-hand "already advised" marker. The tester should write AC-4.1 first; its pass/fail under the status gate decides this. **No external answer needed — the test resolves it.**
2. **T2 / T3 collision construction:** the exact UNIQUE constraint to collide on (`PokerSeat`/`TableSeat`) must be confirmed against `backend/models.py` at test-writing time; the behavioral ACs (AC-2.3, AC-3.2) name the candidates but the tester pins the real one. **No blocking answer needed.**

No open questions block starting T1.
