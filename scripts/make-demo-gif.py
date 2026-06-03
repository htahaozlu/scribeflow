#!/usr/bin/env python3
"""Render docs/images/demo.gif — a stylized, animated terminal demo of the
transcribe -> interrupt -> resume story. Pure Pillow, no terminal/vhs needed,
runs anywhere (CI included). For an authentic screen recording instead, use
scripts/record-demo.sh (needs vhs).

    python scripts/make-demo-gif.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 820, 470
BG, BAR = (13, 17, 23), (22, 27, 34)
GREEN, WHITE, BLUE = (125, 206, 160), (230, 237, 243), (88, 166, 255)
DIM, ACCENT, RED, CMD = (139, 148, 158), (47, 129, 247), (248, 81, 73), (201, 209, 217)

_FONT_CANDIDATES = [
    "/System/Library/Fonts/Menlo.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/Library/Fonts/Menlo.ttc",
]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


MONO, SMALL = _font(16), _font(12)
Seg = tuple[tuple[int, int, int], str]
Line = list[Seg]


def progbar(done: int, total: int, width: int = 22) -> Line:
    filled = round(width * done / total)
    pct = round(100 * done / total)
    color = GREEN if done >= total else ACCENT
    return [
        (DIM, f"chunk {done:2d}/{total}  "),
        (color, "█" * filled),
        (DIM, "░" * (width - filled)),
        (DIM, f"  {pct}%"),
    ]


def render(lines: list[Line]) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 34], fill=BAR)
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        cx = 22 + i * 22
        d.ellipse([cx - 6, 11, cx + 6, 23], fill=c)
    d.text((W / 2, 17), "scribeflow — transcription that resumes", font=SMALL, fill=DIM, anchor="mm")
    y = 58
    for line in lines:
        x = 22
        for color, text in line:
            d.text((x, y), text, font=MONO, fill=color)
            x += int(MONO.getlength(text))
        y += 27
    return img


CMD_LINE: Line = [(GREEN, "$ "), (CMD, "scribeflow transcribe lecture.mp4 --format srt")]
INFO: Line = [(BLUE, "Transcribing — faster-whisper / large-v3-turbo (cpu, int8)")]

frames: list[Image.Image] = []
durations: list[int] = []


def push(lines: list[Line], ms: int) -> None:
    frames.append(render(lines))
    durations.append(ms)


base: list[Line] = [CMD_LINE]
push(base, 1000)
base = [*base, INFO]
push(base, 700)
for done in (2, 4, 6):
    push([*base, progbar(done, 12)], 430)
base = [*base, progbar(6, 12), [(RED, "^C  (interrupted)")]]
push(base, 1300)
base = [
    *base,
    [(DIM, "")],
    [(DIM, "# closed the laptop? run the SAME command — it resumes:")],
    CMD_LINE,
]
push(base, 1300)
base = [*base, [(GREEN, "resumed ✓  chunks 1–6 already done — skipping")]]
push(base, 850)
for done in (8, 10):
    push([*base, progbar(done, 12)], 430)
base = [*base, progbar(12, 12)]
push(base, 550)
base = [*base, [(GREEN, "Done. Output in scribeflow-output/lecture/")]]
push(base, 700)
base = [*base, [(WHITE, "  • lecture_transcript.txt")], [(WHITE, "  • lecture.srt")]]
push(base, 2900)

out = Path(__file__).resolve().parent.parent / "docs" / "images" / "demo.gif"
out.parent.mkdir(parents=True, exist_ok=True)
frames[0].save(
    out, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True, disposal=2
)
print(f"wrote {out} ({len(frames)} frames, {sum(durations) / 1000:.1f}s loop)")
