"""The preserved core: chunking + per-chunk transcribe + atomic checkpointing.

Behavior is frozen per docs/ai/02-engine-checkpoint-spec.md. Lifted verbatim
from the proven ``colab_runtime/drive_batch_transcriber.py``.
"""
