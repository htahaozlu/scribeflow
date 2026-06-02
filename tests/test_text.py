"""Golden cases for the ported text logic (docs/ai/02 §1, §6).

Expected outputs were hand-traced against the frozen ``clean_transcript`` so any
behavioral drift in the port is caught.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from yazit.engine.text import build_full_transcript, clean_transcript, tail_prompt


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # drops the 2-word sentence, keeps the 5-word one
        ("hi there. this sentence has enough words.", "this sentence has enough words"),
        # strips characters outside \w\s.,!?-  ("@" removed)
        ("alpha @beta gamma delta", "alpha beta gamma delta"),
        # consecutive word repeated >2 times collapses to 3
        ("no no no no stop now", "no no no stop now"),
        # whole sentence (3 words, below the 5-gram branch) repeated 3x -> 2 kept
        ("red green blue. red green blue. red green blue", "red green blue. red green blue"),
        # repeated trailing 5-gram phrase is suppressed
        (
            "alpha beta gamma delta epsilon. zeta alpha beta gamma delta epsilon",
            "alpha beta gamma delta epsilon",
        ),
        # empty / all-too-short -> empty
        ("", ""),
        ("a b", ""),
    ],
)
def test_clean_transcript_goldens(raw: str, expected: str) -> None:
    assert clean_transcript(raw) == expected


def test_tail_prompt_empty_returns_none() -> None:
    assert tail_prompt([]) is None
    assert tail_prompt(["   ", ""]) is None


def test_tail_prompt_joins_and_trims() -> None:
    assert tail_prompt(["abc", "def"]) == "abc def"
    assert tail_prompt(["hello world"]) == "hello world"


def test_tail_prompt_respects_max_chars() -> None:
    long = "x" * 400
    out = tail_prompt([long], max_chars=350)
    assert out is not None
    assert out == "x" * 350


def test_build_full_transcript_sorted_skips_empty(tmp_path: Path) -> None:
    (tmp_path / "chunk_000.txt").write_text("A", encoding="utf-8")
    (tmp_path / "chunk_002.txt").write_text("C", encoding="utf-8")
    (tmp_path / "chunk_001.txt").write_text("B", encoding="utf-8")
    (tmp_path / "chunk_003.txt").write_text("   ", encoding="utf-8")  # empty -> skipped
    (tmp_path / "notes.txt").write_text("IGNORE", encoding="utf-8")  # non-chunk -> ignored
    assert build_full_transcript(tmp_path) == "A\n\nB\n\nC"


def test_build_full_transcript_empty_dir(tmp_path: Path) -> None:
    assert build_full_transcript(tmp_path) == ""
