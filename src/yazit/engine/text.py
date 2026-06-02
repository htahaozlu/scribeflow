"""Domain text logic — pure, no I/O. Ported verbatim from the proven engine.

This is the canonical copy of ``clean_transcript`` (the identical twin in the
old ``main.py`` is dead weight and was dropped). See docs/ai/02 §1.
"""

from __future__ import annotations

import re
from pathlib import Path


def clean_transcript(text: str) -> str:
    """Anti-hallucination dedup.

    Drops sub-three-word sentences, strips characters outside ``\\w\\s.,!?-``,
    suppresses repeated 5-gram phrases (sliding window of 10), collapses whole
    sentences repeated more than once and consecutive words repeated more than
    twice. Behavior frozen — golden-tested in ``tests/test_text.py``.
    """
    sentences = re.split(r"[.!?]+", text)
    cleaned_sentences: list[str] = []
    previous_sentence = ""
    repeat_count = 0
    last_phrases: list[str] = []

    for raw_sentence in sentences:
        sentence = raw_sentence.strip()
        if not sentence:
            continue

        sentence = re.sub(r"[^\w\s.,!?-]", "", sentence)
        if len(sentence.split()) < 3:
            continue

        words = sentence.split()
        if len(words) >= 5:
            current_phrase = " ".join(words[-5:])
            if current_phrase in last_phrases:
                continue
            last_phrases.append(current_phrase)
            if len(last_phrases) > 10:
                last_phrases.pop(0)

        if sentence == previous_sentence:
            repeat_count += 1
            if repeat_count > 1:
                continue
        else:
            repeat_count = 0

        cleaned_words: list[str] = []
        previous_word = ""
        word_repeat_count = 0

        for word in words:
            if word == previous_word:
                word_repeat_count += 1
                if word_repeat_count > 2:
                    continue
            else:
                word_repeat_count = 0
            cleaned_words.append(word)
            previous_word = word

        cleaned_sentences.append(" ".join(cleaned_words))
        previous_sentence = sentence

    cleaned_text = ". ".join(cleaned_sentences)
    cleaned_text = re.sub(r"[.!?]+", ".", cleaned_text)
    cleaned_text = re.sub(r"\s+", " ", cleaned_text).strip()
    return cleaned_text


def tail_prompt(texts: list[str], max_chars: int = 350) -> str | None:
    """Build an ``initial_prompt`` continuity hint from the tail of prior text.

    Enables cross-chunk coherence WITHOUT ``condition_on_previous_text`` (which
    can cascade hallucinations on noisy audio). Returns ``None`` when empty.
    """
    joined = " ".join(part.strip() for part in texts if part.strip()).strip()
    if not joined:
        return None
    return joined[-max_chars:]


def build_full_transcript(chunks_text_dir: Path) -> str:
    """Reassemble ``chunk_*.txt`` in sorted order.

    Idempotent — recomputed from disk on every chunk, so partial/duplicate runs
    self-heal on resume (docs/ai/02 §5 invariant 4). The final transcript is
    always exactly the sorted concatenation of the existing chunk txts.
    """
    chunk_texts: list[str] = []
    for chunk_file in sorted(chunks_text_dir.glob("chunk_*.txt")):
        content = chunk_file.read_text(encoding="utf-8").strip()
        if content:
            chunk_texts.append(content)
    return "\n\n".join(chunk_texts).strip()
