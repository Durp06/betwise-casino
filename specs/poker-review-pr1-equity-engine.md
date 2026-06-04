# Poker Review — PR 1: Equity Engine + Decision Grader

**Status:** Plan / ready for tester
**Date:** 2026-06-04
**Parent design:** `specs/poker-review-design.md` (approved) — this is the
"equity engine + grader" component (Decomposition §1).
**Scope:** pure backend only. No endpoints, no persistence, no migration, no
frontend. Those are PR 2.

---

## 1. Context

BetWise blackjack has a chess.com-style decision review
(`backend/game/blackjack/review.py` + `ev.py`, surfaced by
`SessionReviewModal`). The approved design (`specs/poker-review-design.md`)
brings the same equity-backed grading to poker (solo SNG + multiplayer
Hold'em) as a **compute-on-read** feature that writes nothing.

The load-bearing prerequisite is a **win-equity engine**. Today
`live_equity` is stubbed `None` at every oracle call site
(`backend/routers/poker_game.py` lines 421/444/511/633,
`backend/routers/poker_advice.py` line 272). The oracle
(`backend/game/poker/oracle.py::classify_decision`) therefore can only grade
two DETERMINISTIC buckets (short-stack push/fold via `nash.py`, and pot-odds
call-vs-all-in) — everything else falls through to a HEURISTIC `no_verdict`.

PR 1 builds the missing piece and uses it:

1. A new pure module `backend/game/poker/equity.py` that computes a hero's
   win probability against opponent ranges, exactly (enumeration) when ≤2
   board cards remain and via **seeded** Monte-Carlo otherwise — the
   constraint mandated by `specs/texas-holdem.md` §Modules (line 39:
   "exact enumeration when ≤2 cards remain across players; Monte Carlo
   otherwise") and the design §"Modest, seeded Monte-Carlo".
2. An **extension** of `oracle.py::classify_decision` so that, when
   `live_equity` is now supplied, it grades ordinary call/check/fold via EV
   and bet/raise via a simplified semi-bluff model, producing the design's
   six-tier verdict + `ev_loss_bb`, while leaving the existing DETERMINISTIC
   buckets (and all current callers passing `live_equity=None`) **exactly as
   they are**.

The architectural template is `backend/game/blackjack/ev.py` (pure-sync,
deterministic, memoized) and the bucketing shape is
`backend/game/blackjack/review.py::_bucket_delta` (ported to big-blind
units).

### Constraints carried from the design
- **Pure-sync, deterministic, no DB, no IO.** Same shape as `ev.py`.
- **Seeded RNG**: the engine takes an *explicit* `seed: int` argument and uses
  `random.Random(seed)` (the same primitive `cards.create_deck` uses). Same
  seed → byte-identical float. The *source* of the seed (hand id) is wired in
  PR 2; PR 1 only requires the engine honor whatever seed it is handed.
- **Backward compatibility is a hard gate.** `classify_decision`'s existing
  signature, return type field names, and behavior for `live_equity=None`
  must not change. Existing `backend/tests/test_poker_oracle.py` must stay
  green untouched. New verdict fields are *additive* (optional, defaulted).
- **Range model deliberately simple in v1.** A positional/tightness-tunable
  default range for multiplayer; an adapter that reads bot archetype ranges
  (`archetypes.py` / `ranges.py`) for solo. A single tightness knob is
  acceptable — no per-action range narrowing in v1.

---

## 2. Non-goals (explicitly out of scope for PR 1)

- **No endpoints.** No `GET /api/poker/.../review`, no router edits, no
  `poker_game.py` / `poker_advice.py` changes (they keep passing
  `live_equity=None`). Wiring the engine into the review endpoints is PR 2.
- **No persistence / migration.** No new columns, no stored verdicts, no
  equity cache table. Compute-on-read is PR 2's concern; PR 1 ships only pure
  functions.
- **No frontend.** No types, no client fetchers, no modal.
- **No live-play changes.** The deal/act/showdown path is untouched.
- **No GTO solver, no multi-street game-tree search.** Genuinely contextual
  postflop bet/raise spots that the simplified model cannot resolve return
  `no_verdict` — this is the design's honesty boundary, not a TODO.
- **No multi-way range mixing sophistication.** v1 treats each villain with
  the same default/archetype range; no blocker-aware range removal beyond the
  dead cards already on the board + in hero's hand.
- **No streak / ICM rework.** Existing ICM overlay and `counts_toward_streak`
  semantics are preserved as-is. New EV verdicts inherit the existing
  `counts_toward_streak` rule (HEURISTIC tier ⇒ does not count) unless a task
  below states otherwise.

---

## 3. Files to create / modify

| File | Change | Responsibility |
|---|---|---|
| `backend/game/poker/equity.py` | **new** | `hand_equity(...)` (enum + seeded MC), `random_villain_holdings`, the small range model (`default_range`, `archetype_range` adapter), `range_to_combos`. Pure-sync. |
| `backend/game/poker/oracle.py` | **modify** | Add EV-based call/check/fold grading + simplified bet/raise semi-bluff grading + `_bucket_delta_bb` (ported from blackjack). Add additive optional fields (`ev_loss_bb`, `equity`, `required_equity`, `explanation`) to `DecisionClassification`. Keep existing buckets + `live_equity=None` path byte-for-byte behaviorally identical. |
| `backend/tests/test_poker_equity.py` | **new** | Pure unit tests for the equity engine (see ACs E-*). |
| `backend/tests/test_poker_oracle_ev.py` | **new** | Pure unit tests for the *new* EV/semi-bluff grading paths (see ACs G-*). Keeps `test_poker_oracle.py` untouched for the backward-compat ACs. |

Note: `specs/texas-holdem.md` line 39 sketched a slightly different signature
(`equity(hero_hole, opp_holes_or_ranges, board, iters=20000)`). The approved
review design pins the name/signature to
`hand_equity(hero_hole, villain_ranges, board, *, seed, max_iters=2000)`.
**Honor the design.** Optionally expose a thin `equity = hand_equity` alias
for the older name if any caller in PR 2 wants it — but do not add callers in
PR 1.

---

## 4. Design detail (to ground the tasks)

### 4.1 `hand_equity` signature & semantics
```
hand_equity(
    hero_hole: tuple[Card, Card],
    villain_ranges: list[Range],   # one Range per live villain
    board: list[Card],             # 0 / 3 / 4 / 5 cards
    *,
    seed: int,
    max_iters: int = 2000,
) -> float
```
- Returns hero's probability of winning the pot at showdown, **ties counted
  as fractional wins** (a 2-way chop contributes 0.5; an N-way tie
  contributes 1/N).
- **Exact enumeration** when the number of board cards still to come is ≤ 2
  (i.e. `len(board) >= 3`: turn has 1 to come, river has 0 to come). The
  design and `specs/texas-holdem.md` both say "≤2 cards remain" — interpret
  as **board cards to come ≤ 2**, which is flop/turn/river. (Preflop has 5 to
  come and is always Monte-Carlo.) Enumeration walks every legal combination
  of (villain holdings drawn from their ranges) × (remaining board
  completions) over the live deck and averages the fractional-win outcome.
  When enumeration would exceed `max_iters` worth of combinations
  (e.g. multi-way flop with wide ranges), fall back to seeded MC — but for
  the v1 test matrix (heads-up turn/river, narrow ranges) enumeration is
  exact and cheap.
- **Seeded Monte-Carlo** otherwise: `rng = random.Random(seed)`; for
  `max_iters` trials, sample one concrete holding per villain from its range
  (rejection-sampling against dead cards), deal the remaining board, score
  with `evaluator.best_5_of_7`, accumulate fractional wins, divide.
- Uses `cards.remove_cards` to build the live deck (52 − hero hole − board −
  any fixed villain cards) and `evaluator.best_5_of_7` for ranking. No new
  card math.

### 4.2 Range model (small, lives in `equity.py`)
- A `Range` is a set of canonical hand strings (e.g. `{"AA","AKs",...}`)
  reusing `ranges.ALL_HANDS` / `ranges.top_pct` / `ranges.hand_str`.
- `default_range(tightness: float = 0.40) -> Range`: the positional/default
  range for multiplayer humans. v1 = `ranges.top_pct(tightness * 100)`
  (a single tightness knob — design-sanctioned).
- `archetype_range(spec_or_range) -> Range`: adapter for solo that reads a
  bot archetype's play range. Reuse the existing
  `archetypes._all_play_range` / `top_pct(vpip)` notion — do not duplicate
  the archetype tables. Keep the adapter thin; if it just wraps
  `top_pct(vpip*100)` that is fine for v1.
- `range_to_combos(rng, dead_cards) -> list[tuple[Card, Card]]`: expand a
  `Range` of hand strings to concrete 2-card combos with all `dead_cards`
  removed (used by both enumeration and MC sampling).
- A villain range of `None` / "any" means the full random range (uniform over
  all legal 2-card combos) — used for the AA-vs-KK style pinned matchups where
  the design's ACs fix a *specific* villain hand, achievable by passing a
  singleton range like `{"KK"}` and letting `range_to_combos` enumerate its 6
  combos minus dead cards.

### 4.3 Oracle EV extension
Extend `classify_decision` so that, **after** the two existing DETERMINISTIC
short-circuits and **only when `snapshot.live_equity is not None`**, ordinary
decisions are graded with real EV instead of falling to HEURISTIC:

- **call / check / fold** (facing a bet, `to_call_bb > 0`, not already caught
  by the all-in bucket):
  - `pot_bb` is the pot **before** the opponent's bet — the SAME convention as
    `required_equity(pot_before_call, opp_bet)`, which the existing pot-odds
    bucket uses with `pot_before_call = pot_bb`, `opp_bet = to_call_bb`. The
    final pot after the opponent bets `to_call_bb` and hero calls `to_call_bb`
    is therefore `pot_bb + 2 * to_call_bb`.
  - `EV(call) = equity * (pot_bb + 2 * to_call_bb) - to_call_bb`
  - `EV(fold) = 0` (sunk chips excluded).
  - **Consistency:** substituting `equity = required_equity = to_call_bb /
    (pot_bb + 2*to_call_bb)` gives `EV(call) = 0`, so the EV break-even lands
    exactly at the required-equity threshold. Using `pot_bb + to_call_bb` would
    break even at the wrong equity and mis-scale `ev_loss_bb` — caught in review.
  - `required = required_equity(pot_bb, to_call_bb) + _icm_threshold_adjustment(snapshot)`.
  - Best action = `call` if `equity >= required` else `fold`. `ev_loss_bb` =
    `|EV(best) - EV(played)|` in bb. Bucket via `_bucket_delta_bb`.
  - `confidence_tier = "DETERMINISTIC"` for a clean call/fold-vs-bet pot-odds
    spot (it *is* deterministic given equity). This mirrors the existing
    pot-odds-vs-all-in bucket but generalizes it to any bet size.
- **check when `to_call_bb == 0`**: checking is free (`EV(check) = 0` vs a
  hypothetical bet line the model cannot resolve) → `no_verdict` / HEURISTIC
  in v1 (we are not modeling whether hero *should have bet*). Keep it simple.
- **bet / raise** (hero is the aggressor): simplified semi-bluff model.
  - `fe = bluff_breakeven(pot_bb, bet_bb)` — the fold equity needed to break
    even purely as a bluff (from `pot_odds.py`).
  - A bet is "defensible" if either equity is high enough to value-bet
    (`equity >= mdf(...)`-derived threshold) OR the hand has enough equity +
    plausible fold equity to be a profitable semi-bluff. Because actual fold
    equity is unknowable without a villain model, v1 grades only the
    **clear** cases:
    - Clear value bet (high equity) → `best` / `good`, DETERMINISTIC-ish but
      flagged `HEURISTIC` confidence (we cannot price exact EV without a
      villain response model).
    - Everything genuinely contextual (medium equity, multi-street, sizing
      ambiguous) → `no_verdict`, HEURISTIC, with a principle note. **This is
      the dominant branch and the honest default.**
  - Net effect: bet/raise mostly returns `no_verdict` in v1 except the
    obviously-correct value bet. The AC pins exactly one `no_verdict` case and
    (optionally) one clear-value case.

### 4.4 Bucketing (ported from blackjack, tuned to bb)
Add `_bucket_delta_bb(ev_loss_bb: float) -> Verdict` mirroring
`review.py::_bucket_delta`. **Propose** starting thresholds (to be *pinned by
the grader ACs* — exact values are a tuning task, not a guess to ship blind):

| `ev_loss_bb` | verdict |
|---|---|
| ≤ 0.05 | `best` |
| ≤ 0.25 | `good` |
| ≤ 1.0  | `inaccuracy` |
| ≤ 3.0  | `mistake` |
| > 3.0  | `blunder` |

These are starting values; Task 7 pins them against the grader ACs (G-3,
G-4, G-5). If an AC forces a boundary move, move the boundary, do not special-
case the test.

### 4.5 `DecisionClassification` additive fields
Add, with defaults so existing construction sites keep compiling:
```
equity: Optional[float] = None
required_equity: Optional[float] = None
ev_loss_bb: Optional[float] = None
explanation: Optional[str] = None   # short, reuse coach_summary if simplest
```
Do **not** rename or remove `ev_loss_chips`, `coach_summary`,
`principle_note`, `recommended_action`, `correct`, `verdict`,
`confidence_tier`, `counts_toward_streak`. The existing DETERMINISTIC buckets
may *additionally* populate the new fields, but their existing assertions in
`test_poker_oracle.py` must remain true.

---

## 5. Acceptance criteria (1 test per AC)

Tolerance for Monte-Carlo / equity matchups: **±0.02** unless the AC is exact
(enumeration). Tests pass `seed=...` explicitly and may use `max_iters=5000`
to keep runtime low per `specs/texas-holdem.md` line 360.

### Equity engine — `test_poker_equity.py`
- **E-1 (preflop premium vs premium):** `hand_equity(AhAs, [{"KK"}], board=[],
  seed=1, max_iters=5000)` ∈ **[0.80, 0.84]** (AA vs KK ≈ 0.82).
- **E-2 (preflop coin flip):** `hand_equity(AsKs, [{"QQ"}], board=[], seed=1,
  max_iters=5000)` ∈ **[0.46, 0.54]** (AKs vs QQ ≈ a flip).
- **E-3 (determinism):** two calls of `hand_equity(...)` with **identical
  args incl. seed** return the **exact same float** (`==`, not approx).
- **E-4 (seed sensitivity, MC only):** for a preflop (MC) spot, two *different*
  seeds generally differ — assert the function is seed-driven (not constant)
  by checking at least one pair of seeds yields a different float, OR assert
  both land within tolerance of the analytic value (whichever the tester
  finds robust). [Soft AC — keep if cheap; drop if flaky.]
- **E-5 (exact enumeration on the river → made hand dominates):** flush vs a
  set on a complete 5-card board where hero holds the flush →
  `hand_equity(...) == 1.0` exactly (0 cards to come ⇒ enumeration, single
  showdown, hero wins). Tester picks concrete cards
  (e.g. hero two hearts making a flush, villain a set, board with 3 hearts).
- **E-6 (exact enumeration on the turn):** a 4-card board, 1 card to come,
  hero drawing → equity equals the exactly-enumerated fraction (tester
  computes the expected fraction by hand from the 44 remaining cards; assert
  `== expected` exactly, since enumeration is deterministic).
- **E-7 (guaranteed chop → 0.5):** hero and a single villain whose ranges
  force the same best 5 (e.g. the board is the nut hand both must play —
  "play the board" with no better 5-card hand available) → `hand_equity(...)
  == 0.5` exactly (2-way tie, fractional win 0.5).
- **E-8 (enum vs MC agreement):** for a 1-card-to-come spot, the exact
  enumeration result and a Monte-Carlo run of the *same* spot (forced via a
  test hook or by calling MC with `max_iters=5000`) agree within **±0.02**.
- **E-9 (dead-card correctness):** villain range combos that collide with
  hero's hole cards or the board are excluded (e.g. hero holds `Ah`, villain
  range `{"AA"}` on a board with `As Ad` → only the `Ac`-containing AA combo
  remains; assert the engine does not crash and returns a sane equity). This
  pins `range_to_combos` dead-card removal.
- **E-10 (range vs single hand):** `hand_equity(hero, [default_range(0.40)],
  board, seed=...)` runs and returns a float in (0,1); a *tighter* villain
  range (`default_range(0.10)`) yields **lower or equal** hero equity for a
  marginal hero hand (tighter villain ⇒ stronger villain holdings ⇒ hero does
  no better). [Monotonicity sanity, ±0.02 slack.]

### Grader (new EV/semi-bluff paths) — `test_poker_oracle_ev.py`
- **G-1 (clearly −EV call → mistake/blunder):** a deep postflop snapshot
  (so the existing buckets do NOT fire) with `to_call_bb > 0`, low
  `live_equity` well below `required_equity`, human_action=`call` →
  `verdict ∈ {"mistake","blunder"}` and `ev_loss_bb > 0`.
- **G-2 (+EV value call → best):** same shape, `live_equity` comfortably above
  `required_equity`, human_action=`call` → `verdict == "best"` and
  `ev_loss_bb` ≈ 0.
- **G-3 (correct fold of trash → best):** facing a bet, equity far below
  required, human_action=`fold` → `verdict == "best"`, `recommended_action ==
  "fold"`.
- **G-4 (calling a clear fold spot → bucketed loss):** facing a bet, equity
  far below required, human_action=`call` → verdict is at least `mistake`
  (pins the upper end of `_bucket_delta_bb`).
- **G-5 (marginal call near threshold → good/inaccuracy):** equity just
  above/below required → verdict ∈ {`good`,`inaccuracy`} (pins a middle
  boundary).
- **G-6 (contextual multi-street bet → no_verdict):** a deep postflop
  bet/raise spot with medium equity and ambiguous sizing → `verdict ==
  "no_verdict"`, `confidence_tier == "HEURISTIC"`, `counts_toward_streak is
  False`, and a non-empty `principle_note`.
- **G-7 (new fields populated on an EV verdict):** for the G-2 spot,
  `equity`, `required_equity`, and `ev_loss_bb` are all non-`None` and
  internally consistent (`required_equity == pytest.approx(required_equity(
  pot_bb, to_call_bb) + icm_adj)`).

### Backward compatibility (no regressions)
- **G-BC1:** the entire existing `backend/tests/test_poker_oracle.py` passes
  **unchanged** (short-stack push/fold, pot-odds-vs-all-in, HEURISTIC deep
  postflop, ICM overlay, streak invariants). This is the guardrail that the
  oracle extension stayed additive.
- **G-BC2:** `classify_decision(snapshot_with_live_equity_None, action)` for a
  deep postflop spot still returns `confidence_tier == "HEURISTIC"`,
  `verdict == "no_verdict"`, `counts_toward_streak is False` — i.e. the
  `None`-equity path (what every router caller passes today) is behaviorally
  identical to current `main`.
- **G-BC3:** constructing `DecisionClassification(...)` with only the
  pre-existing kwargs still works (the new fields are optional with defaults)
  — guards against an accidental required-arg break for the live callers.

### Definition of done (verification ACs)
- **D-1:** `ruff check backend` is green.
- **D-2:** `python -m pytest backend/tests/ -v` is green (existing 118+ tests
  plus the new equity + oracle-EV tests).
- **D-3:** the new unit tests run in well under the suite budget (target the
  equity tests at `max_iters ≤ 5000`, total added runtime a few seconds).

---

## 6. Task-by-task plan (build order)

Each task ≈ one commit. Tester writes the listed failing tests first; the
implementer makes them pass, then checks in.

### Task 1 — Range model + combo expansion in `equity.py`
- Create `backend/game/poker/equity.py` with `from __future__ import
  annotations`, module docstring referencing the design + `texas-holdem.md`
  line 39.
- Define a `Range` type alias (`frozenset[str]` / `set[str]` of canonical hand
  strings) and `default_range(tightness=0.40)` reusing `ranges.top_pct`.
- Add `archetype_range(...)` thin adapter reusing the archetype VPIP notion
  (no table duplication).
- Add `range_to_combos(rng, dead_cards) -> list[tuple[Card, Card]]` expanding
  hand strings to concrete combos via suit assignment, removing `dead_cards`
  (use `cards` primitives; reuse `ranges.combos_for` accounting only as a
  sanity reference).
- **Covers:** E-9 (dead-card removal), partial E-10.

### Task 2 — Showdown scoring helper + uniform random villain sampling
- Add an internal `_score_showdown(hero_hole, villain_holes, board) ->
  fractional_win_for_hero` using `evaluator.best_5_of_7` (handle 2-way and
  N-way ties → 1/k).
- Add `random_villain_holdings(ranges, dead_cards, rng) -> list[combo]` by
  rejection sampling from each range against running dead cards.
- **Covers:** internal correctness exercised by E-1..E-7.

### Task 3 — Exact enumeration branch
- Implement the enumeration path used when board cards-to-come ≤ 2
  (`len(board) >= 3`): enumerate villain combos × remaining-board completions
  over the live deck, average the fractional win. Guard with a combination-
  count check that falls back to MC above `max_iters`.
- **Covers:** E-5, E-6, E-7, E-8 (enum side).

### Task 4 — Seeded Monte-Carlo branch + `hand_equity` assembly
- Implement the MC path (`random.Random(seed)`, `max_iters` trials).
- Wire `hand_equity(...)` to dispatch enum vs MC by cards-to-come; return the
  fractional-win mean.
- Optional `equity = hand_equity` alias for the `texas-holdem.md` name (no
  callers added).
- **Covers:** E-1, E-2, E-3, E-4, E-8 (MC side), E-10.

### Task 5 — `_bucket_delta_bb` in `oracle.py`
- Port `review.py::_bucket_delta` to bb units with the proposed thresholds
  (§4.4). Pure helper; no behavior change to existing buckets yet.
- **Covers:** scaffolding for G-3..G-5 (boundaries pinned in Task 7).

### Task 6 — Additive fields on `DecisionClassification`
- Add `equity`, `required_equity`, `ev_loss_bb`, `explanation` as optional
  defaulted fields. Update `__all__` only if needed (the dataclass is already
  exported).
- Re-run `test_poker_oracle.py` to confirm zero behavioral change.
- **Covers:** G-BC3, sets up G-7.

### Task 7 — EV grading for call/check/fold + bet/raise semi-bluff
- After the two existing DETERMINISTIC short-circuits, add the
  `live_equity is not None` EV branch (§4.3): call/check/fold via
  `EV(call)/EV(fold)` + `required_equity` + ICM adj, bucketed by
  `_bucket_delta_bb`; bet/raise via the simplified semi-bluff model that
  returns `no_verdict` for contextual spots and a clear verdict only for the
  obvious value case.
- Ensure the `live_equity is None` deep-postflop path still reaches the
  existing HEURISTIC `no_verdict` return unchanged.
- Tune the §4.4 thresholds so G-1..G-5 pass; move boundaries, never special-
  case tests.
- **Covers:** G-1, G-2, G-3, G-4, G-5, G-6, G-7, and protects G-BC1, G-BC2.

### Task 8 — Verification pass
- `ruff check backend`, `python -m pytest backend/tests/ -v`. Confirm new
  tests pass and the full suite (incl. untouched `test_poker_oracle.py`) is
  green.
- **Covers:** D-1, D-2, D-3.

---

## 7. Determinism notes (for the implementer + PR 2)
- The engine's only randomness is `random.Random(seed)` inside the MC branch.
  The enumeration branch is fully deterministic (no RNG). PR 1 takes `seed`
  as an explicit argument; **deriving it from a hand id is PR 2's job** — do
  not import models or read DB here.
- Do not call the module-level `random` (unseeded). Always thread the local
  `rng`.
- Keep the function pure: no global mutable state except an optional
  `functools.lru_cache` keyed on *immutable* inputs (mirror `ev.py`'s cache
  discipline — cache keys must be hashable tuples, never mutable card lists).
  Caching is optional in v1; correctness + determinism come first.

## 8. Open questions
1. **"≤2 cards remain" interpretation.** This plan reads it as *board cards
   still to come ≤ 2* ⇒ enumeration on flop/turn/river, MC preflop. The
   design text and `texas-holdem.md` line 39 are consistent with this. If the
   intent was "≤2 unknown cards across hero+villain+board" (a much narrower
   enumeration trigger), flag before Task 3 — but flop-and-later enumeration
   is the natural, testable reading and is what the ACs assume.
2. **Bet/raise grading ambition.** v1 grades only the obvious value bet and
   defaults everything else to `no_verdict` (§4.3). If the tester finds a
   second clear, deterministic bet/raise case worth pinning, add it as G-8 —
   otherwise the single `no_verdict` AC (G-6) is the contract.
3. **Threshold values (§4.4).** Proposed, not sacred. Task 7 pins them against
   G-1..G-5. If those ACs can't all be satisfied with one monotone ladder,
   raise it before hand-tuning per-case.
4. **E-6 expected value is mathematically incorrect.** `test_e6_turn_enumeration_draw_exact_fraction` asserts `9/44` exactly for hero holding Ah Th vs KK on board Kh Qh 2c 8d (turn). The test comment says "If river ≠ heart → villain wins (trips > hero's ace-high)" — but it misses that off-suit Jacks give hero a Broadway straight (A-K-Q-J-T) which beats villain's trips. The correct enumeration answer is 10/44 (9 hearts + 3 off-suit Jacks = 10 outs). The engine returns 10/44 which is correct; the test expects 9/44 which is wrong. This test cannot be made to pass without either changing the expected value or lying in the implementation. Needs tester to fix the expected value (or change the board to remove the straight draw) — out of scope for the implementer.
