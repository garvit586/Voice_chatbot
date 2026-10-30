#!/usr/bin/env python3
"""Smoke test: checks /healthz, then calls each model capability once.

Usage:
    python scripts/smoke.py [--base-url http://localhost:8000]

Reads credentials from the .env in the project root (or env vars directly).
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import wave
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

import httpx  # noqa: E402  (after load_dotenv so env vars are set first)


def ok(label: str) -> None:
    print(f"  \033[32m✓\033[0m {label}")


def fail(label: str, detail: str) -> None:
    print(f"  \033[31m✗\033[0m {label}: {detail}")


def check_api(base: str) -> bool:
    r = httpx.get(f"{base}/healthz", timeout=5)
    if r.status_code == 200 and r.json().get("status") == "ok":
        ok(f"API /healthz → {r.json()}")
        return True
    fail("API /healthz", f"status={r.status_code}")
    return False


def check_chat() -> bool:
    from openai import OpenAI
    client = OpenAI(
        base_url=os.environ["CHAT_BASE_URL"],
        api_key=os.environ.get("CHAT_API_KEY", "x"),
    )
    resp = client.chat.completions.create(
        model=os.environ.get("CHAT_MODEL", "gpt-4o-mini"),
        messages=[{"role": "user", "content": "Reply with just the word PONG."}],
        max_tokens=10,
        temperature=0,
    )
    text = resp.choices[0].message.content or ""
    if "PONG" in text.upper():
        ok(f"Chat → {text.strip()!r}")
        return True
    fail("Chat", f"unexpected: {text!r}")
    return False


def check_embed() -> bool:
    from openai import OpenAI
    style = os.environ.get("EMBED_INPUT_STYLE", "plain")
    text = "test query"
    if style == "qwen_chat_template":
        text = (
            "<|im_start|>system\nRepresent the document for retrieval.<|im_end|>\n"
            "<|im_start|>user\ntest<|im_end|>\n<|im_start|>assistant\n"
        )
    client = OpenAI(
        base_url=os.environ["EMBED_BASE_URL"],
        api_key=os.environ.get("EMBED_API_KEY", "x"),
    )
    resp = client.embeddings.create(
        model=os.environ.get("EMBED_MODEL", "text-embedding-3-large"),
        input=text,
    )
    vec = resp.data[0].embedding
    ok(f"Embed → {len(vec)}-dim vector, first={vec[0]:.4f}")
    return True


def _silent_wav(seconds: float = 0.5, sample_rate: int = 16_000) -> bytes:
    n = int(seconds * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(b"\x00\x00" * n)
    return buf.getvalue()


def check_asr() -> bool:
    from openai import OpenAI
    client = OpenAI(
        base_url=os.environ["ASR_BASE_URL"],
        api_key=os.environ.get("ASR_API_KEY", "x"),
    )
    try:
        resp = client.audio.transcriptions.create(
            model=os.environ.get("ASR_MODEL", "whisper-1"),
            file=("silence.wav", _silent_wav(), "audio/wav"),
            response_format="json",
            language="en",
        )
        ok(f"ASR → {resp.text!r} (silence → blank is correct)")
        return True
    except Exception as exc:
        fail("ASR", str(exc))
        return False


def check_tts() -> bool:
    import httpx as hx
    resp = hx.post(
        f"{os.environ['TTS_BASE_URL']}/audio/speech",
        headers={"Authorization": f"Bearer {os.environ.get('TTS_API_KEY','x')}"},
        json={
            "model": os.environ.get("TTS_MODEL", "tts-1"),
            "voice": os.environ.get("TTS_VOICE", "alloy"),
            "input": "Hello.",
            "response_format": os.environ.get("TTS_FORMAT", "pcm"),
        },
        timeout=15,
    )
    if resp.status_code == 200 and len(resp.content) > 100:
        ok(f"TTS → {len(resp.content)} bytes of audio")
        return True
    fail("TTS", f"status={resp.status_code} len={len(resp.content)}")
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()

    print("\nVoice Chatbot — smoke test\n")
    results = []

    print("[1/5] API health")
    results.append(check_api(args.base_url))

    print("[2/5] Chat model")
    results.append(check_chat())

    print("[3/5] Embedding model")
    results.append(check_embed())

    print("[4/5] ASR")
    results.append(check_asr())

    print("[5/5] TTS")
    results.append(check_tts())

    passed = sum(results)
    total = len(results)
    print(f"\n{'All' if passed == total else str(passed)}/{total} checks passed.")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
