"""Knowledge base CRUD."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.db import repo
from server.db.pool import get_pool

router = APIRouter(prefix="/kb", tags=["kb"])


class KBCreate(BaseModel):
    name: str
    description: str = ""


@router.post("", status_code=201)
async def create_kb(body: KBCreate) -> dict:
    async with get_pool().acquire() as conn:
        return await repo.create_kb(conn, body.name, body.description)


@router.get("")
async def list_kbs() -> list[dict]:
    async with get_pool().acquire() as conn:
        return await repo.list_kbs(conn)


@router.get("/{kb_id}")
async def get_kb(kb_id: uuid.UUID) -> dict:
    async with get_pool().acquire() as conn:
        kb = await repo.get_kb(conn, kb_id)
    if not kb:
        raise HTTPException(404, "Knowledge base not found")
    return kb
