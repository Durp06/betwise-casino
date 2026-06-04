# Poker Review — PR 2: compute-on-read endpoints + UI (LOCKED CONTRACT)

Parent: `specs/poker-review-design.md`. Builds on PR1 (`backend/game/poker/equity.py`
`hand_equity(...)`, `backend/game/poker/oracle.py` `classify_decision(snapshot, action, mode)`).

Lightweight + fast: compute-on-read, **no migration**, **no change to live /act/deal/showdown**.
Per-hand Hand Review is the core; Game Review is a thin aggregation. ONE shared frontend modal.

## Locked API (both halves build to this — do not deviate)

Four GET endpoints, all compute-on-read, all require the caller to have held a seat in the
hand/session (else 403), all grade ONLY the caller's own decisions:

- `GET /api/holdem/hands/{hand_id}/review`        → `HandReview`
- `GET /api/holdem/tables/{table_id}/review`      → `GameReview`  (scope = caller's current table visit)
- `GET /api/poker/hands/{hand_id}/review`         → `HandReview`
- `GET /api/poker/tournaments/{tournament_id}/review` → `GameReview` (scope = tournament). UPGRADE the
  existing endpoint at this path to this unified shape (its only FE consumer is the unused
  `getPokerSessionReview`, being replaced here; if a backend test asserts the old `PokerSessionReviewOut`
  shape, update that test minimally — keep it green).

### `HandReview` (JSON)
```
{
  "hand_id": str,
  "game": "holdem" | "poker",
  "your_hole": [Card],            // requesting user's hole cards (always revealed to themselves)
  "board": [Card],                // full board reached in the hand
  "graded_count": int,            // # of caller decisions that got a DETERMINISTIC verdict
  "accuracy": float,              // (best+good)/graded_count, 0.0 if graded_count==0
  "ev_lost_bb": float,            // sum of ev_loss_bb over graded decisions
  "worst_action_index": int | null,
  "actions": [                    // ONLY the caller's own actions, in order
    {
      "action_index": int,
      "street": "preflop"|"flop"|"turn"|"river",
      "action": str,              // fold|check|call|raise|all_in
      "amount_bb": float,
      "verdict": "best"|"good"|"inaccuracy"|"mistake"|"blunder"|"no_verdict",
      "confidence_tier": "DETERMINISTIC"|"HEURISTIC",
      "recommended_action": str | null,
      "equity": float | null,
      "required_equity": float | null,
      "ev_loss_bb": float | null,
      "explanation": str | null
    }
  ]
}
```
`Card` = `{ "suit": str, "value": str }` (project convention). Opponent hole cards are NEVER in the
response (range-based grading needs none); multiplayer must not leak folded/again-in-play holes.

### `GameReview` (JSON)
```
{
  "scope": "tournament" | "table_visit",
  "game": "holdem" | "poker",
  "overall_accuracy": float,
  "total_ev_lost_bb": float,
  "graded_count": int,
  "hands": [
    { "hand_id": str, "accuracy": float, "ev_lost_bb": float, "graded_count": int,
      "worst_verdict": "best"|"good"|"inaccuracy"|"mistake"|"blunder"|"no_verdict"|null }
  ]
}
```

## Shared backend assembly (the meat)

A helper (pure given a hand's rows) that, for one finished hand:
1. Deserialize the stored deck; deal hole cards; iterate the action log in `action_index` order
   through `backend.game.poker.state.apply_action`, rebuilding board/pot/street/current-bet.
2. At each action **belonging to the requesting user**, build a `DecisionSnapshot`
   (convert chip amounts → big blinds using the hand's big-blind size; derive position,
   `n_live_opponents`, `to_call_bb`, `pot_bb` = pot BEFORE the bet faced, `hand_str`, etc.),
   compute `live_equity = hand_equity(hero_hole, villain_ranges, board, seed=<derived from hand id>, max_iters=2000)`
   (multiplayer villain_ranges = `default_range()` per live opponent; solo = `archetype_range(...)` if
   available else `default_range()`), then call `classify_decision(snapshot, action, "odds")`.
3. Collect graded actions → `HandReview`. `GameReview` = aggregate per-hand reviews over the scope.

Seed equity from a stable function of the hand id so reviews are reproducible. Reuse the
DecisionSnapshot-construction logic that `poker_game.py::/act` already uses for solo where possible.

Multiplayer "table visit": hands where the caller currently holds a `HoldemHandSeat` linked to their
seat at this table. If no clean sit-start boundary exists, use "all hands the caller has a seat row for
at this table" and add a `# NOTE:` comment. Cap a Game Review at the most recent 50 hands; if capped,
that's fine for v1 (do not silently imply full coverage in field docs).

## Files
Backend: new `backend/routers/poker_review.py` (or extend holdem.py/poker_game.py — your call; thin
handlers + `_` SQL helpers, centralize SQL, register in `backend/main.py`); shared helper in a new
`backend/game/poker/review.py` (pure, sync) or analytics module; `Out` schemas in `backend/schemas.py`.
Frontend: `frontend/src/types/index.ts` (`PokerReview`, `PokerReviewAction`, `PokerGameReview` — NO `any`);
`frontend/src/api/client.ts` (4 typed fetchers, `{data,error}`); `frontend/src/components/PokerReviewModal.tsx`
(on `ModalShell`, reuse blackjack `ClassificationChip` colors + `EvalBar`); entry points in the Hold'em
table page (minimal hand-result UI + "Review hand" + "Session review") and the solo poker table page.

## Acceptance criteria (each builder writes its own tests)
Backend (pytest-asyncio + in-memory SQLite + existing `seed_*` fixtures; add a holdem hand/action seed
helper if missing):
- A finished holdem hand → `HandReview` with a verdict for EACH caller action and NONE for opponents.
- Non-participant caller → 403.
- Opponent hole cards absent from the response.
- chips→bb conversion uses the table big blind (assert amount_bb for a known bet).
- Reproducible: same hand reviewed twice → identical verdicts/equities (seeded).
- Solo: `GET /api/poker/hands/{id}/review` returns a `HandReview`; tournament endpoint returns `GameReview`.
- `GameReview.overall_accuracy`/`total_ev_lost_bb` aggregate the per-hand values.
Frontend (Vitest + MSW, mock the endpoints):
- `PokerReviewModal` renders a verdict chip + your-action-vs-recommended + ev_loss for each action from a
  mocked `HandReview`.
- Loading and error branches both render.
- Game Review list renders rows and clicking one requests that hand's review.

## Definition of done
`python -m pytest backend/tests/ -v` green; `ruff check backend` green;
`cd frontend && npx tsc --noEmit` clean; `cd frontend && npm test -- --run` green;
`cd frontend && npm run build` succeeds.

## Non-goals
No migration, no live-play changes, no GTO solver, no retry-spot drill, no poker hand-history page,
no opponent-decision grading, no streak rework.
