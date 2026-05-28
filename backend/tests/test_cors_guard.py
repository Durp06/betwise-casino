"""
test_cors_guard.py — startup guard that refuses to boot when
BETWISE_CORS_ORIGINS contains '*'.

Covers CSO Finding #5. The wildcard origin combined with
allow_credentials=True is browser-rejected AND insecure as a config
posture, so we fail fast at startup rather than silently shipping a
broken security stance.
"""
from __future__ import annotations

import importlib
import sys

import pytest


def _reload_main_with_origins(monkeypatch, value: str | None):
    """Reload backend.main with BETWISE_CORS_ORIGINS set to value (or unset).

    Drops any cached backend.main module so the import-time guard re-fires.
    """
    if value is None:
        monkeypatch.delenv("BETWISE_CORS_ORIGINS", raising=False)
    else:
        monkeypatch.setenv("BETWISE_CORS_ORIGINS", value)
    sys.modules.pop("backend.main", None)
    return importlib.import_module("backend.main")


def test_cors_wildcard_raises_at_startup(monkeypatch):
    """BETWISE_CORS_ORIGINS='*' should refuse to boot."""
    with pytest.raises(RuntimeError, match="insecure"):
        _reload_main_with_origins(monkeypatch, "*")


def test_cors_wildcard_among_other_origins_still_raises(monkeypatch):
    """Even a single '*' anywhere in the list is rejected."""
    with pytest.raises(RuntimeError, match="insecure"):
        _reload_main_with_origins(monkeypatch, "https://app.example.com,*")


def test_cors_explicit_origins_boot_clean(monkeypatch):
    """Comma-separated explicit origins are fine."""
    # Should NOT raise.
    mod = _reload_main_with_origins(
        monkeypatch,
        "http://localhost:5173,https://betwise.example.com",
    )
    assert mod.app is not None


def test_cors_default_localhost_boots_clean(monkeypatch):
    """No env var set = default localhost:5173. Boots fine."""
    mod = _reload_main_with_origins(monkeypatch, None)
    assert mod.app is not None
