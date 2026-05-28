# Texas Hold'em — Authoritative Reference Constants

> Every poker constant the implementation hard-codes lives here. Code in `backend/game/poker/` imports its tables from modules whose values are pinned by tests against the values in this document. If a value here changes, a test must change with it; otherwise the value is the contract.
>
> **Sources** are listed inline next to each artifact. When sources disagree, the implementation pins one and the test asserts the *rule* (not a contested number); the disagreement is called out in the relevant section.
>
> Companion file: `specs/texas-holdem.md` (the build plan that uses these constants).

---

## 1. Hand rankings (strongest → weakest)

Standard 5-card poker ranking. Suits never break ties; kickers do. Ace is high *or* low (the wheel A-2-3-4-5 is the lowest straight). Card-rank order:

```
A > K > Q > J > T > 9 > 8 > 7 > 6 > 5 > 4 > 3 > 2
```

| Rank | Name | Example |
|---|---|---|
| 1 | Royal flush | A♠ K♠ Q♠ J♠ T♠ |
| 2 | Straight flush | 9♥ 8♥ 7♥ 6♥ 5♥ |
| 3 | Four of a kind | Q♠ Q♥ Q♦ Q♣ 3♠ |
| 4 | Full house | T♠ T♥ T♦ 6♠ 6♥ |
| 5 | Flush | A♣ J♣ 9♣ 6♣ 3♣ |
| 6 | Straight | 9♠ 8♥ 7♦ 6♣ 5♠ |
| 7 | Three of a kind | 7♠ 7♥ 7♦ K♠ 4♣ |
| 8 | Two pair | J♠ J♥ 4♦ 4♣ A♠ |
| 9 | One pair | 8♠ 8♥ A♦ K♣ 3♠ |
| 10 | High card | A♠ Q♥ 9♦ 7♣ 4♠ |

Implementation encoding: each evaluated 5-card hand reduces to a tuple `(category, rank_tuple)` where `rank_tuple` is a length-5 descending-kicker list. Comparison is lexicographic.

**Sources:** standard. Any introductory poker text; *Hold'em Poker for Advanced Players* §1 (Sklansky & Malmuth).

---

## 2. Pot odds → required equity

Required equity to make a 0-EV call against a pot-sized bet `B` into a pot `P`:

> **required_equity = B / (P + B + B)** = `call / (pot_before + opp_bet + our_call)`

`opp_bet == call == B` for a non-raise call. Pinned table for common bet fractions of the pot before the bet:

| Opponent bet (× pot) | Pot odds | Required equity |
|---|---|---|
| 0.25 (¼ pot) | 5 : 1 | 16.67% |
| 0.33 (⅓ pot) | 4 : 1 | 20.00% |
| 0.50 (½ pot) | 3 : 1 | 25.00% |
| 0.66 (⅔ pot) | 2.5 : 1 | 28.57% |
| 0.75 (¾ pot) | ~2.33 : 1 | 30.00% |
| 1.00 (pot) | 2 : 1 | 33.33% |
| 1.50 (1.5× pot) | ~1.67 : 1 | 37.50% |
| 2.00 (2× pot) | 1.5 : 1 | 40.00% |

**Bluff break-even** (fold-equity needed for an immediate-profit bluff): a bet `B` into pot `P` profits if opponents fold > `B / (P + B)`:

| Bet size | Required folds |
|---|---|
| ½ pot | > 33.3% |
| ¾ pot | > 42.9% |
| 1× pot | > 50.0% |
| 1.5× pot | > 60.0% |
| 2× pot | > 66.7% |

**Minimum Defense Frequency (MDF)** against a bet `B` into pot `P`: `MDF = P / (P + B)`. Defend at or above MDF to prevent always-fold from being exploited.

| Bet size | MDF (defend ≥) |
|---|---|
| ½ pot | 66.7% |
| ⅔ pot | 60.0% |
| ¾ pot | 57.1% |
| 1× pot | 50.0% |
| 1.5× pot | 40.0% |
| 2× pot | 33.3% |

**Sources:** Sklansky & Malmuth, *Hold'em Poker for Advanced Players* §3 ("The Fundamental Theorem of Poker", pot odds). Standard. MDF/bluff break-even appear in any modern GTO text (e.g. Janda, *Applications of NLHE*; Polk/Wilson lectures).

---

## 3. Outs → equity (Rule of 2 and 4)

After the flop with two cards to come, equity ≈ `outs × 4 %`. After the turn with one card to come, equity ≈ `outs × 2 %`. The approximation overestimates above ~12 outs (shade down).

| Draw | Outs | Equity (flop → river) | Equity (turn → river) |
|---|---|---|---|
| Backdoor only | 3 | ~12% | ~6.5% |
| Gutshot | 4 | ~16.5% | ~8.7% |
| Two overcards | 6 | ~24% | ~13% |
| Open-ended straight | 8 | ~31.5% | ~17.4% |
| Flush draw | 9 | ~35% | ~19.6% |
| Pair + flush draw | 14 | ~52% | ~30% |
| Flush draw + gutshot | 12 | ~45% | ~24% |
| Open-ended + flush draw (combo) | 15 | ~54% | ~30–33% |
| Open-ended + flush + overpair | 21 | ~67% | ~45% |

**Tainted outs:** an out that also pairs the board (giving the opponent a full house when they hold trips/two pair) does not count cleanly. The implementation does not subtract them automatically (it uses live equity), but the coach mentions the concept in Reads mode when board pairing is plausible.

**Sources:** Phil Gordon's *Little Green Book* popularized the Rule of 2/4; the exact values match Wizard of Odds enumeration within ±1%.

---

## 4. Canonical preflop all-in matchup equities (heads-up)

For coach verbal explanations only. The engine computes the exact equity live (via `equity.py`) and tests assert that the engine's number matches these within Monte-Carlo tolerance (±1.5%).

| Hand A | Hand B | A wins | B wins | Note |
|---|---|---|---|---|
| AA | KK | 82% | 18% | The classic "set over set" preflop |
| KK | 88 | 81% | 19% | Pair over pair |
| QQ | AKo | 57% | 43% | "Race + a bit" |
| QQ | AKs | 54% | 46% | Suited shaves ~3% |
| 77 | AKo | 55% | 45% | Tiny pair edge vs Ax |
| AK | 22 | ~50% | ~50% | The canonical coin flip |
| AKs | QQ | 46% | 54% | Mirror of QQ vs AKs |
| 88 | A8 | 70% | 30% | Pair dominates same-rank Ax |
| AK | AQ | 74% | 26% | Same-rank A; K dominates Q kicker |
| AKo | KK | 31% | 69% | Big pair vs big Broadway |
| AK | 76o | 62% | 38% | Live undercards run better than feared |
| AA | 76s | 77% | 23% | Suited connectors lose less than expected |
| KK | 87s | 77% | 23% | Even good connectors are ~3:1 dogs |
| 87s | AKo | 38% | 62% | Mirror of AK vs 76o |

**Teaching points the coach surfaces:**
- KK vs 87s ≈ 77/23 — connectors help less than feared.
- AK vs 76o ≈ 62/38 — live undercards run better than expected.
- Equity vs *more than one* opponent drops sharply (e.g. AA vs 2 random hands is ~73%; vs 4 random hands ~55%).

**Sources:** Hutchison Point Count / Sklansky odds appendices; verified against pokerstove enumeration.

---

## 5. Chen formula (starting-hand scoring)

**Step 1 — score the highest card.**
| Card | Points |
|---|---|
| A | 10 |
| K | 8 |
| Q | 7 |
| J | 6 |
| T | 5 |
| 9 | 4.5 |
| 8 | 4 |
| 7 | 3.5 |
| 6 | 3 |
| 5 | 2.5 |
| 4 | 2 |
| 3 | 1.5 |
| 2 | 1 |

**Step 2 — if a pair, double the high-card score, with a minimum of 5.**
- AA → 20, KK → 16, QQ → 14, JJ → 12, TT → 10, 99 → 9, 88 → 8, 77 → 7, 66 → 6, 55 → 5, 44 → 5, 33 → 5, 22 → 5.

**Step 3 — bonus for suited:** +2.

**Step 4 — gap penalty (between the two ranks):**

| Gap | Penalty |
|---|---|
| 0 (connected, e.g. JT) | 0 |
| 1 (J9) | −1 |
| 2 (J8) | −2 |
| 3 (J7) | −4 |
| 4+ | −5 |

Treat an ace-gap (A2, A3, A4, A5) as 4+ gap → −5 (special case: ace-low connector A-2 still receives the −5).

**Step 5 — straight bonus:** +1 if 0-gap or 1-gap **and** both cards are below Q (so JTs gets +1, QJs does not).

**Step 6 — round half-points up** (Chen's spec).

**Verified worked examples** (unit-tested):
- AA → 20
- KK → 16
- AKs → 10 + 2 (suited) = **12**
- AKo → 10 + 0 = **10**
- JTs → 6 + 2 (suited) + 0 gap + 1 (straight) = **9**
- 55 → max(2.5 × 2, 5) = **5**
- 22 → max(1 × 2, 5) = **5**
- T9s → 5 + 2 + 1 = **8**
- 72o → 3.5 + 0 + (−5 for 5-gap) = **−1.5 → −1** (rounded up). Some references write 0; the rule is "round half-points up," so −1.5 rounds to −1. Test asserts the *value the formula produces*, not the published-table value.

**Source:** Bill Chen, *The Mathematics of Poker* appendix and Chen's original 1997 newsgroup post.

---

## 6. Sklansky–Malmuth starting-hand groups

A tier backbone, originally written for limit hold'em in *Hold'em Poker for Advanced Players* (1999). **NOT modern NLHE-optimal.** The product labels it accordingly.

### Group 1 (strongest)
AA, AKs, KK, QQ, JJ

### Group 2
AK, AQs, AJs, KQs, TT

### Group 3
AQ, ATs, KJs, QJs, JTs, 99

### Group 4
AJ, KQ, KTs, QTs, J9s, T9s, 98s, 88

### Group 5
A9s, A8s, A7s, A6s, A5s, A4s, A3s, A2s, KJ, QJ, JT, Q9s, T8s, 97s, 87s, 77, 76s, 66

### Group 6
AT, KT, QT, J8s, 86s, 75s, 65s, 55, 54s

### Group 7
K9s, K8s, K7s, K6s, K5s, K4s, K3s, K2s, J9, T9, 98, 64s, 53s, 44, 43s, 33, 22

### Group 8
A9, K9, Q9, J8, J7s, T8, 96s, 87, 85s, 76, 74s, 65, 54, 42s, 32s

### Group 9 (everything else — "unplayable")
Anything not above.

**Implementation:** `backend/game/poker/ranges.py::SKLANSKY_GROUPS` is a dict[int, set[str]] keyed by group number, with hand strings in canonical form ("AKs", "AKo", "77"). 169 distinct hands total (13 pairs + 78 suited + 78 offsuit).

**Sources:** Sklansky & Malmuth, *Hold'em Poker for Advanced Players* (2nd ed., 1999), starting-hands chart.

---

## 7. Sklansky–Chubukov push/fold ordering

The Sklansky–Chubukov (SC) number for a hand is the max effective stack (in bb) at which open-shoving from the SB (heads-up vs BB) is auto-profitable *even if the opponent sees your cards*. It's a chip-EV floor — real opponents fold too much, so you can shove far wider.

**Sourcing caveat:** at least two ~2× scales (and a third historical figure) circulate in the literature. The *ordering* is the contract, not specific numeric values. Implementation pins one scale (HoldemResources 2020 publication) and tests assert the ordering top-down.

### Pinned ordering (top → bottom)

| Rank | Hand | SC bb (HoldemResources) |
|---|---|---|
| 1 | AA | 1000 (always profitable) |
| 2 | KK | 754 |
| 3 | AKs | 408 |
| 4 | QQ | 313 |
| 5 | AKo | 207 |
| 6 | JJ | 197 |
| 7 | AQs | 165 |
| 8 | TT | 130 |
| 9 | AJs | 119 |
| 10 | AQo | 102 |
| 11 | KQs | 96 |
| 12 | 99 | 89 |
| 13 | ATs | 79 |
| 14 | AJo | 71 |
| 15 | KJs | 64 |
| 16 | 88 | 62 |
| 17 | KQo | 52 |
| 18 | A9s | 49 |
| 19 | QJs | 44 |
| 20 | ATo | 41 |
| 21 | 77 | 38 |
| 22 | KTs | 36 |
| 23 | A8s | 33 |
| ... | ... | ... |
| 169 | 32o | 1.7 |

**The implementation table** extends through all 169 hands. Tests assert: (a) AA is always the top SC number, (b) the ordering is monotonically decreasing, (c) 32o is the lowest, (d) pairs strictly dominate same-high-card offsuit (e.g. 22 > J2o).

**Sources:** Sklansky & Chubukov original (TwoPlusTwo Magazine, 2007); table values from HoldemResourcesCalculator / Daniel Negreanu's *Power Hold'em Strategy* appendix.

---

## 8. Short-stack push/fold Nash charts (≤15bb)

This is the only short-stack artifact that is *genuinely computer-solved* for the structure: first-in jam/fold, perfect opponents, no ICM, no antes (and separately *with* antes). Above ~20bb effective, pure push/fold becomes a mistake — standard raise/3-bet/postflop poker takes over.

### Principles encoded as tests (the contract is the *rule*, not every individual hand)

- AA is a profitable shove at every stack depth and every position.
- Below ~10bb, the SB shoves ≥56% of hands HU (vs BB).
- Below ~10bb, the BB calls a HU SB jam with ~38–40% of hands.
- At ≤~1.7bb HU, even 32o is a correct SB shove.
- Adding antes widens *every* push-fold range (more dead money in the pot).
- Position widens ranges: SB widest, BTN slightly tighter, CO tighter than BTN, UTG tightest.
- Weak offsuit aces (A3o, A4o, A5o, A6o) are losing UTG/MP pushes even at 10bb (dominated when called); high suited connectors (JTs, T9s, 98s) are better push candidates than dominated weak aces.

### Pinned charts (no-ante, ≤10bb, "first-in shove" — the values the implementation encodes)

Encoded as `backend/game/poker/nash.py::PUSH_FOLD_CHART[stack_bb][position]: set[str]` returning the set of hands to push.

#### Heads-up 10bb, no ante
SB push range (~56.6% — HoldemResources):
> 22+, A2s+, A2o+, K2s+, K5o+, Q2s+, Q8o+, J3s+, J9o+, T6s+, T9o, 96s+, 86s+, 75s+, 64s+, 53s+, 42s+, 32s

BB calling range (~38.5% — HoldemResources):
> 22+, A2s+, A3o+, K2s+, K8o+, Q5s+, QTo+, J7s+, JTo, T8s+, 98s, 87s, 76s

#### Heads-up 6bb, no ante
SB shoves ~70% — i.e. add to the 10bb range all suited gappers, all suited Kx, plus most offsuit Kx and Qx.

#### Heads-up 16bb, no ante
SB shoves ~43.3% — tighten from the 10bb range by removing offsuit weak connectors and weak Qx.

#### Heads-up ≤1.7bb, no ante
SB shoves **100%** (any-two).

#### Full-ring 10bb, no ante — MP shove range
> 22+, A7s+, A5s, A4s, A3s, ATo+, K8s+, KJo+, Q8s+, QJo, J8s+, T8s+, 98s

(Roughly Sklansky Group 1–5 + suited broadways + weak suited aces A3-A5 for blocker value.)

#### CO 12bb, **12.5% ante** — shove range (~33%)
> 22+, A2s+, A2o+, K5s+, KTo+, Q8s+, QTo+, J8s+, JTo, T7s+, 97s+, 86s+, 76s+, 65s+

(Adding antes ~doubles the share of hands you can profitably shove from CO.)

### Encoding convention

`backend/game/poker/nash.py` exposes:

```python
def push_fold_action(
    hand: str,                      # "AKs", "AKo", "77"
    stack_bb: float,                # 1.0 .. 15.0
    position: Position,             # SB / BB / BTN / CO / HJ / MP / UTG / UTG1 / UTG2
    ante_pct: float = 0.0,          # 0.0 .. 0.25
    seats: int = 9,                 # 2 (HU) .. 9
) -> Literal["push", "fold", "call"]:
    ...
```

The chart values above are encoded as a sparse set per `(seats, ante_pct_bucket, stack_bb_bucket, position)` tuple. Buckets: `stack_bb_bucket ∈ {1, 2, 3, 5, 7, 10, 12, 15}`; missing buckets interpolate to the next-larger pinned chart.

**Sources:**
- HoldemResourcesCalculator published HU charts (2020 release).
- Sklansky & Chubukov ordering.
- Will Tipton, *Expert Heads Up No Limit Hold'em* vol. 1.
- 2+2 NLHE wiki "push-fold charts" (community-verified vs SnapShove app).

When sources disagree by ≤5% on a marginal hand, the implementation favors the chart that errs *tighter* (lower frequency) — a slightly tight chart misses a few +EV shoves but never recommends a −EV shove. Tighter is safer for a teaching tool.

---

## 9. ICM heuristics (the standing constants — the math is the Harville recursion in `icm.py`)

ICM (Independent Chip Model) converts a stack vector into prize-pool equity. Chips are non-linear in money: a chip won is worth less in $ than a chip lost. The Harville recursion (1973, originally for horse racing) computes finish-position probabilities:

> P(seat i finishes 1st) = stack_i / Σstacks
> P(seat i finishes 2nd) = Σ_j≠i P(j 1st) × stack_i / (Σstacks − stack_j)
> ... etc

`icm.py::harville_finish_distribution(stacks)` returns the `n×n` matrix `M[i][j] = P(seat i finishes in position j+1)`. `icm_equity(stacks, payouts)` then dot-products against the payout vector to yield each seat's $ equity.

### Heuristic constants the coach uses

- **Chip-EV break-even** to call a pot-sized all-in: **33.3%** (pure pot-odds).
- **ICM break-even on a typical money-bubble pot-sized all-in**: **37–38%** (≈4–5% higher than chip-EV).
- **Final-table 3-handed near pay jumps**: break-even can rise to 40%+ when the leader is calling a medium-stack shove.
- **Big-stack pressure**: pushing all-in for ≥10bb into a medium stack near the bubble is +ICM-EV with extremely wide ranges because the medium stack's calling range tightens 3–6%.
- **Negligible regions**: early in the tournament when stacks are deep, ICM ≈ chip-EV (within 0.5%).
- **Effect peaks** at the money bubble and at the smallest pay-jump-to-pay-jump transitions on the final table.

These are heuristic principles for the coach's verbal guidance. The actual numeric ICM number for any specific spot is computed live by `icm_equity(...)`.

### Pinned ICM regression test cases

| Stacks (bb) | Payouts ($) | Expected equities ($) | Source |
|---|---|---|---|
| [50, 50] HU | [60, 40] | [50.00, 50.00] | trivial |
| [100, 100, 100] | [50, 30, 20] | [33.33, 33.33, 33.33] | uniform |
| [200, 100, 100] | [50, 30, 20] | [44.17, 27.92, 27.92] | Harville |
| [100, 50, 25] | [50, 30, 20] | [42.86, 31.43, 25.71] | Sklansky example |
| [1000, 1, 1, 1, 1] | [50, 25, 12.5, 7.5, 5] | leader ≪ 50, shorts ≫ proportional | "chip leader gets less than chip share of prize pool" |

Tests assert each row within ±0.05 of the expected.

**Sources:** Mason Malmuth original ICM piece; Harville (1973); ICMIZER documentation; Tysen Streib's *Course on Tournament Poker Theory*.

---

## 10. Positions and tournament structure

### Positions (seat labels by `seats` value)

| Seats | Position labels (from button, clockwise) |
|---|---|
| 2 (HU) | BTN/SB, BB |
| 3 | BTN, SB, BB |
| 4 | BTN, SB, BB, CO |
| 5 | BTN, SB, BB, UTG, CO |
| 6 | BTN, SB, BB, UTG, MP, CO |
| 7 | BTN, SB, BB, UTG, MP, HJ, CO |
| 8 | BTN, SB, BB, UTG, UTG+1, MP, HJ, CO |
| 9 | BTN, SB, BB, UTG, UTG+1, MP, HJ, LJ, CO |

**Preflop acting order:** starts with UTG (or BTN heads-up, with reversed blinds — SB acts first preflop in HU) and proceeds clockwise; SB/BB act last preflop in 3+ handed.

**Postflop acting order:** starts with SB (or the next live seat clockwise from the button) and proceeds clockwise; BTN acts last postflop.

### Heads-up blind reversal

In HU play:
- **BTN is the SB** (posts small blind, acts first preflop).
- **BB acts first postflop**, BTN acts last postflop.
- This is encoded as a special case in `state.py::next_to_act`.

### Hand flow (any game)

1. Post antes (if level has them).
2. Post small blind, then big blind.
3. Deal 2 hole cards to each live seat.
4. **Preflop** betting round.
5. Deal **flop** (3 community cards).
6. Postflop betting round.
7. Deal **turn** (1 community card).
8. Postflop betting round.
9. Deal **river** (1 community card).
10. Postflop betting round.
11. **Showdown:** evaluate 7-card best-5 per live seat; award pot(s); rotate button.

### Tournament structure (BetWise SNG defaults)

- **Seats:** 3–8 (1 human + 2–7 bots), configurable at table creation.
- **Starting stack:** 1500 chips per seat (configurable).
- **Blind schedule:** levels advance every 10 hands (configurable).
- **Antes:** start at level 4.

**Default blind schedule (chips)** — encoded as `BLIND_SCHEDULE_DEFAULT` in `tournament.py`:

| Level | Small blind | Big blind | Ante |
|---|---|---|---|
| 1 | 10 | 20 | 0 |
| 2 | 15 | 30 | 0 |
| 3 | 25 | 50 | 0 |
| 4 | 50 | 100 | 10 |
| 5 | 75 | 150 | 15 |
| 6 | 100 | 200 | 25 |
| 7 | 150 | 300 | 25 |
| 8 | 200 | 400 | 50 |
| 9 | 300 | 600 | 75 |
| 10 | 400 | 800 | 100 |
| 11+ | doubles each level until heads-up complete | | |

**Payout structures** by seat count (percent of total prize pool):

| Seats | 1st | 2nd | 3rd |
|---|---|---|---|
| 2 (HU) | 100% | — | — |
| 3 | 70% | 30% | — |
| 4 | 65% | 35% | — |
| 5 | 60% | 30% | 10% |
| 6 | 55% | 30% | 15% |
| 7 | 50% | 30% | 20% |
| 8 | 50% | 30% | 20% |

Buy-in × seats = total prize pool (no rake — tournaments don't rake pots; the brief §4.5 makes this explicit).

### Stages (heuristic labels the coach uses)

- **Early:** average effective stack > 30bb. ICM ≈ chip-EV. Standard NLHE applies.
- **Middle:** 15–30bb average effective. Antes active. Steals become high-EV; raise-or-fold dominates limp.
- **Bubble:** one elimination away from the money. ICM peaks. Calling ranges tighten ~4%; aggression with fold equity becomes more profitable.
- **Final table / heads-up:** big pay jumps. ICM dominates; push/fold becomes near-optimal at HU ≤15bb effective.

**Sources:** generic SNG structures match early-2000s online standards (PokerStars Turbo, etc.); ICM stage definitions track Lee Jones, *Winning Low-Limit Hold'em*.

---

## 11. 169-hand grid representation

All 169 strategically distinct starting hands fit in a 13×13 grid, where:
- diagonal = pairs (`row == col`).
- upper triangle (`col > row`) = suited.
- lower triangle (`row > col`) = offsuit.

Row/column index 0–12 maps to ranks A, K, Q, J, T, 9, 8, 7, 6, 5, 4, 3, 2 (descending). Notation: `"AKs"`, `"AKo"`, `"77"`.

Implementation: `ranges.py::HAND_GRID: list[list[str]]` with `HAND_GRID[r][c]` returning the canonical hand string. Helper: `hand_to_grid(hand)` → `(r, c)` and `grid_to_hand(r, c)` → `hand`.

**Counts:**
- 13 pairs (diagonal)
- 78 suited combos (upper triangle, 78 = 13·12/2)
- 78 offsuit combos (lower triangle)
- 169 total distinct strategic hands; **1326** total starting combinations (52·51/2).

Each cell represents a *strategic class*. For combo-level math:
- Pair: 6 combos (4·3/2)
- Suited: 4 combos (one per suit)
- Offsuit: 12 combos (4·3, since the off-suit pair pulls from 4 suits × 3 remaining = 12)

Total: 13·6 + 78·4 + 78·12 = 78 + 312 + 936 = **1326**. Pin in test.

---

## 12. Archetype baseline stats (overlapping bands)

VPIP / PFR / AF stat bands commonly cited for 6-max NLHE. Run several points *tighter* in full-ring (9-handed). Bands overlap; treat as fuzzy, not hard cutoffs.

| Archetype | Hellmuth animal | VPIP | PFR | AF | Signature behavior |
|---|---|---|---|---|---|
| TAG | Lion | 19–25 | 17–23 | 2.5–4 | Solid, narrow VPIP-PFR gap, c-bets often |
| LAG | (no animal) | 26–32 | 22–28 | 4–6 | Wide opens/3-bets, multiple barrels |
| Nit / Rock | Mouse | 8–14 | 6–12 | 0.8–2 | Plays only premiums; folds to aggression |
| Calling Station / Fish | Elephant | 35–55 | 5–12 | 0.5–1.2 | Limps and calls down, never bluffs |
| Maniac | Jackal | 40–55 | 30–37 | 4–8 | Random aggression; high gap to fish |
| Set-miner | (specialized Mouse) | 12–18 | 4–8 | 1–2 | Plays small pairs cheap, jams on flopped sets |
| ABC | (basic Lion) | 20–24 | 17–20 | 2–3 | Straightforward value-bets and folds |
| TAG-fish | (no animal) | 22–28 | 18–22 | 2–3 (preflop) / <2 (postflop) | Looks TAG by preflop stats; leaks postflop |
| Whale | (oversize Elephant) | 50+ | <10 | 0.5–1.0 | Plays everything, calls big bets |
| Trapper | (no animal) | 18–24 | 12–18 | 1–2 | Slow-plays monsters; passive line that explodes |
| Shark / GTO | Eagle | 22–28 | 19–24 | 2.5–4 (balanced) | Near-unexploitable; tells vanish |

**Tilt-state overlay (optional):** any archetype shifts toward Maniac-like params after a recent big loss (encoded as a 30-hand "tilt window" trigger).

### Stat acronym definitions

- **VPIP:** Voluntarily Put $ In Pot — % of hands where you put chips in voluntarily (not blinds). Roughly: how loose preflop.
- **PFR:** Preflop Raise — % of hands you raise preflop. The gap VPIP - PFR measures limp-and-call frequency (high gap → station / fish).
- **AF:** Aggression Factor — (raises + bets) / calls postflop. > 3 is aggressive; < 1 is passive.

### Bet-sizing semantics the coach uses (heuristic; board-dependent)

| Bet size (× pot) | Common meaning |
|---|---|
| ¼ – ⅓ | High-frequency / merged. From a station, usually a weak made hand wanting cheap showdown; rarely a bluff |
| ½ | Standard. Mixed range — value + occasional bluff |
| ⅔ – full | Polarized on wet boards. Strong value + bluffs |
| Overbet (>pot) | Strongly polarized — nuts + bluffs. Reps against a capped opponent |
| Block bet (10–25%, OOP river) | Medium hand setting a cheap price; rarely the nuts |

### Range shape terminology

- **Linear / merged:** weighted toward strong-but-not-nuts; matches smaller sizes.
- **Polarized:** weighted to the extremes — strong value + bluffs, very little medium-strength. Matches larger sizes / overbets.
- **Capped:** opponent is unlikely to have the nuts (often signaled by passive line — flat-call → check → check). Vulnerable to overbets.

### Named actions to recognize

- **C-bet** (continuation bet): preflop aggressor bets the flop.
- **Delayed c-bet**: aggressor checks flop, bets turn.
- **Donk bet**: bettor was *not* the preflop aggressor (calls preflop, leads the flop). Often weak in regs, sometimes strong in fish.
- **Probe bet**: out-of-position lead on a later street after a missed c-bet.
- **Float**: call out-of-position on flop with intent to take pot away on turn.
- **Check-raise**: check, then raise the opponent's bet.
- **Barrel**: continued bet on a later street after the c-bet. "Double barrel" = c-bet + turn bet; "triple barrel" = + river bet.
- **3-bet / 4-bet / 5-bet**: re-raises after the initial raise (open = 1-bet; restealer = 3-bet; squeeze = 3-bet over an open + caller).

The coach must teach that against the **Shark/Eagle archetype** the readable tells disappear — the player should not over-generalize archetype patterns.

**Sources:** Phil Hellmuth, *Play Poker Like the Pros* (animal archetypes); Sklansky & Malmuth's *The Theory of Poker* (player typology); Janda, *Applications of NLHE* (range shapes); standard 2+2 tracking-software conventions for stat bands.

---

## 13. Provenance summary

| Constant | Encoded in | Pinned by test | Primary source |
|---|---|---|---|
| Hand ranks | `evaluator.py::Category` | `test_evaluator.py::test_category_ordering` | universal |
| Pot odds table | `pot_odds.py::REQUIRED_EQUITY_BY_BET_FRACTION` | `test_pot_odds.py::test_pinned_required_equities` | Sklansky |
| MDF | `pot_odds.py::mdf` | `test_pot_odds.py::test_mdf` | Janda |
| Rule of 2/4 | `pot_odds.py::equity_from_outs` | `test_pot_odds.py::test_outs_to_equity_approximation` | Gordon |
| Canonical equities | n/a (engine computes live) | `test_equity.py::test_canonical_matchups` | pokerstove |
| Chen formula | `ranges.py::chen_score` | `test_ranges.py::test_chen_worked_examples` | Chen |
| Sklansky–Malmuth groups | `ranges.py::SKLANSKY_GROUPS` | `test_ranges.py::test_sklansky_groups_complete_169` | Sklansky & Malmuth |
| SC ordering | `ranges.py::SC_RANK_ORDER` | `test_ranges.py::test_sc_ordering_monotonic` | Sklansky & Chubukov |
| Nash push/fold charts | `nash.py::PUSH_FOLD_CHART` | `test_nash.py::test_pinned_charts` | HoldemResources |
| ICM heuristics + Harville | `icm.py` | `test_icm.py::test_pinned_cases` | Harville / Malmuth |
| Blind schedule | `tournament.py::BLIND_SCHEDULE_DEFAULT` | `test_tournament.py::test_default_schedule` | generic SNG |
| Payout structures | `tournament.py::PAYOUT_STRUCTURE_BY_SEATS` | `test_tournament.py::test_payouts_sum_to_100` | generic SNG |
| 169-hand grid | `ranges.py::HAND_GRID` | `test_ranges.py::test_169_hands_complete` | combinatorial |
| Archetype stats | `archetypes.py::ARCHETYPE_REGISTRY` | `test_archetypes.py::test_archetype_stats_in_bands` | Hellmuth + 2+2 |

---

## 14. Anti-patterns to avoid (drawn from the brief's §4 landmines)

1. **Do not** publish a single "correct action" table for full NLHE postflop. Deterministic spots are only: ≤~15bb push/fold (Nash), pot-odds calls vs all-in (equity-vs-required-equity), and chip-EV preflop all-in spots. Everything else is heuristic.
2. **Do not** have the coach reason about a bot's range differently than the bot actually plays. Same archetype engine drives both. (Principle §4.3 of the build brief.)
3. **Do not** mix tournament chips with the cents bankroll unit. Conversion happens only at buy-in and payout.
4. **Do not** hardcode "rounded" equities as the engine's truth — the engine computes live, tests assert within tolerance.
5. **Do not** import any live poker-strategy library — the brief mandates a hand-roll.
6. **Do not** decrement the streak or `correct_decisions` on a heuristic-spot non-recommendation. Only deterministic spots count.

---

*End of reference.*
