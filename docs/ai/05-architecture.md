# 05 — Architecture (Backend Protocol, Seams, RunIdentity)

> Incorporates the Codex architecture review. Principle: **preserve the proven chunk-level
> checkpoint loop verbatim; make ONLY the backend / source / runtime seams pluggable.** The
> pipeline owns all checkpoint files; adapters normalize data and never touch disk state.

## 1. Package layout (`src/yazit/`)

```
src/yazit/
  __about__.py                 # APP_NAME="Yazıt", __version__, slug="yazit"  (single name token)
  engine/                      # PORTED from drive_batch_transcriber.py — behavior frozen (doc 02)
    types.py                   # all dataclasses below (§2) — the shared vocabulary
    io_atomic.py               # read_json, write_json, write_text, append_log, timestamp, format_seconds
    text.py                    # clean_transcript, tail_prompt, build_full_transcript  (was cleaning.py)
    chunking.py                # Chunker, ChunkingSpec, ensure_ffmpeg, probe_duration, prepare_audio_chunks, manifest
    checkpoint.py              # RunIdentity, skip-guard, progress/summary read+write, identity validation
    artifacts.py               # writes chunk_NNN.txt/json, rebuilds transcript (the ONLY writer of checkpoint state)
    pipeline.py                # process_video, run_batch — backend + source injected
    exporters.py               # txt / srt / vtt / json from chunk_NNN.json segments
  backends/
    base.py                    # TranscriptionBackend Protocol (§2)
    registry.py                # name -> backend factory; resolves availability/extras
    faster_whisper.py          # default
    whispercpp.py              # subprocess + JSON parse — Apple-Silicon GPU path
    openai_whisper.py          # reference / fallback
  devices.py                   # detection (doc 03 §4)
  model_policy.py              # (device, vram, ram, want, override) -> (model, compute_type)
  sources/
    base.py                    # SourceAdapter Protocol (§4)
    local.py upload.py drive.py url.py
  runtime/                     # was targets/ — decides RuntimeDirs + bootstrap + device policy
    base.py local.py colab.py
    remote.py                  # DEFERRED: interface stub only (v1 cut)
  config.py                    # layered: defaults <- file(toml/yaml) <- env <- cli/ui -> BatchConfig
  cli.py                       # `yazit transcribe|models|doctor|gen-notebook|web`
  notebook/
    generator.py               # generate_colab_notebook(config) -> .ipynb (replaces build_colab_bundle.py)
    template.ipynb.j2
  web/
    app.py static/             # optional [web] extra — FastAPI; wraps the SAME pipeline
tests/
  test_text.py test_checkpoint_crash.py test_chunk_manifest.py test_backend_normalization.py
  fixtures/sample_5s.mp4
```

## 2. Backend Protocol (the unifying seam) — from Codex memo

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping, Protocol

@dataclass(frozen=True)
class TranscriptSegment:
    start: float        # chunk-relative seconds
    end: float
    text: str

@dataclass(frozen=True)
class TranscribeOptions:
    language: str = "tr"
    task: Literal["transcribe"] = "transcribe"
    beam_size: int = 5
    temperature: float = 0.0           # determinism — see doc 02 invariant 5
    initial_prompt: str | None = None  # from tail_prompt(previous chunk)
    vad_filter: bool = True
    word_timestamps: bool = False

@dataclass(frozen=True)
class ChunkRequest:
    audio_path: Path
    chunk_index: int
    chunk_name: str
    options: TranscribeOptions

@dataclass(frozen=True)
class BackendFingerprint:
    backend: str               # "faster-whisper" | "whispercpp" | "openai-whisper"
    model: str
    version: str | None
    device: str | None
    compute_type: str | None
    extra: Mapping[str, Any]

@dataclass(frozen=True)
class TranscriptionResult:
    text: str                          # raw joined segment text (cleaning happens in pipeline)
    segments: tuple[TranscriptSegment, ...]
    language: str
    duration: float
    fingerprint: BackendFingerprint

class TranscriptionBackend(Protocol):
    @property
    def fingerprint(self) -> BackendFingerprint: ...
    def transcribe_chunk(self, request: ChunkRequest) -> TranscriptionResult: ...
```

**Adapter rule (hard):** adapters normalize backend output ONLY. They must **never** write
`chunk_NNN.txt`, `chunk_NNN.json`, `progress.json`, or `summary.json`. The pipeline (`artifacts.py`)
owns all checkpoint state. `clean_transcript` runs in the pipeline on `result.text`, so raw segment
text is preserved in JSON while the transcript uses cleaned text (store **both**: raw in chunk JSON,
cleaned in chunk txt + final transcript).

Adapter essence per engine (full sketches in the Codex memo / repo):
- **faster-whisper** → `model.transcribe()` returns `(segments_iter, info)`; map `s.start/.end/.text`, `info.language/.duration`. `condition_on_previous_text=False`.
- **openai-whisper** → returns `dict{'segments':[{start,end,text}], 'language', 'text'}`; map directly; `fp16=(device=="cuda")`.
- **whisper.cpp** → run binary via `subprocess` with `-oj -of <prefix>` → read `<prefix>.json` → normalize ms→seconds. `--no-context`, `--prompt`. Validate binary + model file at construction.

`pipeline.process_video` changes ONLY at the transcribe call: replace the inlined
`model.transcribe(...)` with `backend.transcribe_chunk(ChunkRequest(...))` and consume the
normalized `TranscriptionResult`. Everything else (ordering, atomic writes, skip guard, transcript
rebuild) stays byte-for-byte (doc 02 §4–5).

## 3. Chunking stays backend-agnostic

Chunk = the **resumability unit**, not a backend optimization. whisper.cpp / openai-whisper do their
own internal windowing, but those windows are not durable checkpoints — ignore them; keep the 20-min
ffmpeg segments.

```python
@dataclass(frozen=True)
class ChunkingSpec:
    chunk_seconds: int = 20 * 60
    sample_rate: int = 16_000
    channels: int = 1
    codec: str = "pcm_s16le"

@dataclass(frozen=True)
class AudioChunk:
    index: int; path: Path; name: str; start_seconds: float; duration_seconds: float

class Chunker(Protocol):
    def prepare(self, media_path: Path, chunks_dir: Path, spec: ChunkingSpec) -> tuple[AudioChunk, ...]: ...
```

- **No overlap in v1** (overlap → duplicate-removal complexity, weakens "transcript = ordered chunk concat" invariant).
- **Strengthen the manifest identity:** include `ChunkingSpec` + ffmpeg arg/version alongside the existing `video_signature {name,size_bytes,mtime}`. Changing chunk length must invalidate cached WAVs.

## 4. Source contract — resolve to local files (not streaming)

The proven engine assumes local `Path`s (ffmpeg, `media_duration_seconds`, `prepare_audio_chunks`).
Sources materialize media locally, then the engine runs unchanged.

```python
@dataclass(frozen=True)
class FileSignature:
    name: str; size_bytes: int; mtime: int; sha256: str | None = None  # sha256 for copied/downloaded

@dataclass(frozen=True)
class SourceSpec:
    kind: Literal["local", "upload", "drive", "url"]; uri: str

@dataclass(frozen=True)
class ResolvedMedia:
    local_path: Path; display_name: str; source_id: str; origin_uri: str; signature: FileSignature

@dataclass(frozen=True)
class RuntimeDirs:
    workspace_dir: Path   # SCRATCH / heavy I/O: downloads, audio chunks, temp whisper.cpp JSON
    output_dir: Path      # DURABLE: chunk_outputs/, transcript, progress.json, summary.json
    cache_dir: Path       # model downloads

class SourceAdapter(Protocol):
    def resolve(self, spec: SourceSpec, dirs: RuntimeDirs) -> tuple[ResolvedMedia, ...]: ...
```

- `SourceAdapter` writes downloads/copies into `dirs.workspace_dir`; `local.py` returns paths as-is.
- **The Drive Errno-107 split is a RUNTIME/CONFIG concern, NOT a source concern.** `RuntimeTarget`
  chooses `RuntimeDirs`: Colab maps `workspace_dir=/content/...` (local scratch) and
  `output_dir=/content/drive/MyDrive/...` (durable). Sources never decide durability.
- `url.py` uses `yt-dlp`; `drive.py` supports mount (Colab) or Drive API (local) — both land files in `workspace_dir`.

## 5. RunIdentity — the correctness fix (prevents silent cross-run corruption)

Biggest risk Codex flagged: **checkpoint identity drift.** Because the transcript is rebuilt from
disk, resuming with a *different* backend/model/chunking/options could silently mix outputs. Fix:
persist run identity and validate it on resume.

```python
@dataclass(frozen=True)
class RunIdentity:
    source: FileSignature
    chunking: ChunkingSpec
    backend: BackendFingerprint
    options: TranscribeOptions
```

- Persist `RunIdentity` in `progress.json`, `summary.json`, and each `chunk_NNN.json`.
- **Strengthened skip guard** (extends doc 02 §3 dual-condition):
  ```python
  if (index in completed_chunks
          and chunk_text_path.exists()
          and chunk_json_path.exists()
          and stored_identity_matches(chunk_json, current_run_identity)):
      continue
  ```
- On identity mismatch at resume: raise `CheckpointIdentityError` (do NOT mix). Require `--overwrite`
  to start a fresh run with new identity. This preserves resume safety while making backend/model
  swaps explicit and safe.
- Keep all atomic-write ordering from doc 02 §4 exactly; centralize temp-then-`os.replace` in `io_atomic`.

## 6. Device + policy wiring

`devices.choose_device_and_compute()` (doc 03 §4) → `model_policy.choose_model(device, vram, ram,
want, override)`. Apple-Silicon + default backend → prefer `whispercpp` if available (Metal),
else faster-whisper CPU int8 with a warning. `--model/--backend/--compute-type` always win.

## 7. Notebook generator (replaces 5 hand-copied notebooks + build_colab_bundle.py)

`notebook/generator.py: generate_colab_notebook(config) -> Path(.ipynb)` renders `template.ipynb.j2`
into cells: (1) `drive.mount(force_remount=True)`, (2) config (BUNDLE/SOURCE + `workspace_dir` local
`/content`, `output_dir` Drive — the Errno-107 split baked in), (3) `pip install yazit[...]`,
(4) run `yazit transcribe`/`run_batch`. One template, parameterized — no per-set duplication.

## 8. CLI surface (D1)

```
yazit transcribe <source> [--backend ...] [--model ...] [--compute-type ...]
                 [--lang tr] [--chunk-minutes 20] [--out DIR] [--workspace DIR]
                 [--format txt,srt,vtt,json] [--overwrite] [--json]
yazit models            # list models + show auto-selection for THIS machine
yazit doctor            # ffmpeg? device? VRAM/RAM? backend availability? -> checklist
yazit gen-notebook <source> [--drive] [-o nb.ipynb]
yazit web [--host --port]   # [web] extra
```
Respect `NO_COLOR`, auto-disable color when piped, `--json` machine output, `--lang en|tr`.

> Implementation notes (kept honest vs the roadmap):
> - **Audio language is `--language`/`-l`**; **interface language is `--ui-lang`/`--lang en|tr`**
>   (the spec token `--lang` was overloaded above; the CLI splits the two and accepts `--lang`
>   as the UI-language alias).
> - **`--format` and the txt/srt/vtt/json exporters land in P7** (docs/ai/06). Until then
>   `transcribe` always writes the `.txt` transcript; the `formats` config key is inert.
> - `gen-notebook` (P5) and `web` (P8) are added in their phases.

## 9. Web UI (D1, optional [web] extra)

FastAPI wrapping the SAME pipeline. One calm page: pick/upload source → auto-or-choose model
(show `yazit models` result) → start → **live progress by polling `progress.json` + tailing
`activity.log`** (the checkpoint files are purpose-built for this) → download txt/srt/vtt. No
business logic in the UI; it only drives `run_batch` and reads checkpoint files.

## 10. v1 cuts (Codex)

Defer: `runtime/remote.py` (stub only), deep web UI, streaming sources, cross-backend checkpoint
migration (reject identity change unless `--overwrite`), word timestamps, diarization, overlap
stitching, translation, cloud APIs. Keep their seams so they slot in later.
