"""
test_holdem_security.py — regression guards for the security-audit remediation.

The chip-duplication / double-debit races live in concurrent Postgres
transactions, which the in-memory SQLite test engine cannot reproduce (SQLite
serialises writes and ignores FOR UPDATE). So — exactly like the existing
tests/test_action_race.py "CSO Finding #3" guard — we assert the row locks are
PRESENT in the source of the money/turn paths, so a future refactor can't
silently drop them.
"""

from __future__ import annotations

import inspect

from backend.routers import game, holdem


def test_holdem_deal_locks_table_row():
    """deal must lock the table row so it can't interleave with a concurrent
    leave (the deal/leave race that duplicated chips)."""
    src = inspect.getsource(holdem._deal_hand)
    assert "with_for_update" in src


def test_holdem_leave_locks_table_and_seat():
    src = inspect.getsource(holdem._leave_seat)
    # table row + seat row (+ user row on cash-out)
    assert src.count("with_for_update") >= 2


def test_holdem_act_locks_table_and_hand():
    src = inspect.getsource(holdem._act)
    assert src.count("with_for_update") >= 2


def test_holdem_join_locks_table_and_user():
    src = inspect.getsource(holdem._join_seat)
    assert src.count("with_for_update") >= 2


def test_holdem_complete_hand_writeback_keys_on_user_id():
    """Stack write-back must match on user_id, not just physical chair, so a new
    joiner who took a vacated seat mid-hand isn't clobbered."""
    src = inspect.getsource(holdem._complete_hand)
    assert "ps.user_id == hs.user_id" in src


def test_blackjack_deal_locks_user_row():
    """Blackjack initial deal debits the bankroll — lock the user row like the
    double-down path and the holdem buy-in."""
    src = inspect.getsource(game._deal_hand)
    assert "with_for_update" in src
