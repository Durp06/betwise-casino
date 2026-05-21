"""backend.game.blackjack — blackjack-specific game module.

Submodules: engine, strategy, state, review.
"""
from __future__ import annotations

GAME_TYPE = "blackjack"

# Re-export submodules so `from backend.game.blackjack import engine, strategy, state, review` works.
from . import engine, strategy, state, review  # noqa: F401,E402
