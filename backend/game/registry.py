"""backend.game.registry — single source of truth for which games exist.

To add a new game:
  1. Create backend/game/<your_game>/ with __init__.py exposing GAME_TYPE.
  2. Add the package to GAME_REGISTRY below.
  3. Add the literal to backend.game.types.GameType.
  4. (Future) Wire routers to dispatch through this registry.

Routers do NOT yet use this registry — they still import backend.game.* directly.
This module exists so the registry slot is ready when the second game lands.
"""
from __future__ import annotations

from types import ModuleType
from typing import Mapping

from backend.game import blackjack
from backend.game import GameModule  # noqa: F401  # re-exported for type-check sites

# Mapping is intentionally typed as ModuleType (concrete) rather than GameModule
# (Protocol) because today's only entry is a package, and runtime isinstance
# against a Protocol is more friction than it's worth. Document the convention
# in GameModule's docstring; trust the convention.
GAME_REGISTRY: Mapping[str, ModuleType] = {
    blackjack.GAME_TYPE: blackjack,
}
