# backend/game/

This directory holds one Python package per game. Today there is only one:
`blackjack/`. The flat `engine.py`/`strategy.py`/`state.py`/`review.py`
modules visible at this directory's root are **re-exports** from
`blackjack/` for backward compatibility — see `backend/game/__init__.py`.

To add a new game (poker, baccarat, ...), follow the **"Adding a new game"**
section in the project root `CLAUDE.md`. The short version:

1. Create `backend/game/<your_game>/__init__.py` exposing `GAME_TYPE`.
2. Add the package to `backend/game/registry.py::GAME_REGISTRY`.
3. Add the literal to `backend/game/types.py::GameType`.
4. Do NOT add a new module at the root of `backend/game/` — keep
   per-game code inside its package.
