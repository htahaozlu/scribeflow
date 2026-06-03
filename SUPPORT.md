# Support

Thanks for using **Yazıt**! Here is where to look for help.

## First steps

1. **`yazit doctor`** — checks ffmpeg, your device/VRAM/RAM, and which backends are
   available. Most setup issues show up here.
2. **[README](README.md)** ([Türkçe](README.tr.md)) — install, quickstart, backends,
   and how resume works.
3. **[docs/CONFIG.md](docs/CONFIG.md)** — every config option, the `YAZIT_*` env vars,
   `yazit.toml`, and how model auto-selection works.

## Common questions

- **Which model will it use?** Run `yazit models` to see the catalog and your host's
  auto-pick.
- **It's slow on my Mac.** faster-whisper is CPU-only on Apple Silicon. Install the
  Metal path: `pip install 'yazit[cpp]'` and point `YAZIT_WHISPERCPP_BIN` /
  `YAZIT_WHISPERCPP_MODELS` at a whisper.cpp binary + ggml model.
- **My run got interrupted.** Re-run the *same* command — Yazıt resumes from the last
  completed chunk. To start over, add `--overwrite`.
- **Transcribing on Colab?** `yazit gen-notebook <source>` emits a ready-to-run
  notebook.

## Asking a question

- **Questions / ideas / help:** open a
  [GitHub Discussion](https://github.com/htahaozlu/yazit/discussions).
- **Bugs:** open a [GitHub Issue](https://github.com/htahaozlu/yazit/issues/new/choose)
  using the bug template (please include your `yazit doctor` output and the exact
  command).
- **Security problems:** see [SECURITY.md](SECURITY.md) — report privately, not as a
  public issue.

This is a small open-source project maintained on a best-effort basis; please be
patient and kind. See [CONTRIBUTING.md](CONTRIBUTING.md) if you'd like to help.
