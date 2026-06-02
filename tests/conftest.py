"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def sample_video() -> Path:
    """A tiny bundled 5-second media file for chunking/transcription tests."""
    return FIXTURES_DIR / "sample_5s.mp4"
