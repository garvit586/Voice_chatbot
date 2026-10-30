"""The answer pipeline: rewrite → retrieve → prompt → stream → check citations."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import asyncpg  # type: ignore[import-untyped]

from server.db import repo
from server.pipeline.citations import build_citation_objects, check_citations
from server.pipeline.prompt import build_messages, refusal_message
from server.pipeline.rewrite import rewrite_query
from server.providers.base import ChatProvider, EmbeddingProvider, RerankProvider
from server.retrieval.hybrid import retrieve


@dataclass
class AskResult:
    text: str
    citations: list[dict[str, Any]]
    timings: dict[str, float]
    refused: bool = False


async def describe_image(
    chat: ChatProvider, image_bytes: bytes, question: str
) -> str:
    """Turn an image + question into a text retrieval query."""
    import base64
    b64 = base64.b64encode(image_bytes).decode()
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": (
                    f"Describe what is shown in this image relevant to the question: '{question}'. "
                    "Output a concise search query in max 60 words."
                )},
            ],
        }
    ]
    result = await chat.complete(messages, max_tokens=100, temperature=0.1)
    return result.strip() or question


async def ask_stream(
    pool: asyncpg.Pool,
    kb_id: uuid.UUID,
    conv_id: uuid.UUID,
    question: str,
    chat: ChatProvider,
    embedder: EmbeddingProvider,
    model_key: str,
    reranker: RerankProvider | None = None,
    image_bytes: bytes | None = None,
    image_key: str | None = None,
) -> AsyncIterator[str]:
    """Yields SSE-ready token strings, then a final JSON event with citations."""
    t0 = time.monotonic()
    timings: dict[str, float] = {}

    async with pool.acquire() as conn:
        history_rows = await repo.get_messages(conn, conv_id, limit=12)
        history = [{"role": r["role"], "content": r["text"]} for r in history_rows]
        kb = await repo.get_kb(conn, kb_id)
        kb_name = kb["name"] if kb else ""

    # Image: describe first, use description as retrieval query
    retrieval_query = question
    if image_bytes:
        retrieval_query = await describe_image(chat, image_bytes, question)
        timings["describe_image"] = time.monotonic() - t0

    # Rewrite follow-up
    t1 = time.monotonic()
    retrieval_query = await rewrite_query(chat, retrieval_query, history)
    timings["rewrite"] = time.monotonic() - t1

    # Retrieve
    t2 = time.monotonic()
    passages = await retrieve(pool, kb_id, retrieval_query, embedder, model_key, reranker)
    timings["retrieve"] = time.monotonic() - t2

    # Refuse early if no passages
    if not passages:
        async with pool.acquire() as conn:
            doc_titles = await repo.get_document_titles(conn, kb_id)
        text = refusal_message(kb_name, doc_titles)
        async with pool.acquire() as conn:
            await repo.insert_message(
            conn, conv_id, "user", question, image_key=image_key, timings=timings,
        )
            await repo.insert_message(conn, conv_id, "assistant", text, timings=timings)
        yield f"data: {json.dumps({'type': 'token', 'text': text})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'citations': [], 'refused': True})}\n\n"
        return

    # Build prompt
    messages = build_messages(question, passages, history, kb_name, image_bytes)

    # Stream answer
    t3 = time.monotonic()
    full_text = ""
    async for token in chat.stream(messages, max_tokens=1024, temperature=0.7):
        full_text += token
        yield f"data: {json.dumps({'type': 'token', 'text': token})}\n\n"
    timings["generate"] = time.monotonic() - t3

    # Check citations
    cleaned, used_passages = check_citations(full_text, passages)
    citation_objects = build_citation_objects(used_passages)

    # Store turn
    async with pool.acquire() as conn:
        await repo.insert_message(
            conn, conv_id, "user", question, image_key=image_key, timings=timings,
        )
        await repo.insert_message(
            conn, conv_id, "assistant", cleaned,
            citations=citation_objects, timings=timings,
        )

    timings["total"] = time.monotonic() - t0
    done = {"type": "done", "citations": citation_objects, "timings": timings}
    yield f"data: {json.dumps(done)}\n\n"
