# 06 — Implementation Roadmap (phased, with acceptance gates)

> Lowest-risk-first. Each phase has a **gate** that must pass before the next. The engine lift (P1)
> and its crash-injection tests are the foundation — do not skip ahead. Greenfield: build under a new
> directory (`scribeflow/`), `git init`, do NOT mutate the old `Film-Transcriber` tree (it's the reference).

## P0 — Scaffold
- New repo dir `scribeflow/`, `git init`, `src/scribeflow/` layout, `pyproject.toml` (hatchling), `__about__.py` name token.
- Extras declared: `[gpu] [cpp] [openai] [web] [url] [drive] [dev]`. `.gitignore` (dist, *.zip, .idea, __pycache__, media, models, .venv).
- Apache-2.0 LICENSE, empty CI workflows, `ruff`+`mypy`+`pytest` configured.
- **Gate:** `pip install -e .[dev]` works; `scribeflow --version` prints; `ruff`+`mypy` clean on empty pkg.

## P1 — Engine lift + tests (FOUNDATION — parity with proven core)
- Port `io_atomic.py`, `text.py`, `chunking.py` (+ `ChunkingSpec`, manifest w/ chunking identity),
  `artifacts.py`, `checkpoint.py` (+ `RunIdentity`), `pipeline.py` from `drive_batch_transcriber.py`.
  Behavior frozen per doc 02. Centralize atomic temp-then-`os.replace`.
- Tests: `test_text.py` (clean_transcript/tail_prompt/build_full_transcript goldens);
  `test_chunk_manifest.py` (ffmpeg segment on `fixtures/sample_5s.mp4`, reuse/invalidate);
  `test_checkpoint_crash.py` (crash-inject between steps 3↔4, 4↔7, 6↔7 — doc 02 §6 + Codex §4 test).
- **Gate:** all tests green; a `FakeDeterministicBackend` runs `run_batch` end-to-end on the sample
  and resumes correctly after each injected crash with **no duplicated/corrupted transcript**.

## P2 — Backend Protocol + faster-whisper + device/policy
- `backends/base.py` Protocol + dataclasses (doc 05 §2); `registry.py`; `faster_whisper.py`.
- `devices.py` (Colab/CUDA+VRAM/AppleSilicon/CPU detection), `model_policy.py` (doc 03 §3 table).
- Wire `pipeline.process_video` to `backend.transcribe_chunk(ChunkRequest)`; persist `RunIdentity` +
  fingerprint in progress/summary/chunk JSON; enforce identity skip-guard.
- `test_backend_normalization.py` (faster-whisper adapter returns normalized shape on sample).
- **Gate:** `run_batch` transcribes the sample via faster-whisper; auto-select picks a sane model for
  the host; identity mismatch on resume raises `CheckpointIdentityError` (not mixed output).

## P3 — Config + CLI (first usable product)
- `config.py` layered (defaults ← toml ← env ← cli). `cli.py`: `transcribe`, `models`, `doctor`.
- **Gate:** `scribeflow transcribe ./sample.mp4` produces a transcript on a clean machine with zero config;
  `scribeflow doctor` reports ffmpeg/device/VRAM/backends; `scribeflow models` shows the host's auto-pick.

## P4 — Sources + runtime targets
- `sources/`: `local` → `url` (yt-dlp) → `drive`. `runtime/`: `local` → `colab` (RuntimeDirs split:
  workspace=/content, output=Drive — Errno-107 baked in). `remote.py` = stub.
- **Gate:** `scribeflow transcribe <youtube-url>` works; Colab target writes heavy I/O local, transcripts
  to the durable dir; a forced FUSE-style failure during chunking does NOT lose committed transcripts.

## P5 — Notebook generator (kill the duplication)
- `notebook/generator.py` + `template.ipynb.j2`; `scribeflow gen-notebook`. Delete `build_colab_bundle.py`
  reliance; one parameterized template replaces the 5 copied notebooks.
- **Gate:** generated `.ipynb` opens in Colab and runs the proven flow (mount→install→transcribe→resume) on a small input.

## P6 — Additional backends
- `whispercpp.py` (subprocess + JSON normalize, binary/model validation — the **Apple-Silicon GPU path**);
  `openai_whisper.py` (reference). Register both.
- **Gate:** same sample → consistent normalized output across all 3 backends; Mac-arm64 routes default
  to whisper.cpp (Metal) and never offers cuda/mps to faster-whisper.

## P7 — Exporters
- `exporters.py`: txt (default) + srt + vtt + json from `chunk_NNN.json` segments. `--format`.
- **Gate:** `--format srt,vtt` yields valid, timecode-correct subtitle files (segment offsets account for chunk start).

## P8 — Web UI ([web] extra)
- `web/app.py` FastAPI: source pick/upload → model auto/choose → run → live progress (poll
  `progress.json` + tail `activity.log`) → download. Minimal, artful, one accent color.
- **Gate:** a non-technical user transcribes a file end-to-end in the browser; progress bar reflects real chunk completion.

## P9 — Polish, docs, release
- Bilingual `README.md` + `README.tr.md` (centered header, badges, demo GIF), governance files,
  `docs/PUBLISHING.md`/`RELEASING.md`/`CONFIG.md`, CHANGELOG.
- CI: matrix tests (Linux/macOS, py3.10–3.12) + `release.yml` + idempotent `publish.yml` (PyPI OIDC).
- **Gate:** tag `v0.1.0` → CI publishes to PyPI; `pip install scribeflow` from PyPI works on a fresh box;
  README quickstart reproduces a transcription.

## Cross-cutting rules (every phase)
- Never break a doc-02 invariant; if a change touches the checkpoint loop, add/extend a crash test first.
- Conventional Commits, **subject-only ≤72 chars, no body, no attribution, never amend** (owner rule, doc 04 §5).
- Keep base install tiny; heavy deps behind extras. Document ffmpeg as the one system dep.
- Adversarially verify each phase's gate before advancing (the workflow does this — doc 07).
