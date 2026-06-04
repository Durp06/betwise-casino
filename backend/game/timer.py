"""backend.game.timer — pure move-timer helpers shared across multiplayer games.

The move timer is a *server-authoritative absolute deadline*: when a human
becomes next-to-act, the router stamps an absolute UTC instant `move_deadline_at`
on the row that holds the turn pointer. Enforcement is lazy — the next `/state`
poll or `/act` for that table checks the deadline and, if it has passed, makes
the safest legal move for the player (Hold'em: check-or-fold; blackjack: stand).

These helpers are deliberately free of any DB or framework dependency so they
can be unit-tested in isolation and reused by both the blackjack and Hold'em
routers. All timestamps are tz-aware UTC (CLAUDE.md rule #13: never
`datetime.utcnow()`).
"""

from __future__ import annotations

from datetime import datetime, timedelta

# Seconds a player has to act before the server auto-resolves their turn.
MOVE_TIMER_SECONDS: int = 30


def move_deadline(now: datetime) -> datetime:
    """The absolute instant a turn that begins at `now` expires."""
    return now + timedelta(seconds=MOVE_TIMER_SECONDS)


def is_expired(deadline: datetime | None, now: datetime) -> bool:
    """True only if a deadline exists and `now` has moved strictly past it.

    A `None` deadline means nobody is on the clock (all-in run-out, hand over),
    so it can never be expired.
    """
    return deadline is not None and now > deadline
