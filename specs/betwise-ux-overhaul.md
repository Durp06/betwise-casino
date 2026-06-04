# BetWise UX/UI Overhaul — Balatro-grade juice across all three games

Status: planned
Date: 2026-06-03
Owner: durpsalt
Scope: Blackjack + Solo Poker Trainer + Multiplayer Texas Hold'em (all three, fully)

---

## North star

BetWise should feel like a hand-drawn 1930s casino that's alive in your hands:
every click lands with an instant ink-squish and a sound, every card flies in
from the deck and **then** reveals its value, and every win escalates — a small
pop for a push, a screen-shaking gold burst with a racing chip counter for a
blackjack or a winning streak. Three games live behind one obvious, consistent
picker so you always know where you are and what to do next, and creating a
table drops you straight into the felt. The loop pulls you forward with visible
momentum — bankroll, streaks, and "play another hand" framed as the single
obvious primary action. The whole thing shares one palette, one type scale, one
shadow language, and one motion grammar so it reads as a single intentional
artifact, not three apps stapled together.

This overhaul is delivered in phases. **Phase 0 ships first** as a small,
independently-shippable, high-visibility batch. Phases 1–6 are outlined here but
executed one at a time, each its own PR, with a user check-in between them.

---

## Context

A prior 8-agent audit (66 issues across 7 dimensions) plus live testing by the
user confirmed seven concrete complaints. This spec tightens that audit's
7-phase roadmap into an executable plan grounded in real file paths. The work is
ordered quick-wins-first because four of the seven complaints have tiny,
high-impact fixes whose code already exists in the repo.

The seven confirmed complaints and their root causes (all verified against
current `main`):

1. **Results show before they happen.** `ActionBar.tsx::handleAction` calls
   `setMyHand(result.data)` synchronously, so `myHand.outcome` and the outcome
   banner (`Table.tsx:380-416`) update instantly, but the dealer's cards live in
   `tableState.session.dealer_cards` and only refresh on the next 3s poll
   (`useTablePoll.ts`, `POLL_INTERVAL_MS=3000`; `Table.tsx` passes no
   `onActionSuccess`). Net: the outcome banner appears up to 3s **before** the
   dealer reveal renders. There is no hole-card flip (the `.card-3d` flip CSS in
   `index.css:185-201` exists but `PlayingCard.tsx` never uses it); `CardHand.tsx`
   keys cards by `index` so `.card-deal` can't re-fire on reveal; the hand-value
   badge updates immediately.
2. **Buttons "kind of work".** Lobby plaques carry a perpetual `.wobble` with a
   per-item `Math.random()` `animationDelay` (`Lobby.tsx:201`) that re-jitters the
   list every 5s and makes buttons un-clickable in Playwright. Poker/Hold'em
   action buttons (`PokerActionBar.tsx`, `HoldemActionBar.tsx`) use plain
   `border-2 border-ink bg-*-200` — no `ink-shadow` press feedback — and their
   submit handlers never push the server response into a store, so a click feels
   dead until the next poll.
3. **No intuitive multi-game UI.** `Lobby.tsx:142-145` renders `HoldemLobbyCard`
   + `PokerLobbyCard` inline inside the blackjack "Open Tables" list with no
   "choose a game" framing; entry flows are asymmetric; headers differ across
   `Table` / `PokerTablePage` / `HoldemTablePage` / `HoldemLobby`; `PokerSetup`
   has no back/cancel and strands the user.
4. **New table doesn't auto-join.** `Lobby.tsx:57-64` `handleCreateTable` calls
   `createTable` then only `fetchTables()` — it ignores the returned `table.id`.
   `createTable` already returns `TableOut` with `.id` (`client.ts:126-136`) and
   `joinTable` + `navigate` already exist in the same file (`handleJoin`).
5. **Old tables clutter.** `tables.py::_list_tables` selects every `CasinoTable`
   with no status filter, ordered only by `created_at`; finished/empty tables
   persist forever; names are `Table ${Date.now()%10000}`.
6. **Chipy sprite clippings.** **The audit MISDIAGNOSES this.** The audit claims
   the bug is `(col/(COLS-1))*100` and says to change to `(col/COLS)*100`. **That
   is wrong.** `Chipy.tsx` sets `backgroundSize: 400% 400%` and shows a single
   cell; with a 400% background, `index/(N-1)*100%` (→ 0 / 33.3 / 66.6 / 100%) is
   the **correct** CSS percentage-sprite formula that lands exactly on cell
   boundaries. Changing to `/COLS` would shift every sprite off-center and make it
   **worse**. The real cause (confirmed by opening the spritesheet) is that the
   sprite **art overflows its grid cells** — hands/chips/white outlines spill into
   neighbouring cells — so any rectangular crop shows fragments of adjacent
   sprites. The fix must be **asset-level**, not a formula tweak.
7. **Wants Balatro juice.** No audio anywhere; static win banner (the `.sparkle`
   `index.css:147-153` and `.banner-pulse` `index.css:157-161` keyframes are
   defined but never applied); no chip/payout count-up; no streak/momentum
   (backend already tracks `users.current_streak/best_streak`; `gameStore` has
   none); Chipy ignores its `animation` prop entirely (`Chipy.tsx:82-88`).

### Constraints (from `CLAUDE.md`, baked into every phase)

- **TDD loop.** Each phase past the one-liner threshold goes
  planner → tester → implementer → oracle → verify. Tests map 1:1 to ACs. Every
  AC below is written test-first-friendly (concrete, assertable).
- **CI gates that must stay green every phase:** `ruff check backend`;
  `python -m pytest backend/tests/` (118+ tests); `cd frontend && npx tsc --noEmit`
  (NO `any` — use `unknown` + narrow); `npm test -- --run` (vitest + jsdom + MSW;
  do not mock React Query/Zustand — render real components); `npm run build`.
- **Frontend conventions:** components PascalCase, utils camelCase, hooks `use*`;
  all user-facing strings through `t()` from `frontend/src/i18n.ts`; Tailwind only
  (inline styles only for dynamic numeric values); every fetch shows loading +
  error states; the api client returns `{ data, error }`.
- **Backend conventions:** async everywhere; `datetime.now(timezone.utc)` never
  `utcnow()`; per-router `_helper` SQL functions (no duplicated SELECTs);
  `HTTPException` not bare raises; type hints + `from __future__ import annotations`.
- **One coherent change per PR; refactor separate from feature work.** The
  design-system token cleanup is its own final phase (Phase 6), not mixed in.
- **New deps:** `howler.js` (~7kb, CC0 SFX) is approved for sound (Phase 4).
  Confetti/celebration must be CSS/framer-motion only — **NO confetti
  dependency**. No other new deps without flagging.
- **Test fixtures:** backend uses `seed_user`, `seed_table`, `seed_session`,
  `seed_hand`, `seed_actions` (`backend/tests/conftest.py`, in-memory SQLite;
  `seed_table(status=...)` already exists). Frontend uses MSW `setupServer`
  (`frontend/tests/ChipyPanel.test.tsx`).

---

## Acceptance criteria — Phase 0 (quick wins)

Phase 0 is a single coherent PR. Items below are ordered by impact. Each AC is a
concrete, testable outcome a `tester` subagent can encode before implementation.

### P0-1 — Auto-join on create (complaint 4) — `frontend/src/pages/Lobby.tsx`, `frontend/src/api/client.ts`

- **AC P0-1a:** After `createTable` succeeds in `handleCreateTable`, the handler
  reads `result.data.id`, calls `joinTable(id)`, and on join success calls
  `navigate(\`/table/${id}\`)`. Verified with an MSW test: mock
  `POST /api/tables` → `{ id, ... }` and `POST /api/tables/:id/join` → `{ message }`;
  click "Open Table"; assert `navigate` was invoked with `/table/<that id>` (assert
  via a `MemoryRouter` + a route that renders a sentinel, or a `useNavigate` spy).
- **AC P0-1b:** If `joinTable` returns `{ error }`, `actionError` is shown
  (`role="alert"`) and **no** navigation occurs. MSW test: join mocked to 409;
  assert the alert text renders and the sentinel route is not reached.
- **AC P0-1c:** `createTable` failure path is unchanged (still surfaces
  `actionError`, no join attempt).

### P0-2 — Backend lobby status filter + ordering + nicer names (complaint 5) — `backend/routers/tables.py`, `frontend/src/pages/Lobby.tsx`

- **AC P0-2a (backend filter):** `_list_tables` returns only tables with
  `status IN ('waiting','playing')`. Pytest: seed three tables (`waiting`,
  `playing`, `finished`); `GET /api/tables` returns exactly the two non-finished,
  and the `finished` table's id is absent.
- **AC P0-2b (backend ordering):** results are ordered `waiting` before `playing`
  before any other status, then `created_at DESC` within a status (use a SQL
  `CASE`/`order_by` expression — keep it in the `_list_tables` helper, no inline
  SQL elsewhere). Pytest: seed `waiting` (older) + `playing` (newer); assert the
  `waiting` table is index 0.
- **AC P0-2c (nicer names):** new tables created with no explicit name get a
  human-readable name instead of `Table ${Date.now()%10000}`. Decide the source of
  truth in **Open question Q1**; default plan: the **frontend** generates a
  friendly name (e.g. a small curated adjective+noun list in a camelCase util
  `frontend/src/utils/tableName.ts`, all strings via `t()`), because the backend
  `TableCreateIn.name` is required and this keeps the change client-only. Vitest:
  the generator returns a non-empty string not matching `/^Table \d+$/`.
- **AC P0-2d (defensive client filter):** `Lobby.tsx` filters
  `result.data?.filter(t => t.status !== "finished")` before `setTables`, so a
  stale `finished` row never renders even if the API regresses. Vitest (MSW): mock
  `GET /api/tables` to include a `finished` row; assert its name is not in the DOM.

### P0-3 — Deterministic wobble delay (complaint 2 jank) — `frontend/src/pages/Lobby.tsx`

- **AC P0-3a:** The table-card `animationDelay` is derived from the map `index`
  (e.g. `\`${index * 0.15}s\``), not `Math.random()`. There are **zero**
  occurrences of `Math.random(` in `Lobby.tsx`. Vitest: render two identical table
  lists; assert the nth card's inline `animation-delay` is identical across renders
  (deterministic), or simply grep-assert no `Math.random` in source via a unit
  test that imports nothing (a source-scan test is acceptable but a render-stability
  assertion is preferred).

### P0-4 — Poker/Hold'em button reskin + busy state (complaint 2, visual half) — `frontend/src/components/PokerActionBar.tsx`, `frontend/src/components/HoldemActionBar.tsx`

- **AC P0-4a (ink styling):** Every action button in both bars (fold, check/call,
  raise, all-in, confirm-raise, cancel) carries `ink-outline` + `ink-shadow`
  classes (reusing the 120ms press transform in `index.css:49-60`) instead of the
  bare `border-2 border-ink`. Vitest: query each button by its existing
  `data-testid` (`poker-action-fold`, `holdem-action-call`, …) and assert
  `className` contains `ink-shadow`.
- **AC P0-4b (busy label):** While `submitting` is true, each action button's
  visible label becomes a busy indicator (`t("…")`) and `aria-busy="true"` is set
  (mirroring `ActionBar.tsx:119-126`). Vitest (MSW with a delayed resolve): click
  Fold; before the response resolves, assert the button shows `…` and
  `aria-busy="true"`; after resolve, `onActed` fires.
- **AC P0-4c:** Disabled buttons keep working (legality math unchanged); existing
  poker/holdem endpoint tests stay green. No optimistic store wiring in Phase 0
  (that is Phase 3) — this item is visual + busy-state only.

### P0-5 — "Choose a Game" framing (complaint 3, framing only) — `frontend/src/pages/Lobby.tsx`

- **AC P0-5a:** A heading rendered via `t("Choose a Game")` plus a visual divider
  appears **above** the `HoldemLobbyCard`/`PokerLobbyCard` group and is visually
  separated from the "Open Tables" table browser below. Vitest: assert the heading
  text renders and appears in DOM order before the game cards and before the table
  list. No new components, no routing changes — full `GamePicker` is Phase 1.

### P0-6 — Interim outcome-banner celebration (complaint 7 down-payment) — `frontend/src/pages/Table.tsx`, `frontend/src/index.css`

- **AC P0-6a:** The outcome banner div (`Table.tsx:383`) applies the
  already-defined `.banner-pulse` class, and on a winning outcome
  (`chipyMood.expression === "happy"` / win / blackjack) additionally applies
  `.sparkle`. Vitest: render `Table` in a win state (seed store/poll so
  `isHandFinished && myHand.id === lastFinishedHandId && chipyMood.title`); assert
  the banner element's `className` contains `banner-pulse` and `sparkle`.
- **AC P0-6b:** On a losing/push outcome the banner does **not** carry `sparkle`
  (escalation down-payment: win ≠ loss). Vitest: render a bust state; assert
  `sparkle` absent, `banner-pulse` present.
- **AC P0-6c:** `prefers-reduced-motion` continues to disable these animations
  (the existing `@media (prefers-reduced-motion)` rule already covers
  `.wobble`/`.wobble-strong`; extend it to cover `.sparkle`/`.banner-pulse` if not
  already). Assert via a CSS-presence test or a jsdom media-query mock.

### P0-7 — Chipy bleed fix, verified visually (complaint 6, corrected diagnosis) — `frontend/src/components/Chipy.tsx` (+ possibly `frontend/src/assets/chipy/`)

> **Do NOT apply the audit's `(col/COLS)*100` "fix" — it is wrong for a 400%
> background and will move every sprite off-centre.** The bug is art overflow, not
> formula. The planner has evaluated the three options below; the **recommended**
> Phase-0 path is **Option B (circular clip-path mask)** because it is the
> lowest-risk change that visually eliminates bleed without touching the asset
> pipeline, and Chipy is a round poker chip so a centered circle reads as
> intentional. Option A is the cleaner long-term fix but is asset-pipeline work
> better suited to Phase 6 or a dedicated asset PR.

- **Option A (asset re-cut, deferred):** Use PIL (available in `backend/.venv`) to
  re-cut the 16 cells into individual transparent PNGs — key the black background
  to alpha, pad/gutter each cell so no neighbour bleeds — and switch `Chipy.tsx`
  to per-expression image URLs. Highest fidelity, but changes the asset contract
  and the component's rendering model; **defer to its own PR** unless Q3 says
  otherwise.
- **Option B (circular clip-path, RECOMMENDED for P0):** Add a centered circular
  `clip-path` mask to the Chipy container so corner/edge bleed is clipped and the
  mascot reads as a round chip. Set `imageRendering: "crisp-edges"` (replacing the
  current `"auto"` at line 104). **Leave the `spritePosition` formula unchanged.**
- **Option C (regenerate art):** Out of scope for this overhaul; note only.

- **AC P0-7a:** `Chipy.tsx` `imageRendering` is `"crisp-edges"` (not `"auto"`), and
  the `spritePosition` formula is **unchanged** (still `(col/(COLS-1))*100`). Unit
  test / source assertion.
- **AC P0-7b (Option B):** the Chipy container renders with a circular `clip-path`
  (e.g. `circle(50%)`) applied via Tailwind/`style`. Vitest: assert the computed
  style includes a `clip-path` circle (or assert the class that supplies it).
- **AC P0-7c (visual verification — mandatory):** A screenshot of Chipy at the
  three call-sites it appears in (Lobby header `size=80`, empty-state `size=120`,
  outcome banner `size=88`) shows **no fragments of neighbouring sprites**. This is
  verified by the `verify`/`run` skill capturing a PNG and the implementer
  confirming no bleed before declaring P0-7 done. (This AC is human/visual, not an
  automated test, but it is a hard gate — the complaint is visual.)

### Phase 0 — out of scope (explicit)

- No `GamePicker` / `GameHeader` components (Phase 1).
- No motion-before-state sequencing, no hole-card flip, no `Board` `noAnimate`
  removal (Phase 2).
- No shared `ActionButton`, no optimistic poker/holdem store updates, no poll
  tightening (Phase 3).
- No audio, no `useCountUp`, no `OutcomeBanner` component, no Chipy `animation`-prop
  wiring (Phase 4).
- No streak/momentum, no lobby stats banner (Phase 5).
- No inline-hex → token migration, no focus-ring sweep, no contrast fixes (Phase 6).
- No `owner_id` / "Your Table" badge (Phase 1; needs a schema + type change).
- No table archival column / `is_archived` migration (deferred; the status filter
  is sufficient for Phase 0).

---

## Plan — Phase 0 tasks (each ≈ one commit)

Ordered by impact. The implementer executes one task at a time and checks in.

### Task 0.A — Auto-join on create (P0-1) [DONE]
- In `Lobby.tsx::handleCreateTable`, after `createTable` success, read
  `result.data.id`, call `joinTable(id)`; on success `navigate(\`/table/${id}\`)`,
  on error set `actionError` and do not navigate.
- Keep `setCreating(false)` and the existing `createTable`-error branch intact.
- Add MSW tests for P0-1a/b/c.

### Task 0.B — Backend lobby filter + ordering (P0-2a/b) [DONE]
- In `tables.py::_list_tables`, add `.where(CasinoTable.status.in_(("waiting","playing")))`
  and an `order_by(case(...))` status-priority expression then `created_at.desc()`.
  Keep all SQL inside the helper.
- Pytest: seed mixed-status tables; assert filtering + ordering.

### Task 0.C — Defensive client filter + nicer names (P0-2c/d) [DONE]
- Add `frontend/src/utils/tableName.ts` (camelCase util) producing a friendly
  name via `t()`; use it in `handleCreateTable` instead of `Table ${Date.now()%10000}`.
- In `Lobby.tsx::fetchTables`, filter out `status === "finished"` before
  `setTables`.
- Vitest for the generator and the defensive filter.

### Task 0.D — Deterministic wobble (P0-3) [DONE]
- Replace the `Math.random()` `animationDelay` at `Lobby.tsx:201` with
  `\`${index * 0.15}s\`` (the `.map` already exposes a usable index; thread it in).
- Vitest render-stability assertion.

### Task 0.E — Poker/Hold'em button reskin + busy state (P0-4) [DONE]
- In `PokerActionBar.tsx` and `HoldemActionBar.tsx`, swap `border-2 border-ink`
  for `ink-outline ink-shadow` on every button; while `submitting`, render
  `t("…")` and set `aria-busy`.
- Keep legality math + `data-testid`s unchanged.
- Vitest per `data-testid`; confirm `backend/tests/test_poker_endpoints.py` stays
  green (no API change).

### Task 0.F — "Choose a Game" framing (P0-5) [DONE]
- Add a `t("Choose a Game")` heading + divider above the game-card group in
  `Lobby.tsx`; visually separate from the table browser.
- Vitest DOM-order assertion.

### Task 0.G — Interim banner celebration (P0-6) [DONE]
- In `Table.tsx`, add `.banner-pulse` to the outcome banner and conditionally add
  `.sparkle` on wins; extend the `prefers-reduced-motion` CSS guard in `index.css`
  to cover these if needed.
- Vitest for win vs loss class presence.

### Task 0.H — Chipy bleed fix (P0-7, Option B) [DONE — P0-7a/b automated; P0-7c awaits visual verification]
- In `Chipy.tsx`, set `imageRendering: "crisp-edges"`, add a centered circular
  `clip-path`; **leave `spritePosition` unchanged**.
- Unit assertions for P0-7a/b green; **P0-7c mandatory screenshot verification** required from orchestrator.

---

## Phases 1–6 (outlined; executed one at a time, each its own PR)

### Phase 1 — Unified multi-game navigation IA  (closes complaint 3; structural half of 4/5)
Make the three games read as one cohesive casino. **Goal:** clear, consistent path
in and out. **Key items:** new `GamePicker.tsx` (three consistently-styled cards —
Blackjack / Solo Poker / Multiplayer Hold'em — with icon, one-line description,
single CTA, hover-lift + `whileTap` juice) rendered at the top of the Lobby,
visually separated from the now-live-only table browser; new shared `GameHeader.tsx`
(game title + suit icon left; Back-to-`<parent>` button + persistent
Profile/Leaderboard links right) adopted by `Table`, `PokerTablePage`,
`HoldemTablePage`, `HoldemLobby` — **passing leave/navigate handlers in** rather
than moving navigation into the header (preserves `Table.tsx` `pagehide`/`handleLeave`
semantics); a Back/Cancel button on `PokerSetup`; add `owner_id` to `TableListOut`
(`schemas.py`) + `_list_tables` + `TableListRow` (`types/index.ts`) and a "YOUR
TABLE" gold-ring badge so the auto-joined table is scannable; **optional** `/poker`
lobby route for entry symmetry with `/holdem` (can defer). **Files:**
`GamePicker.tsx`, `GameHeader.tsx`, `Lobby.tsx`, `PokerSetup.tsx`, `Table.tsx`,
`PokerTablePage.tsx`, `HoldemTablePage.tsx`, `HoldemLobby.tsx`, `PokerLobbyCard.tsx`,
`HoldemLobbyCard.tsx`, `App.tsx`, `tables.py`, `schemas.py`, `types/index.ts`.

### Phase 2 — Motion plays the event (sequencing engine)  (closes complaint 1)
Fix the core Balatro violation: **motion precedes state.** **Goal:** establish a
staged-reveal pattern in blackjack, then reuse for poker/holdem. **Key items:**
buffer the server hand result in a local/staging slice instead of calling
`setMyHand` immediately (`ActionBar.tsx:76`, `BettingControls.tsx:123`); drive card
entry through framer-motion with `onAnimationComplete` and commit
hand-value/outcome/payout **after** the deal+stagger finishes; add a post-land
value-reveal pop in `PlayingCard.tsx`; delay the hand-value badge pop in
`CardHand.tsx` until the last card's stagger completes; detect dealer hole-card
reveal (`[Card,null] → [Card,Card]`) and play the existing
`.card-3d/.card-inner/.card-face` flip before showing the dealer total; **gate the
outcome banner** until the dealer animation completes; remove the hard-coded
`noAnimate` from `Board.tsx` and wrap in `deal-stagger` so flop/turn/river deal in;
apply the same to poker/holdem hole cards (`PokerSeat`/`HoldemSeat`). **Files:**
`ActionBar.tsx`, `BettingControls.tsx`, `PlayingCard.tsx`, `CardHand.tsx`,
`Table.tsx`, `Board.tsx`, `PokerSeat.tsx`, `HoldemSeat.tsx`, `gameStore.ts`,
`index.css`, `useTablePoll.ts`. **This is the riskiest phase — see Risks (sequencing
lock).**

### Phase 3 — Zero dead clicks (tactile + responsive buttons)  (completes complaint 2)
**Goal:** every press has instant visual feedback and the table reflects the action
before the next poll. **Key items:** shared `ActionButton.tsx` wrapping
`ink-shadow` + `whileTap` scale 0.94 + `focus:ring`, adopted across `ActionBar`,
`PokerActionBar`, `HoldemActionBar`, `BettingControls`, `Lobby`; optimistic store
updates in `PokerActionBar`/`HoldemActionBar` from the `act()` response (mirror
blackjack's `setMyHand`); reduce `POLL_INTERVAL_MS` to ~1500ms in
`usePokerPoll`/`useHoldemPoll`; `animate-pulse` "currently to act" seat highlight
(`PokerSeat`/`HoldemSeat`) and pulsing waiting text on poker/holdem pages;
`focus:outline-none focus:ring-2 focus:ring-gold-bright` on all interactive controls;
style the `BetSizingSlider` thumb/track/presets with `ink-shadow`. **Files:**
`ActionButton.tsx`, `ActionBar.tsx`, `PokerActionBar.tsx`, `HoldemActionBar.tsx`,
`BettingControls.tsx`, `PokerSeat.tsx`, `HoldemSeat.tsx`, `BetSizingSlider.tsx`,
`usePokerPoll.ts`, `useHoldemPoll.ts`, `PokerTablePage.tsx`, `HoldemTablePage.tsx`,
`gameStore.ts`. **See Risks (poll cost-amplification).**

### Phase 4 — Escalating juice: audio, count-ups, win celebration  (core of complaint 7)
**Goal:** make wins feel earned and escalate from small pop to screen-shaking burst.
**This is where `howler.js` is justified; confetti is CSS/framer-motion only — no
dep.** **Key items:** `frontend/src/utils/soundManager.ts` (Howler):
`playButtonPress/playChipClick/playCardDeal/playCardReveal/playWin/playLoss/playStreak`,
lazy-init on first user gesture, mute toggle, default **respects
`prefers-reduced-motion`**; wire into `ActionButton`, the deal/reveal sequence, and
outcome. `useCountUp.ts` (framer-motion `useMotionValue`, **no new dep**) applied to
payout (`Table.tsx:402`), pot (`PotDisplay`), and chip balances so numbers race up.
`OutcomeBanner.tsx` with `AnimatePresence`: small win = pop; big win / blackjack /
streak = larger scale pulse + sparkles + **CSS/framer-motion particle burst** (no
confetti dep) + screen shake; loss = shake; intensity driven by win magnitude. Wire
Chipy's `animation` prop (`Chipy.tsx:82-88`): switch on bounce/shake/spin/think,
strengthen idle amplitude — making blackjack visibly louder than a normal win.
Chip-fly motion on bet placement and payout collection. **Files:** `package.json`,
`soundManager.ts`, `useCountUp.ts`, `OutcomeBanner.tsx`, `Chipy.tsx`, `PotDisplay.tsx`,
`ChipStack.tsx`, `BettingControls.tsx`, `Table.tsx`. **See Risks (audio gesture
unlock).**

### Phase 5 — Addictive loop: streaks + momentum + meta visibility  (loop side of complaint 7)
**Goal:** the "one more hand" pull via visible meta-progression. **Key items:** add
`streakCount` + `bestStreak` to `gameStore`, synced with backend
`users.current_streak/best_streak`; increment on win/blackjack, reset on loss/push;
surface a `t("WIN ×3")` badge in `OutcomeBanner` with escalating juice tied to streak
length; player-stats banner on the Lobby (bankroll, hands played, win rate, current
streak); make "Play another hand" the **single visually-dominant** primary action in
the post-hand menu (`Table.tsx:451-493`) and demote secondary actions; **fix the
redundant "Review last hand" vs "Review this hand" buttons** observed in testing;
streak/momentum feedback consistent across blackjack and (where applicable) poker.
**Files:** `gameStore.ts`, `Lobby.tsx`, `Table.tsx`, `OutcomeBanner.tsx`, `Chipy.tsx`,
and the advice/streak source (`backend/routers/advice.py` already increments
`current_streak/best_streak`).

### Phase 6 — Design-system cohesion + accessibility  (closes complaint 7 cohesion; pure cleanup)
**Goal:** read as one intentional artifact and pass a11y gates. **Pure-cleanup PR,
run after the feature phases are green** (per "refactor separate from feature work").
**Key items:** migrate inline `style={{ backgroundColor: "#..." }}` hex to Tailwind
tokens (`bg-felt-dark`, `bg-action-hit`, `bg-gold-bright`, …) across `Lobby`,
`Table`, `ChipyPanel`, `BettingControls`, `HoldemLobbyCard`; add any missing tokens
to `tailwind.config.ts`; standardize shadows on `.ink-shadow`/`.ink-shadow-sm`
(replace ad-hoc `drop-shadow` in `ChipStack`/`PlayingCard`); define a button-size
scale (`.btn-lg/.btn-md/.btn-sm`) and a type scale; **fix `.gold-drop` shadow
contrast** (`#9A7D0A` → darker) to WCAG AA and replace `opacity-40` disabled states
with explicit 4.5:1 colors; **focus rings everywhere**; remove legacy color
aliases/saloon palette once migrated; document tokens in `DESIGN_TOKENS.md`; apply
`paper-grain`/`table-surface` consistently. **Files:** `Lobby.tsx`, `Table.tsx`,
`ChipyPanel.tsx`, `BettingControls.tsx`, `HoldemLobbyCard.tsx`, `ChipStack.tsx`,
`PlayingCard.tsx`, `index.css`, `tailwind.config.ts`, new `DESIGN_TOKENS.md`.

---

## Risks & sequencing

- **Phase 2 is the riskiest.** Deferring `setMyHand`/state commits until animations
  complete can race with the poll reconciler (`reconcileFromPoll` in `gameStore`)
  and the existing `pendingActionId`/optimistic-hit guard. A poll landing mid-reveal
  could overwrite the staged buffer. **Mitigation:** add a **sequencing-lock flag**
  that gates poll reconciliation while a reveal is in flight; keep the existing
  `pendingActionId` guard intact; add tests for the deal → hit → stand sequence and
  for a poll arriving mid-reveal.
- **Audio (Phase 4) needs a user-gesture unlock** on mobile/Safari (Web Audio
  autoplay policy) plus asset licensing. **Mitigation:** lazy-init Howler on first
  interaction; ship a mute toggle; **default to respecting `prefers-reduced-motion`**
  (reduced motion ⇒ muted/no-juice by default); source CC0 SFX only.
- **No confetti dependency.** Big-win bursts are CSS/framer-motion particle effects
  only. If a self-rolled canvas helper is needed, keep it tiny and in-tree;
  `npm run build` + `tsc` must stay clean.
- **Backend lobby filtering (Phase 0) changes API response semantics.** Finished
  tables disappearing from `GET /api/tables` could break any test/screen that
  expects them. **Mitigation:** filter **only** the lobby list endpoint; update
  backend tests; if a history/admin view ever needs finished tables, add an explicit
  query param or a separate `/archive` endpoint rather than relaxing the filter.
  (No current admin/history view depends on finished tables — verify during
  implementation by grepping callers of `listTables`/`GET /api/tables`.)
- **GameHeader/GamePicker refactor (Phase 1) touches every game page's navigation.**
  Risk of breaking `leaveTable`-on-navigate in `Table.tsx` (`pagehide` listener +
  explicit `handleLeave`). **Mitigation:** keep leave logic in the pages; **pass
  handlers into `GameHeader`** rather than moving navigation into it.
- **Poll tightening to 1.5s (Phase 3) roughly doubles poker/holdem read load.**
  Verify it does not trip the cost-amplification protections from prior security
  work (PR #4) before shipping.
- **Workflow discipline:** every phase past the one-liner threshold runs
  planner → tester → implementer → oracle → verify and must keep **all** CI gates
  green (ruff, pytest 118+, tsc, vitest, vite build). Phases are sized as independent
  PRs to honour "one coherent change per PR" and "refactor separate from feature
  work."

---

## Open questions

> **RESOLVED 2026-06-03 (user-confirmed scope pass):**
> - **Q1 → frontend.** Friendly names are generated client-side in
>   `frontend/src/utils/tableName.ts`; no backend/migration change.
> - **Q2 → Option B (circular clip-path) for Phase 0.** Leave `spritePosition`
>   unchanged; PIL asset re-cut (Option A) deferred to its own PR. Clipping
>   wave/thumbsup poses is acceptable now (`pose` is a documented no-op).
> - **Q3 → defer** the `/poker` lobby route; Phase 1 ships `GamePicker` regardless.
> - **Q4 → Phase 5 problem;** confirm/​add the streak read path when Phase 5 starts.

- **Q1 (P0-2c, naming source of truth):** Generate friendly default table names on
  the **frontend** (client-only, recommended — `TableCreateIn.name` is required and
  this avoids a backend/migration change) or on the **backend** (e.g. server-side
  default when `name` is blank)? Default plan assumes frontend.
- **Q2 (P0-7, Chipy fix tier):** Confirm **Option B (circular clip-path)** for
  Phase 0, with **Option A (PIL asset re-cut)** deferred to its own PR? Or is the
  asset re-cut wanted now? The clip-path option may clip meaningful poses
  (wave/thumbsup/point); since `pose` is currently a documented no-op this is
  acceptable for Phase 0, but flag if pose art matters before Phase 4 wires Chipy
  animation.
- **Q3 (Phase 1 `/poker` lobby):** Build the optional `/poker` lobby route for
  entry symmetry in Phase 1, or defer until poker tournaments are browseable? Phase 1
  ships the `GamePicker` regardless; this only affects whether Poker gets a
  dedicated intermediate lobby.
- **Q4 (streak sync, Phase 5):** Is there an existing endpoint that returns
  `users.current_streak/best_streak` for the lobby stats banner and `gameStore` sync,
  or does Phase 5 add one? (`advice.py` writes them; confirm a read path exists.)
