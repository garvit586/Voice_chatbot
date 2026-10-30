"""Citation checking: strip any [n] that doesn't point at a retrieved passage."""

from __future__ import annotations

import re
from typing import Any

_CITE_RE = re.compile(r"\[(\d+)\]")


def check_citations(
    text: str, passages: list[dict[str, Any]]
) -> tuple[str, list[tuple[int, dict[str, Any]]]]:
    """Return (cleaned_text, [(n, passage)]) where every [n] left in the text is valid."""
    valid: set[int] = set()

    def replace(m: re.Match[str]) -> str:
        idx = int(m.group(1))
        if 1 <= idx <= len(passages):
            valid.add(idx)
            return m.group(0)
        return ""

    cleaned = _CITE_RE.sub(replace, text)
    return cleaned, [(i, passages[i - 1]) for i in sorted(valid)]


def build_citation_objects(used: list[tuple[int, dict[str, Any]]]) -> list[dict[str, Any]]:
    # Keep the number the answer text uses, so [3] in the text maps to citation 3.
    return [
        {
            "index": n,
            "doc_title": p.get("doc_title", ""),
            "page": p.get("page", 0),
            "snippet": p.get("text", "")[:600],
            "chunk_id": str(p.get("id", "")),
        }
        for n, p in used
    ]
