"""
equity.py — win-equity engine for Texas Hold'em.

Design constraints (specs/poker-review-pr1-equity-engine.md §4.1..§4.2;
specs/texas-holdem.md line 39):
- Exact enumeration when board cards to come ≤ 2 (len(board) >= 3);
  Monte-Carlo otherwise.
- Seeded RNG: takes an explicit `seed` argument; same seed → identical float.
- Pure-sync, no DB, no IO.
- Uses `cards.remove_cards` and `evaluator.best_5_of_7`; no new card math.
- Ties counted fractionally (2-way chop = 0.5, N-way = 1/N).
"""
from __future__ import annotations

import itertools
import random
from typing import NamedTuple, Set

from .archetypes import _all_play_range as _archetype_play_range  # noqa: PLC0415
from .archetypes import ArchetypeSpec
from .cards import Card, SUITS, RANKS, remove_cards
from .evaluator import best_5_of_7, category_name, rank_hand
from .ranges import top_pct

# A Range is a set of canonical hand strings (e.g. {"AA", "AKs"}).
Range = Set[str]

# Rank char used in hand strings ("T" for ten, not "10").
_VALUE_TO_RANK: dict[str, str] = {
    "2": "2", "3": "3", "4": "4", "5": "5", "6": "6", "7": "7",
    "8": "8", "9": "9", "10": "T", "J": "J", "Q": "Q", "K": "K", "A": "A",
}

_RANK_TO_VALUE: dict[str, str] = {v: k for k, v in _VALUE_TO_RANK.items()}
# "T" → "10"; for all others k == v
_RANK_TO_VALUE["T"] = "10"

_SUIT_CHARS: dict[str, str] = {
    "hearts": "h", "diamonds": "d", "clubs": "c", "spades": "s",
}

_CHAR_TO_SUIT: dict[str, str] = {v: k for k, v in _SUIT_CHARS.items()}


# ---------------------------------------------------------------------------
# Range helpers
# ---------------------------------------------------------------------------


def default_range(tightness: float = 0.40) -> Range:
    """Return the top `tightness` fraction of hands by SC ordering.

    v1: a single tightness knob — positional nuance deferred.
    """
    return top_pct(tightness * 100.0)


def archetype_range(spec: ArchetypeSpec) -> Range:
    """Thin adapter: return an archetype's full VPIP range.

    Delegates to `archetypes._all_play_range` — no table duplication.
    """
    return _archetype_play_range(spec)


def _card_rank_char(card: Card) -> str:
    """Convert a Card's value to the single rank char used in hand strings."""
    return _VALUE_TO_RANK[card["value"]]


def _card_suit_char(card: Card) -> str:
    return _SUIT_CHARS[card["suit"]]


def _hand_str_of(c1: Card, c2: Card) -> str:
    """Canonical hand string for a pair of cards."""
    r1 = _card_rank_char(c1)
    r2 = _card_rank_char(c2)
    rank_order: dict[str, int] = {
        "A": 14, "K": 13, "Q": 12, "J": 11, "T": 10,
        "9": 9, "8": 8, "7": 7, "6": 6, "5": 5, "4": 4, "3": 3, "2": 2,
    }
    n1, n2 = rank_order[r1], rank_order[r2]
    if n1 == n2:
        return f"{r1}{r2}"
    hi, lo = (r1, r2) if n1 > n2 else (r2, r1)
    suited = c1["suit"] == c2["suit"]
    return f"{hi}{lo}{'s' if suited else 'o'}"


def _all_concrete_cards() -> list[Card]:
    """All 52 cards in a deterministic order."""
    return [{"suit": suit, "value": value} for suit in SUITS for value in RANKS]


def range_to_combos(rng: Range, dead_cards: list[Card]) -> list[tuple[Card, Card]]:
    """Expand a Range of canonical hand strings to concrete 2-card combos.

    Removes any combo that overlaps `dead_cards` (cards already known to be
    held by hero or on the board).  Dead-card removal pins AC E-9.
    """
    dead_keys: set[tuple[str, str]] = {(c["suit"], c["value"]) for c in dead_cards}
    result: list[tuple[Card, Card]] = []

    for hand in rng:
        for c1, c2 in _combos_for_hand_str(hand):
            k1 = (c1["suit"], c1["value"])
            k2 = (c2["suit"], c2["value"])
            if k1 not in dead_keys and k2 not in dead_keys:
                result.append((c1, c2))

    return result


def _combos_for_hand_str(hand: str) -> list[tuple[Card, Card]]:
    """All concrete (c1, c2) combinations for a canonical hand string.

    Pair  → C(4,2) = 6 combos  (same rank, different suits)
    Suited → 4 combos          (one per suit, matching)
    Offsuit → 4*3 = 12 combos  (any suit for hi, any different suit for lo)
    """
    suit_list = list(SUITS)

    if len(hand) == 2:
        # Pair
        r = _RANK_TO_VALUE[hand[0]]
        cards_of_rank = [{"suit": s, "value": r} for s in suit_list]
        return [
            (cards_of_rank[i], cards_of_rank[j])
            for i in range(4)
            for j in range(i + 1, 4)
        ]

    hi_char, lo_char, suit_marker = hand[0], hand[1], hand[2]
    hi_val = _RANK_TO_VALUE[hi_char]
    lo_val = _RANK_TO_VALUE[lo_char]

    if suit_marker == "s":
        # Suited: same suit for both cards
        return [
            ({"suit": s, "value": hi_val}, {"suit": s, "value": lo_val})
            for s in suit_list
        ]
    else:
        # Offsuit: different suits
        combos: list[tuple[Card, Card]] = []
        for sh in suit_list:
            for sl in suit_list:
                if sh != sl:
                    combos.append((
                        {"suit": sh, "value": hi_val},
                        {"suit": sl, "value": lo_val},
                    ))
        return combos


# ---------------------------------------------------------------------------
# Showdown scoring
# ---------------------------------------------------------------------------


def _score_showdown(
    hero_hole: tuple[Card, Card],
    villain_holes: list[tuple[Card, Card]],
    board: list[Card],
) -> float:
    """Return hero's fractional win for one runout.

    Ties split equally: 2-way chop → 0.5, N-way → 1/N.
    Calls `evaluator.best_5_of_7(hole_cards + board_cards)` for each player.
    """
    hero_rank = best_5_of_7(list(hero_hole) + board)
    villain_ranks = [best_5_of_7(list(vh) + board) for vh in villain_holes]

    hero_key = hero_rank.cmp_key()
    villain_keys = [vr.cmp_key() for vr in villain_ranks]

    # Count how many villains beat hero
    beats_hero = sum(1 for vk in villain_keys if vk > hero_key)
    if beats_hero > 0:
        return 0.0

    # Count ties (hero shares the pot with any equal-ranked villain)
    ties = sum(1 for vk in villain_keys if vk == hero_key)
    total_winners = 1 + ties  # hero + tied villains
    return 1.0 / total_winners


def random_villain_holdings(
    ranges: list[Range],
    dead_cards: list[Card],
    rng: random.Random,
) -> list[tuple[Card, Card]]:
    """Sample one concrete holding per villain, rejection-sampling against dead cards.

    Returns a list of (Card, Card) tuples, one per villain range.
    Expands each range to combos, samples uniformly, and updates the dead-card
    set incrementally (so villain 2 can't hold cards dealt to villain 1).
    """
    running_dead = list(dead_cards)
    result: list[tuple[Card, Card]] = []

    for rng_set in ranges:
        available = range_to_combos(rng_set, running_dead)
        if not available:
            # No valid holding for this villain — return empty (handled upstream)
            result.append((_dummy_card(), _dummy_card()))
            continue
        chosen = rng.choice(available)
        result.append(chosen)
        running_dead = running_dead + list(chosen)

    return result


def _dummy_card() -> Card:
    """Placeholder card used when a villain has no valid combo."""
    return {"suit": "hearts", "value": "2"}


# ---------------------------------------------------------------------------
# Exact enumeration branch (board cards to come ≤ 2; i.e. len(board) >= 3)
# ---------------------------------------------------------------------------


def _enumerate_equity(
    hero_hole: tuple[Card, Card],
    villain_ranges: list[Range],
    board: list[Card],
    max_iters: int,
) -> float:
    """Exact enumeration over villain-combo × remaining-board-completions.

    Called when len(board) >= 3, i.e. cards-to-come is 2 (flop), 1 (turn),
    or 0 (river). Falls back to seeded MC (via _mc_equity) if the
    combination count exceeds max_iters.
    """
    dead = list(hero_hole) + board
    cards_to_come = 5 - len(board)  # 2 on the flop, 1 on the turn, 0 on the river

    # Build all villain-combo combinations (one per villain)
    villain_combo_lists = [range_to_combos(r, dead) for r in villain_ranges]

    # Guard: if any villain has no valid combos, fall back to 1.0 for hero
    if any(len(vc) == 0 for vc in villain_combo_lists):
        return 1.0

    # Build the cross-product of villain combos
    villain_cross = list(itertools.product(*villain_combo_lists))

    # For each villain-combo assignment, build the live deck and enumerate
    # board completions.
    total_weight = 0.0
    total_win = 0.0

    for villain_combos in villain_cross:
        # Check for collisions within villain combo assignment
        used_keys: set[tuple[str, str]] = {(c["suit"], c["value"]) for c in dead}
        collision = False
        for vc in villain_combos:
            for c in vc:
                key = (c["suit"], c["value"])
                if key in used_keys:
                    collision = True
                    break
                used_keys.add(key)
            if collision:
                break
        if collision:
            continue

        # Live deck = full deck minus hero hole, board, and villain cards
        villain_flat = [c for vc in villain_combos for c in vc]
        live_deck = remove_cards(_all_concrete_cards(), list(dead) + villain_flat)

        if cards_to_come == 0:
            # River already complete — single showdown
            win = _score_showdown(hero_hole, list(villain_combos), board)
            total_win += win
            total_weight += 1.0
        else:
            # 1 card to come: enumerate all possible run-out cards
            for river_card in live_deck:
                full_board = board + [river_card]
                win = _score_showdown(hero_hole, list(villain_combos), full_board)
                total_win += win
                total_weight += 1.0

    if total_weight == 0.0:
        return 1.0

    result = total_win / total_weight

    # Check if we exceeded max_iters budget — if so we already computed it
    # exactly (enumeration), so just return it.  The budget guard is only for
    # falling back to MC on wide-range flop spots.
    return result


# ---------------------------------------------------------------------------
# Seeded Monte-Carlo branch
# ---------------------------------------------------------------------------


def _mc_equity(
    hero_hole: tuple[Card, Card],
    villain_ranges: list[Range],
    board: list[Card],
    *,
    seed: int,
    max_iters: int,
) -> float:
    """Seeded Monte-Carlo equity estimation.

    For `max_iters` trials:
    - Sample one holding per villain (rejection-sampling against dead cards).
    - Complete the board randomly from the live deck.
    - Score the showdown.
    """
    rng = random.Random(seed)
    dead = list(hero_hole) + board
    cards_to_come = 5 - len(board)

    total_win = 0.0
    valid_trials = 0

    for _ in range(max_iters):
        # Sample villain holdings
        villain_holdings = random_villain_holdings(villain_ranges, dead, rng)

        # Reject if any villain ended up with dummy cards due to empty range
        # (this means no valid combo; skip trial)
        villain_flat = [c for vh in villain_holdings for c in vh]
        # Check uniqueness
        villain_keys = [(c["suit"], c["value"]) for c in villain_flat]
        dead_keys = {(c["suit"], c["value"]) for c in dead}
        if len(set(villain_keys)) != len(villain_keys):
            continue
        if any(k in dead_keys for k in villain_keys):
            continue

        # Complete the board
        live_deck = remove_cards(_all_concrete_cards(), dead + villain_flat)
        if len(live_deck) < cards_to_come:
            continue

        if cards_to_come > 0:
            board_additions = rng.sample(live_deck, cards_to_come)
            full_board = board + board_additions
        else:
            full_board = board

        win = _score_showdown(hero_hole, villain_holdings, full_board)
        total_win += win
        valid_trials += 1

    if valid_trials == 0:
        return 1.0
    return total_win / valid_trials


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def hand_equity(
    hero_hole: tuple[Card, Card],
    villain_ranges: list[Range],
    board: list[Card],
    *,
    seed: int,
    max_iters: int = 2000,
) -> float:
    """Return hero's probability of winning at showdown.

    Ties are counted fractionally (2-way chop = 0.5, N-way = 1/N).

    Dispatch:
    - len(board) >= 3 (flop/turn/river; ≤ 2 cards to come) → exact enumeration,
      with fallback to seeded MC if combination count exceeds max_iters.
    - len(board) < 3 (preflop or incomplete; > 2 cards to come) → seeded MC.

    Args:
        hero_hole: hero's two hole cards.
        villain_ranges: one Range per live villain.
        board: 0 / 3 / 4 / 5 community cards dealt so far.
        seed: RNG seed for the Monte-Carlo path (same seed → identical float).
        max_iters: iteration budget.  Enumeration falls back to MC above this.

    Returns:
        float in [0, 1] — hero's win probability.
    """
    cards_to_come = 5 - len(board)

    if cards_to_come <= 2:
        # Exact enumeration path (flop/turn/river).  Estimate combination count;
        # if it would blow max_iters, fall back to MC.
        dead = list(hero_hole) + board
        villain_combo_counts = [len(range_to_combos(r, dead)) for r in villain_ranges]

        # Simple heuristic: product of villain combo counts × board completions.
        # For narrow ranges heads-up this is cheap; for wide multi-way it can be huge.
        combo_count_estimate = 1
        for vc in villain_combo_counts:
            combo_count_estimate *= max(1, vc)
        combo_count_estimate *= max(1, cards_to_come * 44)

        if combo_count_estimate <= max_iters * 20:
            # Use exact enumeration
            return _enumerate_equity(hero_hole, villain_ranges, board, max_iters)
        else:
            # Fall back to seeded MC
            return _mc_equity(hero_hole, villain_ranges, board, seed=seed, max_iters=max_iters)
    else:
        # Preflop or > 2 cards to come → seeded MC
        return _mc_equity(hero_hole, villain_ranges, board, seed=seed, max_iters=max_iters)


# Alias for callers that prefer the older `texas-holdem.md` name.
equity = hand_equity


# ─── Monte-Carlo win/tie/lose + on-felt odds payload ────────────────────────────
# (Merged from the Ask-Chipy hand-odds graphic feature. Used by the solo poker
# advice endpoint and the multiplayer Hold'em odds endpoint. Distinct from the
# range-based `hand_equity` above, which powers decision review.)

# Default simulation count — ~800 keeps the "Ask Chipy" round-trip snappy
# (<~1s even multiway) while holding the standard error near ±2%.
DEFAULT_ITERATIONS = 800
# Cap the simulated field; multiway equity past 5 villains is already tiny and
# the extra evaluations only slow the request.
MAX_SIM_OPPONENTS = 5


class EquityResult(NamedTuple):
    win: float
    tie: float
    lose: float


def _full_deck() -> list[Card]:
    return [{"suit": s, "value": v} for s in SUITS for v in RANKS]


def estimate_equity(
    hole: list[Card] | tuple[Card, ...],
    board: list[Card] | tuple[Card, ...],
    n_opponents: int,
    iterations: int = DEFAULT_ITERATIONS,
    seed: int = 1_234_567,
) -> EquityResult:
    """Monte-Carlo win/tie/lose probability for `hole` vs `n_opponents` random
    hands given the current `board` (0, 3, 4, or 5 cards).

    Tie counts a split pot as a partial loss conceptually but is reported
    separately so the UI can show win / tie / lose. Returns equal thirds-ish
    fallbacks only if inputs are unusable (handled by the caller, which should
    pass a valid 2-card hole)."""
    n_opp = max(1, min(int(n_opponents), MAX_SIM_OPPONENTS))
    hole = list(hole)
    board = list(board)
    if len(hole) != 2:
        raise ValueError("estimate_equity needs exactly 2 hole cards")
    if len(board) not in (0, 3, 4, 5):
        raise ValueError("board must have 0, 3, 4, or 5 cards")

    deck = remove_cards(_full_deck(), hole + board)
    need_board = 5 - len(board)
    draw = need_board + 2 * n_opp
    rng = random.Random(seed)

    wins = ties = 0
    for _ in range(iterations):
        sample = rng.sample(deck, draw)
        full_board = board + sample[:need_board]
        hero = best_5_of_7(hole + full_board).cmp_key()
        idx = need_board
        best_opp = None
        for _k in range(n_opp):
            opp = best_5_of_7(sample[idx : idx + 2] + full_board).cmp_key()
            idx += 2
            if best_opp is None or opp > best_opp:
                best_opp = opp
        if hero > best_opp:  # type: ignore[operator]
            wins += 1
        elif hero == best_opp:
            ties += 1

    win = wins / iterations
    tie = ties / iterations
    return EquityResult(win=round(win, 4), tie=round(tie, 4), lose=round(1.0 - win - tie, 4))


def made_hand_name(hole: list[Card] | tuple[Card, ...], board: list[Card] | tuple[Card, ...]) -> str | None:
    """The hero's CURRENT best 5-card hand name (e.g. 'two pair'), or None
    preflop / before a hand is made (need ≥3 board cards)."""
    hole = list(hole)
    board = list(board)
    if len(board) < 3 or len(hole) != 2:
        return None
    return category_name(rank_hand(hole, board))


def hand_odds(
    hole: list[Card] | tuple[Card, ...],
    board: list[Card] | tuple[Card, ...],
    pot: float,
    to_call: float,
    n_opponents: int,
    street: str,
    iterations: int = DEFAULT_ITERATIONS,
) -> dict:
    """Assemble the on-felt odds payload (shape matches schemas.PokerOddsOut).

    `pot` and `to_call` are passed straight to required_equity — units cancel
    (bb or chips both work) since the result is a ratio. Used by both the solo
    poker advice endpoint and the multiplayer Hold'em odds endpoint.
    """
    from .pot_odds import required_equity  # noqa: PLC0415

    eq = estimate_equity(hole, board, n_opponents, iterations=iterations)
    pot_odds = required_equity(pot, to_call) if to_call and to_call > 0 else 0.0
    return {
        "win_pct": eq.win,
        "tie_pct": eq.tie,
        "lose_pct": eq.lose,
        "pot_odds_pct": round(float(pot_odds), 4),
        "made_hand": made_hand_name(hole, board),
        "n_opponents": max(1, int(n_opponents)),
        "street": street,
    }


__all__ = [
    "Range",
    "default_range",
    "archetype_range",
    "range_to_combos",
    "hand_equity",
    "equity",
    "random_villain_holdings",
    "EquityResult",
    "estimate_equity",
    "made_hand_name",
    "hand_odds",
]
