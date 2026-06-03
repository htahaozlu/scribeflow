# Configuration

ScribeFlow resolves every setting from **four layers**, each overriding the one before it:

```
defaults  <  config file (scribeflow.toml)  <  environment (SCRIBEFLOW_*)  <  CLI flags
```

So a value passed on the command line always wins, an environment variable beats
the config file, and the config file beats the built-in defaults. Anything you
leave unset falls through to the next-lower layer — and several knobs left unset
mean *auto-select for the detected host* (model, backend, device, compute type).

The resolved settings become a frozen `ScribeFlowConfig`, which the CLI turns into the
engine's run config plus the backend resolution.

---

## The `ScribeFlowConfig` fields

Every field below maps 1:1 to a `scribeflow.toml` key, a `SCRIBEFLOW_*` env var, and/or a
CLI flag. `None` means *unset → auto / runtime-filled*.

| Field | Default | Meaning |
| --- | --- | --- |
| `output_dir` | `None` → `scribeflow-output` | Durable output: transcripts, exports, and resume checkpoints. On Colab this stays on Drive. |
| `workspace_dir` | `None` → `scribeflow-workspace` | Scratch: extracted audio chunks and heavy I/O. On Colab this moves to local `/content` to dodge the Errno-107 Drive-FUSE split. |
| `cache_dir` | `None` | Model download cache (passed to the backend's `download_root`). |
| `backend` | `None` → auto | `faster-whisper` (default), `whispercpp`, or `openai-whisper`. |
| `model` | `None` → auto | Model id (e.g. `large-v3-turbo`). Unset lets the policy pick per host + `want`. |
| `device` | `None` → auto | `cpu` or `cuda`. Auto-detected from the host. |
| `compute_type` | `None` → auto | e.g. `int8`, `float16`, `int8_float16`. Auto-selected from device + VRAM. |
| `want` | `default` | Quality/speed bias: `default`, `speed`, or `quality`. Steers the model auto-pick. |
| `language` | `tr` | Audio language. `auto` lets the backend detect it. |
| `chunk_minutes` | `20` | Chunk length in minutes (the resume granularity). Must be `>= 1`. |
| `beam_size` | `5` | Beam search width. Must be `>= 1`. |
| `vad_filter` | `True` | Voice-activity-detection filtering before decode. |
| `temperature` | `0.0` | Decode temperature. `0.0` is deterministic — which is what makes resume byte-stable. |
| `word_timestamps` | `False` | Emit per-word timestamps (heavier; needed for word-level exports). |
| `overwrite` | `False` | Discard any existing run for this source and start fresh. |
| `keep_audio_chunks` | `True` | Keep extracted audio chunks in the workspace after a run. |
| `formats` | `("txt",)` | Output formats. `txt` is always written; add `srt`, `vtt`, `json`. |
| `json_output` | `False` | Emit machine-readable JSON to stdout instead of the human summary. |
| `ui_lang` | `en` | Interface/message language: `en` or `tr`. (This is the UI, not the audio.) |

> Note: `ui_lang` controls the language of ScribeFlow's own messages. The **audio**
> language is `language` (CLI `--language/-l`). Don't confuse the two.

---

## Sample `scribeflow.toml`

Drop a `scribeflow.toml` (or `.scribeflow.toml`) in the directory you run from, or place a
`config.toml` under `$XDG_CONFIG_HOME/scribeflow/` (defaults to
`~/.config/scribeflow/config.toml`). All sections and keys are optional.

```toml
# scribeflow.toml — every key is optional; unset keys fall through to defaults/auto.

[output]
dir       = "scribeflow-output"        # durable: transcripts + checkpoints
workspace = "scribeflow-workspace"     # scratch: audio chunks / heavy I/O
cache     = "~/.cache/scribeflow"      # model download cache
formats   = ["txt", "srt", "vtt"] # txt is always written regardless

[backend]
name         = "faster-whisper"   # faster-whisper | whispercpp | openai-whisper
model        = "large-v3-turbo"   # omit to auto-pick for this host
device       = "cpu"              # cpu | cuda  (omit to auto-detect)
compute_type = "int8"             # omit to auto-select from device/VRAM
want         = "default"          # default | speed | quality

[transcribe]
language        = "tr"            # audio language; "auto" to detect
chunk_minutes   = 20             # resume granularity (>= 1)
beam_size       = 5              # >= 1
vad_filter      = true
temperature     = 0.0            # 0.0 = deterministic (safe resume)
word_timestamps = false

[ui]
lang = "en"                      # interface language: en | tr
```

Paths support `~` expansion. `formats` may also be written as a comma string
(`"txt,srt,vtt"`); it is split and trimmed for you.

### Section → field mapping

| TOML | Field |
| --- | --- |
| `[output] dir` / `workspace` / `cache` / `formats` | `output_dir` / `workspace_dir` / `cache_dir` / `formats` |
| `[backend] name` / `model` / `device` / `compute_type` / `want` | `backend` / `model` / `device` / `compute_type` / `want` |
| `[transcribe] language` / `chunk_minutes` / `beam_size` / `vad_filter` / `temperature` / `word_timestamps` | same-named fields |
| `[ui] lang` | `ui_lang` |

---

## Environment variables

These override the config file. Values are coerced (ints, floats, bools) just
like file/CLI values; a bad value (e.g. `SCRIBEFLOW_CHUNK_MINUTES=abc`) is reported as
a clean *config error*, never a traceback.

| Env var | Field |
| --- | --- |
| `SCRIBEFLOW_OUTPUT_DIR` | `output_dir` |
| `SCRIBEFLOW_WORKSPACE_DIR` | `workspace_dir` |
| `SCRIBEFLOW_CACHE_DIR` | `cache_dir` |
| `SCRIBEFLOW_BACKEND` | `backend` |
| `SCRIBEFLOW_MODEL` | `model` |
| `SCRIBEFLOW_DEVICE` | `device` |
| `SCRIBEFLOW_COMPUTE_TYPE` | `compute_type` |
| `SCRIBEFLOW_WANT` | `want` |
| `SCRIBEFLOW_LANGUAGE` | `language` (audio) |
| `SCRIBEFLOW_CHUNK_MINUTES` | `chunk_minutes` |
| `SCRIBEFLOW_BEAM_SIZE` | `beam_size` |
| `SCRIBEFLOW_VAD_FILTER` | `vad_filter` |
| `SCRIBEFLOW_LANG` | `ui_lang` (interface) |

Booleans accept `1`, `true`, `yes`, `on` (case-insensitive) as true; anything
else is false.

> `SCRIBEFLOW_LANG` also seeds the default interface language when no `--ui-lang` is
> passed: if it (or `LANG`) starts with `tr`, the UI defaults to Turkish.

### whisper.cpp environment variables

The whisper.cpp backend (Apple-Silicon Metal path) is located at runtime and is
**not** part of `ScribeFlowConfig`. Point it at your binary and ggml models with:

| Env var | Meaning |
| --- | --- |
| `SCRIBEFLOW_WHISPERCPP_BIN` | Path to the `whisper-cli` binary (resolution order: explicit arg → this var → `whisper-cli` / `whisper-cpp` / `main` on `PATH`). |
| `SCRIBEFLOW_WHISPERCPP_MODELS` | Directory containing ggml `.bin` model files. |

```bash
export SCRIBEFLOW_WHISPERCPP_BIN="$HOME/whisper.cpp/build/bin/whisper-cli"
export SCRIBEFLOW_WHISPERCPP_MODELS="$HOME/whisper.cpp/models"
scribeflow transcribe ./lecture.mp4 --backend whispercpp
```

If the binary or a ggml model can't be found, the backend raises a clean message
telling you to install `whisper-cli` (or set `SCRIBEFLOW_WHISPERCPP_BIN`) and to
provide a ggml `.bin` (or set `SCRIBEFLOW_WHISPERCPP_MODELS`).

---

## Model auto-select

When you leave `backend`, `model`, `device`, and `compute_type` unset, ScribeFlow
picks them for the **detected host** — biased by `want`
(`default` / `speed` / `quality`). The global default model is `large-v3-turbo`.

Run `scribeflow models` to see the catalog plus this host's auto-pick and the reason,
and `scribeflow doctor` to see device/VRAM/RAM/backend availability.

The policy in short:

- **Apple Silicon** → whisper.cpp on Metal **when its binary is available**,
  otherwise faster-whisper on CPU with `int8`. ScribeFlow never offers `cuda`/`mps`
  to faster-whisper on macOS-arm64.
- **NVIDIA CUDA** → `float16` when VRAM `>= 8 GB`, else `int8_float16`.
- **CPU** → `int8`.
- **Turkish quality guard**: the auto-pick never lands on `tiny`/`base`/`distil`
  models for Turkish — those are filtered out and replaced with
  `large-v3-turbo`.

Any explicit override (flag, env, or file) **always wins** over the auto-pick —
the policy only fills the blanks you leave.

---

## Precedence cheatsheet

```
1. defaults                 (built into ScribeFlowConfig)
2. scribeflow.toml / .scribeflow.toml (cwd) or ~/.config/scribeflow/config.toml, or --config FILE
3. SCRIBEFLOW_* environment variables
4. CLI flags (--model, --language, --format, ...)
```

Validation runs after merging: `chunk_minutes >= 1`, `beam_size >= 1`, and every
requested format must be one of `txt`, `srt`, `vtt`, `json`. Any violation, parse
error, or bad coercion surfaces as a single-line config error (exit code `5`),
not a stack trace.
