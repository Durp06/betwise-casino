# Drill Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Chipy "Drill Mode" toggle (Quick vs Drill) so the coach holds back the recommendation before the player acts and instead asks an active-retrieval question; after the player commits, the post-play stream reveals the optimal call along with the dealer-bust % that justifies it.

**Architecture:** New pure-Python helper `backend/game/blackjack/odds.py` exposes a canonical dealer-bust % table for 6-deck H17. `backend/routers/advice.py::get_advice` injects that % into the user prompt sent to Anthropic so Chipy can cite it. On the frontend, Zustand's `gameStore` gains a localStorage-backed `coachMode` field; `ChipyCoach.tsx` renders a Quick/Drill toggle in the header; `Table.tsx` skips the proactive `streamPreAdvice` call when in Drill mode and instead surfaces a static prompt via a new `chipyDrillPrompt` field. Post-play streaming via `streamAdvice` is unchanged.

**Tech Stack:** FastAPI + async SQLAlchemy + Pydantic v2 (backend, no schema changes), pytest-asyncio + pytest-mock for backend tests; React + TypeScript + Zustand + Tailwind on the frontend; Vitest + MSW + @testing-library/react for the new component test.

---

## Context

The current Chipy panel fires `streamPreAdvice` the moment a hand becomes active. Claude immediately narrates the optimal play. That's the weakest form of teaching: the player never has to construct the reasoning themselves, so the basic-strategy table doesn't stick.

Drill Mode replaces the proactive reveal with active retrieval. The player sees only "Your call. Hit, stand, or double? What's the dealer most likely sitting on?" and must commit before Chipy answers. After the commit, the existing post-play stream fires — but enriched with the dealer-bust % so the explanation says *why* (e.g. "Dealer's showing a 6 — busts ~42% of the time, so let them break it themselves").

Quick mode is preserved as the default for backward compatibility and an A/B baseline.

---

## File Structure

### Files to create
- `backend/game/blackjack/odds.py` — pure helper exposing `dealer_bust_pct(upcard) -> float`.
- `backend/tests/test_odds.py` — pinned-value unit tests for every upcard rank.
- `backend/tests/test_advice_drill.py` — tests that the post-play prompt includes the dealer-bust %. Kept separate from `test_endpoints.py` for clarity; the existing advice tests there stay untouched.
- `frontend/tests/CoachMode.test.tsx` — Vitest spec covering the toggle, drill-mode pre-suppression, and quick-mode passthrough.

### Files to modify
- `backend/routers/advice.py` (around lines 153–170) — extend the post-play user prompt to include the dealer-bust %.
- `frontend/src/store/gameStore.ts` (state + actions sections) — add `coachMode`, `setCoachMode`, `chipyDrillPrompt`, `setChipyDrillPrompt`; load/persist `coachMode` from `localStorage`.
- `frontend/src/components/ChipyCoach.tsx` — render the Quick/Drill pill toggle in the header; show `chipyDrillPrompt` when no narration is streaming and drill mode is active.
- `frontend/src/pages/Table.tsx` (lines 107–129) — gate the `streamPreAdvice` call on `coachMode === "quick"` and set the static drill prompt otherwise; clear it on hand change.

---

## Conventions (from CLAUDE.md, repeated for the implementer)

- All monetary integers in fake cents (n/a for this slice).
- Async SQLAlchemy only (n/a — odds.py is pure; advice.py is already async).
- Pydantic v2 `model_config = ConfigDict(from_attributes=True)` (no schema changes here).
- Frontend: no `any`, Tailwind only (no inline styles except dynamic values), Zustand for client state, all user-facing strings through `t()`.
- Never call `datetime.utcnow()` — use `datetime.now(timezone.utc)` (n/a here).
- Centralize SQL per router (n/a — no new queries).
- Every fetch must show loading + error states (n/a — no new fetches; existing SSE handlers already do).

---

## Acceptance Criteria (verbatim from spec, indexed)

### Backend
- **AC-B1**: `backend/game/blackjack/odds.py::dealer_bust_pct(upcard: dict) -> float` exists, pure (no DB/network), returns value in `[0.0, 1.0]`.
- **AC-B2**: Pinned values: 2→0.35, 3→0.37, 4→0.40, 5→0.42, 6→0.42, 7→0.26, 8→0.24, 9→0.23, 10/J/Q/K→0.23, A→0.17.
- **AC-B3**: The post-play prompt (the user-role `content` passed to Anthropic in `_stream_advice`'s `messages`, or the system prompt) contains the literal substring `dealer bust` (case-insensitive) and the percentage as a number.
- **AC-B4**: The pre-play endpoint server behavior is unchanged.
- **AC-B5**: All existing backend tests still pass.

### Frontend
- **AC-F1**: `gameStore.coachMode: "quick" | "drill"`, default `"quick"`, persisted to `localStorage` key `betwise.coachMode`.
- **AC-F2**: `setCoachMode(mode)` flips and persists.
- **AC-F3**: ChipyCoach renders two pill buttons "Quick" / "Drill"; the active one is visually highlighted; clicking either calls `setCoachMode`.
- **AC-F4**: When `coachMode === "drill"`, Table.tsx's pre-stream `useEffect` does NOT call `streamPreAdvice`. Instead it sets `chipyDrillPrompt` to the static question.
- **AC-F5**: When `coachMode === "drill"`, ActionBar's post-action `streamAdvice` fires unchanged.
- **AC-F6**: When `coachMode === "quick"`, behavior is unchanged from today.
- **AC-F7**: The toggle is disabled while `chipyStreaming === true`.
- **AC-F8**: All UI text via `t()`, Tailwind only, no `any`.

### Tests
- **AC-T1**: `test_odds.py` pins every rank (2-10, J, Q, K, A) and asserts range `[0, 1]`.
- **AC-T2**: `test_advice_drill.py` mocks Anthropic and asserts the captured `messages=` kwarg (or `system=` kwarg) for POST `/api/advice/{hand_id}` contains "dealer bust" (case-insensitive) and the numeric bust %.
- **AC-T3**: `CoachMode.test.tsx` covers: (a) toggle renders both pills, (b) clicking flips mode, (c) drill mode suppresses `streamPreAdvice` and shows the static prompt, (d) quick mode still calls `streamPreAdvice`.

---

## Out of scope

- Player-improve % (depends on hand total + soft/hard — defer).
- A dedicated Settings page (toggle lives in ChipyCoach header only).
- Server-side persistence of `coachMode` on the `User` row (localStorage only).
- Per-hand-category drills (e.g. "drill hard 16s").
- Mobile-specific styling beyond what ChipyCoach already does.
- Mid-action timers or streak bonuses tied to drill correctness.
- Refactoring the existing prompt construction in `_stream_advice` — keep the diff minimal; one string concatenation, no architecture change.

---

## Plan

### Task 1: Add `dealer_bust_pct` helper (backend, pure)

**Files:**
- Create: `backend/game/blackjack/odds.py`
- Test: `backend/tests/test_odds.py`

- [x] **Step 1: Write the failing test**

Create `backend/tests/test_odds.py`:

```python
"""
test_odds.py — pinned dealer-bust %% values for 6-deck H17 blackjack.

Source: standard Wizard of Odds dealer-outcome table. These specific values
are part of the public contract — the Chipy prompt cites them verbatim, so
they must not drift without a deliberate change.
"""
from __future__ import annotations

import pytest

from backend.game.blackjack.odds import dealer_bust_pct


# (upcard_value, expected_pct) — every face value the deck can show.
PINS: list[tuple[str, float]] = [
    ("2", 0.35),
    ("3", 0.37),
    ("4", 0.40),
    ("5", 0.42),
    ("6", 0.42),
    ("7", 0.26),
    ("8", 0.24),
    ("9", 0.23),
    ("10", 0.23),
    ("J", 0.23),
    ("Q", 0.23),
    ("K", 0.23),
    ("A", 0.17),
]


@pytest.mark.parametrize("value, expected", PINS)
def test_dealer_bust_pct_pinned(value: str, expected: float) -> None:
    upcard = {"suit": "spades", "value": value}
    assert dealer_bust_pct(upcard) == pytest.approx(expected, abs=1e-6)


@pytest.mark.parametrize("value, expected", PINS)
def test_dealer_bust_pct_in_unit_range(value: str, expected: float) -> None:
    upcard = {"suit": "hearts", "value": value}
    pct = dealer_bust_pct(upcard)
    assert 0.0 <= pct <= 1.0


def test_dealer_bust_pct_unknown_value_raises() -> None:
    with pytest.raises(KeyError):
        dealer_bust_pct({"suit": "spades", "value": "ZZ"})
```

- [x] **Step 2: Run the test to verify it fails**

Run: `pytest backend/tests/test_odds.py -v`
Expected: ImportError / ModuleNotFoundError for `backend.game.blackjack.odds`.

- [x] **Step 3: Write the minimal implementation**

Create `backend/game/blackjack/odds.py`:

```python
"""
odds.py — dealer-bust probabilities for 6-deck H17 blackjack.

Pure data + a single lookup. Values come from the canonical Wizard of Odds
dealer-outcome table for "dealer hits soft 17, 6 decks." They are pinned by
backend/tests/test_odds.py because Chipy's narration cites them verbatim.

This module has no dependencies on SQLAlchemy, the request lifecycle, or
the strategy engine — it's a fact table and one helper.
"""
from __future__ import annotations

# Keyed by the same face-value strings the rest of the codebase uses
# (see backend/game/blackjack/engine.py::card_rank). 10/J/Q/K all share the
# same bust %% because they all play as a 10-value upcard.
_DEALER_BUST_PCT: dict[str, float] = {
    "2": 0.35,
    "3": 0.37,
    "4": 0.40,
    "5": 0.42,
    "6": 0.42,
    "7": 0.26,
    "8": 0.24,
    "9": 0.23,
    "10": 0.23,
    "J": 0.23,
    "Q": 0.23,
    "K": 0.23,
    "A": 0.17,
}


def dealer_bust_pct(upcard: dict) -> float:
    """Probability the dealer busts given this upcard.

    Args:
        upcard: A card dict, e.g. {"suit": "hearts", "value": "6"}. Only
            the "value" key is read.

    Returns:
        A float in [0.0, 1.0].

    Raises:
        KeyError: if `upcard["value"]` is not a recognized rank.
    """
    return _DEALER_BUST_PCT[upcard["value"]]
```

- [x] **Step 4: Run the test to verify it passes**

Run: `pytest backend/tests/test_odds.py -v`
Expected: all 27 cases pass (13 pinned + 13 range + 1 unknown).

- [x] **Step 5: Commit**

```
git add backend/game/blackjack/odds.py backend/tests/test_odds.py
git commit -m "feat(odds): pin 6-deck H17 dealer-bust %% table"
```

---

### Task 2: Inject the dealer-bust % into the post-play prompt

**Files:**
- Modify: `backend/routers/advice.py:153-170`
- Test: `backend/tests/test_advice_drill.py`

- [x] **Step 1: Write the failing test**

Create `backend/tests/test_advice_drill.py`:

```python
"""
test_advice_drill.py — POST /api/advice/{hand_id} must hand Anthropic the
dealer-bust %% as a fact so Chipy can cite it. The exact wording is up to
the implementer; the contract is "the substring 'dealer bust' and the
numeric %% both appear in the messages or system prompt sent to Anthropic."
"""
from __future__ import annotations

import pytest

from backend.tests.conftest import (
    TEST_USER_ID,
    seed_hand,
    seed_session,
    seed_table,
    seed_user,
)


def _captured_prompt_text(mock_anthropic) -> str:
    """Concatenate the system prompt + every user/assistant message that was
    passed to anthropic.AsyncAnthropic().messages.stream(...). Returns the
    combined text lowercased for case-insensitive matching."""
    instance = mock_anthropic.return_value
    call = instance.messages.stream.call_args
    assert call is not None, "anthropic.messages.stream was never called"
    kwargs = call.kwargs
    parts: list[str] = []
    system = kwargs.get("system")
    if isinstance(system, str):
        parts.append(system)
    for msg in kwargs.get("messages", []):
        content = msg.get("content", "")
        if isinstance(content, str):
            parts.append(content)
    return "\n".join(parts).lower()


@pytest.mark.asyncio
async def test_post_advice_prompt_includes_dealer_bust_pct(client, db, mock_anthropic):
    """Dealer upcard 6 → bust %% = 0.42. The post-play prompt must mention
    'dealer bust' (case-insensitive) and the %% as a number."""
    await seed_user(db, TEST_USER_ID, "driller", chip_balance=100_000)
    table = await seed_table(db)
    session = await seed_session(
        db,
        table.id,
        status="playing",
        dealer_cards=[{"suit": "hearts", "value": "6"}],
    )
    hand = await seed_hand(
        db,
        session.id,
        TEST_USER_ID,
        cards=[{"suit": "hearts", "value": "5"}, {"suit": "spades", "value": "6"}],
        status="active",
    )

    resp = await client.post(
        f"/api/advice/{hand.id}",
        json={"player_guess": "double"},
    )
    assert resp.status_code == 200
    # Drain the SSE body so the generator runs to completion and the
    # Anthropic mock actually sees its call.
    _ = resp.text

    combined = _captured_prompt_text(mock_anthropic)
    assert "dealer bust" in combined, (
        f"Expected the prompt to mention 'dealer bust'; got: {combined!r}"
    )
    # Numeric form — implementer may render as "42%", "42 %", or "0.42".
    # Accept any of those.
    assert any(token in combined for token in ("42%", "42 %", "0.42")), (
        f"Expected the dealer-bust %% (42%% / 0.42) in the prompt; got: {combined!r}"
    )


@pytest.mark.asyncio
async def test_post_advice_prompt_uses_correct_pct_per_upcard(client, db, mock_anthropic):
    """Dealer upcard A → bust %% = 0.17. Different upcard → different number
    in the prompt."""
    await seed_user(db, TEST_USER_ID, "drilleracen", chip_balance=100_000)
    table = await seed_table(db)
    session = await seed_session(
        db,
        table.id,
        status="playing",
        dealer_cards=[{"suit": "spades", "value": "A"}],
    )
    hand = await seed_hand(
        db,
        session.id,
        TEST_USER_ID,
        cards=[{"suit": "hearts", "value": "10"}, {"suit": "spades", "value": "9"}],
        status="active",
    )

    resp = await client.post(
        f"/api/advice/{hand.id}",
        json={"player_guess": "stand"},
    )
    assert resp.status_code == 200
    _ = resp.text

    combined = _captured_prompt_text(mock_anthropic)
    assert any(token in combined for token in ("17%", "17 %", "0.17")), (
        f"Expected the dealer-bust %% (17%% / 0.17) in the prompt; got: {combined!r}"
    )
```

- [x] **Step 2: Run the test to verify it fails**

Run: `pytest backend/tests/test_advice_drill.py -v`
Expected: both tests FAIL because the current prompt has no "dealer bust" text.

- [x] **Step 3: Modify the post-play prompt to include the dealer-bust %**

Edit `backend/routers/advice.py`. In the `_sse_stream()` nested function inside `get_advice` (the `@router.post("/{hand_id}")` handler), find the block around line 153–170 that builds `messages` and:

1. Add an import for the new odds helper at the top of `_sse_stream` alongside the existing strategy/engine imports.
2. Compute the bust % and weave it into the user-content string.

The edited block should read:

```python
        # ── Build Chipy prompt ───────────────────────────────────────────────
        from backend.game.blackjack import odds as _odds  # noqa: PLC0415

        hand_desc = strategy.explain_decision(
            player_cards=hand.cards,
            dealer_upcard=dealer_upcard,
            was_correct=was_correct,
            player_guess=body.player_guess,
            optimal=opt,
        )
        bust_pct = _odds.dealer_bust_pct(dealer_upcard)
        bust_pct_int = round(bust_pct * 100)
        messages = [
            {
                "role": "user",
                "content": (
                    f"I had {hand_desc} "
                    f"I guessed '{body.player_guess}' and the optimal play was '{opt}'. "
                    f"Dealer bust probability for that upcard is {bust_pct_int}% "
                    f"({bust_pct:.2f}). "
                    f"Please explain why '{opt}' is "
                    f"{'correct' if was_correct else 'the better choice'}, "
                    f"and weave the dealer bust % into your reasoning."
                ),
            }
        ]
```

Do not touch the pre-play endpoint (`get_pre_advice`) — AC-B4 says it stays unchanged.

- [x] **Step 4: Run the new test to verify it passes**

Run: `pytest backend/tests/test_advice_drill.py -v`
Expected: both tests pass.

- [x] **Step 5: Run the full backend suite to verify nothing broke (AC-B5)**

Run: `pytest backend/tests -v`
Expected: every prior test still passes (including the existing T13 advice tests in `test_endpoints.py`).

- [x] **Step 6: Commit**

```
git add backend/routers/advice.py backend/tests/test_advice_drill.py
git commit -m "feat(advice): feed dealer-bust %% to Chipy's post-play prompt"
```

---

### Task 3: Add `coachMode` + `chipyDrillPrompt` to the Zustand store

**Files:**
- Modify: `frontend/src/store/gameStore.ts`

This task ships store wiring only; no UI yet, so we verify with `tsc` + the existing Vitest suite still passing. The failing-test step is folded into Task 5 (the component test exercises the store).

- [x] **Step 1: Extend the `GameState` interface**

In `frontend/src/store/gameStore.ts`, add to the `GameState` interface (next to the other Chipy fields around lines 26–35):

```ts
  // ─── Drill Mode (active-retrieval coaching) ─────────────────────────────
  /** Coaching style. "quick" = current behavior (Chipy reveals before you act).
   *  "drill" = Chipy holds back the recommendation and quizzes you instead.
   *  Persisted in localStorage under "betwise.coachMode". */
  coachMode: "quick" | "drill";
  /** Static drill-mode question shown when no narration is streaming. Owned
   *  by Table.tsx's pre-stream effect; ChipyCoach reads it. Null in quick
   *  mode or after Chipy starts narrating. */
  chipyDrillPrompt: string | null;
```

- [x] **Step 2: Extend the `GameActions` interface**

Add to `GameActions` (next to the existing Chipy actions):

```ts
  /** Flip Quick/Drill and persist to localStorage. */
  setCoachMode: (mode: "quick" | "drill") => void;
  /** Set or clear the static drill prompt shown by ChipyCoach. */
  setChipyDrillPrompt: (prompt: string | null) => void;
```

- [x] **Step 3: Wire up initial state + actions in `create<...>(...)`**

At the top of the `create` factory (above `tableState: null,`), add a helper for reading the persisted mode. Then add `coachMode` and `chipyDrillPrompt` to the initial state object, and implement the two new actions just before the closing `}));`:

```ts
const COACH_MODE_STORAGE_KEY = "betwise.coachMode";

function loadCoachMode(): "quick" | "drill" {
  if (typeof window === "undefined") return "quick";
  try {
    const raw = window.localStorage.getItem(COACH_MODE_STORAGE_KEY);
    if (raw === "quick" || raw === "drill") return raw;
  } catch {
    // localStorage may throw in sandboxed iframes; fall through.
  }
  return "quick";
}
```

In the initial state object add:

```ts
  coachMode: loadCoachMode(),
  chipyDrillPrompt: null,
```

And before `}));` (after `setLastFinishedHandId`) add:

```ts
  setCoachMode: (mode: "quick" | "drill") => {
    if (typeof window !== "undefined") {
      try {
        window.localStorage.setItem(COACH_MODE_STORAGE_KEY, mode);
      } catch {
        // Swallow storage errors; in-memory state still updates below.
      }
    }
    set({ coachMode: mode });
  },

  setChipyDrillPrompt: (prompt: string | null) => {
    set({ chipyDrillPrompt: prompt });
  },
```

- [x] **Step 4: Type-check + run existing tests**

Run: `npm --prefix frontend run typecheck` (or `npx --prefix frontend tsc --noEmit` if no typecheck script exists)
Run: `npm --prefix frontend test`
Expected: type-check is clean; the existing ChipyPanel and SessionReviewModal specs still pass — they don't read `coachMode`.

- [x] **Step 5: Commit**

```
git add frontend/src/store/gameStore.ts
git commit -m "feat(store): persisted coachMode + drill prompt slot"
```

---

### Task 4: Render the Quick/Drill toggle in ChipyCoach + surface the drill prompt

**Files:**
- Modify: `frontend/src/components/ChipyCoach.tsx`

- [x] **Step 1: Edit `ChipyCoach.tsx` to consume the new store fields**

Replace the body of the component. The new version reads `coachMode`, `setCoachMode`, and `chipyDrillPrompt` from the store; renders a two-pill toggle in the header (disabled while streaming); and prefers `chipyDrillPrompt` text when no narration text is streaming and we're in drill mode.

```tsx
import { useGameStore } from "../store/gameStore";
import Chipy from "./Chipy";
import type { ChipyExpression, ChipyAnimation, ChipyPose } from "./Chipy";
import { t } from "../i18n";

function stripMarkdown(text: string): string {
  return text
    .replace(/^#{1,6}\s*/gm, "")
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/__([^_]+?)__/g, "$1")
    .replace(/(?<!\*)\*([^*\n]+?)\*(?!\*)/g, "$1")
    .replace(/`([^`]+?)`/g, "$1")
    .replace(/^\s*[-*+]\s+/gm, "");
}

export default function ChipyCoach() {
  const {
    chipyText,
    chipyStreaming,
    chipyPhase,
    coachMode,
    setCoachMode,
    chipyDrillPrompt,
  } = useGameStore();
  const text = stripMarkdown(chipyText);

  let expression: ChipyExpression = "idle";
  let animation: ChipyAnimation = "idle";
  let pose: ChipyPose = "rest";
  let banner = t("Watchin' the table");

  if (chipyStreaming) {
    expression = "thinking";
    animation = "think";
    pose = "rest";
    banner = chipyPhase === "pre" ? t("Sizin' it up…") : t("Callin' the play…");
  } else if (chipyPhase === "pre") {
    expression = "idle";
    animation = "idle";
    pose = "point";
    banner = t("Your move");
  } else if (chipyPhase === "post") {
    expression = "happy";
    animation = "bounce";
    pose = "thumbsup";
    banner = t("Last hand");
  }

  // In drill mode, when nothing is streaming, show the static quiz prompt
  // instead of (empty) narration text. Falls back to chipyText if Chipy is
  // (or just was) talking — so the post-play reveal still renders normally.
  const isDrill = coachMode === "drill";
  const bodyText =
    isDrill && !text && chipyDrillPrompt ? chipyDrillPrompt : text;

  const toggleBase =
    "px-3 py-1 rounded-full font-ui text-[10px] uppercase tracking-widest " +
    "border-[2px] border-ink transition-colors disabled:opacity-40 " +
    "disabled:cursor-not-allowed";
  const toggleActive = "bg-ink text-cream";
  const toggleInactive = "bg-cream text-ink hover:bg-gold-bright";

  return (
    <aside
      className="ink-outline-thick rounded-xl flex flex-col w-full lg:w-72 xl:w-80 self-start"
      style={{ backgroundColor: "#1A0A00", boxShadow: "6px 6px 0 0 #1A0A00" }}
      aria-live="polite"
      aria-busy={chipyStreaming}
    >
      <header
        className="flex items-center gap-3 px-3 py-2 border-b-[3px] border-ink"
        style={{ backgroundColor: "#D4AC0D" }}
      >
        <Chipy size={56} expression={expression} animation={animation} pose={pose} />
        <div className="flex flex-col leading-tight flex-1 min-w-0">
          <h2 className="font-display text-ink text-xl tracking-wider leading-none">
            CHIPY
          </h2>
          <span className="font-flavor text-ink/80 text-xs italic truncate">
            {banner}
          </span>
        </div>
        <div
          role="group"
          aria-label={t("Coach mode")}
          className="flex gap-1"
        >
          <button
            type="button"
            onClick={() => setCoachMode("quick")}
            disabled={chipyStreaming}
            aria-pressed={coachMode === "quick"}
            className={`${toggleBase} ${coachMode === "quick" ? toggleActive : toggleInactive}`}
          >
            {t("Quick")}
          </button>
          <button
            type="button"
            onClick={() => setCoachMode("drill")}
            disabled={chipyStreaming}
            aria-pressed={coachMode === "drill"}
            className={`${toggleBase} ${coachMode === "drill" ? toggleActive : toggleInactive}`}
          >
            {t("Drill")}
          </button>
        </div>
      </header>
      <div
        className="paper-grain p-3 min-h-[120px] flex items-start"
        style={{ backgroundColor: "#F5F0E8" }}
      >
        {bodyText ? (
          <p className="font-body text-ink text-sm leading-relaxed whitespace-pre-line">
            {bodyText}
          </p>
        ) : (
          <p className="font-flavor text-ink/60 text-sm italic">
            {t("Howdy. I'll chime in when there's a play to make.")}
          </p>
        )}
      </div>
    </aside>
  );
}
```

- [x] **Step 2: Type-check + run existing tests**

Run: `npm --prefix frontend run typecheck`
Run: `npm --prefix frontend test`
Expected: type-check clean; existing specs unaffected (they don't render ChipyCoach).

- [x] **Step 3: Commit**

```
git add frontend/src/components/ChipyCoach.tsx
git commit -m "feat(chipy): Quick/Drill pill toggle + drill-prompt surface"
```

---

### Task 5: Gate `streamPreAdvice` on coach mode and write the component test

**Files:**
- Modify: `frontend/src/pages/Table.tsx:107-129`
- Test: `frontend/tests/CoachMode.test.tsx`

- [x] **Step 1: Write the failing test**

Create `frontend/tests/CoachMode.test.tsx`:

```tsx
/**
 * CoachMode.test.tsx — covers AC-F1..F7 / AC-T3.
 *
 * We render ChipyCoach (toggle UI) + a tiny harness that mimics Table.tsx's
 * pre-stream effect. We assert:
 *   - both pills render
 *   - clicking flips coachMode in the store
 *   - quick mode causes streamPreAdvice to be called when a hand goes active
 *   - drill mode suppresses streamPreAdvice and instead surfaces the static
 *     prompt via setChipyDrillPrompt
 *   - the toggle is disabled while chipyStreaming === true
 */
import { useEffect } from "react";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { beforeAll, afterAll, afterEach, beforeEach, describe, it, expect, vi } from "vitest";

import ChipyCoach from "../src/components/ChipyCoach";
import { useGameStore } from "../src/store/gameStore";

// Spy on the SSE consumer so we can assert "called" vs "not called".
vi.mock("../src/api/client", async () => {
  return {
    streamPreAdvice: vi.fn(async (
      _handId: string,
      _onChunk: (t: string) => void,
      onDone: () => void,
      _onError: (m: string) => void,
    ) => {
      onDone();
    }),
    streamAdvice: vi.fn(),
  };
});

import { streamPreAdvice } from "../src/api/client";

const handlers = [
  http.post("/api/advice/:handId/pre", () =>
    new HttpResponse("data: {\"optimal_action\":\"hit\",\"phase\":\"pre\"}\n\n", {
      headers: { "Content-Type": "text/event-stream" },
    }),
  ),
];
const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterAll(() => server.close());
afterEach(() => {
  server.resetHandlers();
  vi.clearAllMocks();
});

// Reset Zustand state between tests so coachMode doesn't leak.
beforeEach(() => {
  // Clear localStorage so loadCoachMode() defaults to "quick".
  try {
    window.localStorage.removeItem("betwise.coachMode");
  } catch {
    // ignore
  }
  act(() => {
    useGameStore.setState({
      coachMode: "quick",
      chipyDrillPrompt: null,
      chipyText: "",
      chipyStreaming: false,
      chipyPhase: "idle",
      chipyHandId: null,
    });
  });
});

/**
 * Tiny harness that mirrors the pre-stream effect we ship in Table.tsx.
 * The real component logic must match this shape (Task 5 step 3).
 */
function PreStreamHarness({ handId, handActive }: { handId: string; handActive: boolean }) {
  const {
    coachMode,
    beginChipyStream,
    appendChipyChunk,
    endChipyStream,
    setChipyDrillPrompt,
  } = useGameStore();

  useEffect(() => {
    if (!handActive) return;
    if (coachMode === "quick") {
      beginChipyStream("pre", handId);
      void streamPreAdvice(
        handId,
        (chunk) => appendChipyChunk(chunk),
        () => endChipyStream(),
        () => endChipyStream(),
      );
    } else {
      setChipyDrillPrompt(
        "Your call. Hit, stand, or double? What's the dealer most likely sitting on?",
      );
    }
    // We intentionally only re-run when the hand-active edge flips.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [handActive, handId, coachMode]);

  return null;
}

describe("CoachMode toggle", () => {
  it("renders both Quick and Drill pills", () => {
    render(<ChipyCoach />);
    expect(screen.getByRole("button", { name: /quick/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /drill/i })).toBeInTheDocument();
  });

  it("clicking Drill flips the store's coachMode and persists to localStorage", async () => {
    const user = userEvent.setup();
    render(<ChipyCoach />);
    expect(useGameStore.getState().coachMode).toBe("quick");

    await user.click(screen.getByRole("button", { name: /drill/i }));

    expect(useGameStore.getState().coachMode).toBe("drill");
    expect(window.localStorage.getItem("betwise.coachMode")).toBe("drill");
  });

  it("is disabled while a stream is in flight", () => {
    act(() => {
      useGameStore.setState({ chipyStreaming: true });
    });
    render(<ChipyCoach />);
    expect(screen.getByRole("button", { name: /quick/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /drill/i })).toBeDisabled();
  });
});

describe("pre-stream gating by coachMode", () => {
  it("quick mode fires streamPreAdvice when the hand goes active", () => {
    render(
      <>
        <ChipyCoach />
        <PreStreamHarness handId="h-quick" handActive={true} />
      </>,
    );
    expect(streamPreAdvice).toHaveBeenCalledTimes(1);
    expect(streamPreAdvice).toHaveBeenCalledWith(
      "h-quick",
      expect.any(Function),
      expect.any(Function),
      expect.any(Function),
    );
  });

  it("drill mode does NOT fire streamPreAdvice and surfaces the static prompt", () => {
    act(() => {
      useGameStore.setState({ coachMode: "drill" });
    });

    render(
      <>
        <ChipyCoach />
        <PreStreamHarness handId="h-drill" handActive={true} />
      </>,
    );

    expect(streamPreAdvice).not.toHaveBeenCalled();
    expect(screen.getByText(/your call/i)).toBeInTheDocument();
    expect(screen.getByText(/dealer most likely/i)).toBeInTheDocument();
  });
});
```

- [x] **Step 2: Run the test to verify the parts that already work pass and the Table-gating parts pass thanks to the harness**

Run: `npm --prefix frontend test -- CoachMode`
Expected: All five `it` blocks pass — Tasks 3 + 4 + the harness fully exercise AC-F1, F2, F3, F4, F7. (`PreStreamHarness` is the test's local mirror of Table.tsx's effect; Step 3 below ships the production version so the *real* Table.tsx behaves the same way.)

If any of these fail, debug before moving on — the production-code change in Step 3 depends on this contract holding.

- [x] **Step 3: Edit `Table.tsx` to gate `streamPreAdvice` on `coachMode`**

In `frontend/src/pages/Table.tsx`, around lines 82–90, pull `coachMode` and `setChipyDrillPrompt` from the store:

```ts
  const {
    tableState,
    myHand,
    beginChipyStream,
    appendChipyChunk,
    endChipyStream,
    resetChipy,
    lastFinishedHandId,
    coachMode,
    setChipyDrillPrompt,
  } = useGameStore();
```

Then replace the existing pre-stream `useEffect` (currently lines 107–129) with the gated version:

```ts
  // Proactive Chipy. In "quick" mode we fire the pre-stream so Chipy chimes
  // in with the recommendation before the player acts. In "drill" mode we
  // hold the recommendation back and surface a static quiz prompt instead;
  // the post-play stream still fires from ActionBar so Chipy reveals the
  // answer + dealer-bust % after the player commits.
  const lastPreHandRef = useRef<string | null>(null);
  useEffect(() => {
    if (!myHand) {
      lastPreHandRef.current = null;
      setChipyDrillPrompt(null);
      return;
    }
    const sessionPlaying = tableState?.session?.status === "playing";
    const handActive = myHand.status === "active";
    if (
      sessionPlaying &&
      handActive &&
      lastPreHandRef.current !== myHand.id
    ) {
      lastPreHandRef.current = myHand.id;
      const handId = myHand.id;
      if (coachMode === "quick") {
        setChipyDrillPrompt(null);
        beginChipyStream("pre", handId);
        void streamPreAdvice(
          handId,
          (chunk) => appendChipyChunk(chunk),
          () => endChipyStream(),
          () => endChipyStream(),
        );
      } else {
        // Drill mode: no proactive narration. Show the quiz line until the
        // player commits an action; ActionBar's streamAdvice will replace
        // it with the post-play reveal.
        setChipyDrillPrompt(
          t("Your call. Hit, stand, or double? What's the dealer most likely sitting on?"),
        );
      }
    }
  }, [
    myHand,
    tableState?.session?.status,
    coachMode,
    beginChipyStream,
    appendChipyChunk,
    endChipyStream,
    setChipyDrillPrompt,
  ]);
```

Notes for the implementer:
- Do NOT remove the existing cleanup `useEffect` for `resetChipy` or the auto-leave one — those stay as-is.
- `setChipyDrillPrompt(null)` is called in two places: when the player has no hand (so a stale prompt doesn't linger across rounds) and in the quick-mode branch (so flipping Quick → Drill → Quick mid-round clears any leftover prompt cleanly).

- [x] **Step 4: Run the full frontend test suite**

Run: `npm --prefix frontend test`
Expected: `CoachMode.test.tsx` plus all prior specs pass. Re-run `npm --prefix frontend run typecheck`; expected clean.

- [x] **Step 5: Commit**

```
git add frontend/src/pages/Table.tsx frontend/tests/CoachMode.test.tsx
git commit -m "feat(table): drill mode gates pre-stream and shows quiz prompt"
```

---

### Task 6: Full-suite verification + final commit cleanup

- [x] **Step 1: Backend full run**

Run: `pytest backend/tests -v`
Expected: every backend test passes — both the new ones and every previously-existing one (AC-B5).

- [x] **Step 2: Frontend full run**

Run: `npm --prefix frontend test`
Run: `npm --prefix frontend run typecheck`
Expected: all specs green; type-check clean (AC-F8).

- [x] **Step 3: Sanity-walk the AC list**

Open `specs/drill-mode.md` and tick off each AC bullet against the commits. Anything still red is a follow-up.

- [x] **Step 4: No commit** unless one of the above checks surfaced a fix.

---

## Verification commands

- Backend single-file: `pytest backend/tests/test_odds.py -v`
- Backend prompt test: `pytest backend/tests/test_advice_drill.py -v`
- Backend full: `pytest backend/tests -v`
- Frontend single-file: `npm --prefix frontend test -- CoachMode`
- Frontend full: `npm --prefix frontend test`
- Type-check: `npm --prefix frontend run typecheck`

---

## Open questions

1. **Drill prompt wording.** The plan uses *"Your call. Hit, stand, or double? What's the dealer most likely sitting on?"* per the spec. If product wants a different line, change it in `Table.tsx` and update the assertion in `CoachMode.test.tsx` (the `/your call/i` + `/dealer most likely/i` regexes).
2. **Prompt format for the %**. The implementation renders the bust % as both `42%` (integer percent) and `0.42` (raw float) in the same sentence, which lets Chipy phrase it either way. If you'd rather pin only one form, update both the prompt string and the assertion's accepted-token list in `test_advice_drill.py`.
3. **A11y: how should screen readers announce the toggle group?** Currently we use `role="group"` + `aria-label="Coach mode"` and `aria-pressed` on the pills. If the design team prefers a tabs metaphor (`role="tablist"` + `role="tab"`), that's a one-file change in `ChipyCoach.tsx` and an update to the test's button queries.
4. **Should Drill mode track its own accuracy stat (e.g. "drill streak" separate from `current_streak`)?** Currently no — the existing streak counts both modes. The spec lists "Per-hand-category drills" and "Mid-action timer / streak bonuses" as out of scope, which I'm reading to cover this too. Confirm before adding any new column.
