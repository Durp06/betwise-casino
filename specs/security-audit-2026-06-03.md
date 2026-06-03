# BetWise Casino — Security Audit (2026-06-03)

**Method:** adversarial multi-agent audit — 15 finders (per-router + cross-cutting auth/concurrency/info-leak sweeps) across the whole backend + frontend, then every candidate finding re-read and adversarially verified against the real code (63 agents total). The critical was reproduced end-to-end against a real `uvicorn` server, not just static reasoning.

**Result:** 27 verified findings — **1 critical, 2 high, 6 medium, 10 low, 8 info** (deduplicated to ~16 distinct issues below). 17 candidate findings were checked and **cleared** as not-exploitable (see §"What's already solid").

This maps directly to the grader's stated attack plan (no-token / forged-JWT / id-swap / double-submit races / unauthorized cross-user access / missing loading+error states / explain-your-logic).

---

## Grader attack-vector → what we found

| Grader will try… | Verdict |
|---|---|
| 1. No token / forged / expired JWT | **Auth core is solid.** JWT alg-confusion, expired-token, and forged-token bypasses were tested and refuted. The one anonymous hole is the **critical path-traversal** (not a JWT issue — an unauthenticated static route). |
| 2. Swap ids in URLs to read others' data | **Mostly solid.** No high-impact IDOR (no hole-card/seed/balance write leak). Low/info: leaderboard leaks balances unauthenticated, chat is readable by non-seated users, session-review is an enumeration oracle. |
| 3. Double-submit / two-user races | **Richest vein.** One **high** (poker buy-in double-spend → chip mint) + several medium/low (blackjack seat-grab 500, streak inflation, poker `/act` 500). |
| 4. Back button / refresh mid-flow | **Largely fine** (5 candidate issues refuted — backend guards prevent the damage). |
| 5. Missing loading/error states | **One real medium:** all three table poll hooks swallow errors → permanent spinner with no escape. |
| 6. Explain your nontrivial logic | **One logic bug:** dealer natural pushes a player's 3-card 21 instead of winning. Otherwise showdown/side-pot math conserves chips. |

---

## CRITICAL

### C1 — Path traversal / arbitrary file read in the SPA catch-all
**`backend/main.py:148-159`** · category: info-disclosure · **anonymous, no auth required**

The SPA fallback builds a filesystem path straight from the URL and serves it with no containment check:
```python
candidate = os.path.join(_frontend_dist, full_path)
if full_path and os.path.isfile(candidate):
    return FileResponse(candidate)
```
The only guard is the `api/` prefix rejection — useless against `..`. `os.path.join` honors `..` segments and *discards the base* on an absolute second arg. Starlette percent-decodes the path, so `%2e%2e` / `..%2f` survive client normalization and arrive as literal `../`.

**Exploit (anonymous, against prod):**
- `GET /%2e%2e/%2e%2e/backend/auth.py` → streams backend source (then `database.py`, `migrate.py`, every router) → maps the whole app's logic for follow-on attacks.
- `GET /..%2Fsecret.txt`, absolute-path reads of OS files.

Mounted in production: the Dockerfile builds `frontend/dist` and `uvicorn` serves it directly (no nginx normalization in front). **Reproduced against a live uvicorn server via raw sockets — returns `200` with the sibling file body.**

**Fix:** after computing `candidate`, resolve and contain it:
```python
real = os.path.realpath(candidate)
if full_path and os.path.commonpath([real, os.path.realpath(_frontend_dist)]) == os.path.realpath(_frontend_dist) and os.path.isfile(real):
    return FileResponse(real)
return FileResponse(_index_html)
```
Better: serve only an allowlist of top-level static files (`favicon.ico`, `robots.txt`, `manifest`); everything else returns the SPA shell. Reject any `full_path` containing `..` or a leading slash/drive letter outright.

---

## HIGH

### H1 — Poker tournament buy-in is a non-atomic debit → double-submit mints chips
**`backend/routers/poker_tables.py:97,124`** (helper `_create_tournament_with_seats`; endpoint `:43-59`) · money-integrity

The docstring says "Atomic:" but the User row is read **without** a lock:
```python
user = (await db.execute(select(User).where(User.id == current_user))).scalar_one_or_none()   # :97 — no with_for_update()
...
user.chip_balance -= body.buy_in_cents                                                          # :124
```
Every *other* money path locks the row — blackjack deal (`game.py:105`), blackjack double (`game.py:318`), holdem join (`holdem.py:333`). This is the lone unlocked debit. Two concurrent `POST /api/poker/tournaments` both read the same balance, both pass the sufficiency check, both debit, both commit (CHECK ≥ 0 still holds). Each tournament is winner-take-all and refunds the full buy-in → net **+buy_in per extra stake** → unbounded bankroll inflation (and the leaderboard the grader inspects).

Amplified by **H1b / M7 — no rate limit on this endpoint** (`poker_tables.py:43`): it's the only mutator in the poker/holdem surface missing `@limiter.limit(MUTATION_RATE_LIMIT)`, so the race window can be hammered in a parallel burst, and tournament/seat rows can be spammed (DB amplification).

**Fix:** lock the row before the check, exactly like the siblings — `select(User).where(User.id == current_user).with_for_update()` — and add `@limiter.limit(MUTATION_RATE_LIMIT)` + `request.state.user_id = str(current_user)` to the endpoint. Belt-and-suspenders: wrap the commit in `except IntegrityError` for the CHECK-constraint case (mirror `holdem._join_seat:365-372`).

---

## MEDIUM

### M1 — Blackjack seat-grab race returns 500 instead of 409
**`backend/routers/tables.py:199-224`** · concurrency

`_join_seat` reads occupied seat numbers into a Python set, picks the lowest free one, and INSERTs — **no** table-row lock and **no** `IntegrityError` handling. Two concurrent joins compute the same `seat_number`; the loser hits `UNIQUE(table_id, seat_number)` and the caller gets an opaque `500` instead of a clean retryable `409`. The holdem join does this correctly (`holdem.py:312` lock + `:365-372` IntegrityError→409). This is precisely the "duplicate-rows / broken-state" outcome the grader's race attack hunts.
**Fix:** mirror the holdem discipline — `with_for_update()` on the table row + `try/except IntegrityError → 409`.

### M2 — Streak inflation: advice endpoint has no idempotency guard
**`backend/routers/advice.py:94-160`** · money-integrity (score integrity)

`POST /api/advice/{hand_id}` bumps `current_streak`/`best_streak` whenever `player_guess == optimal`, but only checks the hand exists + is owned — **not** `hand.status` and **no** "already advised" marker. Replay the same owned `hand_id` with the known-correct guess ~10×/min (the rate-limit ceiling) → `best_streak` climbs without bound and shows on the public leaderboard. Pure fabrication; no game advances.
**Fix:** make streak attribution idempotent per decision — gate on `hand.status == 'active'` + a per-hand "advised" marker (e.g. require/insert the `player_actions` row in the same txn and key the streak on its uniqueness), or move the streak mutation onto the authoritative game-action write path.

### M3 — Dealer natural blackjack pushes a player's 3-card 21 (should lose)
**`backend/game/blackjack/state.py:43-65`** · money-integrity (logic)

`resolve_hand` only checks dealer-blackjack **inside** the player-blackjack branch (`:47-51`). A player who reaches 21 with 3+ cards falls through to `player_val == dealer_val → ('push', bet)` (`:62`) even when the dealer has a *natural* — `hand_value` has no notion of "natural." Standard rules: dealer natural beats any non-natural 21 → player should **lose**. The bet was debited up front (`game.py:192`), so the push refunds chips that should go to the house. A player who draws to 21 whenever the dealer shows an Ace/ten systematically dodges losses.
**Fix:** resolve dealer natural before the generic compare:
```python
if eng.is_blackjack(dealer_cards):
    return ("push", bet) if eng.is_blackjack(cards) else ("loss", 0)
```
Add a test: player 3-card 21 vs dealer A+K must return `("loss", 0)`.

### M4 — Table poll hooks swallow errors → infinite spinner, no error state
**`frontend/src/hooks/useTablePoll.ts:24-32`** (and `useHoldemPoll`, `usePokerPoll`) · frontend-states · **grader item 5**

All three hooks do `if (result.error || result.data === null) return;` and never surface the failure. The table pages render their spinner while the store value is null (`Table.tsx` "Pulling up a chair…", `HoldemTablePage`, `PokerTablePage` "Loading…"). A `401/403/404/500` on `/state` (expired token, deleted/stale/bookmarked table) → poll silently returns → page is **pinned to the spinner forever** with no error message and no escape. `PokerTablePage`'s `error` state is set only by the deal effect, never by the poll.
**Fix:** have each hook set an error state (or `onError`) after N consecutive failures; render an error panel with Retry / Back-to-lobby when the initial state never loads. Distinguish "still loading" from "failed to load."

### M5 — (= H1b) No rate limit on `POST /api/poker/tournaments`
See H1 above — `poker_tables.py:43`.

---

## LOW

- **L1 — Blackjack double-settlement race** · `game/blackjack/state.py:105-174` via `game.py:388`. No row lock on `GameSession.status`; concurrent last-player actions can run dealer settlement twice. Turn-guard currently prevents a live double-credit, so low — but lock `GameSession` for defense-in-depth.
- **L2 — `DealIn.bet` accepts negatives; safety relies on config** · `schemas.py:141-143`, enforced only at `game.py:116-120`; `CasinoTable.min_bet` (`models.py:94`) has no `> 0` CHECK. A negative bet would *credit* the bankroll; only the `bet < table.min_bet` check (default 500) blocks it. **Fix:** `bet: int = Field(gt=0)` + `CheckConstraint('min_bet > 0 AND max_bet >= min_bet')`.
- **L3 — Leaderboard unauthenticated, leaks user UUIDs + exact balances** · `routers/leaderboard.py:21-58`. Add `CurrentUser`; don't expose internal UUIDs/raw balances to anonymous callers.
- **L4 — Session-review enumeration oracle** · `routers/sessions.py:49-69`. Distinct `403` vs `404` vs detail strings let a caller probe which session ids exist / belong to others. Return a uniform `404` for both not-found and not-owned.
- **L5 — Streak counter lost-update race** · `routers/advice.py:136-147`. Non-atomic read-modify-write on `current_streak`; concurrent advice requests can lose an update. (Same endpoint as M2.)
- **L6 — Poker `/act` double-submit → 500** · `routers/poker_game.py:337-452` / `:464-472`. Resolves `action_index` via `MAX()` with no lock and no `IntegrityError` catch; double-submit returns 500 instead of a clean reject. Relies on `UNIQUE(hand_id, action_index)` for actual safety (so no corruption — just a 500).
- **L7 — Chat readable by any authenticated user, not just seated players** · `routers/chat.py:97-107, 172-192`. Eavesdrop on any table's chat by id. Add a seated-at-table check on GET (the POST path already checks membership).
- **L8 — Join silently evicts the caller from any other table** · `routers/tables.py:191-197`. A destructive cross-resource delete on join; confirm it's intended (single-table invariant) and surface it in the UI rather than doing it silently.

---

## INFO / by-design (worth knowing for the demo)

- **I1** — `GET /api/tables`, `GET /api/leaderboard`, `GET /api/holdem/tables` are unauthenticated lobby/leaderboard reads (`tables.py:33`, `leaderboard.py:21`, `holdem.py:62`). Public lobby data is a product choice; just decide it deliberately (leaderboard balance exposure is L3).
- **I2** — `GET /api/hands/{hand_id}/actions` lets any authenticated user read a *finished* hand's action log by `hand_id` (`game.py:403-460`). Documented "gold replay" design; leaks only post-game upcard + the target's own card snapshots, no hidden hole card. UUIDs aren't enumerable → negligible. Add a participation check if you want strict isolation.
- **I3** — Poker `/state` & `/replay` reveal all seats' hole cards once the hand is `complete` (`poker_game.py:796-810, 882-905`). Matches "owner during play, public after showdown"; opponents are bots → no real secret. **Confirmed NOT a seed/deck leak.**
- **I4** — `GET /holdem/tables/{id}/state` doesn't verify the caller is seated — spectating public state only; backend masks hole cards rigorously (verified). Fine.
- **I5** — Username upsert lacks validation / `IntegrityError` handling → opaque 500 on collision (`users.py:57-64, 161-188`).
- **I6** — Polymorphic `chat.table_id` has no FK / existence check; GET to unknown ids returns `200 []` (`chat.py:172-192`).

---

## What's already solid (defensible at the demo)

These were probed and **cleared** — good answers when the grader asks "what about…":

- **JWT auth core** — alg-confusion (HS-vs-RS dispatch can't be forced to verify with a public key), expired-token, and forged-token bypasses all **refuted**. Dev-bypass (`BETWISE_DEV_USER_ID`) is guarded against `ENVIRONMENT=production` and isn't attacker-reachable. (`aud`-missing and `iss`-when-`SUPABASE_URL`-unset are real-but-unreachable defense-in-depth gaps — tighten if you want, not exploitable.)
- **Holdem multiplayer (the real money table)** — per-table `with_for_update()` serializer on every mutator; per-user bankroll lock on buy-in; hole-card masking shows only your own cards mid-hand and reveals opponents only at a true showdown (folded stay mucked); turn guard + seated + in-hand authz on `/act`; chip-conserving leave-mid-hand. **No seed/deck leak anywhere** (verified across schemas + serializers).
- **Showdown / side-pot math** conserves chips.
- **Frontend back-button / refresh / spectating** — 5 candidate issues refuted: backend guards (turn checks, masking, server-side validation) prevent the speculated damage. `localStorage` session is the standard Supabase default. Client-side double-submit is backstopped server-side.
- **CORS** rejects `*` + credentials at boot; explicit origin allowlist.

---

## Recommended fix order

1. **C1 path traversal** — ship first; it's anonymous, trivial to trigger, and leaks the whole source tree.
2. **H1 poker buy-in lock + rate limit** — one-line `with_for_update()` + the missing limiter decorator.
3. **M1 seat-grab 409, M2 streak idempotency, M3 dealer-natural, M4 poll error states** — each small and self-contained.
4. **Lows** — `Field(gt=0)` + CHECK constraints, leaderboard auth, uniform 404s, chat read gate.

All fixes are localized and match patterns already in the codebase (the holdem router is the reference implementation for the money/concurrency ones). Recommend doing them through the repo's planner → tester → implementer → oracle loop, with a regression test per fix (e.g. the two concurrency races need tests that bypass the `commit→flush` conftest patch, since that patch hides them).
