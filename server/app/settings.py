"""All configuration from environment variables (via .env)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql://vchat:vchat@localhost:5433/vchat"

    # Object storage
    object_dir: str = "./data/objects"

    # Chat / VLM
    chat_base_url: str = "https://api.openai.com/v1"
    chat_api_key: str = ""
    chat_model: str = "gpt-4o-mini"
    chat_vllm: bool = False      # true for vLLM servers: top_k + Qwen3 thinking off
    chat_timeout_s: float = 60.0

    # Embeddings (embed_dims must equal the vector(N) column in migration 0002)
    embed_base_url: str = "https://api.openai.com/v1"
    embed_api_key: str = ""
    embed_model: str = "text-embedding-3-large"
    embed_dims: int = 2048
    embed_input_style: str = "plain"   # plain | qwen_chat_template
    embed_images: bool = False

    # ASR
    asr_base_url: str = "https://api.openai.com/v1"
    asr_api_key: str = ""
    asr_model: str = "whisper-1"
    asr_timeout_s: float = 30.0  # seconds; default AsyncOpenAI is 600 — too long for voice

    # TTS
    tts_base_url: str = "https://api.openai.com/v1"
    tts_api_key: str = ""
    tts_model: str = "tts-1"
    tts_voice: str = "alloy"
    tts_format: str = "pcm"   # the browser player needs 24 kHz 16-bit mono PCM

    # Rerank (optional)
    rerank_base_url: str = ""
    rerank_api_key: str = ""

    @property
    def model_key(self) -> str:
        return f"{self.embed_model}:{self.embed_dims}:{self.embed_input_style}"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
