#!/usr/bin/env bash
# Generate docs/images/demo.gif — a real "transcribe → interrupt → resume" run.
#
# Repeatable, not ad-hoc: edit scripts/demo.tape to change the script, re-run this.
#
# Requires:
#   - vhs        https://github.com/charmbracelet/vhs   (brew install vhs)
#   - ffmpeg     (the one ScribeFlow system dependency)
#   - scribeflow on PATH   (pipx install scribeflow  /  pip install scribeflow)
#   - a TTS voice for the sample: macOS `say` or Linux `espeak-ng` (optional;
#     falls back to a tone if neither is present).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

need() { command -v "$1" >/dev/null 2>&1 || { echo "✗ missing: $1 — $2"; exit 1; }; }
need vhs "brew install vhs  (https://github.com/charmbracelet/vhs)"
need ffmpeg "install ffmpeg (brew install ffmpeg / apt-get install ffmpeg)"
need scribeflow "pipx install scribeflow"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cd "$work"

echo "▸ Building a ~2-minute speech sample so --chunk-minutes 1 yields several chunks…"
text="ScribeFlow turns your recordings into clean transcripts and subtitles. \
It runs on your own computer, and if a run is interrupted it picks up exactly \
where it left off, so you never lose work."
if command -v say >/dev/null 2>&1; then
  say -o base.aiff "$text"
elif command -v espeak-ng >/dev/null 2>&1; then
  espeak-ng -w base.aiff "$text"
else
  echo "  (no TTS found — using a tone; the transcript will be empty but the resume still shows)"
  ffmpeg -hide_banner -loglevel error -f lavfi -i "sine=frequency=320:duration=30" base.aiff
fi
ffmpeg -hide_banner -loglevel error -stream_loop 8 -i base.aiff -t 135 -ar 16000 -ac 1 -y demo.wav

echo "▸ Warming the model cache so the recording isn't dominated by a download…"
scribeflow transcribe demo.wav --model tiny -l en --chunk-minutes 1 >/dev/null 2>&1 || true
rm -rf scribeflow-output scribeflow-workspace   # fresh start so the recorded run truly resumes

echo "▸ Recording with vhs…"
vhs "$REPO/scripts/demo.tape"

mkdir -p "$REPO/docs/images"
cp demo.gif "$REPO/docs/images/demo.gif"
echo "✓ Wrote docs/images/demo.gif"
echo "  Then point the README <img> at docs/images/demo.gif (it currently shows demo.svg)."
