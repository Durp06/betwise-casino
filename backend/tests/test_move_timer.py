"""
test_move_timer.py — unit tests for the pure move-timer helpers
(backend/game/timer.py). These are framework-free: no DB, no FastAPI.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.game.timer import (
    MOVE_TIMER_SECONDS,
    is_expired,
    move_deadline,
)

_NOW = datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc)


def test_move_timer_seconds_is_thirty():
    assert MOVE_TIMER_SECONDS == 30


def test_move_deadline_adds_timer_seconds():
    assert move_deadline(_NOW) == _NOW + timedelta(seconds=MOVE_TIMER_SECONDS)


def test_is_expired_true_when_now_is_past_deadline():
    assert is_expired(_NOW - timedelta(seconds=1), _NOW) is True


def test_is_expired_false_when_now_is_before_deadline():
    assert is_expired(_NOW + timedelta(seconds=1), _NOW) is False


def test_is_expired_false_when_now_equals_deadline():
    # The clock has not yet *passed* the deadline at the exact instant.
    assert is_expired(_NOW, _NOW) is False


def test_is_expired_false_when_deadline_is_none():
    # No deadline means nobody is on the clock — never expired.
    assert is_expired(None, _NOW) is False


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
