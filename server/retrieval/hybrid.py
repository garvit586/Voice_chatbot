"""Hybrid retrieval: exact pgvector + FTS, fused with RRF, optional rerank."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import asyncpg  # type: ignore[import-untyped]

from server.db import repo
from server.providers.base import EmbeddingProvider, RerankProvider
from server.retrieval.rrf import rrf

TOP_K_EACH = 20
FINAL_K = 8


async def retrieve(
    pool: asyncpg.Pool,
    kb_id: uuid.UUID,
    query: str,
    embedder: EmbeddingProvider,
    model_key: str,
    reranker: RerankProvider | None = None,
    top_k: int = FINAL_K,
) -> list[dict[str, Any]]:
    """Returns up to ``top_k`` chunks, each with doc_title, page, text, heading, id."""
    query_vec = await embedder.embed_query(query)

    # Each leg gets its own connection — asyncpg connections are not safe
    # to share across concurrent coroutines (raises "another operation in progress").
    async def _vec() -> list[dict[str, Any]]:
        async with pool.acquire() as conn:
            return await repo.vector_search(conn, kb_id, model_key, query_vec, TOP_K_EACH)

    async def _fts() -> list[dict[str, Any]]:
        async with pool.acquire() as conn:
            return await repo.fts_search(conn, kb_id, query, TOP_K_EACH)

    vec_hits, fts_hits = await asyncio.gather(_vec(), _fts())

    fused = rrf(vec_hits, fts_hits, top_k=top_k * 2)

    if not fused:
        return []

    # Enrich with document title — sequential, single connection
    async with pool.acquire() as conn:
        enriched: list[dict[str, Any]] = []
        for chunk in fused:
            full = await repo.get_chunk(conn, chunk["id"])
            if full:
                enriched.append(full)
    fused = enriched

    if reranker and len(fused) > 1:
        texts = [c["text"] for c in fused]
        order = await reranker.rerank(query, texts, top_n=top_k)
        fused = [fused[i] for i in order]

    return fused[:top_k]
