# Blackjack multiplayer — synchronized betting round

## Problem (root cause, traced)
Blackjack shares one session/dealer across seated players, but the round starts
on the *first* player's deal (`game.py` flips `playing`) and the dealer runs the
moment no `active` hands remain (`state.advance_turn`). So a player who hasn't
dealt yet has no hand to keep the round open → the first player's stand ends the
round → late players spawn a *separate* session. `/state` shows only the latest
session, so players see each other's rounds and lose their own hand. The frontend
also marks *every* active hand "your turn", so out-of-turn players click → 403.

## Fix: a real betting phase (mirrors the proven Pai Gow round lifecycle)
Separate **placing a bet** from **dealing**. One active round per table; deal is
**synchronized** once all seated players have bet (or a betting-window timer fires).

No DB migration: a placed-but-undealt bet is `Hand(status="active", cards=[])`
(the `hands.status` CHECK already allows `active`); "awaiting deal" is signalled
by the session being in `betting`. New status strings would violate the CHECK.

## Acceptance criteria

### Backend
- **AC1 (place bet, multi-seat):** With A (seat 1) and B (seat 2) seated, A's
  `POST /tables/{id}/deal {bet}` creates A's hand with `cards == []`, debits A's
  chips, and leaves the session in `betting` (no dealer cards). The round is NOT
  dealt yet.
- **AC2 (synchronized deal on all-bet):** Once B also bets, the round auto-deals:
  session → `playing`, A and B each get 2 cards, dealer gets 2 (hole masked in
  `/state`), and the current actor is seat 1 (A's hand has `move_deadline_at`,
  B's is null).
- **AC3 (single-player unaffected):** A alone (1 seat) bets → round deals
  immediately (session `playing`, A active with 2 cards). No waiting.
- **AC4 (betting-window timeout):** If A bets and B never does, once the betting
  window (`BLACKJACK_BETTING_WINDOW_SECONDS`) elapses past `session.created_at`,
  the next `/state` poll deals the players who bet (session → `playing`).
- **AC5 (betting closed during play):** Placing a bet while the active session is
  `playing` returns 409 (you bet on the next hand, not mid-round).
- **AC6 (turn order intact):** During `playing`, only the lowest-seat active hand
  is the actor; acting out of turn → 403; standing advances to the next seat;
  when none remain the dealer runs and all hands resolve (unchanged).
- **AC7 (no fragmentation):** Two seated players who both bet always share one
  session; neither is left in a separate round.

### Frontend
- **AC8:** During `betting`, a player who has bet sees "waiting for players
  (N/M)…"; a player who hasn't sees Place-Bet. Cards appear together when the
  round deals.
- **AC9:** Only the current actor's seat glows / shows action buttons (no
  out-of-turn 403s, no duplicate "their turn").

## Out of scope (follow-up)
- Refund on leave during `betting` (rare; current behavior keeps the escrow).
- Replacing the betting-window heuristic with an explicit per-session deadline
  column (would need a migration; `created_at + window` suffices).
