"""Embed chunks and images; store in DB."""

from __future__ import annotations

import uuid
from pathlib import Path

import asyncpg  # type: ignore[import-untyped]

from server.db import repo
from server.ingest.chunk import Chunk
from server.providers.base import EmbeddingProvider

BATCH_SIZE = 16


async def embed_chunks(
    conn: asyncpg.Connection,
    chunks: list[Chunk],
    chunk_ids: list[uuid.UUID],
    embedder: EmbeddingProvider,
    model_key: str,
    object_dir: Path,
) -> None:
    texts = [c.text for c in chunks]

    # Embed in batches
    all_vecs: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        vecs = await embedder.embed_documents(batch)
        all_vecs.extend(vecs)

    for chunk_id, vec in zip(chunk_ids, all_vecs):
        await repo.insert_embedding(conn, chunk_id, model_key, vec)

    # Store figure objects and, if the embedder supports it, embed images too
    for chunk, chunk_id in zip(chunks, chunk_ids):
        if chunk.figure is None:
            continue
        fig_path = object_dir / f"fig_{chunk_id}.jpg"
        fig_path.write_bytes(chunk.figure)
        img_vec = await embedder.embed_image(chunk.figure)
        if img_vec is not None:
            await repo.insert_embedding(
                conn, chunk_id, model_key + ":img", img_vec
            )
