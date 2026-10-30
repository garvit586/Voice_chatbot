"""Run the full ingest pipeline for one document."""

from __future__ import annotations

import uuid
from pathlib import Path

import asyncpg  # type: ignore[import-untyped]

from server.db import repo
from server.ingest.chunk import Chunk, chunk_pages
from server.ingest.parse import parse
from server.providers.base import EmbeddingProvider

BATCH_SIZE = 16


async def _compute_embeddings(
    chunks: list[Chunk],
    chunk_ids: list[uuid.UUID],
    embedder: EmbeddingProvider,
    object_dir: Path,
) -> tuple[list[list[float]], list[tuple[uuid.UUID, list[float]]]]:
    texts = [c.text for c in chunks]
    all_vecs: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        vecs = await embedder.embed_documents(texts[i : i + BATCH_SIZE])
        all_vecs.extend(vecs)

    img_vecs: list[tuple[uuid.UUID, list[float]]] = []
    for chunk, chunk_id in zip(chunks, chunk_ids):
        if chunk.figure is None:
            continue
        fig_path = object_dir / f"fig_{chunk_id}.jpg"
        fig_path.write_bytes(chunk.figure)
        img_vec = await embedder.embed_image(chunk.figure)
        if img_vec is not None:
            img_vecs.append((chunk_id, img_vec))

    return all_vecs, img_vecs


async def ingest_document(
    pool: asyncpg.Pool,
    doc_id: uuid.UUID,
    kb_id: uuid.UUID,
    data: bytes,
    mime: str,
    embedder: EmbeddingProvider,
    model_key: str,
    object_dir: Path,
) -> int:
    try:
        async with pool.acquire() as conn:
            await repo.set_document_status(conn, doc_id, "ingesting")

        pages = parse(data, mime)
        chunks = chunk_pages(pages)

        if not chunks:
            async with pool.acquire() as conn:
                await repo.set_document_status(conn, doc_id, "ready", pages=0)
            return 0

        # Insert chunks
        rows = [
            (doc_id, kb_id, c.page, c.ordinal, c.heading, c.text, None)
            for c in chunks
        ]
        async with pool.acquire() as conn:
            chunk_ids = await repo.insert_chunks(conn, rows)

        # Embed (external API calls — no connection held)
        vecs, img_vecs = await _compute_embeddings(
            chunks, chunk_ids, embedder, object_dir
        )

        # Persist embeddings
        async with pool.acquire() as conn:
            for chunk_id, vec in zip(chunk_ids, vecs):
                await repo.insert_embedding(conn, chunk_id, model_key, vec)
            for chunk_id, img_vec in img_vecs:
                await repo.insert_embedding(conn, chunk_id, model_key + ":img", img_vec)

        async with pool.acquire() as conn:
            await repo.set_document_status(conn, doc_id, "ready", pages=len(pages))
        return len(chunks)

    except Exception as exc:
        async with pool.acquire() as conn:
            await repo.set_document_status(conn, doc_id, "error", error_msg=str(exc)[:500])
        raise
