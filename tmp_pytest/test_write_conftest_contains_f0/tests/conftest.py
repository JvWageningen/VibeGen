"""Shared pytest fixtures for mytool tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def data_dir() -> Path:
    """Return the path to the test data directory."""
    d = Path(__file__).parent / "data"
    d.mkdir(exist_ok=True)
    return d
