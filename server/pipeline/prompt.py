"""Build messages for the chat model."""

from __future__ import annotations

from typing import Any

import tiktoken

_enc = tiktoken.get_encoding("cl100k_base")
MAX_HISTORY_TOKENS = 2_000
MAX_PASSAGE_TOKENS = 3_000


def _tok(text: str) -> int:
    return len(_enc.encode(text))


SYSTEM_PROMPT = """\
You are a knowledgeable assistant. Answer only from the provided passages.
Cite each passage you use as [n] inline.
If you are unsure or the passages do not cover the question, say so honestly.
Do not invent information not in the passages."""


def build_messages(
    question: str,
    passages: list[dict[str, Any]],
    history: list[dict[str, str]],
    kb_name: str = "",
    image_bytes: bytes | None = None,
) -> list[dict[str, Any]]:
    # System
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]

    if not passages:
        messages.append({
            "role": "user",
            "content": (
                f"No passages were found in the knowledge base '{kb_name}' for this question.\n"
                f"Question: {question}"
            ),
        })
        return messages

    # Passages block (always fits first — capped at MAX_PASSAGE_TOKENS)
    passage_lines: list[str] = []
    used_tokens = 0
    for i, p in enumerate(passages):
        line = (
            f"[{i+1}] {p.get('doc_title','')} (p.{p.get('page',0)}): {p.get('text','')}"
        )
        t = _tok(line)
        if used_tokens + t > MAX_PASSAGE_TOKENS:
            break
        passage_lines.append(line)
        used_tokens += t

    passages_text = "Passages:\n" + "\n\n".join(passage_lines)
    messages.append({"role": "user", "content": passages_text})
    messages.append({
        "role": "assistant",
        "content": "Understood. I will answer only from the passages above.",
    })

    # Trimmed history
    history_tokens = 0
    trimmed: list[dict[str, str]] = []
    for msg in reversed(history[-20:]):
        t = _tok(msg.get("content", ""))
        if history_tokens + t > MAX_HISTORY_TOKENS:
            break
        trimmed.insert(0, msg)
        history_tokens += t
    messages.extend(trimmed)  # type: ignore[arg-type]

    # User question (with optional image)
    if image_bytes:
        import base64
        b64 = base64.b64encode(image_bytes).decode()
        content: Any = [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            {"type": "text", "text": question},
        ]
    else:
        content = question

    messages.append({"role": "user", "content": content})
    return messages


def refusal_message(kb_name: str, doc_titles: list[str]) -> str:
    covers = ", ".join(f'"{t}"' for t in doc_titles[:5]) if doc_titles else "no documents yet"
    return (
        f"I could not find anything relevant in the knowledge base **{kb_name}**. "
        f"It currently covers: {covers}. "
        "Please rephrase your question or check a different knowledge base."
    )
