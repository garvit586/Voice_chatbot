"""Document upload + ingest + list."""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from server.app.deps import embed_provider
from server.app.settings import get_settings
from server.db import repo
from server.db.pool import get_pool
from server.ingest.jobs import ingest_document

router = APIRouter(prefix="/kb/{kb_id}/documents", tags=["documents"])

_INGEST_TASKS: set[asyncio.Task[None]] = set()


@router.get("")
async def list_documents(kb_id: uuid.UUID) -> list[dict]:
    async with get_pool().acquire() as conn:
        return await repo.list_documents(conn, kb_id)


@router.post("", status_code=202)
async def upload_document(kb_id: uuid.UUID, file: UploadFile) -> dict:
    settings = get_settings()
    data = await file.read()
    sha256 = hashlib.sha256(data).hexdigest()
    mime = file.content_type or "application/octet-stream"
    title = file.filename or "untitled"

    object_dir = Path(settings.object_dir)
    object_dir.mkdir(parents=True, exist_ok=True)
    object_key = f"{sha256}{Path(title).suffix}"
    (object_dir / object_key).write_bytes(data)

    pool = get_pool()
    async with pool.acquire() as conn:
        kb = await repo.get_kb(conn, kb_id)
        if not kb:
            raise HTTPException(404, "Knowledge base not found")
        doc = await repo.create_document(conn, kb_id, title, mime, object_key, sha256)

    doc_id = uuid.UUID(str(doc["id"]))

    # Run ingest in the background
    async def _ingest() -> None:
        await ingest_document(
            pool, doc_id, kb_id, data, mime,
            embed_provider(), settings.model_key,
            object_dir,
        )

    # asyncio keeps only weak references to tasks; hold one so ingestion isn't collected midway.
    task = asyncio.create_task(_ingest())
    _INGEST_TASKS.add(task)
    task.add_done_callback(_INGEST_TASKS.discard)
    return {"id": str(doc_id), "status": "ingesting"}


@router.delete("/{doc_id}", status_code=204)
async def delete_document(kb_id: uuid.UUID, doc_id: uuid.UUID) -> None:
    async with get_pool().acquire() as conn:
        if not await repo.delete_document(conn, kb_id, doc_id):
            raise HTTPException(404, "Document not found")


@router.get("/{doc_id}")
async def get_document(kb_id: uuid.UUID, doc_id: uuid.UUID) -> dict:
    async with get_pool().acquire() as conn:
        docs = await repo.list_documents(conn, kb_id)
    for d in docs:
        if str(d["id"]) == str(doc_id):
            return d
    raise HTTPException(404, "Document not found")
