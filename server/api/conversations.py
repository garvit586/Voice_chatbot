"""Conversation history across all knowledge bases (the sidebar)."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from server.app.settings import get_settings
from server.db import repo
from server.db.pool import get_pool

router = APIRouter(tags=["conversations"])

_OBJECT_KEY = re.compile(r"^img_[0-9a-f]{32}\.(jpg|png|webp)$")


class Rename(BaseModel):
    title: str = Field(min_length=1, max_length=120)


@router.get("/conversations")
async def list_conversations() -> list[dict]:
    async with get_pool().acquire() as conn:
        return await repo.list_all_conversations(conn)


@router.get("/conversations/{conv_id}")
async def get_conversation(conv_id: uuid.UUID) -> dict:
    async with get_pool().acquire() as conn:
        conv = await repo.get_conversation(conn, conv_id)
        if not conv:
            raise HTTPException(404, "Conversation not found")
        conv["messages"] = await repo.get_messages(conn, conv_id, limit=500)
    return conv


@router.patch("/conversations/{conv_id}")
async def rename_conversation(conv_id: uuid.UUID, body: Rename) -> dict:
    async with get_pool().acquire() as conn:
        conv = await repo.rename_conversation(conn, conv_id, body.title.strip())
    if not conv:
        raise HTTPException(404, "Conversation not found")
    return conv


@router.delete("/conversations/{conv_id}", status_code=204)
async def delete_conversation(conv_id: uuid.UUID) -> None:
    async with get_pool().acquire() as conn:
        if not await repo.delete_conversation(conn, conv_id):
            raise HTTPException(404, "Conversation not found")


@router.get("/objects/{key}")
async def get_object(key: str) -> FileResponse:
    # Only keys this app generated; blocks path traversal.
    if not _OBJECT_KEY.match(key):
        raise HTTPException(404, "Not found")
    path = Path(get_settings().object_dir) / key
    if not path.is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=86400"})
