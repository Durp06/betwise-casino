"""
test_pai_gow_canonical.py — Chipy cache key contract.

Verifies the canonical-form algorithm from spec §12.4 (round-4 corrected):
- Equivalent hands (rank multiset + suit-equivalence-class structure)
  collapse to identical keys → cache hits across suit rotations.
- Non-equivalent hands (different rank multiset OR different suit-equivalence
  structure) map to different keys → cache never returns wrong EV.
- Joker-present vs joker-absent are distinct (joker materially changes
  optimal play, so they must NOT collide).
- Input order doesn't affect output (the round-4 catch: rank-sort first,
  THEN relabel by first occurrence).
- Commission-ruleset version is bundled in the full cache key so future
  rule changes invalidate stale entries automatically.
"""
from __future__ import annotations

from backend.game.pai_gow.cards import JOKER
from backend.game.pai_gow.canonical import (
    COMMISSION_RULESET_VERSION,
    cache_key,
    canonical_form,
)


_SUIT_SHORT = {"h": "hearts", "d": "diamonds", "c": "clubs", "s": "spades"}


def C(suit: str, value: str) -> dict:
    return {"suit": _SUIT_SHORT.get(suit, suit), "value": value}


# ─── Equivalence: suit rotation collapses to same key ───────────────────────


def test_suit_rotation_produces_same_canonical_form():
    """Two hands with the same rank multiset and same suit-equivalence-class
    structure should produce identical keys.

    K-K-Q where Q shares the LOWER-ordered K's suit:
      hand_a: K♥, K♦, Q♦  (sort order: K♦, K♥, Q♦ → K-A, K-B, Q-A)
      hand_b: K♣, K♠, Q♣  (sort order: K♣, K♠, Q♣ → K-A, K-B, Q-A)
    """
    hand_a = [C("h", "K"), C("d", "K"), C("d", "Q")]
    hand_b = [C("c", "K"), C("s", "K"), C("c", "Q")]
    assert canonical_form(hand_a) == canonical_form(hand_b)


def test_input_order_does_not_affect_canonical_form():
    """Permuting the input list must not change the key. This is the round-4
    catch: rank-sort happens BEFORE suit relabel, so input order can't bleed
    into the relabeling step.
    """
    hand_a = [C("h", "K"), C("s", "5"), C("d", "K"), C("c", "2")]
    hand_b = [C("c", "2"), C("d", "K"), C("h", "K"), C("s", "5")]
    assert canonical_form(hand_a) == canonical_form(hand_b)


# ─── Non-equivalence: different structure → different keys ──────────────────


def test_different_rank_multiset_produces_different_canonical_form():
    """Different ranks must produce different keys."""
    hand_a = [C("h", "K"), C("d", "K"), C("h", "Q")]
    hand_b = [C("h", "K"), C("d", "K"), C("h", "J")]
    assert canonical_form(hand_a) != canonical_form(hand_b)


def test_different_flush_potential_produces_different_canonical_form():
    """Same rank multiset but different suit-equivalence structure → distinct
    keys. All-hearts (flush potential) vs mixed-suits (no flush).
    """
    hand_flush = [C("h", "K"), C("h", "Q"), C("h", "J"), C("h", "9"), C("h", "5")]
    hand_mixed = [C("h", "K"), C("d", "Q"), C("c", "J"), C("s", "9"), C("h", "5")]
    assert canonical_form(hand_flush) != canonical_form(hand_mixed)


# ─── Joker as distinct token ────────────────────────────────────────────────


def test_joker_present_vs_absent_produces_different_keys():
    """Joker substantially changes optimal play → must have distinct keys
    even when the rank/suit projection is similar."""
    hand_with_joker = [JOKER, C("h", "K"), C("d", "Q")]
    hand_no_joker = [C("h", "A"), C("h", "K"), C("d", "Q")]
    assert canonical_form(hand_with_joker) != canonical_form(hand_no_joker)


def test_joker_only_hand():
    """Edge case: joker alone produces (True, ())."""
    form = canonical_form([JOKER])
    assert form == (True, ())


def test_two_joker_hands_same_suit_structure_collapse():
    """Joker + 4 hearts vs joker + 4 spades — same structural form (single
    suited group, all in one suit), so canonical_form collapses them.
    """
    hand_a = [JOKER, C("h", "K"), C("h", "Q"), C("h", "J"), C("h", "9")]
    hand_b = [JOKER, C("s", "K"), C("s", "Q"), C("s", "J"), C("s", "9")]
    assert canonical_form(hand_a) == canonical_form(hand_b)


# ─── Canonical sort order contract ──────────────────────────────────────────


def test_canonical_form_orders_by_rank_descending():
    """First entry must be the highest-rank card."""
    hand = [C("h", "2"), C("h", "K"), C("h", "7")]
    form = canonical_form(hand)
    assert form[1][0][0] == "K"
    assert form[1][-1][0] == "2"


def test_canonical_form_assigns_first_suit_as_A():
    """First card's suit always gets label 'A', regardless of which physical
    suit it is."""
    form_spades = canonical_form([C("s", "K"), C("s", "Q")])
    form_clubs = canonical_form([C("c", "K"), C("c", "Q")])
    assert form_spades == form_clubs
    assert form_spades[1][0] == ("K", "A")


def test_canonical_form_no_joker_first_tuple_element_is_False():
    form = canonical_form([C("h", "K")])
    assert form[0] is False


def test_canonical_form_with_joker_first_tuple_element_is_True():
    form = canonical_form([JOKER, C("h", "K")])
    assert form[0] is True


# ─── Cache key (canonical + commission version) ─────────────────────────────


def test_cache_key_combines_commission_version_with_canonical_form():
    """The full Chipy cache key is `(commission_version, canonical_form)`.
    Future rule changes flip the version tag and invalidate stale entries.
    """
    hand = [C("h", "K"), C("d", "Q"), C("h", "J")]
    key = cache_key(hand)
    assert key == (COMMISSION_RULESET_VERSION, canonical_form(hand))


def test_cache_key_different_commission_versions_distinct():
    """Same hand under different commission versions → different keys.
    Ensures a future rule change doesn't accidentally serve v1 EVs.
    """
    hand = [C("h", "K"), C("d", "Q")]
    key_v1 = cache_key(hand, commission_version="no_commission_v1")
    key_future = cache_key(hand, commission_version="commission_5pct_v1")
    assert key_v1 != key_future


def test_cache_key_equivalent_hands_same_key():
    """Suit-rotation-equivalent hands hash to the same cache key."""
    hand_a = [C("h", "K"), C("d", "K"), C("d", "Q")]
    hand_b = [C("c", "K"), C("s", "K"), C("c", "Q")]
    assert cache_key(hand_a) == cache_key(hand_b)


def test_commission_version_constant_pinned_for_v1():
    """v1 ships with the no-commission ruleset (§7.6). Pin the constant so a
    silent rename doesn't go unnoticed."""
    assert COMMISSION_RULESET_VERSION == "no_commission_v1"
