"""Single source of the project's name and version (the one name token).

Everything else reads the display name / slug / version from here so the
project can be renamed by editing this file alone (see docs/ai/00-INDEX.md).
"""

from __future__ import annotations

APP_NAME = "ScribeFlow"
"""Human-facing display name (used in CLI help, README, banners)."""

SLUG = "scribeflow"
"""ASCII package / console-script / PyPI name."""

__version__ = "0.1.0"

__all__ = ["APP_NAME", "SLUG", "__version__"]
