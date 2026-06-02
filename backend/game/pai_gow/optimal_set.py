"""backend.game.pai_gow.optimal_set — Chipy's optimal split + EV evaluation.

Pure functions. Layered on top of `house_way` with a documented Wong
deviation table — v1 ships with the deviation table EMPTY, so
`find_optimal` mirrors `house_way` for every input.

Two public functions:

- `find_optimal(seven_cards) -> OptimalSplit`
    Returns Chipy's recommended split for a 7-card hand. v1: always
    `house_way` output with `ev_unit_cents=0` and `reasoning_key="house_way"`.
    v2 may return deviated splits with `ev_unit_cents > 0` (the gain over
    house way) and a deviation identifier in `reasoning_key`.

- `evaluate_split(seven_cards, player_front, player_back) -> SplitEvaluation`
    Evaluates a player's chosen split against `find_optimal`'s output.
    Returns `is_optimal: bool`, `ev_loss_unit_cents: int`, and the optimal
    split alongside so Chipy can render the post-play "should have been …"
    explanation. Uses the spec §12.5 canonical-sort comparison so the
    player's input card order doesn't affect equality.

**Phase 4 contract** (user-flagged after the house_way review): `state.py`
must route `was_optimal` / strategy-streak updates through `evaluate_split`,
NOT through a direct comparison against `house_way.foxwoods`. When v2 adds
Wong deviations, `find_optimal` will diverge from house_way on specific
patterns — comparing against house_way would falsely penalize the player
for correctly following Chipy's deviation. Verified by
`test_phase4_contract_was_optimal_uses_optimal_set_not_house_way`.

Caching: `find_optimal` is deterministic on canonical hand form. Phase 7's
Chipy advice endpoint should wrap calls with `canonical.cache_key(...)` so
repeated evaluations of structurally-equivalent hands hit a single entry.

Spec refs: §12.2 (Chipy tool calls), §12.5 (was_optimal canonical sort),
§7.6 (no-commission ruleset baked into the deviation EVs when v2 adds them).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from backend.game.pai_gow.cards import Card
from backend.game.pai_gow.evaluator import score_hand
from backend.game.pai_gow.house_way import foxwoods


@dataclass(frozen=True)
class OptimalSplit:
    """Chipy's recommended split for a 7-card hand.

    front: 2 cards.
    back: 5 cards.
    ev_unit_cents: cents-per-unit-bet gain over the house way. 0 when the
        optimal split IS the house way (v1 always); positive when v2
        deviations are active and a deviated split adds EV.
    reasoning_key: short identifier for the recommendation. "house_way" in
        v1; v2 deviation entries use stable keys like "wong_low_two_pair"
        so Chipy's prompt template can look up the right explanation.
    """
    front: list[Card]
    back: list[Card]
    ev_unit_cents: int
    reasoning_key: str


@dataclass(frozen=True)
class SplitEvaluation:
    """Result of comparing a player's split to Chipy's optimal.

    is_optimal: True iff player's split (after canonical sort per §12.5)
        matches the optimal split exactly.
    ev_loss_unit_cents: cents-per-unit-bet sacrificed by deviating from
        optimal. 0 when is_optimal=True. v1 attributes the loss as
        `optimal.ev_unit_cents` for non-optimal plays (a simplification —
        v2 may compute the actual EV loss from the player's specific
        alternative split).
    optimal_front / optimal_back: the optimal split, exposed so Chipy can
        render "should have been ..." in the post-play explanation.
    reasoning_key: passed through from OptimalSplit for prompt lookup.
    """
    is_optimal: bool
    ev_loss_unit_cents: int
    optimal_front: list[Card]
    optimal_back: list[Card]
    reasoning_key: str


# Deviation table: maps canonical-form keys to deviated splits with EV.
# Empty in v1 — `find_optimal` always falls through to `house_way`. Adding
# a deviation in v2 is a localized change to this dict; callers (state.py,
# the Chipy advice router) don't need to change.
#
# Future entry shape (v2):
#   _DEVIATIONS[canonical_form_key] = {
#       "front_pattern": [...],
#       "back_pattern": [...],
#       "ev_unit_cents": N,
#       "reasoning_key": "wong_<pattern_name>",
#   }
_DEVIATIONS: dict = {}


# ─── Public API ──────────────────────────────────────────────────────────────


def find_optimal(cards: list[Card]) -> OptimalSplit:
    """Return Chipy's optimal split for a 7-card hand.

    v1: every hand returns `house_way`'s split with `ev_unit_cents=0` and
    `reasoning_key="house_way"`. v2 may consult the `_DEVIATIONS` table
    keyed by canonical form and return a deviated split.

    Raises ValueError if `cards` is not exactly 7 cards long.
    """
    if len(cards) != 7:
        raise ValueError(f"find_optimal expects 7 cards, got {len(cards)}")

    # v2 deviation lookup (currently no-op — table is empty).
    # When populated, the canonical_form key gives suit-rotation-invariant
    # access; the lookup would happen here before falling through.
    #
    # if (deviation := _DEVIATIONS.get(canonical_form(cards))) is not None:
    #     return _materialize_deviation(cards, deviation)

    front, back = foxwoods(cards)
    return OptimalSplit(
        front=front,
        back=back,
        ev_unit_cents=0,
        reasoning_key="house_way",
    )


def evaluate_split(
    cards: list[Card],
    player_front: list[Card],
    player_back: list[Card],
) -> SplitEvaluation:
    """Compare the player's chosen split against `find_optimal`'s output.

    Uses **hand-strength equality** (`score_hand`) instead of card-identity
    equality. This is the round-7 catch over and above round-6 #5: comparing
    the actual cards (even after canonical sort) falsely flags EV-equivalent
    swaps as suboptimal. Examples:

    - Quad K split (`KK | KK + kickers`): all 4 K's are interchangeable for
      front; picking K♣K♦ vs K♥K♠ for front are EV-identical pair-of-K hands,
      but card-identity comparison would say "wrong cards" and reset the
      streak.
    - Straight using one of two same-rank cards (e.g., 9-8-7-6-5 with two 9's
      in hand): either 9 can fill the straight slot, same EV.
    - Flush using any 5 of N+ suited cards.

    Hand-strength equality correctly identifies all these as optimal because
    `score_hand` returns identical tuples for EV-identical hands. Order
    independence (round-6 #5) is free because `score_hand` sorts ranks
    internally — no need for explicit canonical sort of the lists.

    Phase 4 calls this from the post-set advice endpoint and the
    strategy-streak update path. It is the AUTHORITATIVE oracle for
    `was_optimal` — do NOT compare directly against `house_way.foxwoods`
    in Phase 4, because v2 deviations will route through `find_optimal`
    and a house_way-based comparison would falsely penalize the player.
    """
    if len(cards) != 7:
        raise ValueError(f"evaluate_split expects 7 cards, got {len(cards)}")

    optimal = find_optimal(cards)

    # Hand-strength equality (round-7 fix): score_hand handles both order
    # independence (internal sort) AND EV-equivalent card swaps in a single
    # comparison. Two splits with identical strength tuples ARE EV-identical
    # by definition — the player's "win-on-side" probability against any
    # dealer hand depends only on the strength tuple, not on which specific
    # cards built it.
    is_optimal = (
        score_hand(player_front) == score_hand(optimal.front)
        and score_hand(player_back) == score_hand(optimal.back)
    )

    if is_optimal:
        ev_loss = 0
    else:
        # v1 simplification: attribute the full optimal-vs-house-way gain
        # as the loss. v2 may compute the specific player-split EV vs
        # optimal-split EV for a more accurate value.
        ev_loss = optimal.ev_unit_cents

    return SplitEvaluation(
        is_optimal=is_optimal,
        ev_loss_unit_cents=ev_loss,
        optimal_front=optimal.front,
        optimal_back=optimal.back,
        reasoning_key=optimal.reasoning_key,
    )
