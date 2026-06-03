"""Generate a runnable Colab notebook from one parameterized template.

Replaces the old five hand-copied notebooks + build_colab_bundle.py (docs/ai/05
§7). Dependency-free: the template is valid notebook JSON whose string fields
hold ``{{ var }}`` placeholders; we parse it and substitute on the parsed
strings, so values are inserted safely (no JSON-escaping hazard) and neither
jinja2 nor nbformat is needed at runtime.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TEMPLATE_PATH = Path(__file__).parent / "template.ipynb.j2"
_PLACEHOLDER = re.compile(r"{{\s*(\w+)\s*}}")


@dataclass(frozen=True)
class NotebookSpec:
    source: str
    output_dir: str = "/content/drive/MyDrive/scribeflow-output"  # durable (Drive)
    workspace_dir: str = "/content/scribeflow-workspace"  # local scratch (Errno-107 split)
    model: str | None = None  # None → auto-select on the Colab host
    backend: str | None = None
    language: str = "tr"
    chunk_minutes: int = 20
    extras: tuple[str, ...] = ()  # e.g. ("url",) so the notebook installs scribeflow[url]


def pip_target(extras: tuple[str, ...]) -> str:
    return f"scribeflow[{','.join(extras)}]" if extras else "scribeflow"


def _context(spec: NotebookSpec) -> dict[str, str]:
    return {
        "pip_target": pip_target(spec.extras),
        "source_repr": repr(spec.source),
        "output_repr": repr(spec.output_dir),
        "workspace_repr": repr(spec.workspace_dir),
        "model_repr": repr(spec.model) if spec.model else "None",
        "backend_repr": repr(spec.backend) if spec.backend else "None",
        "language_repr": repr(spec.language),
        "chunk_minutes": str(spec.chunk_minutes),
    }


def _substitute(node: Any, ctx: dict[str, str]) -> Any:
    if isinstance(node, str):
        return _PLACEHOLDER.sub(lambda m: ctx[m.group(1)], node)
    if isinstance(node, list):
        return [_substitute(item, ctx) for item in node]
    if isinstance(node, dict):
        return {key: _substitute(value, ctx) for key, value in node.items()}
    return node


def build_notebook(spec: NotebookSpec) -> dict[str, Any]:
    """Return the notebook as an nbformat-v4 dict (already parameterized)."""
    template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    notebook: dict[str, Any] = _substitute(template, _context(spec))
    return notebook


def generate_colab_notebook(spec: NotebookSpec, path: Path) -> Path:
    """Write the generated ``.ipynb`` and return its path."""
    notebook = build_notebook(spec)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path
