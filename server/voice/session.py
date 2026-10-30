"""Voice WebSocket session: ASR → pipeline → TTS, with barge-in support."""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
import uuid
from typing import Any

from fastapi import WebSocket

from server.pipeline.ask import ask_stream
from server.providers.base import (
    ChatProvider,
    EmbeddingProvider,
    RerankProvider,
    SpeechProvider,
    TranscriptionProvider,
)
from server.voice.sentences import SentenceBuffer


async def _send_json(ws: WebSocket, payload: dict[str, Any]) -> None:
    await ws.send_text(json.dumps(payload))


_CITATION = re.compile(r"\s*\[\d+\]")


async def _speaker(ws: WebSocket, tts: SpeechProvider, queue: asyncio.Queue[str | None]) -> None:
    """Speaks sentences one at a time, in order, until it reads None."""
    while (sentence := await queue.get()) is not None:
        spoken = _CITATION.sub("", sentence).strip()
        if not spoken:
            continue
        try:
            async for pcm in tts.speak(spoken):
                await ws.send_bytes(pcm)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await _send_json(ws, {"type": "tts_error", "msg": str(exc)[:200]})


async def run_voice_session(
    ws: WebSocket,
    pool: Any,
    kb_id: uuid.UUID,
    conv_id: uuid.UUID,
    asr: TranscriptionProvider,
    tts: SpeechProvider,
    chat: ChatProvider,
    embedder: EmbeddingProvider,
    model_key: str,
    reranker: RerankProvider | None,
) -> None:
    """Drive one WebSocket voice conversation until disconnect."""
    turn: asyncio.Task[None] | None = None

    async def cancel_turn() -> None:
        nonlocal turn
        if turn and not turn.done():
            turn.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await turn
        turn = None

    async def answer(question: str) -> None:
        buf = SentenceBuffer()
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        speaker = asyncio.create_task(_speaker(ws, tts, queue))
        try:
            await _send_json(ws, {"type": "thinking"})
            async for event in ask_stream(
                pool, kb_id, conv_id, question, chat, embedder, model_key, reranker
            ):
                payload = json.loads(event.removeprefix("data: "))
                if payload["type"] == "token":
                    for sentence in buf.feed(payload["text"]):
                        queue.put_nowait(sentence)
                    await _send_json(ws, {"type": "token", "text": payload["text"]})
                elif payload["type"] == "done":
                    for sentence in buf.flush():
                        queue.put_nowait(sentence)
                    queue.put_nowait(None)
                    await speaker
                    await _send_json(ws, {
                        "type": "done",
                        "citations": payload.get("citations", []),
                        "refused": payload.get("refused", False),
                    })
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await _send_json(ws, {"type": "error", "msg": str(exc)[:200]})
        finally:
            speaker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await speaker

    try:
        while True:
            data = await ws.receive()
            if data["type"] == "websocket.disconnect":
                break
            if data.get("bytes"):
                await cancel_turn()
                await _send_json(ws, {"type": "transcribing"})
                try:
                    transcript = await asr.transcribe(data["bytes"], mime="audio/webm")
                except Exception as exc:
                    await _send_json(ws, {"type": "asr_error", "msg": str(exc)[:200]})
                    continue
                if not transcript.strip():
                    await _send_json(ws, {"type": "done", "citations": [], "refused": False})
                    continue
                await _send_json(ws, {"type": "transcript", "text": transcript})
                turn = asyncio.create_task(answer(transcript))
            elif data.get("text"):
                msg = json.loads(data["text"])
                await cancel_turn()
                if msg.get("type") == "text" and msg.get("text", "").strip():
                    turn = asyncio.create_task(answer(msg["text"].strip()))
    finally:
        await cancel_turn()
