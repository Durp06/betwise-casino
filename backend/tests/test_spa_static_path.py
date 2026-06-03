"""
test_spa_static_path.py — T1 (C1) Path traversal in SPA catch-all.

Tests the to-be-extracted `_safe_static_path(dist, full_path)` helper in
`backend/main.py` plus a structural check that `spa_fallback` delegates to it.

AC-1.1: traversal via `..` segments returns None (never resolves outside dist).
AC-1.2: normal file inside dist returns the real path; missing file returns None.
AC-1.3: the `spa_fallback` route source calls `_safe_static_path` (structural guard
        that the route cannot path-traverse independently of the helper).

These tests FAIL until `_safe_static_path` is extracted from `spa_fallback` in
`backend/main.py` (the helper does not exist yet → AttributeError on import).
"""
from __future__ import annotations

import inspect
import os


# ─── AC-1.1 — traversal via `..` segments rejected ──────────────────────────

def test_safe_static_path_rejects_dotdot_traversal(tmp_path):
    """AC-1.1: `../../backend/auth.py`-style paths must return None.

    Build a dist dir with an `index.html` and a sibling secret file outside
    dist; assert the helper does not resolve to the secret file.
    """
    from backend.main import _safe_static_path  # type: ignore[attr-defined]  # noqa: PLC0415

    # Lay out:
    #   tmp_path/
    #     dist/
    #       index.html   ← legitimate file inside dist
    #     secret.txt     ← outside dist, must never be served
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<html></html>")
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("TOP SECRET")

    # Classic Unix traversal
    result = _safe_static_path(str(dist_dir), "../../secret.txt")
    assert result is None, (
        f"_safe_static_path must return None for '../../secret.txt' traversal; "
        f"got {result!r}"
    )

    # Absolute path (should also be rejected)
    result_abs = _safe_static_path(str(dist_dir), str(secret_file))
    assert result_abs is None, (
        f"_safe_static_path must return None for absolute path traversal; "
        f"got {result_abs!r}"
    )

    # Ensure the resolved path is never pointing at the secret
    result_nested = _safe_static_path(str(dist_dir), "../secret.txt")
    assert result_nested is None, (
        f"_safe_static_path must return None for '../secret.txt' traversal; "
        f"got {result_nested!r}"
    )


# ─── AC-1.2 — normal file inside dist returns real path; missing → None ──────

def test_safe_static_path_returns_real_path_for_legit_file(tmp_path):
    """AC-1.2: a file that exists inside dist returns its real path; a
    non-existent file returns None so the route serves the SPA shell.
    """
    from backend.main import _safe_static_path  # type: ignore[attr-defined]  # noqa: PLC0415

    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    favicon = dist_dir / "favicon.ico"
    favicon.write_bytes(b"ICO")
    (dist_dir / "index.html").write_text("<html></html>")

    # Existing top-level file
    result = _safe_static_path(str(dist_dir), "favicon.ico")
    assert result is not None, (
        "Expected _safe_static_path to return the real path to favicon.ico inside dist"
    )
    assert os.path.isfile(result), f"Returned path {result!r} is not a file"
    assert os.path.realpath(str(favicon)) == result, (
        f"Returned path {result!r} does not match the expected {os.path.realpath(str(favicon))!r}"
    )

    # Missing file (e.g. 'lobby' — no such file on disk; SPA shell should serve)
    result_missing = _safe_static_path(str(dist_dir), "lobby")
    assert result_missing is None, (
        f"Expected None for a non-existent path 'lobby'; got {result_missing!r}"
    )

    # Empty full_path must also return None
    result_empty = _safe_static_path(str(dist_dir), "")
    assert result_empty is None, (
        f"Expected None for empty full_path; got {result_empty!r}"
    )


# ─── AC-1.3 — structural: spa_fallback's source calls `_safe_static_path` ───

def test_spa_fallback_source_calls_safe_static_path():
    """AC-1.3 (structural): the `spa_fallback` route must delegate file
    resolution to `_safe_static_path` — not pass `full_path` to FileResponse
    directly. If the route stops calling the helper (e.g. reverted to a direct
    os.path.join call), traversal is re-introduced silently.

    Read main.py's source TEXT rather than the live `spa_fallback` function
    object: the route is registered inside `if os.path.isdir(_frontend_dist)`,
    so the function is only *defined* when `frontend/dist` exists at import time.
    In a backend-only environment (CI runs pytest without building the frontend)
    `spa_fallback` is absent, but its `def` is always present in the source file.
    The `_safe_static_path` helper is always defined regardless.
    """
    import backend.main as main_mod  # noqa: PLC0415

    # The helper must always be importable as a module-level function.
    assert hasattr(main_mod, "_safe_static_path"), (
        "backend.main must expose `_safe_static_path` as a module-level function"
    )

    # Inspect the module source text (works whether or not the route was
    # registered at import time).
    module_src = inspect.getsource(main_mod)
    assert "def spa_fallback" in module_src, (
        "backend.main must define a `spa_fallback` SPA catch-all route"
    )
    fallback_src = module_src[module_src.index("def spa_fallback"):]
    assert "_safe_static_path" in fallback_src, (
        "spa_fallback must call `_safe_static_path`; "
        "passing full_path directly to FileResponse re-introduces the "
        "path-traversal vulnerability."
    )
