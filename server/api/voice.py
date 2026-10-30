"""WebSocket voice endpoint."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from server.app.deps import (
    asr_provider,
    chat_provider,
    embed_provider,
    rerank_provider,
    tts_provider,
)
from server.app.settings import get_settings
from server.db.pool import get_pool
from server.voice.session import run_voice_session

router = APIRouter(tags=["voice"])


@router.websocket("/kb/{kb_id}/conversations/{conv_id}/voice")
async def voice_ws(
    websocket: WebSocket,
    kb_id: uuid.UUID,
    conv_id: uuid.UUID,
) -> None:
    await websocket.accept()
    settings = get_settings()
    try:
        await run_voice_session(
            websocket,
            get_pool(),
            kb_id,
            conv_id,
            asr=asr_provider(),
            tts=tts_provider(),
            chat=chat_provider(),
            embedder=embed_provider(),
            model_key=settings.model_key,
            reranker=rerank_provider(),
        )
    except WebSocketDisconnect:
        pass
