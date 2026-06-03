"""
ev.py — Pure-sync infinite-deck H17 expected-value engine for BetWise Casino.

Model assumptions (specs/blackjack-study.md §Architecture):
- Infinite deck: draw probability for rank r is 1/13 for A and 2..9, 4/13 for
  ten-valued (10/J/Q/K treated uniformly as rank 10).
- Dealer hits hard <=16 and soft 17 (H17); stands hard 17+ and soft 18+.
- Peek (no-hole-card BJ) model: dealer is assumed to have already checked for
  a natural blackjack before the player acts.  When the upcard is Ace, the hole
  card is conditioned on NOT being ten-valued (renormalized first draw).  When
  the upcard is ten-valued, the hole card is conditioned on NOT being an Ace.
  This is the standard assumption underlying published basic-strategy tables.
- EV is in units of the initial bet: win = +1.0, push = 0.0, loss = -1.0.
- Double pays 2× ev_stand over one drawn rank (bust → -2).
- Split EV is deliberately omitted in v1 (split is HTTP 501 in the game layer).
- Pure sync: no async, no random, no sqlalchemy, no IO.
"""

from __future__ import annotations

from typing import Union

from backend.game.blackjack.engine import card_rank, hand_value, is_soft

# ─── Rank probabilities (infinite deck) ──────────────────────────────────────
# Numeric ranks used internally: 2..10 (ten-valued) and 11 (Ace).
# Ten-valued cards (10/J/Q/K) all map to rank 10 with combined probability 4/13.

_RANKS: list[int] = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11]

_RANK_PROB: dict[int, float] = {
    **{r: 1.0 / 13.0 for r in [2, 3, 4, 5, 6, 7, 8, 9, 11]},
    10: 4.0 / 13.0,
}

# Conditional probabilities for the dealer's hole card when no BJ (peek model).
# When upcard is Ace: hole card is not ten-valued → exclude rank 10, renormalize.
# When upcard is 10: hole card is not Ace → exclude rank 11, renormalize.
_RANK_PROB_NO_TEN: dict[int, float] = {
    r: _RANK_PROB[r] / (1.0 - _RANK_PROB[10])
    for r in _RANKS if r != 10
}  # for Ace-upcard first draw (no ten hole-card)

_RANK_PROB_NO_ACE: dict[int, float] = {
    r: _RANK_PROB[r] / (1.0 - _RANK_PROB[11])
    for r in _RANKS if r != 11
}  # for ten-upcard first draw (no Ace hole-card)


def _card_rank_int(card: dict) -> int:
    """Convert a card dict to its numeric rank (2-10, 11 for Ace)."""
    return card_rank(card)  # type: ignore[arg-type]


# ─── Dealer state helpers ─────────────────────────────────────────────────────

def _dealer_should_hit(total: int, soft: bool) -> bool:
    """Return True if the dealer must draw under H17 rules."""
    if total < 17:
        return True
    if total == 17 and soft:
        return True  # soft 17: hit
    return False  # hard 17+, soft 18+: stand


def _dealer_next_state(total: int, soft: bool, drawn_rank: int) -> tuple[int, bool]:
    """Return (new_total, new_soft) after the dealer draws drawn_rank.

    An Ace is counted as 11 (soft) when it doesn't bust; otherwise as 1.
    If the existing hand is soft and the new total busts, the soft ace is demoted.
    """
    if drawn_rank == 11:  # Ace
        if total + 11 <= 21:
            return total + 11, True
        return total + 1, soft  # ace counts as 1; existing softness unchanged
    new_total = total + drawn_rank
    new_soft = soft
    if new_total > 21 and new_soft:
        # Demote the existing soft ace
        new_total -= 10
        new_soft = False
    return new_total, new_soft


# ─── Dealer outcome distribution (memoized per state) ────────────────────────
# The cache key is an IMMUTABLE tuple (total, soft) — never per-call mutable state
# (AC-B-EV9).  The first-draw conditioning for the peek model is handled by
# passing a modified probability dict to the recursive helper rather than by a
# separate cache dimension, so all subsequent draws use the same cached states.

_dealer_cache: dict[tuple[int, bool], dict[Union[int, str], float]] = {}


def _dealer_distribution_from_state(
    total: int, soft: bool
) -> dict[Union[int, str], float]:
    """Recursively compute the dealer's final-state probability distribution.

    Returns a dict over {17, 18, 19, 20, 21, "bust"} where values sum to 1.0.
    Memoized on (total, soft) — subsequent draws always use normal probabilities.
    """
    key = (total, soft)
    if key in _dealer_cache:
        return _dealer_cache[key]

    if not _dealer_should_hit(total, soft):
        # Standing state — resolve to outcome
        result: dict[Union[int, str], float]
        if total > 21:
            result = {17: 0.0, 18: 0.0, 19: 0.0, 20: 0.0, 21: 0.0, "bust": 1.0}
        else:
            result = {17: 0.0, 18: 0.0, 19: 0.0, 20: 0.0, 21: 0.0, "bust": 0.0}
            result[total] = 1.0
        _dealer_cache[key] = result
        return result

    # Dealer must hit — aggregate over all drawn ranks using normal probabilities
    agg: dict[Union[int, str], float] = {
        17: 0.0, 18: 0.0, 19: 0.0, 20: 0.0, 21: 0.0, "bust": 0.0
    }
    for rank in _RANKS:
        prob = _RANK_PROB[rank]
        new_total, new_soft = _dealer_next_state(total, soft, rank)
        sub = _dealer_distribution_from_state(new_total, new_soft)
        for outcome, p in sub.items():
            agg[outcome] = agg[outcome] + prob * p

    _dealer_cache[key] = agg
    return agg


def _dealer_distribution_from_upcard_peek(
    upcard_rank: int,
) -> dict[Union[int, str], float]:
    """Compute dealer distribution from upcard under the peek (no-BJ) model.

    Conditions the first draw on the dealer NOT having a natural blackjack:
    - Upcard Ace  → first draw cannot be ten-valued (prob renormalized over non-tens).
    - Upcard ten  → first draw cannot be Ace (prob renormalized over non-aces).
    - Other upcards → no conditioning needed (no BJ possible); uses normal probs.
    """
    if upcard_rank == 11:  # Ace upcard — no ten hole-card
        initial_total, initial_soft = 11, True
        first_draw_probs = _RANK_PROB_NO_TEN
    elif upcard_rank == 10:  # Ten upcard — no Ace hole-card
        initial_total, initial_soft = 10, False
        first_draw_probs = _RANK_PROB_NO_ACE
    else:
        # No BJ possible; standard recursion applies immediately
        return _dealer_distribution_from_state(upcard_rank, False)

    # One step of the dealer draw using the conditioned first-draw probabilities,
    # then continue with the memoized normal-probability recursion.
    agg: dict[Union[int, str], float] = {
        17: 0.0, 18: 0.0, 19: 0.0, 20: 0.0, 21: 0.0, "bust": 0.0
    }
    for rank, prob in first_draw_probs.items():
        new_total, new_soft = _dealer_next_state(initial_total, initial_soft, rank)
        sub = _dealer_distribution_from_state(new_total, new_soft)
        for outcome, p in sub.items():
            agg[outcome] = agg[outcome] + prob * p
    return agg


def dealer_outcome_distribution(upcard: dict) -> dict[Union[int, str], float]:
    """Return the dealer's final-state distribution given an upcard.

    Keys: {17, 18, 19, 20, 21, "bust"}.  Values sum to 1.0 within 1e-9.
    Dealer follows H17; the peek (no-BJ) model is applied for Ace and ten upcards.

    upcard is a card dict {suit, value} as per CLAUDE.md conventions.
    """
    rank = _card_rank_int(upcard)
    return _dealer_distribution_from_upcard_peek(rank)


# ─── ev_stand ────────────────────────────────────────────────────────────────

def ev_stand(player_total: int, player_is_soft: bool, upcard: dict) -> float:  # noqa: ARG001
    """Return the EV of standing on player_total against dealer's upcard.

    player_is_soft is accepted for interface completeness; it does not affect
    the stand outcome (the player's total is fixed once standing).

    Under the peek model: dealer is known not to have a natural BJ already.
    EV: dealer bust → +1; player_total > dealer_total → +1;
        tie → 0; player_total < dealer_total → -1.
    """
    total = player_total if player_total <= 21 else 22  # bust is always -1

    dist = dealer_outcome_distribution(upcard)
    ev = 0.0
    for outcome, prob in dist.items():
        if outcome == "bust":
            ev += prob * 1.0
        else:
            dealer_total = int(outcome)
            if total > dealer_total:
                ev += prob * 1.0
            elif total == dealer_total:
                ev += prob * 0.0
            else:
                ev += prob * (-1.0)
    return ev


# ─── Internal hit recursion helpers ──────────────────────────────────────────

# Memoize _ev_hit_state by (total, soft, upcard_rank) for speed and determinism.
_ev_hit_cache: dict[tuple[int, bool, int], float] = {}


def _upcard_rank_from_int(rank: int) -> dict:
    """Build a minimal upcard card dict from a numeric rank (internal use only)."""
    value = "A" if rank == 11 else str(rank)
    return {"suit": "hearts", "value": value}


def _ev_hit_state(total: int, soft: bool, upcard_rank: int) -> float:
    """EV of hitting from state (total, soft) against upcard_rank.

    Recursion is bounded because total ≤ 21 (drawing always increases total until bust).
    After each draw: if bust → -1; else max(ev_stand, ev_hit_again).
    """
    key = (total, soft, upcard_rank)
    if key in _ev_hit_cache:
        return _ev_hit_cache[key]

    upcard_dict = _upcard_rank_from_int(upcard_rank)
    ev = 0.0
    for rank in _RANKS:
        prob = _RANK_PROB[rank]
        new_total, new_soft = _dealer_next_state(total, soft, rank)

        if new_total > 21:
            ev += prob * (-1.0)
        elif new_total >= 21:
            # At 21: cannot improve further; stand is optimal
            ev += prob * ev_stand(new_total, new_soft, upcard_dict)
        else:
            ev_s = ev_stand(new_total, new_soft, upcard_dict)
            ev_h = _ev_hit_state(new_total, new_soft, upcard_rank)
            ev += prob * max(ev_s, ev_h)

    _ev_hit_cache[key] = ev
    return ev


def ev_hit(hand_cards: list[dict], upcard: dict) -> float:
    """Return the EV of hitting hand_cards against upcard.

    Expectation over next drawn rank: bust → -1;
    else max(ev_stand(new), ev_hit(new)).  Recursion bounded by total ≤ 21.
    """
    total = hand_value(hand_cards)  # type: ignore[arg-type]
    soft = is_soft(hand_cards)  # type: ignore[arg-type]
    upcard_rank = _card_rank_int(upcard)
    return _ev_hit_state(total, soft, upcard_rank)


# ─── ev_double ────────────────────────────────────────────────────────────────

def ev_double(hand_cards: list[dict], upcard: dict) -> float:
    """Return the EV of doubling down on hand_cards against upcard.

    One card is drawn; if the resulting total busts → -2;
    otherwise 2 × ev_stand(new_total, new_soft, upcard).

    Ace drawn to the hand is counted with proper soft-ace demotion:
    if total + 11 ≤ 21 → (total+11, soft=True); else ace counts as 1
    (→ total+1, soft unchanged).  This matches the formula documented in
    AC-B-EV7: bust → -2, non-bust → 2×ev_stand.
    """
    total = hand_value(hand_cards)  # type: ignore[arg-type]
    soft = is_soft(hand_cards)  # type: ignore[arg-type]

    ev = 0.0
    for rank in _RANKS:
        prob = _RANK_PROB[rank]
        new_total, new_soft = _dealer_next_state(total, soft, rank)

        if new_total > 21:
            ev += prob * (-2.0)
        else:
            ev += prob * 2.0 * ev_stand(new_total, new_soft, upcard)

    return ev


# ─── action_evs / best_action_ev ─────────────────────────────────────────────

def action_evs(
    hand_cards: list[dict],
    upcard: dict,
    can_double: bool,
    can_split: bool,  # accepted but ignored — split EV omitted in v1
) -> dict[str, float]:
    """Return a dict of EV estimates for all legal non-split actions.

    Keys: always "hit" and "stand"; "double" iff len(hand_cards) == 2 and
    can_double is True.  "split" key is never returned (v1 omits split EV).

    can_split is accepted for API compatibility but has no effect on the
    returned dict (see specs/blackjack-study.md §Decisions #2).
    """
    total = hand_value(hand_cards)  # type: ignore[arg-type]
    soft = is_soft(hand_cards)  # type: ignore[arg-type]
    evs: dict[str, float] = {
        "stand": ev_stand(total, soft, upcard),
        "hit": ev_hit(hand_cards, upcard),
    }
    if len(hand_cards) == 2 and can_double:
        evs["double"] = ev_double(hand_cards, upcard)
    return evs


# Action tiebreak order for deterministic argmax: prefer double > hit > stand
# (more aggressive action wins ties to match basic strategy on marginal cells).
_ACTION_PRIORITY: dict[str, int] = {"double": 2, "hit": 1, "stand": 0}


def best_action_ev(
    hand_cards: list[dict],
    upcard: dict,
    can_double: bool,
    can_split: bool,
) -> tuple[str, float]:
    """Return (best_action, best_ev) where best_action is the argmax of action_evs.

    Tiebreaking is deterministic: prefer double > hit > stand when EVs are equal.
    """
    evs = action_evs(hand_cards, upcard, can_double=can_double, can_split=can_split)
    best_act = max(evs, key=lambda a: (evs[a], _ACTION_PRIORITY.get(a, 0)))
    return best_act, evs[best_act]
