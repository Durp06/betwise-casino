# Centralized Money System

Status: APPROVED — ready for tester → implementer.
Date: 2026-06-03
Branch suggestion: `feat/centralized-money-system`

## 1. Goal & non-goals

### Goal
Make BetWise's bankroll one coherent, well-named thing:

1. Raise the starting balance from `100_000` cents ($1,000.00) to
   **`5_000_000` cents ($50,000.00)**, expressed as a single Python constant
   `STARTING_BALANCE_CENTS` that every Python code path references.
2. Reset **all existing users** to the new amount and bump the SQL column
   DEFAULT, via one new forward migration.
3. Make the player's account bankroll (`chip_balance` — the cashier balance,
   money not committed on a table) visible on **every** page through one shared
   client-side balance source: a small Zustand wallet store + a `useBalance()`
   hook, rendered by a persistent `<BalanceHeader/>`.
4. Keep the reset-chips bailout consistent: it refills to
   `STARTING_BALANCE_CENTS`, still gated by the unchanged `< 1000` eligibility
   threshold.
5. Update CLAUDE.md convention #5 and the tests that assert the old default.

### Non-goals (explicitly out of scope — do NOT do these)
- **No transaction ledger.** Keep the existing locked column-mutation model on
  `users.chip_balance`. No new `transactions`/`ledger` table.
- **Do NOT touch the poker tournament winner-take-all / anti-mint payout.** That
  is a security guard from a prior audit; bankroll already reconciles on
  buy-in/payout. Leave `backend/routers/poker*.py` and the holdem payout path
  alone.
- **No bet / table-stakes rebalance.** Even though $50k makes the current
  `min_bet`/`max_bet` (e.g. 500 / 50_000) feel small, do not change table
  stakes, blinds, buy-in ranges, or `PokerSetup` defaults.
- **No new endpoints.** The frontend reads balance from the existing
  `GET /api/users/me` (`getMe()`); the wallet store is purely client-side.
- **Do NOT rename `chip_balance`** in the DB, schema, or API. "Wallet" is a
  frontend-store concept only.

## 2. Background (verified current state)

The backend money store is **already one column** — `User.chip_balance`
(integer cents). There is no scattered balance state to consolidate on the
backend; what is scattered is the **literal `100_000`** and the **absence of a
persistent balance display** on the frontend.

Verified references (file:line):

- `backend/models.py:66` — `chip_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=100_000)`.
- `backend/models.py:82` — `CheckConstraint("chip_balance >= 0", name="chip_balance_non_negative")`. Resetting to a positive `5_000_000` trivially satisfies this.
- `backend/routers/users.py:178` — `_upsert_user` constructs `User(..., chip_balance=100_000, ...)`.
- `backend/routers/users.py:89,100` — `reset_chips` docstring says "Reset chip balance to 100000"; sets `user.chip_balance = 100_000` only when `user.chip_balance >= 1000` is false (else raises HTTP 409 at line 94-98). The `< 1000` gate must stay.
- `backend/dev_seed.py:33` — `session.add(User(id=DEV_USER_ID, username="dev", chip_balance=100_000))`.
- `backend/migrations/001_initial.sql:24` — `chip_balance INTEGER NOT NULL DEFAULT 100000 CHECK (chip_balance >= 0)`. **Historical — do NOT edit.**
- `backend/migrate.py:50-92` — `_split_statements` splits a `.sql` file on top-level `;`, treating `$$ ... $$` dollar-quoted regions as opaque and stripping full-line `--` comments. Each plain statement (no `$$`) is delimited by a top-level `;`. Highest existing migration: `007_hand_advice_graded.sql` → **next number is `008`**.
- `frontend/src/api/client.ts:101` — `getMe()` returns `ApiResult<UserStats>` (includes `chip_balance`); `client.ts:112` — `resetChips()`.
- `frontend/src/types/index.ts:45` — `UserStats.chip_balance: number`.
- `frontend/src/utils/money.ts:11` — `formatMoney(cents: number): string`. `formatMoney(5_000_000)` → `"$50,000"` (whole-dollar, no decimals).
- `frontend/src/i18n.ts:5` — `t(key)` passthrough helper.
- `frontend/src/store/gameStore.ts` — Zustand store; has **no** balance field today.
- `frontend/src/pages/Profile.tsx:141` — the only place the bankroll renders today: `{formatMoney(stats.chip_balance)}`, fed by `getMe()` in the page's own `load()` (Profile.tsx:35-48).
- `frontend/src/pages/Lobby.tsx` — header at lines 87-119; **does not** call `getMe()` or render balance today.
- `frontend/src/pages/HoldemLobby.tsx`, `frontend/src/pages/PokerSetup.tsx` — no balance display today.
- `frontend/src/App.tsx:72-166` — all protected routes are wrapped individually in `<AuthGate>`. There is **no shared layout component** between `AuthGate` and the page; the persistent header has to be introduced (Task 8).

## 3. Acceptance criteria

Each AC is atomic and maps 1:1 to a test (see §5). Grouped Backend / Frontend / Docs.

### Backend

- **AC-B1.** A module-level constant `STARTING_BALANCE_CENTS` exists in
  `backend/models.py` and equals `5_000_000`.
- **AC-B2.** `User.chip_balance`'s ORM column default is
  `STARTING_BALANCE_CENTS` (not a literal). A `User()` created with no
  `chip_balance` and flushed to the DB has `chip_balance == 5_000_000`.
- **AC-B3.** `POST /api/users/me` for a brand-new user returns
  `chip_balance == 5_000_000` (i.e. `_upsert_user` uses the constant, not
  `100_000`).
- **AC-B4.** `POST /api/users/me/reset-chips` for a user with
  `chip_balance < 1000` sets and returns `chip_balance == 5_000_000`.
- **AC-B5.** `POST /api/users/me/reset-chips` for a user with
  `chip_balance >= 1000` still returns **HTTP 409** and does not change the
  balance (threshold unchanged).
- **AC-B6.** No `100_000` (or `100000`) literal remains in the three production
  starting-balance paths: `backend/models.py` (User default),
  `backend/routers/users.py` (`_upsert_user` + `reset_chips`),
  `backend/dev_seed.py`. Each references `STARTING_BALANCE_CENTS`.
- **AC-B7.** A new migration file `backend/migrations/008_centralize_starting_balance.sql`
  exists and contains, as **two separate top-level statements**:
  (a) `ALTER TABLE users ALTER COLUMN chip_balance SET DEFAULT 5000000;`
  (b) `UPDATE users SET chip_balance = 5000000;`
- **AC-B8.** `backend.migrate._split_statements` applied to the new migration's
  text returns a list whose statements include both the `ALTER ... SET DEFAULT`
  and the `UPDATE users ...` as **distinct** entries (asyncpg single-statement
  compatibility), and neither is dropped/merged.
- **AC-B9.** After the migration runs against a DB that has pre-existing users
  with arbitrary balances, every user row has `chip_balance == 5_000_000` and
  the column DEFAULT is `5000000` (a subsequent DEFAULT-inserted row gets
  `5_000_000`).

### Frontend

- **AC-F1.** A `useBalance()` hook backed by a Zustand wallet store exposes
  `{ balance: number | null, loading: boolean, error: string | null, refresh: () => Promise<void> }`
  (exact shape may be refined by the tester, but must include a numeric balance,
  loading, error, and a refresh trigger). Calling `refresh()` invokes `getMe()`
  and stores `data.chip_balance` on success; on `{ error }` it stores the error
  and leaves any prior balance untouched.
- **AC-F2.** A `<BalanceHeader/>` component renders the formatted balance via
  `formatMoney`. Given a wallet balance of `5_000_000` it shows `"$50,000"`.
- **AC-F3.** `<BalanceHeader/>` shows a loading state (e.g. a `role="status"`
  element / skeleton) while `loading` is true and `balance` is null, and an
  error state (e.g. `role="alert"`) when `error` is set and `balance` is null —
  no happy-path-only render.
- **AC-F4.** `<BalanceHeader/>` is rendered on the lobby and on all three game
  surfaces: `Lobby` (blackjack lobby), `HoldemLobby`, `PokerSetup`, and the
  in-game pages `Table` (blackjack), `HoldemTablePage`, `PokerTablePage`.
  (Mounting once in a shared layout that wraps these routes satisfies this for
  all of them — see Task 8.)
- **AC-F5.** On lobby mount the balance is fetched (`getMe()` called once) and
  the formatted value appears.
- **AC-F6.** After a money-moving action completes, the balance refetches. The
  canonical mechanism is: **the wallet store's `refresh()` is invoked after a
  successful money-moving mutation.** Concretely, at least these call sites
  trigger a refresh after the awaited mutation resolves without error:
  blackjack deal (`Table.tsx` deal handler), hold'em join and leave
  (`HoldemLobby`/`HoldemTablePage`), poker buy-in/create
  (`PokerSetup`/`PokerTablePage`). The test asserts that after such a mutation
  the wallet store issues a fresh `getMe()` and the displayed balance updates to
  the server's new value (no stale balance).
- **AC-F7.** No `any` types are introduced; `cd frontend && npx tsc --noEmit`
  is clean.
- **AC-F8.** `cd frontend && npm run build` succeeds.
- **AC-F9.** All user-facing strings added (labels, loading/error text) go
  through `t()`.

### Docs

- **AC-D1.** `CLAUDE.md` project convention #5 reads the new value, e.g.
  "User always starts with `5_000_000` (= $50,000.00)." No remaining
  "100000 (= $1,000.00)" in convention #5.

## 4. Task breakdown

Ordered so the tester can write a failing test before each task. Backend first,
then frontend. Each task is ~one commit.

### Task 1 — Introduce `STARTING_BALANCE_CENTS` and use it as the model default
- Add `STARTING_BALANCE_CENTS = 5_000_000` at module level in
  `backend/models.py` (above the `User` class, near the top after imports).
- Change `backend/models.py:66` default from `100_000` to
  `STARTING_BALANCE_CENTS`.
- Files: `backend/models.py`.
- Satisfies: **AC-B1, AC-B2**, part of **AC-B6**.

### Task 2 — Point `_upsert_user` and `reset_chips` at the constant
- In `backend/routers/users.py`, import `STARTING_BALANCE_CENTS` from
  `backend.models` (lazy import inside the helper is fine per CLAUDE.md, matching
  the existing `from backend.models import User  # noqa: PLC0415` pattern).
- `_upsert_user` (~line 178): `chip_balance=STARTING_BALANCE_CENTS`.
- `reset_chips` (~line 100): `user.chip_balance = STARTING_BALANCE_CENTS`. Update
  the docstring at line 89 to say `STARTING_BALANCE_CENTS`. Leave the `>= 1000`
  gate (line 94) untouched.
- Files: `backend/routers/users.py`.
- Satisfies: **AC-B3, AC-B4, AC-B5**, part of **AC-B6**.

### Task 3 — Use the constant in dev_seed
- `backend/dev_seed.py:33`: `chip_balance=STARTING_BALANCE_CENTS` (import from
  `backend.models`).
- Files: `backend/dev_seed.py`.
- Satisfies: part of **AC-B6**.

### Task 4 — Add migration `008_centralize_starting_balance.sql`
- Create `backend/migrations/008_centralize_starting_balance.sql` with a header
  comment and two separate statements (see §6 for exact SQL). Mirror the
  comment style of `007_hand_advice_graded.sql`. Use the literal `5000000` in
  SQL with a comment noting it **must match `STARTING_BALANCE_CENTS`**.
- Files: `backend/migrations/008_centralize_starting_balance.sql`.
- Satisfies: **AC-B7, AC-B8, AC-B9**.

### Task 5 — Wallet store + `useBalance()` hook
- Add a small Zustand wallet store. Either extend `gameStore.ts` with
  `walletBalance: number | null` + setters, or (preferred for separation) add
  `frontend/src/store/walletStore.ts`. Expose a `useBalance()` hook
  (`frontend/src/hooks/useBalance.ts`) that reads the store and provides
  `refresh()` which calls `getMe()` and writes `data.chip_balance` (handling the
  `{ data, error }` contract — set error on failure, keep prior balance).
- No `any`; type the store state explicitly.
- Files: `frontend/src/store/walletStore.ts` (new), `frontend/src/hooks/useBalance.ts` (new).
- Satisfies: **AC-F1**, part of **AC-F7**.

### Task 6 — `<BalanceHeader/>` component
- Create `frontend/src/components/BalanceHeader.tsx`. Reads `useBalance()`.
  Renders `formatMoney(balance)` when present; a `role="status"` loading element
  when `loading && balance === null`; a `role="alert"` element when
  `error && balance === null`. All text via `t()`. Tailwind only.
- Files: `frontend/src/components/BalanceHeader.tsx` (new).
- Satisfies: **AC-F2, AC-F3, AC-F9**, part of **AC-F7**.

### Task 7 — Fetch on mount + refresh-on-action wiring
- On lobby mount, call `refresh()` once (e.g. in `Lobby.tsx`'s mount effect, or
  in the shared layout from Task 8 — pick one, document it).
- After each money-moving mutation resolves without error, call the wallet
  `refresh()`:
  - `frontend/src/pages/Table.tsx` — after a successful `dealHand` (and after a
    hand finishes / payout reconciles via the existing poll, if cleanest).
  - `frontend/src/pages/HoldemLobby.tsx` — after `joinHoldemTable` succeeds.
  - `frontend/src/pages/HoldemTablePage.tsx` — after `leaveHoldemTable` succeeds.
  - `frontend/src/pages/PokerSetup.tsx` — after `createPokerTournament` succeeds
    (buy-in deducted server-side).
  - `frontend/src/pages/PokerTablePage.tsx` — after the tournament finalizes /
    payout, if the page has a finalize path; otherwise rely on the lobby-mount
    refresh.
- **Recommendation:** ONE consistent mechanism = call `walletStore.refresh()`
  from the page handler immediately after the awaited mutation's `{ error }` is
  falsy. Do **not** add balance polling to `useTablePoll`/`useHoldemPoll` — keep
  the refresh explicit and tied to mutations to avoid extra request load and to
  keep the poll hooks single-responsibility.
- Files: `Table.tsx`, `HoldemLobby.tsx`, `HoldemTablePage.tsx`, `PokerSetup.tsx`,
  `PokerTablePage.tsx`, `Lobby.tsx`.
- Satisfies: **AC-F5, AC-F6**.

### Task 8 — Mount `<BalanceHeader/>` so it appears on every page
- There is no shared layout today (App.tsx wraps each route in `<AuthGate>`
  individually). Choose the lowest-risk approach:
  - **Preferred:** add a thin `AppLayout` wrapper (or render `<BalanceHeader/>`
    inside `AuthGate` so every protected route gets it). Ensure it appears on
    `Lobby`, `HoldemLobby`, `PokerSetup`, `Table`, `HoldemTablePage`,
    `PokerTablePage`. Do **not** show it on `/login`.
  - If a global mount causes layout/visual regressions on some pages, fall back
    to rendering `<BalanceHeader/>` in each of the six page headers explicitly.
- Files: `frontend/src/App.tsx` (and/or the six pages' headers).
- Satisfies: **AC-F4**, part of **AC-F8**.

### Task 9 — Update CLAUDE.md and the value-asserting tests
- `CLAUDE.md` convention #5 → new value (**AC-D1**).
- Update the backend tests that assert the **default/starting** value (not
  arbitrary fixture overrides) — see §5 for the exact list. Replace asserted
  `100_000` starting values with `STARTING_BALANCE_CENTS` (import from
  `backend.models`) or `5_000_000`.
- Update the frontend test fixture(s) that mock `chip_balance` for a starting
  user where the value is load-bearing.
- Files: `CLAUDE.md`, plus the test files listed in §5.
- Satisfies: **AC-D1**; keeps CI green.

## 5. Test plan (AC → concrete test)

New test modules (tester writes these to fail first):

- `backend/tests/test_starting_balance.py`
  - `test_starting_balance_constant_is_5_000_000` → **AC-B1**.
  - `test_new_user_default_balance_via_orm` (create `User()`, flush, assert
    `chip_balance == STARTING_BALANCE_CENTS`) → **AC-B2**.
  - `test_upsert_me_new_user_gets_starting_balance` (POST `/api/users/me`,
    assert body `chip_balance == 5_000_000`) → **AC-B3**.
  - `test_no_old_literal_in_starting_balance_paths` (read the source of
    `backend/models.py`, `backend/routers/users.py`, `backend/dev_seed.py`;
    assert no `100_000`/`100000` in the User-default / upsert / reset / dev-seed
    lines) → **AC-B6**.
- `backend/tests/test_reset_chips_balance.py`
  - `test_reset_chips_eligible_refills_to_starting_balance` (seed user with
    `chip_balance=500`, POST reset, assert `5_000_000`) → **AC-B4**.
  - `test_reset_chips_ineligible_returns_409` (seed user with
    `chip_balance=2000`, POST reset, assert 409 and unchanged balance) →
    **AC-B5**.
- `backend/tests/test_migration_008.py`
  - `test_migration_file_exists_and_has_two_statements` (read the `.sql`, run it
    through `backend.migrate._split_statements`, assert both the ALTER and
    UPDATE appear as distinct statements) → **AC-B7, AC-B8**.
  - `test_migration_resets_all_users_and_default` (against the test engine:
    insert users with mixed balances, execute the two statements, assert all
    rows == `5_000_000`; insert a DEFAULT row and assert it gets `5_000_000`).
    Note: SQLite (test DB) supports `ALTER TABLE ... ALTER COLUMN ... SET
    DEFAULT`? It does **not** in older SQLite. If the test engine cannot run
    `ALTER COLUMN SET DEFAULT`, the tester should assert the `UPDATE` behavior
    directly and assert the ALTER statement's presence/shape textually (the
    DEFAULT bump is Postgres-prod behavior). Tester picks the approach that runs
    green on the in-memory SQLite engine → **AC-B9**.

New frontend test files:

- `frontend/tests/useBalance.test.tsx` (MSW mocking `GET /api/users/me` per the
  `ChipyPanel.test.tsx` `setupServer` pattern)
  - refresh success stores `chip_balance` → **AC-F1**.
  - refresh error keeps prior balance and exposes `error` → **AC-F1**.
- `frontend/tests/BalanceHeader.test.tsx`
  - renders `"$50,000"` for balance `5_000_000` → **AC-F2**.
  - shows `role="status"` while loading + null, `role="alert"` on error + null →
    **AC-F3**.
- `frontend/tests/BalanceRefresh.test.tsx` (or extend a page test)
  - on lobby mount `getMe` is requested and balance shows → **AC-F5**.
  - after a mocked money-moving mutation, a second `getMe` fires and the
    displayed balance updates → **AC-F6**.
- AC-F4 (presence on all surfaces) can be asserted either by a render test on
  the layout/App or by a per-page presence assertion. Tester chooses; minimum is
  one test proving `<BalanceHeader/>` mounts for a protected route.
- **AC-F7 / AC-F8** are verified by CI commands, not a unit test:
  `cd frontend && npx tsc --noEmit` and `cd frontend && npm run build`.

Existing tests to UPDATE (only where the value is the *default/starting*
balance, not an arbitrary seeded fixture):

- `frontend/tests/HandHistory.test.tsx:42` — `chip_balance: 100000` in a mocked
  `UserStats` for the logged-in user. If the test treats this as the player's
  starting bankroll, bump to `5000000`; if it's just a non-load-bearing stub,
  it may stay — tester decides per assertion.
- `frontend/tests/money.test.ts:6` — `expect(formatMoney(100000)).toBe("$1,000")`
  is a **formatter** test, not a starting-balance test. **Leave it** (it tests
  `formatMoney`, which is unchanged). Optionally add
  `expect(formatMoney(5_000_000)).toBe("$50,000")`.
- `backend/tests/test_holdem_endpoints.py:242,245` — asserts `chip_balance`
  `90_000` then `100_000` after buy-in/leave. These derive from carol/the user
  being **explicitly seeded** with `chip_balance=100_000` (line 224 etc.), not
  the default, so the buy-in math is self-consistent. **Leave as-is** unless the
  seed value is removed. Do **not** change unless a test seeds with the default
  and then asserts the starting number.
- `backend/tests/test_endpoints.py:725` — `initial_balance = 100_000` is a local
  variable for payout math, paired with an explicit seed. **Leave as-is.**
- All `seed_user(..., chip_balance=100_000)` calls and
  `backend/tests/conftest.py:124` (`seed_user` default param) are **explicit
  fixture values**, independent of the production default. **Leave them** — they
  do not assert the starting balance and changing them risks breaking buy-in /
  bet-size math in those tests. (Optional: the tester may bump conftest's
  default to `STARTING_BALANCE_CENTS` for realism, but only if every dependent
  test still passes; default to leaving it.)

Net: the only *required* edits to existing tests are any that assert a brand-new
user's balance equals the old default. Grep confirms none of the current backend
tests assert the *upsert default* (they all seed explicitly), so the binding
existing-test change is the **frontend mock fixture** where `100000` represents
the player's starting bankroll, plus CLAUDE.md.

## 6. Migration & rollback notes

### Exact SQL (`backend/migrations/008_centralize_starting_balance.sql`)

```sql
-- 008_centralize_starting_balance.sql
-- Centralize the starting bankroll at 5,000,000 cents ($50,000.00).
-- 5000000 MUST match backend/models.py::STARTING_BALANCE_CENTS.
-- Idempotent: re-running sets the same DEFAULT and the same balance.

ALTER TABLE users ALTER COLUMN chip_balance SET DEFAULT 5000000;

UPDATE users SET chip_balance = 5000000;
```

### Statement-splitting compatibility
`backend/migrate.py::_split_statements` splits on top-level `;` and treats only
`$$ ... $$` regions as opaque. This file has **no** `$$` blocks, so it yields
exactly two statements:
1. `ALTER TABLE users ALTER COLUMN chip_balance SET DEFAULT 5000000`
2. `UPDATE users SET chip_balance = 5000000`

Each is executed individually via `conn.execute(text(stmt))`, satisfying
asyncpg's one-command-per-statement requirement. The `-- ` header lines are
stripped by the splitter's full-line-comment pass.

### CHECK constraint
`chip_balance >= 0` (models.py:82 / 001_initial.sql:24) is satisfied — `5000000`
is positive. The migration only ever sets a positive value, so the constraint
never trips.

### Idempotency / ledger
`migrate.py` records applied files in `schema_migrations`, so 008 runs once per
deploy. Even if re-run, both statements are idempotent (same DEFAULT, same
UPDATE target value).

### Rollback
There is no down-migration convention in this repo (forward-only). To revert,
ship a `009_*.sql` that sets the DEFAULT and balances back to `100000`. The
`UPDATE users SET chip_balance = 5000000` is destructive to current balances by
design (decision #2: reset ALL users) — note this in the deploy log.

## 7. Risks / edge cases

- **A user seated in a hold'em/poker game when the reset migration runs.** The
  in-play stack on a `holdem_seats` row / tournament state is **separate** from
  `users.chip_balance`. The migration resets the cashier bankroll to
  `5_000_000` but does **not** touch committed stacks. Consequence: when they
  cash out / the tournament finalizes, the cashed-out chips are **added** to the
  already-reset `5_000_000`, so a mid-game player ends slightly above
  `5_000_000`. This is acceptable for a fake-money study tool and is consistent
  with decision #2 ("reset ALL existing users") + non-goal ("do not touch the
  payout path"). Do not attempt to net out in-play stacks.
- **`formatMoney` display.** `formatMoney(5_000_000)` → `"$50,000"` (whole
  dollars, comma-grouped, no decimals) per `money.ts`. The BalanceHeader test
  must assert `"$50,000"`, not `"$50,000.00"`.
- **SQLite vs Postgres in the migration test.** Prod is Postgres (asyncpg);
  tests use in-memory SQLite. `ALTER TABLE ... ALTER COLUMN ... SET DEFAULT` is
  Postgres syntax and may not execute on the SQLite test engine. The migration
  test (§5) should assert the `UPDATE` semantics against SQLite and assert the
  ALTER statement's presence/shape **textually** via `_split_statements`, rather
  than executing the ALTER on SQLite. This keeps the test green while still
  proving prod will get the DEFAULT bump.
- **Balance refresh request volume.** Wiring `refresh()` to mutations (not
  polling) avoids adding a steady stream of `getMe()` calls. Keep it
  mutation-triggered + lobby-mount only.
- **Stale balance after a blackjack hand resolves.** Blackjack payouts settle
  server-side at dealer-turn via the poll, not via an explicit mutation the page
  awaits. Ensure the blackjack hand-finished path triggers a `refresh()` (e.g.
  when the poll observes the hand reached a terminal `outcome`), so the header
  is not stale after a win/loss. The implementer should pick the cleanest hook
  in `Table.tsx` (terminal-outcome effect) — this is the one place where "after
  the awaited mutation" is insufficient.

## 8. Open questions
None blocking. The design decisions are approved. The two implementer judgment
calls (shared-layout vs per-page header mount in Task 8; blackjack
terminal-outcome refresh hook in Task 7) are bounded and documented above —
neither changes the ACs.
