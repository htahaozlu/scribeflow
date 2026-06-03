<!--
  Logo and demo are committed SVGs under docs/images/. The demo is a static
  preview; record an animated GIF of a real run to replace docs/images/demo.svg
  whenever you like.
-->

<p align="center">
  <img src="docs/images/logo.svg" alt="ScribeFlow" width="180" />
</p>

<h1 align="center">ScribeFlow</h1>

<p align="center">
  <strong>English</strong> | <a href="README.tr.md">Türkçe</a>
</p>

<p align="center">
  <strong>Portable, resumable, multi-backend Whisper transcription — runs anywhere.</strong>
</p>

<p align="center">
  Local CPU/GPU, Apple Silicon, or Google Colab. Input from a file, folder, Google Drive,
  or URL. ScribeFlow auto-selects the right model for the hardware it finds, writes durable
  checkpoints as it goes, and resumes cleanly after a crash — no duplicated or corrupted output.
</p>

<p align="center">
  <a href="https://pypi.org/project/scribeflow/"><img alt="PyPI version" src="https://img.shields.io/pypi/v/scribeflow?style=flat-square&color=2F81F7" /></a>
  <a href="https://pypi.org/project/scribeflow/"><img alt="Python 3.10–3.12" src="https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-2F81F7?style=flat-square" /></a>
  <a href="LICENSE"><img alt="License: Apache-2.0" src="https://img.shields.io/badge/license-Apache--2.0-7DCEA0?style=flat-square" /></a>
  <a href="https://github.com/htahaozlu/scribeflow/actions"><img alt="CI status" src="https://img.shields.io/github/actions/workflow/status/htahaozlu/scribeflow/ci.yml?branch=main&style=flat-square&color=2F81F7" /></a>
  <a href="https://pypi.org/project/scribeflow/"><img alt="Downloads" src="https://img.shields.io/pypi/dm/scribeflow?style=flat-square&color=7DCEA0" /></a>
</p>

<p align="center">
  <img alt="Linux" src="https://img.shields.io/badge/Linux-supported-2F81F7?style=flat-square&logo=linux&logoColor=white" />
  <img alt="macOS" src="https://img.shields.io/badge/macOS-Apple%20Silicon-2F81F7?style=flat-square&logo=apple&logoColor=white" />
  <img alt="Google Colab" src="https://img.shields.io/badge/Google%20Colab-ready-7DCEA0?style=flat-square&logo=googlecolab&logoColor=white" />
</p>

---

## Demo

<p align="center">
  <img src="docs/images/demo.svg" alt="ScribeFlow transcribing a lecture and resuming after a crash" width="720" />
</p>

---

## Install

Base install is intentionally small — the pure-Python engine plus the default
**faster-whisper** backend, which runs on CPU out of the box:

```bash
pip install scribeflow
```

ffmpeg is the **one** required system dependency:

```bash
# macOS (Homebrew)
brew install ffmpeg

# Debian / Ubuntu
sudo apt-get install -y ffmpeg

# Fedora
sudo dnf install -y ffmpeg

# Windows (winget)
winget install Gyan.FFmpeg
```

Optional extras layer in heavier backends, the web UI, and remote sources:

```bash
pip install 'scribeflow[gpu]'      # torch + CUDA (documented, not hard-pinned)
pip install 'scribeflow[cpp]'      # whisper.cpp via pywhispercpp — Apple-Silicon Metal path
pip install 'scribeflow[openai]'   # openai-whisper (PyTorch reference baseline)
pip install 'scribeflow[web]'      # FastAPI web UI: scribeflow web
pip install 'scribeflow[url]'      # yt-dlp — transcribe straight from a URL
pip install 'scribeflow[drive]'    # Google Drive API source
pip install 'scribeflow[dev]'      # pytest + ruff + mypy + nbformat
```

From a clone (editable, with the dev toolchain):

```bash
git clone https://github.com/htahaozlu/scribeflow
cd scribeflow
pip install -e '.[dev]'
```

### Run without installing (the `npx` equivalent)

ScribeFlow is a **Python** CLI — there is no `npm`/`npx`; the equivalents are
[pipx](https://pipx.pypa.io) and [uv](https://docs.astral.sh/uv/). Once published to
PyPI:

```bash
pipx install scribeflow                 # isolated global install
uvx scribeflow transcribe lecture.mp4   # run once, no install (like npx)
```

Before the PyPI release you can run it straight from a clone:

```bash
pipx install .            # from the cloned repo
```

### Homebrew (macOS) — planned

After the first PyPI release, a tap will provide a one-liner:

```bash
brew install htahaozlu/tap/scribeflow   # planned (post-PyPI)
```

> **Note** — the `[gpu]` extra documents the torch + CUDA path but does not hard-pin
> a CUDA build, so you stay in control of the wheel that matches your driver.
> See [docs/CONFIG.md](docs/CONFIG.md) for the recommended install line.

---

## Quickstart

```bash
pip install scribeflow                       # base install (CPU-capable)

scribeflow doctor                            # check ffmpeg / device / backends
scribeflow transcribe ./lecture.mp4          # auto-selects backend + model for this host
scribeflow transcribe ./lecture.mp4 --format srt,vtt
```

That's it. The `.txt` transcript is always written; `--format` adds subtitle and
JSON outputs. If the run is interrupted, re-run the **same command** and ScribeFlow
picks up from the last completed chunk.

---

## What it does

ScribeFlow is a single tool that gives you the same transcription pipeline everywhere:

- **Runs anywhere** — local CPU or NVIDIA GPU, Apple Silicon (Metal via whisper.cpp),
  or Google Colab — and adapts to the hardware it detects.
- **Input from anywhere** — a local file or folder, a URL (yt-dlp), a mounted Google
  Drive path, or an upload through the web UI.
- **Auto-selects the model** for the detected hardware, with sensible defaults tuned
  for quality (global default: **large-v3-turbo**).
- **Crash-safe and resumable** — durable per-chunk checkpoints mean an interrupted run
  resumes from where it stopped, with no duplicated or corrupted output.
- **Honest scope** — local models only (no cloud APIs in v1); transcripts are best-effort
  ASR, not verbatim legal records.

---

## Backends & hardware

Every backend normalizes to one output shape, so you can swap them without changing
your workflow. ScribeFlow auto-selects based on the host; you can always override with
`--backend`, `--model`, `--device`, and `--compute-type`.

| Backend          | Best for                          | Install                       | Notes                                                            |
| ---------------- | --------------------------------- | ----------------------------- | ---------------------------------------------------------------- |
| `faster-whisper` | CPU and NVIDIA CUDA (the default) | base install                  | CUDA → `float16` (≥8 GB VRAM) or `int8_float16`; CPU → `int8`.    |
| `whispercpp`     | Apple Silicon — Metal GPU         | `pip install 'scribeflow[cpp]'`    | Needs a `whisper-cli` binary + a ggml model (see env vars below). |
| `openai-whisper` | PyTorch reference baseline        | `pip install 'scribeflow[openai]'` | The reference implementation; slower, useful for comparison.     |

**Hardware auto-select rules:**

- **Apple Silicon** → whisper.cpp on Metal **when its binary is available**, otherwise
  faster-whisper CPU `int8`. ScribeFlow **never** offers `cuda`/`mps` to faster-whisper on
  macOS-arm64 — that path doesn't exist, so it isn't pretended.
- **CUDA** → `float16` for ≥8 GB VRAM, otherwise `int8_float16`.
- **CPU** → `int8`.
- It **never** auto-selects `tiny`/`base`/`distil` for Turkish; the global default is
  `large-v3-turbo`.

To enable the Apple-Silicon Metal path, point ScribeFlow at your whisper.cpp binary and
ggml models:

```bash
export SCRIBEFLOW_WHISPERCPP_BIN=/path/to/whisper-cli
export SCRIBEFLOW_WHISPERCPP_MODELS=/path/to/ggml-models
```

See your host's pick at any time:

```bash
scribeflow models           # lists the catalog + this host's auto-pick
scribeflow doctor           # ffmpeg / device / VRAM / RAM / backends checklist
```

---

## Usage

```bash
scribeflow transcribe <source> [options]
scribeflow models      [--want default|speed|quality] [--json] [--ui-lang en|tr]
scribeflow doctor      [--json] [--ui-lang en|tr]
scribeflow gen-notebook <source> -o nb.ipynb [options]
scribeflow web         [--host 127.0.0.1] [--port 8000]
scribeflow --version
```

### `scribeflow transcribe`

The source is a local file/folder, a `http(s)://` URL, or a `drive:` path. The kind
is inferred from the argument; override it with `--source-kind`.

Key flags:

| Flag                                       | Purpose                                                        |
| ------------------------------------------ | -------------------------------------------------------------- |
| `--backend`                                | `faster-whisper` · `whispercpp` · `openai-whisper`             |
| `--model`                                  | Override the auto-selected model (default: `large-v3-turbo`).  |
| `--device` / `--compute-type`              | `cpu` · `cuda`; e.g. `float16`, `int8`, `int8_float16`.        |
| `--want default\|speed\|quality`           | Bias the auto-pick toward speed or quality.                   |
| `--language` / `-l`                        | Audio language (Turkish `tr` by default; `auto` to detect).   |
| `--chunk-minutes`                          | Chunk length for checkpointing (default 20).                  |
| `--beam-size`                              | Decoder beam width (Turkish default: 5).                      |
| `--format`                                 | `txt,srt,vtt,json` (comma-separated; `txt` is always written). |
| `--out`                                    | Durable output dir (transcripts + checkpoints).               |
| `--workspace`                              | Scratch dir for heavy audio-chunk I/O.                        |
| `--cache-dir`                              | Model download cache.                                         |
| `--runtime auto\|local\|colab`             | Execution target (owns the scratch-vs-durable split).         |
| `--source-kind local\|url\|drive\|upload`  | Force the source kind instead of inferring it.                |
| `--overwrite`                              | Discard any existing run and start fresh.                     |
| `--config FILE`                            | Path to a `scribeflow.toml`.                                       |
| `--json`                                   | Machine-readable JSON output.                                 |
| `--ui-lang` / `--lang en\|tr`              | Interface language (separate from `--language`).              |

Examples:

```bash
# A whole folder, Turkish, with subtitles
scribeflow transcribe ./lectures/ --format srt,vtt

# A URL (needs the [url] extra), auto-detect language, quality bias
scribeflow transcribe "https://example.com/talk.mp4" -l auto --want quality

# Force a backend/model on capable hardware
scribeflow transcribe ./talk.wav --backend faster-whisper --model large-v3 --device cuda --compute-type float16

# Split scratch vs. durable storage explicitly
scribeflow transcribe ./lecture.mp4 --out ./out --workspace /tmp/scribeflow-scratch
```

---

## Web UI

With the `[web]` extra installed, launch a small FastAPI app to upload media and
transcribe from the browser:

```bash
pip install 'scribeflow[web]'
scribeflow web                                   # http://127.0.0.1:8000
scribeflow web --host 0.0.0.0 --port 8080 --out ./out --workspace /tmp/scribeflow-scratch
```

---

## Colab

`scribeflow gen-notebook` emits a runnable `.ipynb` that mounts Drive, pip-installs ScribeFlow,
transcribes, and resumes — top-to-bottom, no editing required:

```bash
scribeflow gen-notebook ./lecture.mp4 -o scribeflow_colab.ipynb
scribeflow gen-notebook "https://example.com/talk.mp4" -o talk.ipynb        # url extra auto-wired
scribeflow gen-notebook "drive:My Drive/lectures/week1.mp4" -o week1.ipynb   # drive extra auto-wired
```

Open the notebook in Colab and run the cells in order.

**The Errno-107 split.** On Colab, a Google Drive FUSE mount can drop mid-write and
raise `OSError: [Errno 107] Transport endpoint is not connected`. ScribeFlow sidesteps this
by keeping **heavy, churny I/O** (audio chunks, temp files) on local `/content` scratch
(the `--workspace`), and writing **only durable transcripts and checkpoints** to Drive
(the `--out`). If the mount blips, your committed transcripts are already safe and the
run resumes.

---

## Output formats

The `.txt` transcript is **always** written. Add more with `--format`
(comma-separated):

| Format | Flag value | Description                                                 |
| ------ | ---------- | ----------------------------------------------------------- |
| Text   | `txt`      | Plain transcript (always produced).                         |
| SubRip | `srt`      | Subtitles with timecodes.                                   |
| WebVTT | `vtt`      | Web-native subtitles with timecodes.                        |
| JSON   | `json`     | Structured segments (text + timing) for downstream tooling. |

Subtitle timecodes are **global**: each chunk's local times are shifted by
`chunk_index * chunk_seconds`, so timing stays correct across the whole file.

```bash
scribeflow transcribe ./lecture.mp4 --format txt,srt,vtt,json
```

---

## How resume works

Resume isn't a bolt-on — it's how the engine runs.

- **Chunk-by-chunk checkpoints.** The media is split into chunks; each completed chunk
  is committed durably to `progress.json` + `chunk_outputs/`, using
  **atomic temp-then-replace** writes (never a half-written file).
- **Just re-run.** Kill the process and run the **same command** again → ScribeFlow resumes
  from the last completed chunk. No duplicated work, no corrupted output.
- **RunIdentity guard.** A resume refuses to silently mix a *different*
  backend/model/chunking/options into an existing run — it raises
  `CheckpointIdentityError`. Want a clean slate with new settings? Pass `--overwrite`.

Determinism makes this safe: Turkish defaults use `temperature=0.0`,
`condition_on_previous_text=False` (with a tail-prompt continuity hint),
`vad_filter=True`, and `beam_size=5`, so re-running a chunk reproduces the same result.

---

## Config

Configuration resolves from CLI flags → a `scribeflow.toml` → environment variables, with
sensible defaults underneath. Full reference: **[docs/CONFIG.md](docs/CONFIG.md)**.

Common environment variables:

| Variable                  | Purpose                                           |
| ------------------------- | ------------------------------------------------- |
| `SCRIBEFLOW_LANG`              | Default interface language (`en` / `tr`).         |
| `SCRIBEFLOW_WHISPERCPP_BIN`    | Path to the `whisper-cli` binary (Apple Silicon). |
| `SCRIBEFLOW_WHISPERCPP_MODELS` | Directory holding ggml models for whisper.cpp.    |
| `NO_COLOR`                | Disable ANSI colors (also auto-off when piped).   |

A project-local `scribeflow.toml` lets you pin defaults:

```toml
# scribeflow.toml
backend = "faster-whisper"
model = "large-v3-turbo"
language = "tr"
chunk_minutes = 20
beam_size = 5
formats = ["txt", "srt"]
```

```bash
scribeflow transcribe ./lecture.mp4 --config scribeflow.toml
```

---

## Contributing

Contributions are welcome — see **[CONTRIBUTING.md](CONTRIBUTING.md)** for the dev
setup, test, and lint workflow:

```bash
pip install -e '.[dev]'
pytest
ruff check .
mypy
```

---

## License

Licensed under the **Apache License 2.0** — see [LICENSE](LICENSE).
