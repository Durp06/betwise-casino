"""backend.game.types — shared types for the multi-game scaffold.

Right now this only declares the GameType literal used by the registry.
When a second game arrives, candidates for promotion here are:
- the Card TypedDict (currently in backend.game.blackjack.engine),
- a GameOutcome literal,
- any shared card/deck constants.

YAGNI for now — only add things here when a second game actually needs them.
"""
from __future__ import annotations

from typing import Literal

# Update this Literal when a new game is added to the registry.
#
# MERGE-CONFLICT NOTE: this file is an expected conflict point when the hold'em
# branches merge in. Their PR adds "poker" to this Literal; ours adds "pai_gow".
# The merger should union them: Literal["blackjack", "poker", "pai_gow"].
# Same pattern in registry.py — additive on both sides.
GameType = Literal["blackjack", "pai_gow"]
