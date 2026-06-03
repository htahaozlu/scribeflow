# Changelog

All notable changes to **ScribeFlow** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-06-03

First public release: portable, resumable, multi-backend Whisper transcription
that runs anywhere and resumes after crashes.

### Added

- **Resumable chunk engine** — chunk-by-chunk durable checkpoints
  (`progress.json` + `chunk_outputs/`) with atomic temp-then-replace writes. Kill
  the process and re-run the same command to resume from the last completed
  chunk, with no duplicated or corrupted output. A `RunIdentity` guard refuses to
  resume a run with a different backend/model/chunking/options (use `--overwrite`
  for a fresh run).
- **Multiple backends** behind one normalized shape:
  - `faster-whisper` (default; CPU and NVIDIA CUDA).
  - `whisper.cpp` (Apple-Silicon Metal path) via a `whisper-cli` binary + a ggml
    model, configured with `SCRIBEFLOW_WHISPERCPP_BIN` / `SCRIBEFLOW_WHISPERCPP_MODELS`.
  - `openai-whisper` (PyTorch reference baseline).
- **Hardware-aware model auto-select** — picks backend/model/device/compute-type
  for the detected host (Apple Silicon → whisper.cpp Metal when available, else
  faster-whisper CPU int8; CUDA → float16/int8_float16 by VRAM; CPU → int8),
  biased by `--want default|speed|quality`. Global default model
  `large-v3-turbo`; never auto-selects tiny/base/distil models for Turkish.
- **CLI** with verbs: `transcribe`, `models`, `doctor`, `gen-notebook`, and
  `web`, plus `--version`. Human and `--json` output, `--ui-lang/--lang en|tr`,
  and `NO_COLOR`-aware styling.
- **Sources**: local file/folder, `url` (yt-dlp), `drive` (mounted Google Drive
  path), and `upload` (web UI). Kind inferred from the argument or forced with
  `--source-kind`.
- **Colab notebook generator** (`scribeflow gen-notebook`) — emits a runnable
  `.ipynb` (mount Drive → pip install → transcribe → resume), with the Errno-107
  scratch-vs-durable split (heavy I/O on local `/content`, durable transcripts on
  Drive).
- **Exporters** — `.txt` transcript always written; `.srt`, `.vtt`, and `.json`
  via `--format`, with global subtitle timecodes shifted per chunk.
- **Web UI** (`scribeflow web`, `[web]` extra) — FastAPI app for uploads and runs.
- **Layered configuration** — `defaults < scribeflow.toml < SCRIBEFLOW_* env < CLI`, with
  `[output]` / `[backend]` / `[transcribe]` / `[ui]` TOML sections and clean
  config-error messages instead of tracebacks. See `docs/CONFIG.md`.
- **Turkish-tuned defaults** — `language=tr`, `vad_filter=True`, `beam_size=5`,
  `temperature=0.0` (deterministic, enabling safe resume), and a tail-prompt
  continuity hint with `condition_on_previous_text=False`.

[Unreleased]: https://github.com/htahaozlu/scribeflow/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/htahaozlu/scribeflow/releases/tag/v0.1.0
