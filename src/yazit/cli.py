"""Command-line entry point for Yazıt.

P0 ships only ``--version`` and ``--help``; the ``transcribe`` / ``models`` /
``doctor`` / ``gen-notebook`` / ``web`` verbs are added in later phases
(see docs/ai/06-implementation-roadmap.md).
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from yazit.__about__ import APP_NAME, SLUG, __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=SLUG,
        description=f"{APP_NAME} — portable, resumable, multi-backend transcription.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{SLUG} {__version__}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
