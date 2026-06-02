<p align="center"><strong>Yazıt</strong></p>
<p align="center"><em>Portable, resumable, multi-backend Whisper transcription — runs anywhere, resumes after crashes.</em></p>

> English | [Türkçe](README.tr.md)

**Yazıt** points at media (file, folder, Google Drive, or URL), detects your hardware,
picks the right Whisper model, and produces clean transcripts — surviving crashes and
disconnects by resuming exactly where it stopped.

> 🚧 Pre-release (v0.1.0 in progress). Full README, demo GIF, and badges land in the
> release phase (see `docs/ai/06-implementation-roadmap.md`).

## Install

```bash
pip install yazit            # base: engine + faster-whisper (CPU-capable)
```

ffmpeg is the one required system dependency.

## Quickstart

```bash
yazit transcribe ./lecture.mp4
```

## License

[Apache-2.0](LICENSE)
