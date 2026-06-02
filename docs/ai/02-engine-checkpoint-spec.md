# 02 — Engine & Checkpoint Spec (THE CROWN JEWEL — port verbatim)

> Source of truth: `colab_runtime/drive_batch_transcriber.py` in the current repo. This document
> freezes its behavior so the rewrite **preserves it exactly**. Do not redesign the checkpoint
> mechanism. Lift the functions, parameterize the seams (model backend, directory roots, video
> discovery), and lock the invariants with tests.

## 0. Why this is the spine

The engine is already **environment-agnostic**. A grep for `drive|colab|/content|MyDrive` inside it
returns only two *cosmetic* hits (an ffmpeg error string, an argparse description). Zero functional
coupling to Colab/Drive. The redesign is **lift-and-shelter**, not rewrite.

## 1. Reusable functions (port as-is, regroup into modules)

### `engine/io_atomic.py` — crash-safety primitives
- `timestamp() -> str` — UTC ISO-8601 `…Z`.
- `format_seconds(seconds: float) -> str` — `HH:MM:SS`.
- `read_json(path, default) -> Any` — returns `default` if missing. Underpins resume.
- `write_json(path, data) -> None` — **atomic**: `mkdir -p` → write `path.suffix + '.tmp'` → `os.replace(tmp, path)`.
- `write_text(path, content) -> None` — same atomic temp-then-replace.
- `append_log(path, msg) -> None` — timestamped append + `print(..., flush=True)` mirror.

### `engine/cleaning.py` — domain text logic (pure, no I/O)
- `clean_transcript(text) -> str` — anti-hallucination dedup: drop <3-word sentences; strip non-`\w\s.,!?-`; suppress repeated 5-gram phrases (sliding window of 10); collapse repeated whole sentences (>1) and repeated consecutive words (>2). **This is the canonical copy** (the twin in old `main.py` is identical — delete that one).
- `tail_prompt(texts, max_chars=350) -> str | None` — builds `initial_prompt` continuity hint from the tail of the previous chunk (enables cross-chunk coherence without `condition_on_previous_text` hallucination risk).
- `build_full_transcript(chunks_text_dir) -> str` — reassembles `chunk_*.txt` in sorted order. **Idempotent** — recomputed from disk on every chunk, self-heals on resume.

### `engine/chunking.py` — ffmpeg audio segmentation (keep; better than moviepy)
- `VIDEO_EXTENSIONS` set; `discover_videos(input_dir) -> list[Path]` (sorted `rglob`).
- `ensure_ffmpeg()`, `media_duration_seconds(path)` (via `ffprobe`), `video_signature(path) -> {name,size_bytes,mtime}`.
- `prepare_audio_chunks(video_path, chunks_dir, chunk_minutes, log_path) -> list[Path]` — ffmpeg
  `-f segment -segment_time N -ac 1 -ar 16000 -c:a pcm_s16le chunk_%03d.wav`. Chunk-level resume cache (see §3 Layer A).

### `engine/pipeline.py` — orchestration (keep core; extract 2 seams)
- `BatchConfig` dataclass — full job config.
- `process_video(model, config, video_path, batch_log_path) -> dict` — single-video resumable loop (§4).
- `run_batch(config) -> dict` — discover → detect device → **load model once** → loop `process_video`, maintaining `batch_summary.json`.
- **Two seams to extract:** (a) video discovery (→ Source adapters), (b) the inline
  `WhisperModel(model_name, device, compute_type)` construction (→ Backend Protocol, doc 05). Note
  `process_video` *already* takes `model` as a parameter — it is nearly backend-agnostic; just
  formalize what it reads: `segment.start/.end/.text`, `info.language`, `info.duration`.

## 2. On-disk layout (per video)

```
<output_dir>/<video_stem>/
  progress.json                 # live resume state — SOURCE OF TRUTH for resume
  summary.json                  # human-facing snapshot (mirrors progress + extras)
  activity.log                  # append-only timestamped log
  <video_stem>_transcript.txt   # rebuilt after EVERY chunk (derived, never appended)
  chunk_outputs/
    chunk_000.txt               # cleaned text for chunk 0
    chunk_000.json              # {chunk_index, chunk_name, segments[{start,end,text}], transcript, language, duration, created_at}
    chunk_001.txt / .json ...
<workspace_dir>/<video_stem>/audio_chunks/
  manifest.json                 # chunk cache key + completion flag
  chunk_000.wav ...
```

`<output_dir>` is **durable** (transcripts/checkpoints — small writes, safe over Drive FUSE).
`<workspace_dir>` is **scratch** (audio WAVs — heavy writes, must be local; regenerable). Keep them
separate; the runtime target decides where each lives (doc 05).

## 3. Two independent checkpoint layers

### Layer A — audio-chunk cache (`prepare_audio_chunks`)
`manifest.json = {video_signature, completed: bool, chunk_minutes, chunks: [names]}`.
On entry: **reuse existing WAVs iff** `manifest.video_signature == current_signature` AND
`completed == True` AND every listed chunk file exists. Otherwise `rmtree` and regenerate.
`completed: True` is written **only after** ffmpeg succeeds and chunks are confirmed present.

> **Invariant A:** chunk reuse requires a *completed* manifest whose signature matches the current
> file AND whose every listed chunk physically exists. A crash mid-ffmpeg leaves `completed` unset →
> next run safely regenerates.

### Layer B — transcription progress (`process_video`)
`progress.json` holds `completed_chunks: [int]`, `total_chunks`, `last_completed_chunk`,
`status: running|completed`. Whole-video skip: if `status == completed` AND transcript exists AND
not overwriting → skip. Per-chunk skip guard:

```python
if index in completed_chunks and chunk_text_path.exists():
    continue   # BOTH the JSON record AND the on-disk artifact must agree
```

## 4. The per-chunk commit sequence (the heart — exact order, do not reorder)

For each chunk `index`:
1. Compute `initial_prompt` from previous chunk's `.txt` tail (`tail_prompt`).
2. `model.transcribe(...)` with `vad_filter=True`, `condition_on_previous_text=False`,
   `temperature=0.0`, fixed `beam_size`. (See doc 03 for Turkish tuning — flags may be exposed but
   defaults stay determinism-friendly.)
3. `write_text(chunk_text_path, cleaned + "\n")` — **atomic**.
4. `write_json(chunk_json_path, {... segments ...})` — **atomic**.
5. `completed_chunks.add(index)` — in memory.
6. Rebuild `transcript_path` from **all** on-disk chunk txts → atomic write.
7. `write_json(progress_path, {... completed_chunks: sorted(...), status ...})`.
8. `write_json(summary_path, {...})`.

## 5. Invariants that make it crash-safe (these are the spec — test them)

1. **Atomic writes everywhere.** temp-then-`os.replace` (atomic on POSIX & Windows). Readers never
   see a half-written file; a crash mid-write leaves the *previous* valid version intact.
2. **Artifact-before-bookkeeping ordering.** Chunk `.txt`/`.json` (steps 3–4) commit *before*
   `progress.json` records the index (step 7). `progress.json` can only ever claim a chunk that
   physically exists. The reverse (artifact exists, progress doesn't) is harmless — the dual guard
   re-does that chunk, overwriting deterministically.
3. **Dual-condition skip guard.** Never trust `progress.json` alone; the file must also exist on disk.
   This makes a torn/stale `progress.json` non-fatal.
4. **Transcript is derived, never appended.** Rebuilt from disk every chunk → partial/duplicate runs
   self-heal; final file is always exactly the sorted concatenation of existing chunk txts.
5. **Determinism enables safe re-do.** `temperature=0.0` + fixed `beam_size` → re-transcribing a
   chunk yields the same text, so overwriting a partially-done chunk is idempotent.
6. **Idempotent finalization + batch resume.** A finished video short-circuits on re-entry;
   `run_batch` rewrites `batch_summary.json` after each video, so batch resume needs no extra state.

> ⚠️ **Backend-swap risk (carry into doc 05/tests):** invariant 5 assumes deterministic decoding.
> If a backend is non-deterministic (e.g. temperature ladder, or whisper.cpp threading variance),
> re-doing a half-written chunk could change text. Mitigation: a chunk is only ever *fully*
> overwritten (atomic), never merged, and `progress.json` is written last — so the worst case is a
> different-but-valid transcription of one chunk, never corruption. Tests must assert "no partial
> chunk is ever read as complete" and "resume never duplicates a chunk in the final transcript."

## 6. Required tests (none exist today — add them)

- `test_cleaning.py` — `clean_transcript`, `tail_prompt`, `build_full_transcript` (golden cases incl. repetition/hallucination patterns).
- `test_checkpoint_resume.py` — **crash injection**: kill between steps 3↔4, 4↔7, 6↔7; assert on resume: no duplicated chunk in final transcript, no half-written JSON read as complete, completed chunks skipped, in-flight chunk redone cleanly.
- `test_chunking.py` — ffmpeg `-f segment` on a tiny bundled sample (`fixtures/sample_5s.mp4`); assert chunk count, 16k mono, manifest signature reuse.
- `test_backend_contract.py` — each backend adapter returns the normalized result shape (doc 05) on the sample; `process_video` runs identically against a fake deterministic backend.

## 7. main.py reconciliation (delete it)

Old `main.py` (openai-whisper + moviepy, whole-file transcribe, no chunking, no resume, duplicate
`clean_transcript`) is **dead weight**. Delete it. Salvage only the cosmetic transcript header idea
(video name / date / model) into `engine/exporters.py` if desired. Drop `moviepy`, `openai-whisper`
(as a hard dep — it becomes an optional backend extra), `imageio*`, `decorator`, and the `numpy` pin
from requirements; let backends resolve their own deps.
