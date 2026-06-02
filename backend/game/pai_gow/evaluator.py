"""backend.game.pai_gow.evaluator — hand strength + comparison for Pai Gow.

Pure functions, no DB, no random state. Card representation matches CLAUDE.md
rule 2 — dicts of `{"suit", "value"}` plus the joker sentinel.

Public surface:
- `score_hand(cards)` → totally-ordered tuple. Higher tuple wins.
  Accepts 2-card OR 5-card hands; the unified comparison protocol (spec §7.3)
  means tuples are comparable across both sizes.
- `compare_hands(a, b)` → -1 / 0 / 1.
- `best_five_card_hand(seven)` → `(best_5, score)` over the 21 C(7,5) combos.
- `is_seven_card_straight_flush(seven)` → bool (Fortune GRAND tier check).

Joker semi-wild semantics (spec §7.1):
- Default role: Ace.
- Becomes a missing rank IFF that completes a straight, flush, or SF.
- Never duplicates a non-Ace rank to make pairs/trips/quads.

Straight rank encoding (spec §7.2 — A-K-Q-J-10 is highest, A-2-3-4-5 second):
  10 = A-K-Q-J-10 (broadway)
   9 = A-2-3-4-5 (wheel — second-highest in PG)
   8 = K-Q-J-10-9
   7 = Q-J-10-9-8
   ...
   1 = 6-5-4-3-2 (lowest)

Category encoding (low to high):
  0 high_card, 1 one_pair, 2 two_pair, 3 three_of_a_kind,
  4 straight, 5 flush, 6 full_house, 7 four_of_a_kind, 8 straight_flush.
"""
from __future__ import annotations

from itertools import combinations
from typing import Optional

from backend.game.pai_gow.cards import Card, RANK_ORDER, card_rank, is_joker

# Category constants for readability + test imports.
HIGH_CARD = 0
ONE_PAIR = 1
TWO_PAIR = 2
THREE_OF_A_KIND = 3
STRAIGHT = 4
FLUSH = 5
FULL_HOUSE = 6
FOUR_OF_A_KIND = 7
STRAIGHT_FLUSH = 8

_ALL_SUITS: tuple[str, ...] = ("hearts", "diamonds", "clubs", "spades")
# Reverse map for joker substitution (rank int → value string).
_RANK_VALUE_MAP: dict[int, str] = {v: k for k, v in RANK_ORDER.items()}


# ─── Public API ──────────────────────────────────────────────────────────────


def score_hand(cards: list[Card]) -> tuple:
    """Score a 2-card or 5-card hand into a totally-ordered tuple.

    Returns `(category, *rank_tuple)`. Higher tuples win.
    Joker semi-wild is resolved by trying valid substitutions and returning
    the max. Raises `ValueError` for any other card count.
    """
    if len(cards) == 2:
        return _score_two_card(cards)
    if len(cards) == 5:
        return _score_five_card(cards)
    raise ValueError(f"score_hand expects 2 or 5 cards, got {len(cards)}")


def compare_hands(a: list[Card], b: list[Card]) -> int:
    """Compare two hands. Returns 1 if a > b, -1 if a < b, 0 if tied."""
    sa, sb = score_hand(a), score_hand(b)
    if sa > sb:
        return 1
    if sa < sb:
        return -1
    return 0


def best_five_card_hand(seven_cards: list[Card]) -> tuple[list[Card], tuple]:
    """Return `(best_5, score)` — the highest-scoring 5-card hand among the
    21 C(7,5) combinations. Used by Fortune qualifying-hand detection (§11.1).
    """
    if len(seven_cards) != 7:
        raise ValueError(f"best_five_card_hand expects 7 cards, got {len(seven_cards)}")
    best_score: Optional[tuple] = None
    best_combo: Optional[list[Card]] = None
    for indexes in combinations(range(7), 5):
        sub = [seven_cards[i] for i in indexes]
        s = score_hand(sub)
        if best_score is None or s > best_score:
            best_score = s
            best_combo = sub
    assert best_combo is not None and best_score is not None
    return best_combo, best_score


def is_seven_card_straight_flush(seven_cards: list[Card]) -> bool:
    """True iff all 7 cards form a 7-card straight flush (Fortune GRAND tier).

    Handles joker as semi-wild filler. Recognizes A-2-3-4-5-6-7 with A as 1
    (the only sub-low extension that creates a valid 7-card SF).
    """
    if len(seven_cards) != 7:
        return False
    non_joker = [c for c in seven_cards if not is_joker(c)]
    joker_count = len(seven_cards) - len(non_joker)

    # All non-joker cards must share a suit (joker takes that suit too).
    suits = {c["suit"] for c in non_joker}
    if len(suits) > 1:
        return False

    ranks = {card_rank(c) for c in non_joker}
    if len(non_joker) - len(ranks) > 0:
        # Duplicate ranks → can't be 7 distinct cards.
        return False
    if len(ranks) + joker_count < 7:
        return False

    # Standard high windows: low=2 (ends at 8) through low=8 (ends at 14 = A-high).
    for low in range(2, 9):
        target = set(range(low, low + 7))
        if ranks.issubset(target):
            missing = target - ranks
            if len(missing) <= joker_count:
                return True

    # A-low window: A treated as 1, sequence {1,2,3,4,5,6,7}.
    if 14 in ranks:
        alt = (ranks - {14}) | {1}
        target = set(range(1, 8))
        if alt.issubset(target):
            missing = target - alt
            if len(missing) <= joker_count:
                return True

    return False


# ─── Internal: 2-card scoring ────────────────────────────────────────────────


def _score_two_card(cards: list[Card]) -> tuple:
    """2-card hand: pair > high card. Joker is always Ace in 2-card (no
    straight/flush is possible with 2 cards)."""
    ranks = sorted(
        [14 if is_joker(c) else card_rank(c) for c in cards],
        reverse=True,
    )
    if ranks[0] == ranks[1]:
        return (ONE_PAIR, ranks[0])
    return (HIGH_CARD, ranks[0], ranks[1])


# ─── Internal: 5-card scoring with joker semi-wild ──────────────────────────


def _score_five_card(cards: list[Card]) -> tuple:
    """5-card hand: enumerate valid joker substitutions, return the max score."""
    joker_present = any(is_joker(c) for c in cards)
    if not joker_present:
        return _score_five_no_joker(cards)

    non_joker = [c for c in cards if not is_joker(c)]
    existing_cards = {(c["suit"], c["value"]) for c in non_joker}
    existing_ranks = {card_rank(c) for c in non_joker}

    candidates: list[tuple] = []

    # Joker as Ace (always-allowed). Skip suits whose A is already in hand
    # (joker can't physically be a duplicate card; that would fake a flush).
    for suit in _ALL_SUITS:
        if (suit, "A") in existing_cards:
            continue
        sub = non_joker + [{"suit": suit, "value": "A"}]
        candidates.append(_score_five_no_joker(sub))

    # Joker as missing rank R (only accepted if it completes straight/flush/SF).
    for r in range(2, 14):  # 2..K; Ace already covered above
        if r in existing_ranks:
            continue  # semi-wild rule: never duplicates a non-Ace rank
        value = _RANK_VALUE_MAP[r]
        for suit in _ALL_SUITS:
            if (suit, value) in existing_cards:
                continue
            sub = non_joker + [{"suit": suit, "value": value}]
            score = _score_five_no_joker(sub)
            if score[0] in (STRAIGHT, FLUSH, STRAIGHT_FLUSH):
                candidates.append(score)

    if not candidates:
        # Physically-impossible fixture (e.g., all 4 aces + joker). Fall back to
        # the joker-as-Ace path with a duplicate-allowed substitution so the
        # 5-of-a-kind branch in `_score_five_no_joker` activates and we return
        # `(FOUR_OF_A_KIND, ...)` rather than crashing.
        sub = non_joker + [{"suit": "hearts", "value": "A"}]
        candidates.append(_score_five_no_joker(sub))

    return max(candidates)


def _score_five_no_joker(cards: list[Card]) -> tuple:
    """Score a 5-card hand with no joker present.

    Tolerates duplicate (suit, value) inputs (which arise only from the
    fallback path in `_score_five_card`); the 5-of-a-kind branch handles them.
    """
    ranks = sorted([card_rank(c) for c in cards], reverse=True)
    suits = [c["suit"] for c in cards]

    is_flush = len(set(suits)) == 1
    straight_rank = _detect_straight(ranks)

    rank_counts: dict[int, int] = {}
    for r in ranks:
        rank_counts[r] = rank_counts.get(r, 0) + 1
    counts_sorted = sorted(rank_counts.values(), reverse=True)

    # 5-of-a-kind: only reachable via the joker-on-4-aces fallback. Treat as
    # quads of that rank with same-rank "kicker" — v1 simplification, see
    # `_score_five_card` fallback comment.
    if counts_sorted[0] == 5:
        rank = next(iter(rank_counts.keys()))
        return (FOUR_OF_A_KIND, rank, rank)

    if is_flush and straight_rank is not None:
        return (STRAIGHT_FLUSH, straight_rank)
    if counts_sorted[0] == 4:
        quad = next(r for r, c in rank_counts.items() if c == 4)
        kicker = next(r for r, c in rank_counts.items() if c == 1)
        return (FOUR_OF_A_KIND, quad, kicker)
    if counts_sorted[0] == 3 and counts_sorted[1] == 2:
        trips = next(r for r, c in rank_counts.items() if c == 3)
        pair = next(r for r, c in rank_counts.items() if c == 2)
        return (FULL_HOUSE, trips, pair)
    if is_flush:
        return (FLUSH, *ranks)
    if straight_rank is not None:
        return (STRAIGHT, straight_rank)
    if counts_sorted[0] == 3:
        trips = next(r for r, c in rank_counts.items() if c == 3)
        kickers = sorted(
            [r for r, c in rank_counts.items() if c == 1], reverse=True
        )
        return (THREE_OF_A_KIND, trips, *kickers)
    if counts_sorted[0] == 2 and counts_sorted[1] == 2:
        pairs = sorted(
            [r for r, c in rank_counts.items() if c == 2], reverse=True
        )
        kicker = next(r for r, c in rank_counts.items() if c == 1)
        return (TWO_PAIR, pairs[0], pairs[1], kicker)
    if counts_sorted[0] == 2:
        pair = next(r for r, c in rank_counts.items() if c == 2)
        kickers = sorted(
            [r for r, c in rank_counts.items() if c == 1], reverse=True
        )
        return (ONE_PAIR, pair, *kickers)
    return (HIGH_CARD, *ranks)


def _detect_straight(ranks: list[int]) -> Optional[int]:
    """Return the straight rank (1..10) or None.

    Encoding (spec §7.2):
      10 = broadway A-K-Q-J-10
       9 = wheel A-2-3-4-5
       8 = K-Q-J-10-9
       ...
       1 = 6-5-4-3-2
    """
    unique = sorted(set(ranks))
    if len(unique) != 5:
        return None
    # Broadway A-K-Q-J-10
    if unique == [10, 11, 12, 13, 14]:
        return 10
    # Wheel A-2-3-4-5
    if unique == [2, 3, 4, 5, 14]:
        return 9
    # Standard 5 consecutive
    if unique[4] - unique[0] == 4:
        # 6-high → rank 1; K-high → rank 8.
        return unique[4] - 5
    return None
