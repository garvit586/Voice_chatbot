"""Split streamed text into sentences for TTS."""

from __future__ import annotations

import re

# End on sentence-ending punctuation followed by space or end
_END_RE = re.compile(r"(?<=[.!?])\s+|(?<=[.!?])$")
MIN_CHARS = 20


class SentenceBuffer:
    """Buffer tokens until a complete sentence is ready, then flush."""

    def __init__(self) -> None:
        self._buf = ""

    def feed(self, token: str) -> list[str]:
        self._buf += token
        sentences: list[str] = []
        while True:
            m = _END_RE.search(self._buf)
            if not m:
                break
            end = m.end()
            candidate = self._buf[:end].strip()
            if len(candidate) >= MIN_CHARS:
                sentences.append(candidate)
                self._buf = self._buf[end:]
            else:
                break
        return sentences

    def flush(self) -> list[str]:
        leftover = self._buf.strip()
        self._buf = ""
        return [leftover] if leftover else []
