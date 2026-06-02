"""backend.game.pai_gow.canonical — Chipy cache-key canonical hand form.

Pure functions. Produces a stable, equivalence-aware fingerprint for a
Pai Gow hand suitable for use as a cache key on Chipy's `optimal_set` /
`pai_gow_evaluate_split` responses. The fingerprint:

- Collapses **suit rotations** to a single key (same rank multiset + same
  suit-equivalence-class structure → identical cache entry). Without this,
  every of `K♥ K♦ Q♥`, `K♣ K♠ Q♣`, etc. would hit a separate cache slot
  for an evaluation that's structurally identical.
- Preserves **flush potential** (same rank multiset but different
  suit-equivalence structure → distinct keys). Without this, an all-hearts
  hand and a mixed-suit hand with the same ranks would collide on the wrong
  EV — the optimal split differs because flush is reachable in only one case.
- Treats the **joker as a distinct token** (`joker_present: bool`). Joker
  semi-wild semantics materially change optimal play; joker-bearing and
  joker-free hands with the same suited rank multiset must NOT collide.
- Is **input-order independent**. The round-4 catch: rank-sort happens
  BEFORE suit relabeling, so input order can't leak into the suit-letter
  assignments. `[K♥, 2♠, A♠]` and `[A♠, K♥, 2♠]` produce the same key.

The `cache_key` function additionally bundles a commission-ruleset version
tag (`COMMISSION_RULESET_VERSION`). When v1 ships with no commission per
§7.6, the tag is `"no_commission_v1"`; any future rule change flips the tag
and stale entries are automatically invalidated.

Algorithm (spec §12.4):

  1. Separate joker (track `joker_present: bool`).
  2. Sort suited cards by `(rank desc, suit asc)` using `cards.RANK_ORDER`
     and `cards.SUIT_ORDER` constants. **Rank-sort first** — round-4 catch.
  3. Walk sorted cards, assign suit labels A, B, C, D in order of first
     occurrence.
  4. Output: `(joker_present, tuple[(rank_value, suit_label), ...])`.

Spec refs: §12.4 (canonical form), §12.5 (was_optimal canonical sort), §7.6
(no-commission ruleset).
"""
from __future__ import annotations

from backend.game.pai_gow.cards import (
    Card,
    RANK_ORDER,
    SUIT_ORDER,
    is_joker,
)


# Commission-ruleset version tag bundled into the full cache key. v1 ships
# without the 5% commission per §7.6; any future rule change should flip
# this constant to a new string ("commission_5pct_v1", "commission_v2", …)
# so stale cache entries are automatically invalidated.
COMMISSION_RULESET_VERSION: str = "no_commission_v1"


def canonical_form(cards: list[Card]) -> tuple:
    """Return `(joker_present, tuple[(rank_value, suit_label), ...])`.

    The returned tuple is hashable and stable under suit rotation. Two
    structurally-equivalent hands produce identical tuples; non-equivalent
    hands (different rank multiset, different suit-equivalence structure,
    or different joker presence) produce distinct tuples.
    """
    joker_present = any(is_joker(c) for c in cards)
    suited = [c for c in cards if not is_joker(c)]

    # Rank desc, suit asc — using cards.py's RANK_ORDER + SUIT_ORDER as the
    # canonical base. Sorting FIRST (before relabeling) is the round-4 fix.
    suited.sort(key=lambda c: (-RANK_ORDER[c["value"]], SUIT_ORDER[c["suit"]]))

    # Walk in sorted order, assign suit labels A, B, C, D as each new suit
    # is first encountered.
    label_map: dict[str, str] = {}
    next_label_idx = 0
    canonical_cards: list[tuple[str, str]] = []
    for c in suited:
        suit = c["suit"]
        if suit not in label_map:
            label_map[suit] = chr(ord("A") + next_label_idx)
            next_label_idx += 1
        canonical_cards.append((c["value"], label_map[suit]))

    return (joker_present, tuple(canonical_cards))


def cache_key(
    cards: list[Card],
    commission_version: str = COMMISSION_RULESET_VERSION,
) -> tuple:
    """Return the full Chipy cache key: `(commission_version, canonical_form)`.

    The commission tag prefixes the canonical form so a future rule change
    (e.g., introducing the 5% commission) invalidates v1 EV entries without
    a manual cache flush. Same hand under different rulesets is correctly
    treated as a separate cache entry.
    """
    return (commission_version, canonical_form(cards))
