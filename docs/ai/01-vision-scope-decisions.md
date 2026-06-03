# 01 — Vision, Scope & Locked Decisions

## Product

**ScribeFlow** is a portable, resumable, multi-backend Whisper transcription tool. You point it at media
(file, folder, Drive, or URL), it detects your hardware, picks the right model, and produces clean
transcripts — surviving crashes and disconnects by resuming exactly where it stopped. Runs as a CLI
or a small local web UI; can generate a ready-to-run Colab notebook for GPU-less users.

## Target users

1. **Researchers / students** transcribing lectures, interviews, film (the origin use case; Turkish first-class).
2. **GPU-less users** who run on free Google Colab (auto-generated notebook + Drive output).
3. **Developers** who want a clean `pip install` CLI and a programmatic engine.
4. **Mac users** (Apple Silicon) — explicitly supported via the whisper.cpp backend (see doc 03 gotcha).

## LOCKED owner decisions (do not relitigate)

| # | Decision | Choice | Implication |
|---|----------|--------|-------------|
| D1 | **Interface** | **CLI + optional web UI** | Ship a strong CLI first; add a minimal FastAPI web UI behind a `[web]` extra and `scribeflow web` / `--serve`. |
| D2 | **Distribution** | **pip / PyPI** (CLI core) + optional web UI extra | `pyproject.toml`, console entry point, extras: `[gpu] [cpp] [openai] [web] [url] [drive] [dev]`. No Docker/binary required for v1. |
| D3 | **Engine scope** | **Pluggable LOCAL backends**: faster-whisper (default) + whisper.cpp + openai-whisper | Backend Protocol unifies all three (doc 05). **No cloud APIs** (Groq/OpenAI hosted) in v1 scope. |
| D4 | **Repo strategy** | **New repo, preserve the proven core** | Greenfield package; lift the engine verbatim; archive the old Colab/zip flow. New Apache-2.0 repo, context-bar conventions. |

## Aesthetic (owner: "sade ama sanatsal" — minimal but artful)

- CLI: clean, color-aware (respect `NO_COLOR`, auto-disable when piped), `--json` for machines, bilingual (`--lang en|tr`).
- Web UI: single calm page. Pick source → (auto/choose) model → run → live progress (poll `progress.json` + tail `activity.log`) → download. No clutter. Tasteful typography, generous whitespace, one accent color.
- Match context-bar's polish bar: scripted demo GIF, brand-colored flat-square badges, bilingual README.

## Non-goals (v1)

- ❌ Cloud transcription APIs (Groq/OpenAI hosted) — architecture stays pluggable so they *could* be added later, but not built now.
- ❌ Speaker diarization, translation, summarization — transcription only.
- ❌ Real-time/streaming microphone capture — batch files only.
- ❌ Heavy desktop app (Tauri/Electron) — web UI covers the GUI need portably.
- ❌ Windows-specific installers — pip works; CI may still build wheels.

## Hard constraints carried from production experience

1. **Resumability is non-negotiable.** Every chunk must be durably checkpointed so a killed Colab
   session / closed laptop loses at most the in-flight chunk. This is the product's spine (doc 02).
2. **The Drive Errno-107 lesson.** Heavy I/O (zip/extract/audio chunks) must NOT go through the
   Google Drive FUSE mount — it drops under load (`OSError 107 Transport endpoint is not connected`).
   Heavy I/O → local scratch (`workspace_dir`); only small transcript checkpoints → durable Drive
   (`output_dir`). The engine already separates these; the Drive source/target MUST default to this split.
3. **Apple Silicon has no faster-whisper GPU path.** Never offer `cuda`/`mps` to faster-whisper on
   macOS-arm64; route Mac-GPU users to whisper.cpp (Metal). Detection must enforce this (doc 03).
4. **Turkish quality defaults.** `language` pinnable, `vad_filter=True`, `beam_size=5`,
   never auto-select an English-only `distil-*` model (doc 03).

## Success criteria (v1 "done")

- `pip install scribeflow && scribeflow transcribe ./video.mp4` works on Linux/macOS/Colab with zero config.
- Auto-selected model matches detected hardware; `--model`/`--backend` override always wins.
- Kill the process mid-run, re-run the same command → resumes, no duplicated or corrupted output (covered by a crash-injection test).
- `scribeflow gen-notebook --source drive --input <folder>` emits a runnable Colab `.ipynb` that mirrors the proven flow.
- `scribeflow web` serves the UI; a non-technical user transcribes a file end-to-end without the terminal.
- Outputs: `.txt` always; `.srt`/`.vtt`/`.json` on request (segment data already captured per chunk).
- Apache-2.0, bilingual README, CI publishes to PyPI on a SemVer tag.
