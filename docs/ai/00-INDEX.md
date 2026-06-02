# AI Design Docs — Portable Transcription Tool (working name: **Yazıt** / `yazit`)

> These documents are the **high-signal context** for an AI implementation team (multi-agent
> dynamic workflow) that will build a portable, resumable, multi-backend audio/video
> transcription tool. They are written to be read by models, not skimmed by humans. Dense on
> purpose. Read in order.

## What we are building (one sentence)

A portable, open-source Whisper transcription tool that runs **anywhere** (local CPU/GPU, Apple
Silicon, Google Colab, remote server), takes input from **anywhere** (local path, upload, Google
Drive, URL), **auto-selects the model for the detected hardware** (user can override), and is
**crash-safe and resumable** — built around a proven resumable chunk-by-chunk engine that already
exists and must be preserved.

## Origin

Evolved from `Film-Transcriber` (a Turkish MA-thesis tool for transcribing lecture/film video).
The engine in `colab_runtime/drive_batch_transcriber.py` is battle-tested on real Colab+Drive runs
and is the asset we carry forward. Sibling open-source project by the same owner:
[`context-bar`](https://github.com/htahaozlu/context-bar) — match its conventions (see doc 04).

## Reading order

| # | Doc | What it pins down |
|---|-----|-------------------|
| 00 | this file | Map + working name + glossary |
| 01 | `01-vision-scope-decisions.md` | Product scope, the 4 LOCKED owner decisions, non-goals, success criteria |
| 02 | `02-engine-checkpoint-spec.md` | **The crown jewel.** Exact resumable-checkpoint design to port verbatim + invariants + required tests |
| 03 | `03-model-hardware-matrix.md` | Model catalog, compute_type per device, auto-select table, detection code, Turkish settings |
| 04 | `04-conventions-publishing.md` | Naming, license, README, packaging, Conventional Commits, governance, release flow |
| 05 | `05-architecture.md` | Module layout + Backend Protocol + Source/Target seams (incorporates Codex review) — *added after Codex memo* |
| 06 | `06-implementation-roadmap.md` | Phased build order with acceptance gates — *added with 05* |
| 07 | `07-WORKFLOW-PROMPT.md` | The exact prompt to feed the dynamic workflow — *added with 05* |

## Working name (owner finalizes)

Primary recommendation: **Yazıt** (Turkish: *inscription / epigraph* — short, evocative, fits a
transcription tool, keeps the Turkish-academic identity). Package/CLI slug: **`yazit`** (ASCII).
Alternatives to consider: `desifre` (TR "deşifre" = to transcribe audio), `scribeflow`, `reescribe`.

**For the implementation team:** treat `Yazıt` / `yazit` as a **single find-and-replace token**.
Use `yazit` for the Python package, console script, and PyPI name; `Yazıt` for display/README.
Do not scatter the name into logic — read it from one constant (`yazit.__about__.APP_NAME`).

## Glossary (used across all docs)

- **Engine** — the preserved core: chunking + per-chunk transcribe + atomic checkpointing.
- **Backend** — a swappable ASR implementation (faster-whisper / whisper.cpp / openai-whisper).
- **Source** — where media comes from (local / upload / Google Drive / URL) → resolves to a local media dir.
- **Runtime target** — where execution happens (local / Colab / remote) → decides scratch vs durable roots + bootstrap.
- **Chunk** — a fixed-duration audio slice (default 20 min); also the **unit of resumability**.
- **Workspace dir** — scratch (audio chunks); may be ephemeral. **Output dir** — durable (transcripts + checkpoints).
- **Checkpoint** — the on-disk state (`manifest.json`, `progress.json`, `chunk_outputs/`) enabling resume.
