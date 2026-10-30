"""OpenAI-SDK adapters for all four capabilities.

Provider quirks (Qwen chat-template wrapping, image embedding) are isolated here.
Every caller sees only the Protocol from providers.base.
"""

from __future__ import annotations

import base64
import io
import re
import wave
from collections.abc import AsyncIterator
from typing import Any

import httpx
from openai import AsyncOpenAI

from server.app.settings import Settings

# ── helpers ───────────────────────────────────────────────────────────────────

_QWEN_DOC_TMPL = (
    "<|im_start|>system\nRepresent the document for retrieval.<|im_end|>\n"
    "<|im_start|>user\n{text}<|im_end|>\n<|im_start|>assistant\n"
)
_QWEN_QUERY_TMPL = (
    "<|im_start|>system\n"
    "Retrieve text or images relevant to the user's question.<|im_end|>\n"
    "<|im_start|>user\n{text}<|im_end|>\n<|im_start|>assistant\n"
)
_SPECIAL = re.compile(r"<\|[^|]+\|>")


def _wrap_doc(text: str, style: str) -> str:
    clean = _SPECIAL.sub("", text).strip()
    if style == "qwen_chat_template":
        return _QWEN_DOC_TMPL.format(text=clean)
    return text


def _wrap_query(text: str, style: str) -> str:
    clean = _SPECIAL.sub("", text).strip()
    if style == "qwen_chat_template":
        return _QWEN_QUERY_TMPL.format(text=clean)
    return text


def _data_url(image_bytes: bytes) -> str:
    b64 = base64.b64encode(image_bytes).decode()
    return f"data:image/jpeg;base64,{b64}"


def _pcm_to_wav(pcm: bytes, sample_rate: int = 24_000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


# ── Chat ──────────────────────────────────────────────────────────────────────

class OpenAIChat:
    def __init__(self, settings: Settings) -> None:
        self._client = AsyncOpenAI(
            base_url=settings.chat_base_url,
            api_key=settings.chat_api_key or "x",
            timeout=settings.chat_timeout_s,
        )
        self._model = settings.chat_model
        self._vllm = settings.chat_vllm

    async def stream(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int,
        temperature: float = 0.7,
        json_schema: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        if self._vllm:
            # vLLM-only sampling knobs; OpenAI rejects them with HTTP 400.
            # Thinking off: Qwen3 otherwise reasons first, adding seconds per answer.
            kwargs["extra_body"] = {
                "top_k": 20,
                "chat_template_kwargs": {"enable_thinking": False},
            }
        if json_schema:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "response", "schema": json_schema},
            }
        stream = await self._client.chat.completions.create(**kwargs)
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int,
        temperature: float = 0.3,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        parts: list[str] = []
        async for tok in self.stream(
            messages, max_tokens=max_tokens, temperature=temperature,
            json_schema=json_schema,
        ):
            parts.append(tok)
        return "".join(parts)


# ── Embeddings ────────────────────────────────────────────────────────────────

class OpenAIEmbeddings:
    def __init__(self, settings: Settings) -> None:
        self._client = AsyncOpenAI(
            base_url=settings.embed_base_url, api_key=settings.embed_api_key or "x"
        )
        self._model = settings.embed_model
        self._dims = settings.embed_dims
        self._style = settings.embed_input_style
        self._images = settings.embed_images

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        wrapped = [_wrap_doc(t, self._style) for t in texts]
        if self._style == "qwen_chat_template":
            # Qwen: send as chat messages
            results: list[list[float]] = []
            for w in wrapped:
                resp = await self._client.embeddings.create(
                    model=self._model,
                    input=w,
                    extra_body={
                        "add_generation_prompt": True,
                        "add_special_tokens": True,
                    },
                )
                results.append(resp.data[0].embedding)
            return results
        resp = await self._client.embeddings.create(
            model=self._model, input=wrapped, **self._dims_kwarg()
        )
        return [d.embedding for d in resp.data]

    def _dims_kwarg(self) -> dict[str, Any]:
        # OpenAI text-embedding-3-* can shorten vectors to match the DB column.
        if "text-embedding-3" in self._model:
            return {"dimensions": self._dims}
        return {}

    async def embed_query(self, text: str) -> list[float]:
        wrapped = _wrap_query(text, self._style)
        if self._style == "qwen_chat_template":
            resp = await self._client.embeddings.create(
                model=self._model,
                input=wrapped,
                extra_body={"add_generation_prompt": True, "add_special_tokens": True},
            )
        else:
            resp = await self._client.embeddings.create(
                model=self._model, input=wrapped, **self._dims_kwarg()
            )
        return resp.data[0].embedding

    async def embed_image(self, image_bytes: bytes) -> list[float] | None:
        if not self._images:
            return None
        messages = [
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": _data_url(image_bytes)}},
            ]},
        ]
        resp = await self._client.embeddings.create(
            model=self._model,
            input=messages,  # type: ignore[arg-type]
            extra_body={"add_generation_prompt": True, "add_special_tokens": True},
        )
        return resp.data[0].embedding


# ── ASR ───────────────────────────────────────────────────────────────────────

class OpenAITranscription:
    def __init__(self, settings: Settings, timeout_s: float = 30.0) -> None:
        self._client = AsyncOpenAI(
            base_url=settings.asr_base_url,
            api_key=settings.asr_api_key or "x",
            timeout=timeout_s,      # default AsyncOpenAI is 600 s — way too long for voice
        )
        self._model = settings.asr_model
        self._timeout = timeout_s

    async def transcribe(
        self, audio: bytes, mime: str = "audio/wav", language: str | None = None
    ) -> str:
        # WAV is the format every speech-to-text server accepts.
        # Convert webm/opus blobs from MediaRecorder → wav so the server
        # doesn't have to guess the codec.
        is_webm = "webm" in mime or "ogg" in mime
        if is_webm:
            # Try ffmpeg first (available in many Docker images); fall back to
            # sending the raw bytes and letting the server handle it.
            try:
                import asyncio
                proc = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-y", "-i", "pipe:0",
                    "-ar", "16000", "-ac", "1", "-f", "wav", "pipe:1",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                wav_bytes, _ = await asyncio.wait_for(
                    proc.communicate(audio), timeout=10
                )
                if wav_bytes:
                    audio = wav_bytes
                    mime = "audio/wav"
            except Exception:
                pass  # send as-is; the ASR server may still handle it

        ext = "wav" if "wav" in mime else "webm"
        kwargs: dict[str, Any] = {
            "model": self._model,
            "file": (f"audio.{ext}", audio, mime),
            "response_format": "json",
        }
        if language:
            kwargs["language"] = language.split("-")[0].lower()
        try:
            resp = await self._client.audio.transcriptions.create(**kwargs)
            return resp.text.strip()
        except Exception as exc:
            raise RuntimeError(f"ASR failed ({type(exc).__name__}): {exc}") from exc


# ── TTS ───────────────────────────────────────────────────────────────────────

class OpenAISpeech:
    CHUNK = 4_800  # 100 ms of 24 kHz 16-bit mono

    def __init__(self, settings: Settings) -> None:
        self._http = httpx.AsyncClient(
            base_url=settings.tts_base_url,
            headers={"Authorization": f"Bearer {settings.tts_api_key or 'x'}"},
            timeout=httpx.Timeout(30, connect=5),
        )
        self._model = settings.tts_model
        self._voice = settings.tts_voice
        self._fmt = settings.tts_format

    async def speak(self, text: str) -> AsyncIterator[bytes]:
        payload = {
            "model": self._model,
            "voice": self._voice,
            "input": text.strip(),
            "response_format": self._fmt,
        }
        async with self._http.stream("POST", "/audio/speech", json=payload) as resp:
            resp.raise_for_status()
            carry = b""
            async for chunk in resp.aiter_bytes(self.CHUNK):
                whole = carry + chunk
                cut = len(whole) - len(whole) % 2
                carry = whole[cut:]
                if cut:
                    yield whole[:cut]


# ── Rerank ────────────────────────────────────────────────────────────────────

class OpenAIRerank:
    def __init__(self, base_url: str, api_key: str) -> None:
        self._http = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key or 'x'}"},
            timeout=30,
        )

    async def rerank(
        self, query: str, documents: list[str], top_n: int = 6
    ) -> list[int]:
        # Relative to RERANK_BASE_URL, which ends in /v1 like every other *_BASE_URL.
        resp = await self._http.post(
            "/rerank",
            json={"query": query, "documents": documents, "top_n": top_n},
        )
        resp.raise_for_status()
        results = resp.json()["results"]
        ranked = sorted(results, key=lambda x: x["relevance_score"], reverse=True)
        return [r["index"] for r in ranked]
