"""Rewrite a follow-up question into a standalone retrieval query."""

from __future__ import annotations

import re
from typing import Any

from server.providers.base import ChatProvider

REWRITE_PROMPT = """\
Given the conversation history below and a follow-up question, rewrite the follow-up as a \
standalone search query (max 80 words). Output only the query, nothing else."""


_REFERS_BACK = re.compile(
    r"\b(it|its|this|that|these|those|they|them|their|he|she|his|her|one|ones|"
    r"same|above|previous|earlier|again|also|else|other|more)\b",
    re.IGNORECASE,
)


def needs_rewrite(question: str, history: list[dict[str, str]]) -> bool:
    """A standalone question skips the extra LLM round trip (~0.5 s)."""
    if not history:
        return False
    return len(question.split()) <= 4 or bool(_REFERS_BACK.search(question))


async def rewrite_query(
    chat: ChatProvider,
    question: str,
    history: list[dict[str, str]],
) -> str:
    if not needs_rewrite(question, history):
        return question

    history_text = "\n".join(
        f"{m['role'].upper()}: {m['content'][:300]}" for m in history[-6:]
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": REWRITE_PROMPT},
        {"role": "user", "content": f"History:\n{history_text}\n\nFollow-up: {question}"},
    ]
    result = await chat.complete(messages, max_tokens=120, temperature=0.1)
    return result.strip() or question
