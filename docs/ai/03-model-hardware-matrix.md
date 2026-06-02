# 03 — Model & Hardware Matrix (Turkish-focused)

> Drives `devices.py` (detection) and `model_policy.py` (auto-select). Current as of 2025–2026,
> sourced from SYSTRAN/faster-whisper, OpenNMT/CTranslate2, OpenAI Whisper, whisper.cpp, HF.

## 1. Model catalog (faster-whisper / CTranslate2)

| Model | Params | DL size | VRAM fp16 | VRAM int8 | CPU RAM int8 | Rel. speed | Quality | Turkish |
|---|---|---|---|---|---|---|---|---|
| tiny | 39M | ~75MB | ~1GB | ~0.5GB | ~0.5–1GB | ~10x | Low | **avoid** |
| base | 74M | ~145MB | ~1GB | ~0.6GB | ~0.7GB | ~7x | Low-mid | weak |
| small | 244M | ~480MB | ~2GB | ~1GB | ~1.5GB | ~4x | Mid | drafts only |
| medium | 769M | ~1.5GB | ~5GB | ~2.5GB | ~3GB | ~2x | Good | good budget |
| large-v2 | 1550M | ~3GB | ~4.5GB | ~2.9GB | ~2.3GB | 1x | High | very good |
| **large-v3** | 1550M | ~3GB | ~4.5GB | ~2.9GB | ~2.3GB | 1x | **Highest** | **best** |
| **large-v3-turbo** | 809M | ~1.6GB | ~2.5GB | ~1.5GB | ~1.5GB | ~8x | High (~1–2% below v3) | **very good** |
| distil-large-v3 | 756M | ~1.5GB | ~2.4GB | ~1.5GB | ~1.5GB | ~6x | High (EN) | **English-only — exclude** |

Key facts:
- **turbo = pruned large-v3** (decoder 32→4 layers, same encoder). ~6–8x faster, minor quality loss. Turkish is well-represented → turbo is **very good** for TR.
- **distil-* is English-only.** Never auto-select for Turkish.
- WER (LibriSpeech clean, faster-whisper #1030): turbo 1.92, distil-v3 2.39, large-v3 fp16 2.88, large-v3 int8 4.59.
- Optional TR-specialized: `selimc/whisper-large-v3-turbo-turkish` (convert to CT2) — offer as opt-in, not default.

## 2. compute_type per device (CTranslate2)

**CPU (x86/ARM):** use **`int8`** (resolves to int8_float32). `float16` on CPU is silently demoted
to float32 — no speed gain, full memory. → never offer fp16 on CPU.

**CUDA GPU:** `float16` (default, modern GPU CC≥7.0) · `int8_float16` (mixed, ~⅓ less VRAM, tiny
loss — for ≤6–8GB) · `int8` (smallest) · `bfloat16` (Ampere+ CC≥8.0).

**Apple Silicon / MPS — THE GOTCHA:** **CTranslate2 has NO Metal/MPS backend.** faster-whisper on
macOS-arm64 runs **CPU only** (`device="cpu", compute_type="int8"`); `cuda`/`mps` are invalid.
→ For Mac GPU acceleration, the tool must route to the **whisper.cpp backend** (Metal/Core ML) or
mlx-whisper. This is the single most important practical rule.

> int8 *lowers GPU VRAM but raises CPU RAM* (large-v3 int8: VRAM 2953MB but CPU mem ~2261MB vs
> 901MB fp16) — account for both when sizing.

## 3. Auto-select decision table (`model_policy.py`)

`want=quality` (archival/subtitle) vs `want=speed` (bulk). Turkish → never distil/tiny/base.

| Detected env | Speed pick | Quality pick | **Sane default** |
|---|---|---|---|
| CPU, 8GB RAM | small / int8 | medium / int8 | **small / int8** |
| CPU, 16GB RAM | medium / int8 | large-v3 / int8 | **large-v3-turbo / int8** |
| GPU ~4GB | turbo / int8_float16 | large-v3 / int8_float16 | **turbo / int8_float16** |
| GPU 6–8GB | turbo / float16 | large-v3 / int8_float16 | **turbo / float16** |
| GPU 12–16GB (**Colab T4 = 16GB**) | turbo / float16 | large-v3 / float16 | **large-v3 / float16** |
| GPU 24GB+ | turbo / float16 (batched) | large-v3 / float16 (batched) | **large-v3 / float16** |
| Apple Silicon | whisper.cpp turbo + Metal | whisper.cpp large-v3 + Metal | **whisper.cpp turbo (Metal)**; fallback faster-whisper large-v3-turbo / int8 (CPU) |

**Single global default if forced to pick one:** `large-v3-turbo`, `float16` on GPU / `int8` on CPU.
User override (`--model` / `--backend` / `--compute-type` / config / UI) **always wins**.

> **Colab T4 is 16GB, not 4** — do not downgrade the model there. Auto-select must read actual VRAM.

## 4. Environment detection (`devices.py`)

```python
import platform, os, subprocess, shutil

def detect_colab() -> bool:
    try:
        import google.colab  # noqa
        return True
    except ImportError:
        return False

def detect_apple_silicon() -> bool:
    return platform.system() == "Darwin" and platform.machine() == "arm64"

def detect_cuda():
    """Return (has_cuda, vram_gb) or (False, 0)."""
    try:
        import torch
        if torch.cuda.is_available():
            _, total = torch.cuda.mem_get_info(0)
            return True, round(total / 1024**3, 1)
    except Exception:
        pass
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                text=True)
            return True, round(int(out.strip().splitlines()[0]) / 1024, 1)
        except Exception:
            pass
    return False, 0

def detect_cpu_ram():
    cores = os.cpu_count() or 1
    try:
        import psutil
        ram_gb = round(psutil.virtual_memory().total / 1024**3, 1)
    except ImportError:
        try:
            ram_gb = round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3, 1)
        except (ValueError, AttributeError):
            ram_gb = 0
    return cores, ram_gb

def choose_device_and_compute():
    if detect_apple_silicon():
        return "cpu", "int8"        # CT2 has no Metal — faster-whisper is CPU-only here
    has_cuda, vram = detect_cuda()
    if has_cuda:
        return "cuda", ("float16" if vram >= 8 else "int8_float16")
    return "cpu", "int8"
```

`model_policy.choose_model(device, vram_gb, ram_gb, want, user_override)` applies the §3 table;
`user_override` short-circuits. On Apple Silicon with `--backend faster-whisper`, warn and stay CPU;
with default backend, prefer whisper.cpp if installed.

## 5. Pluggable backends (D3 — all LOCAL)

| Backend | Sweet spot | Pros | Cons | Install | Role in v1 |
|---|---|---|---|---|---|
| **faster-whisper** (CT2) | NVIDIA GPU, any CPU | fast, low mem, VAD, batching, mature | no Apple GPU | `pip install faster-whisper` | **default** |
| **whisper.cpp** | **Apple Silicon (Metal/Core ML)**, CPU, CUDA/Vulkan | Metal GPU + ANE on Mac, quantized ggml, no Python deps | build step; CLI/subprocess; own long-form windowing | clone + `cmake` (or `pywhispercpp`) | **Mac-GPU path** |
| **openai-whisper** | reference (PyTorch) | canonical correctness baseline, all params | slow, high VRAM | `pip install openai-whisper` | **reference / fallback** |

Interface differences the Backend Protocol must hide (doc 05 + Codex memo):
- faster-whisper → `(segments_iterator, info)`, `segment.start/.end/.text`, `info.language/.duration`.
- openai-whisper → `dict {'segments':[{start,end,text}], 'language'}`.
- whisper.cpp → **separate binary via subprocess** emitting JSON/SRT (parse to segments). Does its
  own long-form chunking — see doc 05 §2 for whether to still pre-chunk (chunk stays the
  resumability unit regardless).

## 6. Turkish settings (defaults the engine should ship)

```python
model.transcribe(
    audio,
    language="tr",                  # pin — skip autodetect errors (overridable; None = auto)
    beam_size=5,                    # quality default
    vad_filter=True,                # Silero VAD — cuts silence + hallucination in lectures/film
    vad_parameters=dict(min_silence_duration_ms=500),
    condition_on_previous_text=False,  # engine uses tail_prompt instead → avoids runaway loops
    temperature=0.0,                # determinism (resume-safety, invariant 5 in doc 02)
    initial_prompt=<tail of previous chunk>,  # continuity without loop risk
)
```

Tradeoffs to expose as flags (keep determinism-safe defaults):
- `condition_on_previous_text=True` improves coherence but can cascade hallucinations on noisy film
  audio — the engine deliberately uses `False` + `tail_prompt`. Keep that default.
- `temperature` ladder (`[0.0,0.2,0.4]`) is more robust against degenerate loops but breaks strict
  determinism — if exposed, document the resume caveat (doc 02 §5 invariant 5).
- `beam_size=1` faster, lower quality.

## Sources
faster-whisper README & issue #1030; CTranslate2 quantization + hardware_support docs; OpenAI
whisper repo; HF whisper-large-v3-turbo & distil-large-v3 cards; whisper.cpp; mlx-whisper.
