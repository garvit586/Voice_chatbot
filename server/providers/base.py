"""Capability protocols — the rest of the code depends only on these."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ChatProvider(Protocol):
    async def stream(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int,
        temperature: float = 0.7,
        json_schema: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]: ...

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int,
        temperature: float = 0.3,
        json_schema: dict[str, Any] | None = None,
    ) -> str: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    async def embed_query(self, text: str) -> list[float]: ...
    async def embed_image(self, image_bytes: bytes) -> list[float] | None:
        """None when the provider does not support image embeddings."""
        ...


@runtime_checkable
class TranscriptionProvider(Protocol):
    async def transcribe(
        self, audio: bytes, mime: str = "audio/wav", language: str | None = None
    ) -> str: ...


@runtime_checkable
class SpeechProvider(Protocol):
    async def speak(self, text: str) -> AsyncIterator[bytes]:
        """Yields 24 kHz 16-bit mono PCM chunks."""
        ...


@runtime_checkable
class RerankProvider(Protocol):
    async def rerank(
        self, query: str, documents: list[str], top_n: int = 6
    ) -> list[int]:
        """Returns indices of ``documents`` in relevance order (best first)."""
        ...
