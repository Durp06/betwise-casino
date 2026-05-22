"""backend.game — multi-game scaffold for BetWise Casino.

Today's only game is blackjack (backend.game.blackjack). To preserve the
historical import surface (used by routers, analytics, and 118 tests), we
re-export the blackjack submodules at this package level:

    from backend.game import engine as eng         # → backend.game.blackjack.engine
    from backend.game import strategy              # → backend.game.blackjack.strategy
    from backend.game import state as game_state   # → backend.game.blackjack.state
    from backend.game.review import classify_action  # → backend.game.blackjack.review.classify_action

When a second game is added, routers will dispatch through
backend.game.registry.GAME_REGISTRY instead of importing blackjack
directly. Until then, the re-exports below are the supported public API.
"""
from __future__ import annotations

import sys
from typing import Protocol

# ─── Re-export blackjack submodules at backend.game.* for back-compat ──────────
# After these imports, the following are all true:
#   backend.game.engine    is backend.game.blackjack.engine
#   backend.game.strategy  is backend.game.blackjack.strategy
#   backend.game.state     is backend.game.blackjack.state
#   backend.game.review    is backend.game.blackjack.review
# which means `from backend.game.engine import X` resolves exactly as before.
from .blackjack import engine, strategy, state, review  # noqa: F401

# Register the submodules under the historical dotted paths so that
# `from backend.game.engine import X` and `from backend.game.review import Y`
# continue to resolve even though the physical files now live under blackjack/.
# Python checks sys.modules before attempting filesystem lookup, so these
# aliases are the minimal, reliable fix for dotted-path imports.
sys.modules.setdefault("backend.game.engine", engine)
sys.modules.setdefault("backend.game.strategy", strategy)
sys.modules.setdefault("backend.game.state", state)
sys.modules.setdefault("backend.game.review", review)


# ─── GameModule Protocol ──────────────────────────────────────────────────────

class GameModule(Protocol):
    """Convention (NOT enforced) for entries in GAME_REGISTRY.

    A game module is a Python package (e.g. backend.game.blackjack) that
    exposes at least:

        GAME_TYPE: str  # the registry key; matches GameType literal

    We deliberately keep this Protocol minimal. Blackjack and poker do not
    share a useful runtime shape today — adding speculative methods like
    apply_action() or legal_actions() would calcify the wrong abstraction.
    When a second game arrives, expand this Protocol with whatever genuinely
    rhymes between the two implementations.

    Not enforced via runtime isinstance checks — purely a documentation /
    type-check hint for IDE tooling.
    """

    GAME_TYPE: str
