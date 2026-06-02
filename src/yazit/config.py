"""Layered configuration: defaults ← config file (toml) ← env ← CLI (docs/ai/05 §1).

The later a layer, the higher its precedence. ``load_config`` returns a frozen
:class:`YazitConfig`; the CLI turns that into the engine's ``EngineConfig`` +
``TranscribeOptions`` and the backend resolution.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib

DEFAULT_OUTPUT_DIR = "yazit-output"
DEFAULT_WORKSPACE_DIR = "yazit-workspace"
CONFIG_FILENAMES = ("yazit.toml", ".yazit.toml")


class ConfigError(ValueError):
    """A configuration file or value could not be parsed — surfaced to the user
    as a clean message, never a traceback."""


@dataclass(frozen=True)
class YazitConfig:
    output_dir: Path = Path(DEFAULT_OUTPUT_DIR)
    workspace_dir: Path = Path(DEFAULT_WORKSPACE_DIR)
    cache_dir: Path | None = None
    # backend / model (None ⇒ auto-select for the detected host)
    backend: str | None = None
    model: str | None = None
    device: str | None = None
    compute_type: str | None = None
    want: str = "default"
    # transcription
    language: str = "tr"  # "auto" ⇒ let the backend detect
    chunk_minutes: int = 20
    beam_size: int = 5
    vad_filter: bool = True
    temperature: float = 0.0
    word_timestamps: bool = False
    # behavior
    overwrite: bool = False
    keep_audio_chunks: bool = True
    formats: tuple[str, ...] = ("txt",)
    json_output: bool = False
    ui_lang: str = "en"


_PATH_FIELDS = {"output_dir", "workspace_dir", "cache_dir"}
_INT_FIELDS = {"chunk_minutes", "beam_size"}
_FLOAT_FIELDS = {"temperature"}
_BOOL_FIELDS = {"vad_filter", "word_timestamps", "overwrite", "keep_audio_chunks", "json_output"}
_VALID_KEYS = {f.name for f in fields(YazitConfig)}


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _coerce(raw: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if key not in _VALID_KEYS or value is None:
            continue
        if key in _PATH_FIELDS:
            out[key] = Path(value).expanduser()
        elif key in _INT_FIELDS:
            out[key] = int(value)
        elif key in _FLOAT_FIELDS:
            out[key] = float(value)
        elif key in _BOOL_FIELDS:
            out[key] = _as_bool(value)
        elif key == "formats":
            out[key] = tuple(value) if not isinstance(value, str) else tuple(
                p.strip() for p in value.split(",") if p.strip()
            )
        else:
            out[key] = value
    return out


def _find_config_file(explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit if explicit.exists() else None
    for name in CONFIG_FILENAMES:
        candidate = Path.cwd() / name
        if candidate.exists():
            return candidate
    xdg = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    candidate = xdg / "yazit" / "config.toml"
    return candidate if candidate.exists() else None


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    """Return a toml table, tolerating a non-table value (e.g. ``output = "x"``)."""
    section = data.get(name, {})
    return section if isinstance(section, dict) else {}


def _from_toml(path: Path) -> dict[str, Any]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    out: dict[str, Any] = {}
    output = _section(data, "output")
    out["output_dir"] = output.get("dir")
    out["workspace_dir"] = output.get("workspace")
    out["cache_dir"] = output.get("cache")
    out["formats"] = output.get("formats")
    backend = _section(data, "backend")
    out["backend"] = backend.get("name")
    out["model"] = backend.get("model")
    out["device"] = backend.get("device")
    out["compute_type"] = backend.get("compute_type")
    out["want"] = backend.get("want")
    transcribe = _section(data, "transcribe")
    for key in (
        "language",
        "chunk_minutes",
        "beam_size",
        "vad_filter",
        "temperature",
        "word_timestamps",
    ):
        out[key] = transcribe.get(key)
    out["ui_lang"] = _section(data, "ui").get("lang")
    return {k: v for k, v in out.items() if v is not None}


_ENV_MAP = {
    "YAZIT_OUTPUT_DIR": "output_dir",
    "YAZIT_WORKSPACE_DIR": "workspace_dir",
    "YAZIT_CACHE_DIR": "cache_dir",
    "YAZIT_BACKEND": "backend",
    "YAZIT_MODEL": "model",
    "YAZIT_DEVICE": "device",
    "YAZIT_COMPUTE_TYPE": "compute_type",
    "YAZIT_WANT": "want",
    "YAZIT_LANGUAGE": "language",
    "YAZIT_CHUNK_MINUTES": "chunk_minutes",
    "YAZIT_BEAM_SIZE": "beam_size",
    "YAZIT_VAD_FILTER": "vad_filter",
    "YAZIT_LANG": "ui_lang",
}


def _from_env(env: dict[str, str]) -> dict[str, Any]:
    return {dst: env[src] for src, dst in _ENV_MAP.items() if src in env}


def load_config(
    cli: dict[str, Any] | None = None,
    *,
    config_path: Path | None = None,
    env: dict[str, str] | None = None,
) -> YazitConfig:
    """Merge the four layers (defaults < file < env < cli) into a YazitConfig.

    Any parse/coercion failure (bad toml, ``YAZIT_CHUNK_MINUTES=abc``, wrong type)
    is raised as :class:`ConfigError` so the CLI can show a clean message instead
    of a traceback.
    """
    env = dict(os.environ) if env is None else env
    merged: dict[str, Any] = {}

    try:
        found = _find_config_file(config_path)
        if found is not None:
            merged.update(_from_toml(found))
        merged.update(_from_env(env))
        if cli:
            merged.update({k: v for k, v in cli.items() if v is not None})
        config = replace(YazitConfig(), **_coerce(merged))
    except (tomllib.TOMLDecodeError, ValueError, TypeError, AttributeError) as exc:
        raise ConfigError(str(exc)) from exc

    if config.chunk_minutes < 1:
        raise ConfigError("chunk_minutes must be >= 1")
    if config.beam_size < 1:
        raise ConfigError("beam_size must be >= 1")
    return config
