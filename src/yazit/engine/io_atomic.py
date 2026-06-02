"""Crash-safety primitives — ported verbatim from the proven engine.

Every checkpoint write goes through here. Atomicity (temp file + ``os.replace``)
is the foundation of the resume guarantee (docs/ai/02 §5 invariant 1): a reader
never sees a half-written file, and a crash mid-write leaves the previous valid
version intact. ``os.replace`` is atomic on POSIX and Windows.

Other modules MUST call these as module attributes (``io_atomic.write_json(...)``)
so a single patch point can inject crashes in tests (docs/ai/02 §6).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def timestamp() -> str:
    """UTC ISO-8601 with a trailing ``Z``."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_seconds(seconds: float) -> str:
    """``HH:MM:SS`` from a float number of seconds."""
    total = int(seconds)
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def read_json(path: Path, default: Any) -> Any:
    """Return parsed JSON, or ``default`` if the file is missing OR corrupt.

    A torn/partial JSON checkpoint (e.g. a non-fsync'd flush dropped by the Drive
    FUSE mount under load) must stay non-fatal: it is treated as "not present" so
    the dual-condition skip guard re-does that chunk and resume self-heals
    (docs/ai/02 §5 invariant 3). Without this, a single corrupt checkpoint would
    abort the whole batch and starve every healthy video queued after it.
    """
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return default


def write_json(path: Path, data: Any) -> None:
    """Atomic JSON write: mkdir -p → write ``<suffix>.tmp`` → ``os.replace``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    temp_path.replace(path)


def write_text(path: Path, content: str) -> None:
    """Atomic text write: same temp-then-replace as :func:`write_json`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        handle.write(content)
    temp_path.replace(path)


def append_log(path: Path, message: str) -> None:
    """Timestamped append to the durable log + a live mirror on **stderr**.

    The mirror goes to stderr (not stdout) so progress never pollutes a CLI
    ``--json`` payload; it stays visible in Colab/terminals all the same.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    stamped = f"[{timestamp()}] {message}"
    print(stamped, file=sys.stderr, flush=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(stamped + "\n")
