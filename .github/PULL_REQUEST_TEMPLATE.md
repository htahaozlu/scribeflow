<!--
  Thanks for contributing to Yazıt!
  Keep the change focused and explain the "why", not just the "what".
-->

## Summary

<!-- What does this PR do, and why? One or two sentences. -->

## Related issues

<!-- e.g. "Closes #123", "Refs #456". Delete if none. -->

## Type of change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that changes existing behavior)
- [ ] Documentation only
- [ ] CI / build / tooling
- [ ] Refactor / internal cleanup (no behavior change)

## Affected areas

<!-- Tick everything this PR touches. -->

- [ ] Engine / pipeline (chunking, resume, checkpoints)
- [ ] Backend: faster-whisper
- [ ] Backend: whisper.cpp (Apple-Silicon Metal)
- [ ] Backend: openai-whisper
- [ ] Hardware auto-select / model policy
- [ ] CLI (`transcribe` / `models` / `doctor` / `gen-notebook` / `web`)
- [ ] Sources (local / url / drive / upload)
- [ ] Exporters (txt / srt / vtt / json)
- [ ] Colab notebook generation
- [ ] Web UI (`[web]` extra)
- [ ] Docs / README

## How was this tested?

<!--
  Describe the verification. Include the exact commands you ran, e.g.:
    pip install -e '.[dev]'
    pytest -q
    ruff check . && mypy
    yazit doctor
    yazit transcribe ./sample.mp4 --format srt,vtt
-->

- [ ] `pytest -q` passes
- [ ] `ruff check .` is clean
- [ ] `mypy` is clean
- [ ] Tested on the relevant hardware (note OS + arch + backend below)

**Environment tested on:**

<!-- e.g. macOS 14 arm64 / whisper.cpp Metal, or Ubuntu 22.04 x86_64 / CUDA 12 -->

## Resume / durability impact

<!--
  Yazıt is crash-safe and resumable. If this PR touches the engine, checkpoints,
  RunIdentity, chunking, or any default option, explain the impact on resume.
  Otherwise write "n/a".
-->

- [ ] No change to checkpoint format / `RunIdentity` (or: migration explained above)
- [ ] Existing in-progress runs still resume correctly

## Checklist

- [ ] My change follows the project's tone and structure
- [ ] I updated docs / README where relevant
- [ ] I added or updated tests where it makes sense
- [ ] Commits use Conventional Commits style
- [ ] I am submitting under the project's Apache-2.0 license
