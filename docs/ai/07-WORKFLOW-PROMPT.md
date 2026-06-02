# 07 — The Dynamic-Workflow Prompt (paste this to build it)

This is the prompt to feed a Claude Code session (ultracode / Workflow orchestration) to build the
whole project as a **long-running, multi-phase, self-verifying** workflow. It binds the
implementation to the specs in `docs/ai/00`–`06`.

## How to launch

1. Open a Claude Code session with workflow orchestration enabled (ultracode on, or include the word
   **workflow**).
2. Make the `docs/ai/` folder reachable (run from inside the current repo, or copy `docs/ai/` to the
   new project and point the prompt at it).
3. Paste the **PROMPT** block below. Optionally tweak the target path and final project name token.

---

## PROMPT (copy from here)

> Build a new open-source Python project from the binding spec in `docs/ai/00`–`06` of the
> `Film-Transcriber` repo. Run it as ONE long-running, multi-phase dynamic workflow — phase by phase,
> verifying each phase's acceptance gate adversarially before advancing. Do not stop until every gate
> in `docs/ai/06-implementation-roadmap.md` passes or you hit a true blocker; if blocked, report and
> propose options.
>
> **Read first (binding spec, in order):** `docs/ai/00-INDEX.md`, `01-vision-scope-decisions.md`,
> `02-engine-checkpoint-spec.md`, `03-model-hardware-matrix.md`, `04-conventions-publishing.md`,
> `05-architecture.md`, `06-implementation-roadmap.md`. Treat doc 02's invariants as inviolable and
> doc 05's Backend Protocol + RunIdentity as the canonical design.
>
> **Where:** greenfield. Create a sibling directory `../yazit/` (or a path I give you), `git init`,
> `src/yazit/` layout. NEVER mutate the old `Film-Transcriber` tree — it is the reference engine to
> port from, not to edit. Name token: `yazit` (package/CLI/PyPI) / `Yazıt` (display); keep it in one
> constant.
>
> **Engine is lift-and-shelter, not rewrite.** Port `colab_runtime/drive_batch_transcriber.py`
> functions verbatim into `engine/*` (doc 02 §1), changing only the two cosmetic Colab strings and
> the two seams: video discovery → Source adapters, and the inlined `WhisperModel(...)` →
> `TranscriptionBackend` Protocol. Preserve the per-chunk commit ordering, atomic temp-then-os.replace
> writes, dual-condition skip guard, derived-not-appended transcript, and temperature-0 determinism
> EXACTLY. Add `RunIdentity` (doc 05 §5) so resuming with a different backend/model/chunking raises
> `CheckpointIdentityError` instead of silently mixing output.
>
> **Orchestration shape (per phase P0–P9 of doc 06):**
> - PLAN: a planning agent reads the relevant docs and emits a concrete file-level task list for the phase.
> - BUILD: fan out implementation agents across non-overlapping files; use **worktree isolation** for
>   any agents that mutate files in parallel to avoid conflicts.
> - VERIFY (adversarial): independent reviewer agents try to BREAK the phase gate — run the phase's
>   tests, attempt crash-injection on the checkpoint loop, check invariants from doc 02 §5, and check
>   spec conformance. A finding stands only if ≥2 independent verifiers agree it's real; fix and
>   re-verify until the gate is green.
> - GATE: do not advance until the phase's acceptance gate (doc 06) passes for real (tests actually
>   run and pass — quote the output; never claim green without running).
> - COMMIT: one Conventional Commit per phase, **subject-only, ≤72 chars, no body, no attribution,
>   never amend** (owner rule, doc 04 §5). Scope by subsystem (`feat(engine):`, `test(checkpoint):`…).
>
> **Hard requirements to honor throughout:**
> - The resumable checkpoint loop is the crown jewel — every change touching it must be guarded by a
>   crash-injection test FIRST (doc 02 §6).
> - Backend adapters normalize data only; they NEVER write checkpoint files (doc 05 §2).
> - Chunking stays backend-agnostic; chunk = resumability unit; no overlap in v1 (doc 05 §3).
> - Apple Silicon: never offer cuda/mps to faster-whisper; route Mac-GPU to whisper.cpp (doc 03 §2).
> - Drive Errno-107 split: heavy I/O on local `workspace_dir`, only transcripts on durable
>   `output_dir`; this is a RuntimeTarget concern (doc 05 §4).
> - Turkish defaults: `language="tr"`, `vad_filter=True`, `beam_size=5`,
>   `condition_on_previous_text=False` + `tail_prompt`; never auto-select English-only `distil-*`.
> - Keep base install tiny; heavy backends behind extras `[gpu][cpp][openai][web][url][drive][dev]`;
>   ffmpeg is the one documented system dep.
>
> **Definition of done (v1):** all P0–P9 gates green; `pip install -e .` then
> `yazit transcribe ./tests/fixtures/sample_5s.mp4` produces a transcript with zero config; kill +
> rerun resumes with no duplication (proven by the crash test); `yazit gen-notebook` emits a runnable
> Colab notebook; all 3 backends produce consistent normalized output; bilingual README + governance
> files + CI publish workflow exist; tag `v0.1.0` is ready.
>
> Scale depth to thoroughness over speed: prefer more verification agents on the engine/checkpoint
> phases (P1–P2) and the backend-normalization phase (P6). Report a short status after each phase gate.

## (end of prompt)

---

## Notes for the owner

- **Cost/time:** this is a large multi-phase build; expect a long run and meaningful token spend. The
  phase gates keep it honest — you'll see real test output at each step, not "looks done".
- **First run scope:** if you want a smaller first bite, tell the workflow "stop after P3" — that
  yields a working local CLI (`yazit transcribe`) you can try immediately, then resume from P4 later.
- **Name:** swap `yazit`/`Yazıt` if you pick a different name before launching; it's a single token.
- **whisper.cpp on your Mac:** P6 gives you the Metal-accelerated path — that's the phase that makes
  local Apple-Silicon transcription fast (faster-whisper alone is CPU-only on Mac).
