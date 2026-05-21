"""backend.game.blackjack — blackjack-specific game module.

Submodules: engine, strategy, state, review.

Re-exports the submodules at the package root for ergonomic access:
    from backend.game.blackjack import engine, strategy, state, review
"""
from __future__ import annotations

GAME_TYPE = "blackjack"

# Submodules will be re-exported here after Task 2 moves them in.
# (Adding the `from . import engine, strategy, state, review` line in Task 2.)
