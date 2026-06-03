# Contributing to Yazıt

Thanks for considering a contribution to **Yazıt** (package/CLI: `yazit`) — a
portable, resumable, multi-backend Whisper transcription tool. This guide covers
the dev setup, the checks every change must pass, the conventions we hold to, and
the few rules that are non-negotiable because they protect the crash-safe resume
guarantee that is the whole point of this project.

By participating you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

---

## Quick links

- Bugs and feature requests: <https://github.com/htahaozlu/yazit/issues>
- Questions and ideas: <https://github.com/htahaozlu/yazit/discussions> (see also [SUPPORT.md](SUPPORT.md))
- Security reports: **do not** open a public issue — see [SECURITY.md](SECURITY.md)

---

## 1. Development setup

You need **Python 3.10–3.12** and **ffmpeg** (the one required system
dependency — for everything from extracting audio to chunking media).

```bash
# 1. Fork on GitHub, then clone your fork
git clone https://github.com/<your-username>/yazit
cd yazit

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Editable install with the full dev toolchain
pip install -e '.[dev]'

# 4. Confirm your host is ready (ffmpeg + device + backends)
yazit doctor
```

The base install pulls only the pure-Python engine plus the default
`faster-whisper` backend (CPU-capable). The optional backends, web UI, and
remote-source support live behind extras. Install whichever you are working on:

```bash
pip install -e '.[dev,web]'      # FastAPI web UI
pip install -e '.[dev,url]'      # yt-dlp URL sources
pip install -e '.[dev,drive]'    # Google Drive sources
pip install -e '.[dev,cpp]'      # whisper.cpp / pywhispercpp (Apple-Silicon Metal)
pip install -e '.[dev,openai]'   # openai-whisper reference backend
```

> `whisper.cpp` also needs a `whisper-cli` binary and a ggml model on disk;
> point `YAZIT_WHISPERCPP_BIN` and `YAZIT_WHISPERCPP_MODELS` at them.
> The `[gpu]` extra (torch + CUDA) is documented rather than hard-pinned — see
> `docs/CONFIG.md` for the install matrix.

---

## 2. The checks: ruff, mypy, pytest

Every change must pass all three before you open a pull request. They are exactly
what CI runs, so running them locally keeps your PR green:

```bash
ruff check .                     # lint
ruff format --check .            # formatting (drop --check to auto-fix)
mypy                             # static types (config in pyproject.toml)
pytest                           # the full test suite
```

A one-liner for the impatient:

```bash
ruff check . && ruff format --check . && mypy && pytest
```

Notes:

- **Line length is 100.** Ruff lint rules: `E, F, I, UP, B, C4, SIM, RUF`. The
  Turkish-character RUF rules (`RUF001/002/003`) are intentionally disabled —
  Turkish text in strings and comments is welcome and expected.
- **mypy is strict-ish:** `check_untyped_defs`, `no_implicit_optional`,
  `warn_unused_ignores`. Type your new code; do not paper over errors with a
  blanket `# type: ignore`.
- **Tests live in `tests/`** and run with `-q`. Add coverage for every behavior
  you add or fix.

---

## 3. Commit and pull-request conventions

We use **Conventional Commits**, and we keep them tight:

- **Subject line only.** No body, no bullet list, no trailing metadata.
- **One line, ≤ 72 characters.**
- **Lowercase** type and subject.
- **Scoped** to the area you touched.
- **No** `Co-Authored-By` / "Generated with …" / attribution trailers.

Format:

```
type(scope): subject
```

Common types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `ci`.
Useful scopes mirror the codebase: `engine`, `backends`, `sources`, `runtime`,
`cli`, `web`, `notebook`, `models`, `config`, `docs`.

Examples:

```
feat(backends): add whisper.cpp metal device detection
fix(engine): atomically replace progress.json on chunk commit
docs(readme): clarify the errno-107 colab scratch split
test(runtime): cover resume after a simulated fuse drop
```

Pull-request etiquette:

- Branch off `main`; one logical change per PR.
- Describe **what** changed and **why**, and link any related issue.
- Make sure ruff, mypy, and pytest all pass.
- If your change is user-visible, update the README/docs and `CHANGELOG.md`.

---

## 4. Extending Yazıt

Yazıt is deliberately pluggable along three axes. Each plugin point normalizes to
one shared shape so the engine and the resume loop never have to special-case it.

### Add a backend

A backend turns audio chunks into normalized segments. New backends register in
`src/yazit/backends/` and must:

1. Implement the backend protocol (transcribe → the **one** normalized segment
   shape every backend returns; look at `faster-whisper` as the reference).
2. Register in the backend registry with a `KNOWN_BACKENDS` entry, including the
   `extra` name so an unavailable backend yields the right
   `pip install 'yazit[<extra>]'` hint instead of a crash.
3. Declare its dependency under the matching extra in `pyproject.toml`, and add
   the module to the mypy `ignore_missing_imports` override list if it ships no
   type stubs.
4. Respect the hardware policy: never offer `cuda`/`mps` to `faster-whisper` on
   macOS-arm64, and slot into `model_policy.auto_select` if it participates in
   auto-selection.

### Add a source

A source resolves a user-supplied argument into local media paths. Sources live
in `src/yazit/sources/` and must:

1. Plug into `infer_kind` (how the argument maps to `local|url|drive|upload`) and
   `resolve_source` (how it materializes local files).
2. Download/copy into the **scratch workspace**, never straight onto a durable or
   network-mounted output dir (this is the Errno-107 split — heavy I/O stays
   local).
3. Gate any heavy dependency behind an extra (e.g. `[url]` → yt-dlp,
   `[drive]` → the Google API client) and fail with a clear "install the extra"
   message when it is missing.

### Add a runtime

A runtime owns the scratch-vs-durable directory split and any bootstrap (mounting
Drive, picking `/content` scratch on Colab, etc.). Runtimes live in
`src/yazit/runtime/` and must implement `resolve_dirs` and `bootstrap`, and
register with `resolve_runtime` so `--runtime auto|local|colab` can pick them.

In every case: keep the normalized output shape, and add tests.

---

## 5. The crash-test-first rule (non-negotiable)

Resumability is Yazıt's core promise: kill the process mid-run, re-run the same
command, and it continues from the last completed chunk with **no duplicated or
corrupted output**. That guarantee rests on a small, load-bearing mechanism:

- per-chunk durable checkpoints (`progress.json` + `chunk_outputs/`),
- **atomic temp-then-replace** writes for every durable file,
- a `RunIdentity` that refuses to resume a run whose backend / model / chunking /
  options differ from the committed run (it raises `CheckpointIdentityError`;
  `--overwrite` starts fresh),
- deterministic decoding (`temperature=0.0`) so a resumed chunk reproduces the
  same bytes.

**Therefore: any change that touches the checkpoint loop must add a crash test
first.** Before you change how chunks are written, committed, named, or resumed,
write a test that:

1. runs the pipeline,
2. simulates a crash at a chunk boundary (or mid-chunk),
3. re-runs the same command, and
4. asserts the final transcript is complete, in order, and byte-identical to a
   clean run — and that resuming with a different backend/model/chunking raises
   `CheckpointIdentityError`.

A PR that modifies checkpointing without such a test will not be merged. If you
are unsure whether your change touches the loop, assume it does and write the
test — it is the cheapest insurance we have.

---

## 6. Honest scope

To keep reviews focused, a reminder of what Yazıt is and is not:

- Local models only in v1 — no cloud transcription APIs.
- Apple-GPU acceleration is available **only** through whisper.cpp (Metal).
- Transcripts are best-effort ASR, not verbatim legal records.

Changes that respect these boundaries are far easier to land. If you want to push
one of them, open a discussion first so we can align on direction.

Thank you for helping make Yazıt better.
