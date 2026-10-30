"""FastAPI dependency injection — providers wired from settings."""

from __future__ import annotations

from functools import lru_cache

from server.app.settings import Settings, get_settings
from server.providers.openai_compat import (
    OpenAIChat,
    OpenAIEmbeddings,
    OpenAIRerank,
    OpenAISpeech,
    OpenAITranscription,
)


@lru_cache(maxsize=1)
def chat_provider(settings: Settings | None = None) -> OpenAIChat:
    return OpenAIChat(settings or get_settings())


@lru_cache(maxsize=1)
def embed_provider(settings: Settings | None = None) -> OpenAIEmbeddings:
    return OpenAIEmbeddings(settings or get_settings())


@lru_cache(maxsize=1)
def asr_provider(settings: Settings | None = None) -> OpenAITranscription:
    s = settings or get_settings()
    return OpenAITranscription(s, timeout_s=s.asr_timeout_s)


@lru_cache(maxsize=1)
def tts_provider(settings: Settings | None = None) -> OpenAISpeech:
    return OpenAISpeech(settings or get_settings())


@lru_cache(maxsize=1)
def rerank_provider(settings: Settings | None = None) -> OpenAIRerank | None:
    s = settings or get_settings()
    if not s.rerank_base_url:
        return None
    return OpenAIRerank(s.rerank_base_url, s.rerank_api_key)
