"""Plain SQL repository — all queries in one place."""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg  # type: ignore[import-untyped]

# ── Knowledge bases ───────────────────────────────────────────────────────────

async def create_kb(conn: asyncpg.Connection, name: str, description: str) -> dict[str, Any]:
    row = await conn.fetchrow(
        "INSERT INTO knowledge_base(name, description) VALUES($1,$2) RETURNING *",
        name, description,
    )
    return dict(row)


async def list_kbs(conn: asyncpg.Connection) -> list[dict[str, Any]]:
    rows = await conn.fetch("SELECT * FROM knowledge_base ORDER BY created_at DESC")
    return [dict(r) for r in rows]


async def get_kb(conn: asyncpg.Connection, kb_id: uuid.UUID) -> dict[str, Any] | None:
    row = await conn.fetchrow("SELECT * FROM knowledge_base WHERE id=$1", kb_id)
    return dict(row) if row else None


# ── Documents ─────────────────────────────────────────────────────────────────

async def create_document(
    conn: asyncpg.Connection, kb_id: uuid.UUID, title: str,
    mime: str, object_key: str, sha256: str,
) -> dict[str, Any]:
    row = await conn.fetchrow(
        """INSERT INTO document(kb_id, title, mime, object_key, sha256)
           VALUES($1,$2,$3,$4,$5) RETURNING *""",
        kb_id, title, mime, object_key, sha256,
    )
    return dict(row)


async def set_document_status(
    conn: asyncpg.Connection, doc_id: uuid.UUID, status: str,
    pages: int = 0, error_msg: str | None = None,
) -> None:
    await conn.execute(
        "UPDATE document SET status=$2, pages=$3, error_msg=$4 WHERE id=$1",
        doc_id, status, pages, error_msg,
    )


async def list_documents(conn: asyncpg.Connection, kb_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        "SELECT * FROM document WHERE kb_id=$1 ORDER BY created_at DESC", kb_id
    )
    return [dict(r) for r in rows]


# ── Chunks ────────────────────────────────────────────────────────────────────

async def insert_chunks(
    conn: asyncpg.Connection,
    rows: list[tuple[uuid.UUID, uuid.UUID, int, int, str, str, str | None]],
    # (doc_id, kb_id, page, ordinal, heading, text, figure_key)
) -> list[uuid.UUID]:
    ids: list[uuid.UUID] = []
    for doc_id, kb_id, page, ordinal, heading, text, figure_key in rows:
        row = await conn.fetchrow(
            """INSERT INTO chunk(document_id, kb_id, page, ordinal, heading, text, figure_key)
               VALUES($1,$2,$3,$4,$5,$6,$7) RETURNING id""",
            doc_id, kb_id, page, ordinal, heading, text, figure_key,
        )
        ids.append(row["id"])
    return ids


async def insert_embedding(
    conn: asyncpg.Connection, chunk_id: uuid.UUID, model_key: str,
    embedding: list[float],
) -> None:
    # pgvector expects a string literal like '[0.1,0.2,...]' cast to vector.
    vec_str = "[" + ",".join(str(v) for v in embedding) + "]"
    await conn.execute(
        """INSERT INTO chunk_embedding(chunk_id, model_key, embedding)
           VALUES($1,$2,$3::vector) ON CONFLICT DO NOTHING""",
        chunk_id, model_key, vec_str,
    )


# ── Hybrid search ─────────────────────────────────────────────────────────────

async def vector_search(
    conn: asyncpg.Connection, kb_id: uuid.UUID, model_key: str,
    query_vec: list[float], top_k: int = 20,
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """SELECT c.id, c.document_id, c.page, c.heading, c.text, c.figure_key,
                  (ce.embedding <=> $3::vector) AS distance
           FROM chunk c
           JOIN chunk_embedding ce ON ce.chunk_id = c.id AND ce.model_key = $2
           WHERE c.kb_id = $1
           ORDER BY ce.embedding <=> $3::vector
           LIMIT $4""",
        kb_id, model_key, "[" + ",".join(str(v) for v in query_vec) + "]", top_k,
    )
    return [dict(r) for r in rows]


async def fts_search(
    conn: asyncpg.Connection, kb_id: uuid.UUID, query: str, top_k: int = 20,
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """SELECT c.id, c.document_id, c.page, c.heading, c.text, c.figure_key,
                  ts_rank(c.tsv, plainto_tsquery('english',$2)) AS rank
           FROM chunk c
           WHERE c.kb_id = $1 AND c.tsv @@ plainto_tsquery('english',$2)
           ORDER BY rank DESC
           LIMIT $3""",
        kb_id, query, top_k,
    )
    return [dict(r) for r in rows]


async def get_chunk(conn: asyncpg.Connection, chunk_id: uuid.UUID) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """SELECT c.*, d.title AS doc_title
           FROM chunk c JOIN document d ON d.id = c.document_id
           WHERE c.id = $1""",
        chunk_id,
    )
    return dict(row) if row else None


async def get_document_titles(conn: asyncpg.Connection, kb_id: uuid.UUID) -> list[str]:
    rows = await conn.fetch(
        "SELECT title FROM document WHERE kb_id=$1 AND status='ready'", kb_id
    )
    return [r["title"] for r in rows]


# ── Conversations ─────────────────────────────────────────────────────────────

async def create_conversation(
    conn: asyncpg.Connection, kb_id: uuid.UUID, title: str = "",
) -> dict[str, Any]:
    row = await conn.fetchrow(
        "INSERT INTO conversation(kb_id, title) VALUES($1,$2) RETURNING *", kb_id, title
    )
    return dict(row)


async def list_conversations(
    conn: asyncpg.Connection, kb_id: uuid.UUID,
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        "SELECT * FROM conversation WHERE kb_id=$1 ORDER BY last_at DESC", kb_id
    )
    return [dict(r) for r in rows]


async def get_conversation(
    conn: asyncpg.Connection, conv_id: uuid.UUID,
) -> dict[str, Any] | None:
    row = await conn.fetchrow("SELECT * FROM conversation WHERE id=$1", conv_id)
    return dict(row) if row else None


async def list_all_conversations(
    conn: asyncpg.Connection, limit: int = 200,
) -> list[dict[str, Any]]:
    """Conversations that have at least one message, newest first, with their KB name."""
    rows = await conn.fetch(
        """SELECT c.id, c.kb_id, c.title, c.created_at, c.last_at, kb.name AS kb_name
           FROM conversation c JOIN knowledge_base kb ON kb.id = c.kb_id
           WHERE EXISTS (SELECT 1 FROM message m WHERE m.conversation_id = c.id)
           ORDER BY c.last_at DESC
           LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


async def rename_conversation(
    conn: asyncpg.Connection, conv_id: uuid.UUID, title: str,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        "UPDATE conversation SET title=$2 WHERE id=$1 RETURNING *", conv_id, title
    )
    return dict(row) if row else None


async def delete_conversation(conn: asyncpg.Connection, conv_id: uuid.UUID) -> bool:
    result = await conn.execute("DELETE FROM conversation WHERE id=$1", conv_id)
    return result.endswith(" 1")


async def delete_document(
    conn: asyncpg.Connection, kb_id: uuid.UUID, doc_id: uuid.UUID,
) -> bool:
    result = await conn.execute(
        "DELETE FROM document WHERE id=$1 AND kb_id=$2", doc_id, kb_id
    )
    return result.endswith(" 1")


def _decode_message(row: asyncpg.Record) -> dict[str, Any]:
    # asyncpg returns jsonb columns as text.
    msg = dict(row)
    for key in ("citations", "timings"):
        if isinstance(msg.get(key), str):
            msg[key] = json.loads(msg[key])
    return msg


async def get_messages(
    conn: asyncpg.Connection, conv_id: uuid.UUID, limit: int = 20,
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        "SELECT * FROM message WHERE conversation_id=$1 ORDER BY created_at DESC LIMIT $2",
        conv_id, limit,
    )
    return list(reversed([_decode_message(r) for r in rows]))


async def insert_message(
    conn: asyncpg.Connection,
    conv_id: uuid.UUID, role: str, text: str,
    image_key: str | None = None,
    citations: list[Any] | None = None,
    timings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = await conn.fetchrow(
        """INSERT INTO message(conversation_id, role, text, image_key, citations, timings)
           VALUES($1,$2,$3,$4,$5,$6) RETURNING *""",
        conv_id, role, text, image_key,
        json.dumps(citations or []), json.dumps(timings or {}),
    )
    # The first question becomes the conversation's title.
    await conn.execute(
        """UPDATE conversation
           SET last_at = now(),
               title = CASE WHEN title = '' AND $2 = 'user'
                            THEN left(regexp_replace($3, '\\s+', ' ', 'g'), 80)
                            ELSE title END
           WHERE id = $1""",
        conv_id, role, text,
    )
    return _decode_message(row)
