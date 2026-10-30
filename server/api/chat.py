"""Chat: SSE streaming answer endpoint + conversation management."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from server.app.deps import chat_provider, embed_provider, rerank_provider
from server.app.settings import get_settings
from server.db import repo
from server.db.pool import get_pool
from server.pipeline.ask import ask_stream

router = APIRouter(prefix="/kb/{kb_id}", tags=["chat"])

MAX_IMAGE_BYTES = 10 * 1024 * 1024
IMAGE_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


# ── Conversations ──────────────────────────────────────────────────────────────

@router.post("/conversations", status_code=201)
async def create_conversation(kb_id: uuid.UUID) -> dict:
    async with get_pool().acquire() as conn:
        return await repo.create_conversation(conn, kb_id)


@router.get("/conversations")
async def list_conversations(kb_id: uuid.UUID) -> list[dict]:
    async with get_pool().acquire() as conn:
        return await repo.list_conversations(conn, kb_id)


@router.get("/conversations/{conv_id}/messages")
async def get_messages(kb_id: uuid.UUID, conv_id: uuid.UUID) -> list[dict]:
    async with get_pool().acquire() as conn:
        return await repo.get_messages(conn, conv_id, limit=500)


# ── Ask (SSE) ─────────────────────────────────────────────────────────────────

@router.post("/conversations/{conv_id}/ask")
async def ask(
    kb_id: uuid.UUID,
    conv_id: uuid.UUID,
    question: str = Form(...),
    image: UploadFile | None = None,
) -> StreamingResponse:
    async with get_pool().acquire() as conn:
        kb = await repo.get_kb(conn, kb_id)
        if not kb:
            raise HTTPException(404, "Knowledge base not found")
        conv = await repo.get_conversation(conn, conv_id)
        if not conv:
            raise HTTPException(404, "Conversation not found")

    settings = get_settings()
    image_bytes: bytes | None = None
    image_key: str | None = None
    if image:
        image_bytes = await image.read()
        if len(image_bytes) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "Image is larger than 10 MB")
        ext = IMAGE_EXT.get(image.content_type or "", ".jpg")
        image_key = f"img_{uuid.uuid4().hex}{ext}"
        object_dir = Path(settings.object_dir)
        object_dir.mkdir(parents=True, exist_ok=True)
        (object_dir / image_key).write_bytes(image_bytes)

    pool = get_pool()

    async def _generate():
        async for chunk in ask_stream(
            pool, kb_id, conv_id, question,
            chat_provider(), embed_provider(), settings.model_key,
            rerank_provider(), image_bytes, image_key,
        ):
            yield chunk

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
