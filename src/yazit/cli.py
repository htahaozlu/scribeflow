"""Command-line entry point for Yazıt (docs/ai/05 §8).

Verbs: ``transcribe`` · ``models`` · ``doctor`` (``gen-notebook`` and ``web`` are
added in later phases). Respects ``NO_COLOR`` and auto-disables color when piped,
``--json`` emits machine output, and ``--ui-lang en|tr`` switches message language.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any, TextIO

from yazit.__about__ import APP_NAME, SLUG, __version__
from yazit.backends import registry
from yazit.config import ConfigError, YazitConfig, load_config
from yazit.devices import detect_host
from yazit.engine.chunking import ensure_ffmpeg, ffmpeg_version
from yazit.engine.pipeline import EngineConfig, run_batch
from yazit.engine.types import ChunkingSpec, RuntimeDirs, SourceSpec, TranscribeOptions
from yazit.model_policy import MODEL_CATALOG, ModelResolution, auto_select
from yazit.runtime.base import resolve_runtime
from yazit.sources.base import infer_kind, resolve_source

# --------------------------------------------------------------------------- #
# Tiny i18n + color helpers (no dependencies; "sade ama sanatsal")
# --------------------------------------------------------------------------- #

MESSAGES: dict[str, dict[str, str]] = {
    "no_media": {"en": "No media found at: {path}", "tr": "Medya bulunamadı: {path}"},
    "transcribing": {
        "en": "Transcribing {n} file(s) — {backend} / {model} on {device} ({compute})",
        "tr": "{n} dosya deşifre ediliyor — {backend} / {model}, {device} ({compute})",
    },
    "done": {"en": "Done. Output in {out}", "tr": "Bitti. Çıktı: {out}"},
    "backend_unavailable": {
        "en": "Backend '{backend}' is unavailable. Install it: pip install 'yazit[{extra}]'",
        "tr": "'{backend}' arka ucu yok. Kur: pip install 'yazit[{extra}]'",
    },
    "ffmpeg_missing": {
        "en": "ffmpeg not found — it is the one required system dependency.",
        "tr": "ffmpeg yok — tek zorunlu sistem bağımlılığı.",
    },
}


def t(key: str, lang: str, **kw: Any) -> str:
    template = MESSAGES[key].get(lang, MESSAGES[key]["en"])
    return template.format(**kw)


class Style:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def _c(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def bold(self, s: str) -> str:
        return self._c("1", s)

    def dim(self, s: str) -> str:
        return self._c("2", s)

    def green(self, s: str) -> str:
        return self._c("32", s)

    def red(self, s: str) -> str:
        return self._c("31", s)

    def yellow(self, s: str) -> str:
        return self._c("33", s)

    def cyan(self, s: str) -> str:
        return self._c("36", s)


def make_style(stream: TextIO) -> Style:
    enabled = not os.environ.get("NO_COLOR") and hasattr(stream, "isatty") and stream.isatty()
    return Style(enabled)


# --------------------------------------------------------------------------- #
# Shared resolution
# --------------------------------------------------------------------------- #


def _resolve(cfg: YazitConfig) -> ModelResolution:
    return auto_select(
        want=cfg.want,  # type: ignore[arg-type]
        backend=cfg.backend,
        model=cfg.model,
        device=cfg.device,
        compute_type=cfg.compute_type,
    )


def _engine_config(cfg: YazitConfig, dirs: RuntimeDirs) -> EngineConfig:
    return EngineConfig(
        output_dir=dirs.output_dir,
        workspace_dir=dirs.workspace_dir,
        chunking=ChunkingSpec(chunk_seconds=cfg.chunk_minutes * 60),
        options=TranscribeOptions(
            language=cfg.language,
            beam_size=cfg.beam_size,
            vad_filter=cfg.vad_filter,
            temperature=cfg.temperature,
            word_timestamps=cfg.word_timestamps,
        ),
        overwrite=cfg.overwrite,
        keep_audio_chunks=cfg.keep_audio_chunks,
    )


# --------------------------------------------------------------------------- #
# Verbs
# --------------------------------------------------------------------------- #


def cmd_transcribe(args: argparse.Namespace) -> int:
    cfg = load_config(
        {
            "output_dir": args.out,
            "workspace_dir": args.workspace,
            "cache_dir": args.cache_dir,
            "backend": args.backend,
            "model": args.model,
            "device": args.device,
            "compute_type": args.compute_type,
            "want": args.want,
            "language": args.language,
            "chunk_minutes": args.chunk_minutes,
            "beam_size": args.beam_size,
            "overwrite": args.overwrite,
            "json_output": args.json,
            "ui_lang": args.ui_lang,
        },
        config_path=Path(args.config) if args.config else None,
    )
    style = make_style(sys.stdout)
    lang = cfg.ui_lang

    try:
        ensure_ffmpeg()
    except RuntimeError:
        print(style.red(t("ffmpeg_missing", lang)), file=sys.stderr)
        return 4

    # The runtime target owns the scratch-vs-durable split (Errno-107).
    runtime = resolve_runtime(args.runtime)
    dirs = runtime.resolve_dirs(cfg.output_dir, cfg.workspace_dir, cfg.cache_dir)
    runtime.bootstrap()

    kind = args.source_kind or infer_kind(args.source)
    spec = SourceSpec(kind=kind, uri=args.source)  # type: ignore[arg-type]
    try:
        media = resolve_source(spec, dirs)
    except FileNotFoundError:
        print(style.red(t("no_media", lang, path=args.source)), file=sys.stderr)
        return 2
    except (RuntimeError, NotImplementedError) as exc:
        print(style.red(str(exc)), file=sys.stderr)
        return 6
    media_paths = [m.local_path for m in media]
    if not media_paths:
        print(style.red(t("no_media", lang, path=args.source)), file=sys.stderr)
        return 2

    res = _resolve(cfg)
    if not registry.is_available(res.backend):
        backend_spec = registry.KNOWN_BACKENDS.get(res.backend)
        extra = backend_spec.extra if backend_spec and backend_spec.extra else "?"
        print(
            style.red(t("backend_unavailable", lang, backend=res.backend, extra=extra)),
            file=sys.stderr,
        )
        return 3
    try:
        backend = registry.create_backend(
            res.backend,
            model=res.model,
            device=res.device,
            compute_type=res.compute_type,
            download_root=str(dirs.cache_dir),
        )
    except NotImplementedError as exc:
        print(style.red(str(exc)), file=sys.stderr)
        return 3

    if not cfg.json_output:
        print(
            style.cyan(
                t(
                    "transcribing",
                    lang,
                    n=len(media_paths),
                    backend=res.backend,
                    model=res.model,
                    device=res.device,
                    compute=res.compute_type,
                )
            )
        )

    try:
        summary = run_batch(_engine_config(cfg, dirs), backend, media_paths)
    except (RuntimeError, OSError) as exc:
        # ffmpeg failure, model load/download error, FUSE drop, etc. — a clean
        # message, never a traceback (committed transcripts are already durable).
        print(style.red(f"transcription failed: {exc}"), file=sys.stderr)
        return 7

    if cfg.json_output:
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    else:
        print(style.green(t("done", lang, out=dirs.output_dir)))
        for video in summary.get("videos", []):
            transcript = video.get("transcript_path")
            if transcript:
                print(f"  {style.dim('•')} {video.get('video_name')} → {transcript}")
    return 0


def cmd_models(args: argparse.Namespace) -> int:
    cfg = load_config({"json_output": args.json, "ui_lang": args.ui_lang, "want": args.want})
    style = make_style(sys.stdout)
    host = detect_host()
    res = auto_select(want=cfg.want)  # type: ignore[arg-type]

    if cfg.json_output:
        print(
            json.dumps(
                {"host": asdict(host), "auto_select": asdict(res), "catalog": MODEL_CATALOG},
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
        return 0

    print(style.bold(f"{APP_NAME} — models for this host"))
    print(
        style.dim(
            f"  device={host.device} compute={host.compute_type} "
            f"cuda={'yes' if host.has_cuda else 'no'} "
            f"vram={host.vram_gb}GB ram={host.ram_gb}GB cores={host.cpu_cores}"
        )
    )
    print(
        f"  {style.green('auto-pick')}: {style.bold(res.backend + ' / ' + res.model)} "
        f"({res.device}/{res.compute_type})"
    )
    print(style.dim(f"  reason: {res.reason}"))
    print()
    print(style.bold(f"  {'model':<18}{'params':<9}{'turkish':<14}note"))
    for name, info in MODEL_CATALOG.items():
        marker = style.green("→ ") if name == res.model else "  "
        print(f"  {marker}{name:<16}{info['params']:<9}{info['turkish']:<14}{info['note']}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    cfg = load_config({"json_output": args.json, "ui_lang": args.ui_lang})
    style = make_style(sys.stdout)
    host = detect_host()

    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")
    backends = {name: registry.is_available(name) for name in registry.KNOWN_BACKENDS}

    checks: list[tuple[str, bool, str]] = [
        ("ffmpeg", bool(ffmpeg_path), ffmpeg_version() if ffmpeg_path else "not found"),
        ("ffprobe", bool(ffprobe_path), ffprobe_path or "not found"),
        ("device", True, f"{host.device} / {host.compute_type}"),
        ("cuda", host.has_cuda, f"{host.vram_gb} GB VRAM" if host.has_cuda else "not present"),
        ("cpu/ram", host.ram_gb > 0, f"{host.cpu_cores} cores, {host.ram_gb} GB RAM"),
        ("colab", host.is_colab, "yes" if host.is_colab else "no"),
        ("apple-silicon", host.is_apple_silicon, "yes" if host.is_apple_silicon else "no"),
    ]
    for name, spec in registry.KNOWN_BACKENDS.items():
        available = backends[name]
        if available:
            detail = "available"
        elif spec.extra:
            detail = f"missing (pip install 'yazit[{spec.extra}]')"
        else:
            detail = "missing"
        checks.append((f"backend:{name}", available, detail))

    ok = bool(ffmpeg_path) and any(backends.values())

    if cfg.json_output:
        print(
            json.dumps(
                {
                    "ok": ok,
                    "host": asdict(host),
                    "checks": [{"name": n, "ok": p, "detail": d} for n, p, d in checks],
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
        return 0 if ok else 1

    print(style.bold(f"{APP_NAME} doctor"))
    for name, passed, detail in checks:
        mark = style.green("✓") if passed else style.yellow("•")
        print(f"  {mark} {name:<20} {style.dim(detail)}")
    verdict = style.green("ready") if ok else style.red("not ready (need ffmpeg + a backend)")
    print(f"\n  {style.bold('status')}: {verdict}")
    return 0 if ok else 1


# --------------------------------------------------------------------------- #
# Parser + dispatch
# --------------------------------------------------------------------------- #


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="machine-readable JSON output")
    parser.add_argument(
        "--ui-lang",
        "--lang",
        dest="ui_lang",
        choices=["en", "tr"],
        default=None,
        help="interface language (audio language is --language/-l)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=SLUG,
        description=f"{APP_NAME} — portable, resumable, multi-backend transcription.",
    )
    parser.add_argument("--version", action="version", version=f"{SLUG} {__version__}")
    sub = parser.add_subparsers(dest="command")

    tr = sub.add_parser("transcribe", help="transcribe a file or folder")
    tr.add_argument("source", help="local media file or folder")
    tr.add_argument("--backend", default=None, help="faster-whisper | whispercpp | openai-whisper")
    tr.add_argument("--model", default=None, help="override the auto-selected model")
    tr.add_argument("--device", default=None, help="cpu | cuda")
    tr.add_argument("--compute-type", dest="compute_type", default=None)
    tr.add_argument("--want", choices=["default", "speed", "quality"], default=None)
    tr.add_argument(
        "--language", "-l", default=None, help="audio language (tr default; 'auto' to detect)"
    )
    tr.add_argument("--chunk-minutes", dest="chunk_minutes", type=int, default=None)
    tr.add_argument("--beam-size", dest="beam_size", type=int, default=None)
    tr.add_argument("--out", default=None, help="durable output dir (transcripts + checkpoints)")
    tr.add_argument("--workspace", default=None, help="scratch dir (audio chunks; heavy I/O)")
    tr.add_argument("--cache-dir", dest="cache_dir", default=None, help="model download cache")
    tr.add_argument(
        "--runtime", choices=["auto", "local", "colab"], default=None, help="execution target"
    )
    tr.add_argument(
        "--source-kind",
        dest="source_kind",
        choices=["local", "url", "drive", "upload"],
        default=None,
        help="override source kind (else inferred from the argument)",
    )
    tr.add_argument(
        "--overwrite", action="store_true", help="discard any existing run and start fresh"
    )
    tr.add_argument("--config", default=None, help="path to a yazit.toml")
    _add_common(tr)
    tr.set_defaults(func=cmd_transcribe)

    md = sub.add_parser("models", help="list models + show this host's auto-pick")
    md.add_argument("--want", choices=["default", "speed", "quality"], default=None)
    _add_common(md)
    md.set_defaults(func=cmd_models)

    dc = sub.add_parser("doctor", help="check ffmpeg / device / backends")
    _add_common(dc)
    dc.set_defaults(func=cmd_doctor)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    # Default ui-lang from env/locale if not given.
    if getattr(args, "ui_lang", None) is None:
        env_lang = os.environ.get("YAZIT_LANG") or os.environ.get("LANG", "")
        args.ui_lang = "tr" if env_lang.lower().startswith("tr") else "en"
    try:
        return int(args.func(args))
    except ConfigError as exc:
        style = make_style(sys.stderr)
        print(style.red(f"config error: {exc}"), file=sys.stderr)
        return 5


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
