"""backend.game.pai_gow.house_way — Foxwoods house way for Pai Gow Poker.

Pure function. Given a 7-card hand, deterministically produces the dealer's
2-card front + 5-card back split following Foxwoods house rules.

The split is **LEGAL by construction**: `score_hand(back) >= score_hand(front)`
under §7.3 unified ordering for every possible 7-card input. The high-quad
split case (`KK | KK + 3 kickers`) — which the round-4 review flagged as the
load-bearing foul-pass case — works because §7.3's kicker tiebreak lets the
length-5 back-tuple win over the length-2 front-tuple even when both are
"pair of K" by category. Verified by
`test_rule2_HIGH_QUAD_split_passes_foul_check_round4_round6_catch`.

Dispatch by highest applicable category in priority order:
  1.  Straight flush / royal flush  → keep 5-card SF in back, 2 leftover → front
  2.  Four of a kind                → split rule depends on quad rank (low/mid/high)
  3.  Full house                    → always split (pair → front, trips → back)
  4.  Three pairs                   → highest pair → front, other two → back
  5.  Flush                         → 5 highest of dominant suit → back
  6.  Straight                      → highest 5-card straight → back (incl. wheel)
  7.  Three of a kind               → keep trips in back (NEVER split — Foxwoods)
  8.  Two pair                      → split / keep based on pair ranks + Ace kicker
  9.  One pair                      → pair + 3 lowest → back; 2 highest → front
  10. No pair (high card)           → highest + 4 lowest → back; 2nd, 3rd → front

**v1 joker handling**: the joker is resolved as **Ace of an unused suit**
before dispatch. This is a simplification — in some hands the joker would
optimally complete a straight or flush. v2 may add joker-aware optimization.
The Ace substitution always produces a legal split, so the v1 simplification
is safe (suboptimal at worst).

Used by: state.py for both the dealer's hand (every round) and the player's
auto-set on timeout (§9.4 lazy fallback).
"""
from __future__ import annotations

from typing import Optional

from backend.game.pai_gow.cards import (
    Card,
    card_rank,
    card_sort_key,
    is_joker,
)


# ─── Public API ──────────────────────────────────────────────────────────────


def foxwoods(cards: list[Card]) -> tuple[list[Card], list[Card]]:
    """Apply Foxwoods house way to a 7-card hand.

    Returns `(front, back)`:
      - `front`: list of exactly 2 cards.
      - `back`:  list of exactly 5 cards.
      - Together, front + back contain exactly the 7 input cards (joker
        substituted for an Ace per the v1 simplification).

    Raises `ValueError` if `cards` is not exactly 7 cards long.
    """
    if len(cards) != 7:
        raise ValueError(f"house_way expects 7 cards, got {len(cards)}")

    # v1 joker handling: substitute Ace of an unused suit (module docstring).
    resolved = _resolve_joker_as_ace(cards)

    # Canonical ordering: rank descending, suit ascending (per cards.py).
    sorted_cards = sorted(resolved, key=card_sort_key)

    # Dispatch by highest applicable category, priority order.
    # Rule 1: Straight flush.
    sf = _find_straight_flush(sorted_cards)
    if sf is not None:
        return _split_with_back_5(sf, sorted_cards)

    groups = _rank_groups(sorted_cards)
    pair_count = _count_pairs(groups)

    # Rule 2: Four of a kind.
    if _has_four_of_a_kind(groups):
        return _split_four_of_a_kind(sorted_cards, groups)

    # Rule 3: Full house (includes two-trips edge case).
    if _has_full_house(groups):
        return _split_full_house(sorted_cards, groups)

    # Rule 4: Three pairs.
    if pair_count >= 3:
        return _split_three_pairs(sorted_cards, groups)

    # Rule 5: Flush.
    flush = _find_flush(sorted_cards)
    if flush is not None:
        return _split_with_back_5(flush, sorted_cards)

    # Rule 6: Straight (uses the §7.2 broadway > wheel > K-high … ordering).
    straight = _find_straight(sorted_cards)
    if straight is not None:
        return _split_with_back_5(straight, sorted_cards)

    # Rule 7: Three of a kind (always keep — Foxwoods).
    if _has_three_of_a_kind(groups):
        return _split_three_of_a_kind(sorted_cards, groups)

    # Rule 8: Two pair.
    if pair_count == 2:
        return _split_two_pair(sorted_cards, groups)

    # Rule 9: One pair.
    if pair_count == 1:
        return _split_one_pair(sorted_cards, groups)

    # Rule 10: No pair (high card).
    return _split_no_pair(sorted_cards)


# ─── Joker resolution (v1 simplification) ────────────────────────────────────


def _resolve_joker_as_ace(cards: list[Card]) -> list[Card]:
    """Substitute joker → Ace of an unused suit.

    The chosen suit avoids duplicating an existing Ace. If all 4 ace suits
    are present (impossible in a 53-card deck — defensive only), defaults to
    hearts. The evaluator's 5-of-a-kind fallback handles the result.
    """
    joker_idx = next((i for i, c in enumerate(cards) if is_joker(c)), -1)
    if joker_idx < 0:
        return list(cards)

    existing_ace_suits = {
        c["suit"] for c in cards if not is_joker(c) and c["value"] == "A"
    }
    chosen_suit = next(
        (s for s in ("hearts", "diamonds", "clubs", "spades") if s not in existing_ace_suits),
        "hearts",  # defensive — all 4 aces already present
    )
    out = list(cards)
    out[joker_idx] = {"suit": chosen_suit, "value": "A"}
    return out


# ─── Rank-group helpers ──────────────────────────────────────────────────────


def _rank_groups(cards: list[Card]) -> dict[int, int]:
    """Return {rank: count} for the cards."""
    counts: dict[int, int] = {}
    for c in cards:
        r = card_rank(c)
        counts[r] = counts.get(r, 0) + 1
    return counts


def _count_pairs(groups: dict[int, int]) -> int:
    """Count ranks with EXACTLY 2 cards. Does not count trips or quads."""
    return sum(1 for c in groups.values() if c == 2)


def _has_three_of_a_kind(groups: dict[int, int]) -> bool:
    """At least one rank has exactly 3 cards (not 4 — that's quads)."""
    return any(c == 3 for c in groups.values())


def _has_four_of_a_kind(groups: dict[int, int]) -> bool:
    return any(c >= 4 for c in groups.values())


def _has_full_house(groups: dict[int, int]) -> bool:
    """At least one rank has ≥3 cards AND at least 2 ranks have ≥2 cards.

    Covers both standard FH (trips + pair) and the two-trips edge case
    (treated as full house by Foxwoods).
    """
    has_trips = any(c >= 3 for c in groups.values())
    pair_or_more = sum(1 for c in groups.values() if c >= 2)
    return has_trips and pair_or_more >= 2


# ─── Straight / flush / straight-flush detection ─────────────────────────────


# All possible 5-card straights, ordered by their §7.2 straight rank
# (high to low). Each entry is (set_of_5_ranks, straight_rank_for_docs).
# We iterate this order so the FIRST match is always the highest-ranked
# straight available — including the round-4 §7.2 placement of A-2-3-4-5
# (wheel) as second-highest above K-Q-J-10-9.
_STRAIGHTS_HIGH_TO_LOW: list[tuple[tuple[int, ...], int]] = [
    ((14, 13, 12, 11, 10),  10),  # broadway A-K-Q-J-10
    ((14, 5, 4, 3, 2),       9),  # wheel A-2-3-4-5 (round-4 §7.2 placement)
    ((13, 12, 11, 10,  9),   8),  # K-Q-J-10-9
    ((12, 11, 10,  9,  8),   7),  # Q-J-10-9-8
    ((11, 10,  9,  8,  7),   6),  # J-10-9-8-7
    ((10,  9,  8,  7,  6),   5),  # 10-9-8-7-6
    (( 9,  8,  7,  6,  5),   4),  # 9-8-7-6-5
    (( 8,  7,  6,  5,  4),   3),  # 8-7-6-5-4
    (( 7,  6,  5,  4,  3),   2),  # 7-6-5-4-3
    (( 6,  5,  4,  3,  2),   1),  # 6-5-4-3-2
]


def _pick_one_per_rank(cards: list[Card], rank_sequence: tuple[int, ...]) -> Optional[list[Card]]:
    """Pick one card per rank from `cards`, in the given order. Returns the
    picked cards (length == len(rank_sequence)) or None if any rank is
    missing. Used by straight + straight-flush detectors.
    """
    picked: list[Card] = []
    taken: set[int] = set()
    for r in rank_sequence:
        found = False
        for i, c in enumerate(cards):
            if i in taken:
                continue
            if card_rank(c) == r:
                picked.append(c)
                taken.add(i)
                found = True
                break
        if not found:
            return None
    return picked


def _find_straight(cards: list[Card]) -> Optional[list[Card]]:
    """Return 5 cards forming the HIGHEST straight under §7.2 ordering, or
    None. Picks one card per straight-rank in descending order so the
    returned list is sorted high-to-low (matches canonical card_sort_key).
    """
    rank_set = {card_rank(c) for c in cards}
    for ranks, _ in _STRAIGHTS_HIGH_TO_LOW:
        if set(ranks).issubset(rank_set):
            return _pick_one_per_rank(cards, ranks)
    return None


def _find_flush(cards: list[Card]) -> Optional[list[Card]]:
    """Return the 5 HIGHEST cards of the dominant suit if any suit has ≥5
    cards, else None.
    """
    suit_counts: dict[str, int] = {}
    for c in cards:
        suit_counts[c["suit"]] = suit_counts.get(c["suit"], 0) + 1
    for suit, count in suit_counts.items():
        if count >= 5:
            suited = sorted(
                (c for c in cards if c["suit"] == suit),
                key=card_sort_key,
            )
            return suited[:5]  # highest 5 of this suit
    return None


def _find_straight_flush(cards: list[Card]) -> Optional[list[Card]]:
    """Return 5 cards forming a straight flush (any suit), or None.

    For 7-card SF inputs, picks the highest 5-card straight subset within
    the dominant suit, so the back hand gets the strongest straight rank
    (e.g., broadway for A-K-Q-J-10-9-8 all hearts).
    """
    suit_counts: dict[str, int] = {}
    for c in cards:
        suit_counts[c["suit"]] = suit_counts.get(c["suit"], 0) + 1
    for suit, count in suit_counts.items():
        if count >= 5:
            suited = [c for c in cards if c["suit"] == suit]
            sf = _find_straight(suited)
            if sf is not None:
                return sf
    return None


# ─── Shared split helper (for rules 1, 5, 6) ────────────────────────────────


def _split_with_back_5(back: list[Card], all_cards: list[Card]) -> tuple[list[Card], list[Card]]:
    """Given a 5-card back (identified by SF/flush/straight detection), pick
    the 2 highest leftover cards as front.

    Identity comparison (`is`) — `back` references are the exact card objects
    from `all_cards`, because the detectors pick cards directly from `cards`
    without copying or substitution.
    """
    leftover = [c for c in all_cards if not any(c is bc for bc in back)]
    leftover.sort(key=card_sort_key)  # descending by rank
    front = leftover[:2]
    return front, back


# ─── Rule 2: Four of a kind ─────────────────────────────────────────────────


def _split_four_of_a_kind(
    cards: list[Card], groups: dict[int, int]
) -> tuple[list[Card], list[Card]]:
    """Foxwoods rule 2 — Four of a kind:

    - Quads 2–6 (LOW):    KEEP. quads + highest non-quad → back; next 2 → front.
    - Quads 7–10 (MED):   KEEP if hand has an Ace kicker; SPLIT otherwise.
    - Quads J–A (HIGH):   SPLIT into two pairs of the quad rank.

    SPLIT mechanics: `front = quad_cards[:2]` (pair of quad-rank), `back =
    quad_cards[2:] + 3 highest non-quad`. Both halves are "pair of X" by
    category; back wins via §7.3 kicker tiebreak (length-5 tuple > length-2
    tuple). This is the **round-4 catch** — the high-quad split that earlier
    drafts would have falsely fouled is now legal by construction.
    """
    quad_rank = next(r for r, c in groups.items() if c >= 4)
    quad_cards = [c for c in cards if card_rank(c) == quad_rank]
    non_quad = sorted(
        (c for c in cards if card_rank(c) != quad_rank),
        key=card_sort_key,
    )

    is_low = quad_rank <= 6
    is_mid = 7 <= quad_rank <= 10
    has_ace_kicker = any(card_rank(c) == 14 for c in non_quad)

    keep_in_back = is_low or (is_mid and has_ace_kicker)

    if keep_in_back:
        # quads + highest non-quad → back; next 2 → front
        back = quad_cards + non_quad[:1]
        front = non_quad[1:3]
        return front, back

    # SPLIT (high quads always; medium quads when no Ace kicker)
    front = quad_cards[:2]
    back = quad_cards[2:] + non_quad[:3]  # 2 quad-rank + 3 highest non-quad = 5
    return front, back


# ─── Rule 3: Full house (always split, including two-trips case) ────────────


def _split_full_house(
    cards: list[Card], groups: dict[int, int]
) -> tuple[list[Card], list[Card]]:
    """Foxwoods rule 3 — Full house (and two-trips edge):

    Always SPLIT. The pair → front, trips + 2 highest other kickers → back.
    Back ends up as three-of-a-kind (not full house) but with strong kickers;
    the pair-front is competitive vs most opponent 2-card hands. EV is
    higher than KEEP (full house in back + weak high-card front).

    Two-trips edge case (e.g., 999 + 666 + 1 kicker): treat the LOWER trips
    as a "pair" — front gets 2 cards of the lower trip rank, the 3rd card
    of the lower trips joins back as a kicker alongside the higher trips
    and any other non-pair cards.
    """
    trip_ranks_desc = sorted(
        [r for r, c in groups.items() if c >= 3],
        reverse=True,
    )

    # Two-trips edge case
    if len(trip_ranks_desc) >= 2:
        high_rank = trip_ranks_desc[0]
        low_rank = trip_ranks_desc[1]
        high_trips = [c for c in cards if card_rank(c) == high_rank]
        low_trips = [c for c in cards if card_rank(c) == low_rank]
        other = sorted(
            (c for c in cards if card_rank(c) not in (high_rank, low_rank)),
            key=card_sort_key,
        )
        front = low_trips[:2]                       # pair from lower trips
        back = high_trips + [low_trips[2]] + other[:1]   # 3 + 1 + 1 = 5
        return front, back

    # Standard FH: 1 trip + ≥1 pair
    trip_rank = trip_ranks_desc[0]
    trips = [c for c in cards if card_rank(c) == trip_rank]
    # When multiple pairs exist (FH + extra pair), use the HIGHEST pair as
    # the pair-half. Other pair-ranks become "non-pair kickers" by category.
    pair_ranks_desc = sorted(
        [r for r, c in groups.items() if c == 2],
        reverse=True,
    )
    pair_rank = pair_ranks_desc[0]
    pair_cards = [c for c in cards if card_rank(c) == pair_rank]
    other = sorted(
        (c for c in cards if card_rank(c) not in (trip_rank, pair_rank)),
        key=card_sort_key,
    )
    front = pair_cards[:2]
    back = trips + other[:2]   # trips + 2 highest others (not pair, not trips)
    return front, back


# ─── Rule 4: Three pairs ────────────────────────────────────────────────────


def _split_three_pairs(
    cards: list[Card], groups: dict[int, int]
) -> tuple[list[Card], list[Card]]:
    """Foxwoods rule 4 — Three pairs:

    HIGHEST pair → FRONT. Other 2 pairs + 1 kicker → BACK as two-pair.

    Counter-intuitive but standard Foxwoods: putting the strongest pair in
    front maximizes the front's win probability, and the two-pair back
    (medium + low) still beats most opponent 5-card hands. Net EV favors
    this split over "low pair → front + top two-pair → back".
    """
    pair_ranks_desc = sorted(
        [r for r, c in groups.items() if c == 2],
        reverse=True,
    )
    high_rank, mid_rank, low_rank = pair_ranks_desc[:3]

    high_pair = [c for c in cards if card_rank(c) == high_rank]
    mid_pair = [c for c in cards if card_rank(c) == mid_rank]
    low_pair = [c for c in cards if card_rank(c) == low_rank]
    kicker = [c for c in cards if card_rank(c) not in pair_ranks_desc[:3]]

    front = high_pair                       # 2 cards
    back = mid_pair + low_pair + kicker[:1] # 2 + 2 + 1 = 5
    return front, back


# ─── Rule 7: Three of a kind (ALWAYS keep; Foxwoods never splits) ──────────


def _split_three_of_a_kind(
    cards: list[Card], groups: dict[int, int]
) -> tuple[list[Card], list[Card]]:
    """Foxwoods rule 7 — Three of a kind:

    ALWAYS KEEP. Trips → back + 2 LOWEST non-trip kickers; 2 HIGHEST non-trip
    → front. **Even trip Aces stay in back** in Foxwoods (some PG variants
    split trip aces, but splitting would either foul the hand or break trips).
    """
    trip_rank = next(r for r, c in groups.items() if c >= 3)
    trips = [c for c in cards if card_rank(c) == trip_rank]
    non_trips = sorted(
        (c for c in cards if card_rank(c) != trip_rank),
        key=card_sort_key,
    )
    front = non_trips[:2]                # 2 highest non-trip
    back = trips + non_trips[2:]         # trips + 2 lowest non-trip = 5
    return front, back


# ─── Rule 8: Two pair (split/keep with Ace-kicker rule) ─────────────────────


def _split_two_pair(
    cards: list[Card], groups: dict[int, int]
) -> tuple[list[Card], list[Card]]:
    """Foxwoods rule 8 — Two pair:

    KEEP both pairs in back when EITHER:
      (a) both pairs are LOW (≤ 6) — splitting low pairs gives a weak front, or
      (b) hand contains an Ace kicker — putting the Ace in front beats most
          opponent fronts, and back stays strong as two-pair.

    Otherwise SPLIT — higher pair to back + 3 highest non-pair kickers;
    lower pair → front.

    Tested cases:
      - both low + no Ace        → KEEP (test_rule8_two_pair_both_low_keep_together)
      - both high                → SPLIT (test_rule8_two_pair_both_high_split)
      - mixed + Ace kicker       → KEEP (test_rule8_two_pair_mixed_with_ace_kicker_keeps)
      - mixed + no Ace kicker    → SPLIT (test_rule8_two_pair_mixed_no_ace_splits)
    """
    pair_ranks_desc = sorted(
        [r for r, c in groups.items() if c == 2],
        reverse=True,
    )
    higher_rank, lower_rank = pair_ranks_desc[0], pair_ranks_desc[1]

    higher_pair = [c for c in cards if card_rank(c) == higher_rank]
    lower_pair = [c for c in cards if card_rank(c) == lower_rank]
    non_pair = sorted(
        (c for c in cards if card_rank(c) not in (higher_rank, lower_rank)),
        key=card_sort_key,
    )

    has_ace_kicker = any(card_rank(c) == 14 for c in non_pair)
    both_low = higher_rank <= 6 and lower_rank <= 6

    if has_ace_kicker or both_low:
        # KEEP: both pairs → back + 1 lowest non-pair kicker; 2 highest non-pair → front
        front = non_pair[:2]
        back = higher_pair + lower_pair + non_pair[2:]  # 2 + 2 + 1 = 5
        return front, back

    # SPLIT: higher pair → back + 3 highest non-pair; lower pair → front
    front = lower_pair
    back = higher_pair + non_pair[:3]  # 2 + 3 = 5
    return front, back


# ─── Rule 9: One pair ───────────────────────────────────────────────────────


def _split_one_pair(
    cards: list[Card], groups: dict[int, int]
) -> tuple[list[Card], list[Card]]:
    """Foxwoods rule 9 — One pair:

    Pair → BACK + 3 LOWEST non-pair kickers. 2 HIGHEST non-pair → FRONT.

    Pair anchors the back hand (beats most opponent high-card hands). The
    front gets the strongest 2-card high-card combo possible from the
    leftover non-pair cards.
    """
    pair_rank = next(r for r, c in groups.items() if c == 2)
    pair_cards = [c for c in cards if card_rank(c) == pair_rank]
    non_pair = sorted(
        (c for c in cards if card_rank(c) != pair_rank),
        key=card_sort_key,
    )
    front = non_pair[:2]                # 2 highest
    back = pair_cards + non_pair[2:]    # pair + 3 lowest = 5
    return front, back


# ─── Rule 10: No pair (high card hand) ──────────────────────────────────────


def _split_no_pair(cards: list[Card]) -> tuple[list[Card], list[Card]]:
    """Foxwoods rule 10 — No pair (high card):

    Highest card + 4 LOWEST → BACK. 2nd and 3rd highest → FRONT.

    The single highest card (Ace if present) anchors a high-card-hand back;
    the next two-highest cards form the strongest possible 2-card front,
    which is still a high-card hand but with strong upper cards.

    Input is pre-sorted by `card_sort_key` (rank desc, suit asc).
    """
    # cards[0] = highest; cards[1], cards[2] = next two highest
    front = [cards[1], cards[2]]
    back = [cards[0]] + cards[3:]   # highest + 4 lowest = 5
    return front, back
