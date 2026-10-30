# Voice Chatbot

**A self-hostable assistant for your own documents.** People can ask by typing, talking or sending a photo. Each answer streams back as text, is spoken aloud, and cites the passages it came from.

It talks to **any OpenAI-compatible API**, such as OpenAI, vLLM, Ollama, Kokoro-FastAPI, Speaches or your own gateway. You configure chat, embeddings, speech-to-text and text-to-speech separately, so you can mix providers and switch between them by editing `.env` only.

```
 Type, speak or attach a photo  ─▶  hybrid search over YOUR documents  ─▶  streamed, cited answer  ─▶  spoken aloud
```

---

## Contents

- [Features](#features)
- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Quick start (fork → run in 10 minutes)](#quick-start)
- [Run with Docker Compose](#run-with-docker-compose)
- [Configuration reference](#configuration-reference)
- [Provider recipes](#provider-recipes)
- [Using the app](#using-the-app)
- [API reference](#api-reference)
- [Tuning](#tuning)
- [Project structure](#project-structure)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [Security and production notes](#security-and-production-notes)
- [Limitations and roadmap](#limitations-and-roadmap)
- [Contributing](#contributing)

---

## Features

| | |
|---|---|
| **Three ways to ask** | Type, talk (tap-to-talk with a live waveform), or attach a photo ("what is wrong here?") |
| **Grounded answers** | The model answers only from retrieved passages and cites them inline as `[1]`, `[2]`. Any citation that doesn't point at a retrieved passage is removed before the answer is saved. |
| **Spoken answers** | Speech starts as soon as the first sentence is complete, while the model is still writing the rest. Tap the mic to interrupt. |
| **Hybrid retrieval** | Exact vector search (pgvector) plus Postgres full-text search, merged with Reciprocal Rank Fusion; optional reranker |
| **Knowledge bases** | Separate document collections. Search is filtered by knowledge base in SQL, so answers never mix collections. |
| **Conversation history** | A sidebar grouped by date, with search, rename and delete. Titles are set automatically, and the open chat survives a page refresh. |
| **Any provider** | One OpenAI-compatible base URL, key and model per capability, so you can mix providers |
| **Professional UI** | Light and dark themes, markdown answers with tables and code, a sources panel, a documents manager with drag-and-drop, works on phones |
| **One database** | PostgreSQL + pgvector stores documents, vectors, chats and history; there is no separate vector database |

---

## How it works

```
 Browser (React + Vite)
   text · photo · tap-to-talk · 24 kHz PCM audio player
        │ HTTP + SSE  (/api/…/ask)              │ WebSocket  (/api/…/voice)
        ▼                                       ▼
 FastAPI server (one async process)
   providers/   OpenAI-compatible clients: chat · embeddings · ASR · TTS · rerank
   ingest/      PDF/TXT/MD → text → ~400-token chunks → embeddings → Postgres
   retrieval/   pgvector cosine ‖ full-text search → RRF fusion → (rerank) → top 8
   pipeline/    rewrite follow-up → retrieve → prompt → stream → citation check → save
   voice/       speech-to-text → pipeline → sentence splitter → TTS → PCM over WebSocket
        │
        ▼
 PostgreSQL + pgvector          ./data/objects (uploaded files, photos)
        │
        ▼
 Your model endpoints:  /v1/chat/completions · /v1/embeddings · /v1/audio/transcriptions · /v1/audio/speech · /v1/rerank
```

### The answer pipeline (text, photo and voice all use it)

1. **Rewrite (only when needed).** A follow-up that refers back ("and what about *it*?") or is four words or fewer is rewritten into a standalone search query with one short model call. Standalone questions skip this step, which saves about 0.5 s.
2. **Describe the photo (photo questions only).** The vision model turns the image and the question into a text search query.
3. **Retrieve.** The vector search and the full-text search run in parallel, both limited to the selected knowledge base (top 20 each). Their results are merged with RRF, optionally reranked, and the best 8 passages are kept.
4. **Empty knowledge base.** If nothing at all is found, the server answers with a fixed message listing what the knowledge base contains, without calling the model.
5. **Prompt.** A short system prompt, then the numbered passages (capped at about 3,000 tokens), then the recent history (capped at about 2,000 tokens), then the question, plus the photo if there is one.
6. **Stream.** Tokens are sent to the browser as they arrive; in voice mode, each completed sentence goes to TTS straight away.
7. **Check citations.** Only `[n]` markers that refer to passages actually retrieved are kept; each one becomes a citation object (document, page, passage).
8. **Save.** The question, the answer, the citations and the time each stage took are stored with the conversation.

### A voice turn

```
tap mic → MediaRecorder (webm/opus) → tap ✓ → audio sent over the WebSocket
  → server: ffmpeg converts to 16 kHz WAV (if ffmpeg is installed) → speech-to-text
  → transcript event → answer pipeline → each sentence → TTS (PCM, streamed)
  → 100 ms audio chunks → browser schedules them back to back (no gaps)
  → tapping the mic again stops playback and cancels the server's turn (barge-in)
```

---

## Requirements

| Tool | Version | Notes |
|---|---|---|
| Python | 3.12+ | |
| Node.js | 20.19+ or 22.12+ | Needed by Vite 7 |
| PostgreSQL | 16+ with the **pgvector** extension | The easiest option is Docker: `pgvector/pgvector:pg17` |
| ffmpeg | any recent | Recommended. It converts browser audio to WAV before speech-to-text; without it the raw webm is sent, which OpenAI accepts but some self-hosted servers don't. |
| Model endpoints | OpenAI-compatible | See [Provider recipes](#provider-recipes) |

The chat model must accept images (`image_url` content) if you want photo questions. Text and voice work with any chat model.

---

## Quick start

### 1. Fork and clone

Fork the repository on GitHub, then:

```bash
git clone https://github.com/<your-user>/voice-chatbot.git
cd voice-chatbot
```

### 2. Configure

```bash
cp .env.example .env          # Windows PowerShell: copy .env.example .env
```

Open `.env` and fill in your endpoints and keys. With OpenAI you only need to replace the four `sk-your-key` values. Other providers are covered in [Provider recipes](#provider-recipes).

> **Check this before your first start:** `EMBED_DIMS` must match the vector size in `server/db/migrations/0002_documents.sql` (2048 by default). See [Changing the embedding size](#changing-the-embedding-size).

### 3. Start PostgreSQL

```bash
docker compose up -d postgres            # pgvector/pgvector:pg17 on localhost:5433
```

Using your own Postgres? Set `DATABASE_URL` and run `CREATE EXTENSION vector;` once as a superuser.

### 4. Start the API

```bash
python -m venv .venv
# macOS/Linux:        source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Windows Git Bash:   source .venv/Scripts/activate
pip install -e ".[dev]"

uvicorn server.app.main:app --reload --port 8000
```

Database migrations run automatically when the API starts. Check that it's up: `curl http://localhost:8000/healthz` should return `{"status":"ok"}`. Interactive API docs are at <http://localhost:8000/docs>.

### 5. Start the web app (in a second terminal)

```bash
cd web
npm install
npm run dev                              # http://localhost:5173
```

### 6. Try it

1. Open <http://localhost:5173>, create a knowledge base, and upload a PDF in the **Documents** window.
2. Wait until the document shows **Ready**, then ask a question, tap the mic, or attach a photo.

### 7. (Optional) Check your providers

```bash
python scripts/smoke.py                  # checks /healthz, chat, embeddings, ASR and TTS once each
```

---

## Run with Docker Compose

```bash
cp .env.example .env                     # fill in your keys
docker compose up --build -d
```

| Service | URL | What |
|---|---|---|
| `web` | <http://localhost:5173> | Built React app served by nginx; proxies `/api` (including WebSockets) to the API |
| `api` | <http://localhost:8000> | FastAPI. Uploaded files live in the `objects` volume. |
| `postgres` | `localhost:5433` | PostgreSQL 17 + pgvector, data in the `pgdata` volume |

**Models running on your own machine** (Ollama, vLLM on the host): inside a container, `localhost` means the container itself. Use `http://host.docker.internal:<port>/v1` in `.env` instead; `docker-compose.yml` already maps that name on Linux.

---

## Configuration reference

All settings come from environment variables, which are read from `.env` in the working directory. Names are case-insensitive.

### Chat / vision model

| Variable | Default | Description |
|---|---|---|
| `CHAT_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible root, ending in `/v1` |
| `CHAT_API_KEY` | — | Bearer key |
| `CHAT_MODEL` | `gpt-4o-mini` | Must support images for photo questions |
| `CHAT_VLLM` | `false` | `true` adds vLLM-only settings: `top_k=20` and `chat_template_kwargs.enable_thinking=false` (turns off Qwen3's reasoning step, which is much faster). **Keep `false` for OpenAI and other hosted APIs**, which reject these fields. |
| `CHAT_TIMEOUT_S` | `60` | Request timeout in seconds |

### Embeddings

| Variable | Default | Description |
|---|---|---|
| `EMBED_BASE_URL` | `https://api.openai.com/v1` | |
| `EMBED_API_KEY` | — | |
| `EMBED_MODEL` | `text-embedding-3-large` | |
| `EMBED_DIMS` | `2048` | **Must equal** the `vector(N)` column size. For `text-embedding-3-*` it is also sent as `dimensions`, so OpenAI shortens the vectors to match. |
| `EMBED_INPUT_STYLE` | `plain` | `plain` sends text as it is. `qwen_chat_template` wraps text in the Qwen chat template, with separate document and query instructions, as Qwen3 embedding models served by vLLM expect. |
| `EMBED_IMAGES` | `false` | `true` also embeds page images during ingestion. They are stored but **not yet used in search**; see the [roadmap](#limitations-and-roadmap). Only enable this with an embedding endpoint that accepts images. |

### Speech-to-text

| Variable | Default | Description |
|---|---|---|
| `ASR_BASE_URL` | `https://api.openai.com/v1` | Must serve `POST /audio/transcriptions` |
| `ASR_API_KEY` | — | |
| `ASR_MODEL` | `whisper-1` | |
| `ASR_TIMEOUT_S` | `30` | Voice shows an error instead of waiting longer |

### Text-to-speech

| Variable | Default | Description |
|---|---|---|
| `TTS_BASE_URL` | `https://api.openai.com/v1` | Must serve `POST /audio/speech` |
| `TTS_API_KEY` | — | |
| `TTS_MODEL` | `tts-1` | |
| `TTS_VOICE` | `alloy` | Provider-specific voice name |
| `TTS_FORMAT` | `pcm` | Leave as `pcm`. The browser plays raw **24 kHz, 16-bit, mono PCM**, which OpenAI and Kokoro both return for `pcm`. |

### Rerank (optional)

| Variable | Default | Description |
|---|---|---|
| `RERANK_BASE_URL` | empty (off) | Root ending in `/v1`. The server calls `POST {base}/rerank` with `{query, documents, top_n}` and expects `{"results":[{"index", "relevance_score"}]}` (the Cohere/Jina/vLLM format). |
| `RERANK_API_KEY` | — | |

### Storage

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://vchat:vchat@localhost:5433/vchat` | Any PostgreSQL 16+ database with pgvector |
| `OBJECT_DIR` | `./data/objects` | Where uploaded documents, page images and chat photos are stored |

---

## Provider recipes

Every capability is configured on its own. These recipes are starting points; **check the model names against your provider**, because catalogues change.

### OpenAI (simplest)

This is exactly what `.env.example` contains. Put your key in all four `*_API_KEY` values and keep `CHAT_VLLM=false`.

### Self-hosted (vLLM + Kokoro-FastAPI + Speaches)

You can run the whole stack on your own hardware with no data leaving it. Point each `*_BASE_URL` at the matching server, or at one gateway in front of all of them:

```env
CHAT_BASE_URL=http://gpu-box:8000/v1          # vLLM, e.g. a Qwen2.5-VL or Qwen3-VL model
CHAT_MODEL=<served model name>
CHAT_VLLM=true                                # thinking off, vLLM sampling
EMBED_BASE_URL=http://gpu-box:8001/v1         # vLLM serving an embedding model
EMBED_MODEL=<served embedding model>
EMBED_DIMS=<its output size>                  # and change the DB column to match (see below)
EMBED_INPUT_STYLE=qwen_chat_template          # for Qwen3 embedding models; else plain
ASR_BASE_URL=http://gpu-box:8002/v1           # Speaches (faster-whisper), OpenAI-compatible
ASR_MODEL=Systran/faster-whisper-large-v3
TTS_BASE_URL=http://gpu-box:8880/v1           # Kokoro-FastAPI, OpenAI-compatible
TTS_MODEL=kokoro
TTS_VOICE=af_heart
```

For low voice latency, run this API **on the same machine or LAN as the models**. Each model call over a long network path adds its round-trip time, and a voice turn makes at least three calls (speech-to-text, chat, TTS).

### Local with Ollama (chat + embeddings) and hosted speech

Ollama serves `/v1/chat/completions` and `/v1/embeddings` but has no speech endpoints, so pair it with OpenAI or a self-hosted server for ASR and TTS:

```env
CHAT_BASE_URL=http://localhost:11434/v1
CHAT_API_KEY=ollama
CHAT_MODEL=llama3.2-vision                    # a vision model, for photo questions
CHAT_VLLM=false
EMBED_BASE_URL=http://localhost:11434/v1
EMBED_API_KEY=ollama
EMBED_MODEL=nomic-embed-text
EMBED_DIMS=768                                # → the DB column must be vector(768)
EMBED_INPUT_STYLE=plain
ASR_BASE_URL=https://api.openai.com/v1        # or your Speaches server
TTS_BASE_URL=https://api.openai.com/v1        # or your Kokoro server
```

### Changing the embedding size

The vector column size is fixed in `server/db/migrations/0002_documents.sql` (`vector(2048)`), and it must equal `EMBED_DIMS`.

- **Before the first start:** edit the number in `0002_documents.sql`.
- **On a database that already exists** (migrations never run twice), run this in `psql` and then re-upload your documents:

  ```sql
  TRUNCATE chunk_embedding;
  ALTER TABLE chunk_embedding ALTER COLUMN embedding TYPE vector(768);   -- your size
  ```

- **Switching embedding model** (even at the same size): vectors from different models can't be compared. The server keeps them apart (each vector is tagged with `model:dims:style`), so old documents simply stop matching. **Delete and re-upload documents after you switch.**

---

## Using the app

| Action | How |
|---|---|
| Create a knowledge base | Use the switcher at the bottom of the sidebar, or the first-run screen |
| Add documents | **Documents** → drag files in (PDF, TXT, MD). Status goes from *Processing* to *Ready*. |
| Ask by text | Type and press **Enter** (**Shift+Enter** for a new line). The ■ button stops generation. |
| Ask by voice | Tap 🎤, speak, then tap ✓ (✕ cancels). The answer is spoken as it streams. Tap 🎤 again to interrupt. |
| Ask about a photo | Click the image button, paste an image, or drag one onto the composer. It is shrunk to 1,600 px before upload. |
| See sources | Click a `[n]` badge or a source chip under the answer to open the passage in the side panel |
| History | The sidebar lists every chat with at least one message. Hover a chat to rename or delete it. The open chat is in the URL (`#/c/<id>`). |
| New chat | The **New chat** button, or **Ctrl/Cmd + Shift + O** |
| Mute speech | The speaker icon at the top right |
| Theme | The sun/moon icon in the sidebar (it follows your system theme by default) |

The microphone only works on `http://localhost` or over **HTTPS**, because browsers block microphone access on plain HTTP from any other address.

---

## API reference

Base URL: `http://localhost:8000`. Every JSON route is under `/api`. The full OpenAPI schema is at `/docs` and `/openapi.json`.

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/healthz` | Liveness check → `{"status":"ok"}` |
| `GET` | `/api/kb` | List knowledge bases |
| `POST` | `/api/kb` | Create a knowledge base: `{"name": "...", "description": "..."}` → **201** |
| `GET` | `/api/kb/{kb_id}` | Get one knowledge base |
| `GET` | `/api/kb/{kb_id}/documents` | List its documents with their ingestion status |
| `POST` | `/api/kb/{kb_id}/documents` | Upload a file (multipart field `file`) → **202**; ingestion runs in the background |
| `GET` | `/api/kb/{kb_id}/documents/{doc_id}` | Get one document's status |
| `DELETE` | `/api/kb/{kb_id}/documents/{doc_id}` | Remove a document and its chunks → **204** |
| `POST` | `/api/kb/{kb_id}/conversations` | Start a conversation → **201** |
| `GET` | `/api/kb/{kb_id}/conversations` | Conversations of one knowledge base |
| `GET` | `/api/kb/{kb_id}/conversations/{conv_id}/messages` | Messages, oldest first |
| `POST` | `/api/kb/{kb_id}/conversations/{conv_id}/ask` | **Ask a question**: multipart `question` (+ optional `image`), responds with a **Server-Sent Events** stream |
| `WS` | `/api/kb/{kb_id}/conversations/{conv_id}/voice` | **Voice session** (protocol below) |
| `GET` | `/api/conversations` | History: every conversation that has messages, newest first, with `kb_name` |
| `GET` | `/api/conversations/{conv_id}` | A conversation with all of its `messages` |
| `PATCH` | `/api/conversations/{conv_id}` | Rename: `{"title": "..."}` |
| `DELETE` | `/api/conversations/{conv_id}` | Delete a conversation and its messages → **204** |
| `GET` | `/api/objects/{key}` | A stored chat photo (keys come from `message.image_key`) |

Errors return JSON `{"detail": "..."}` with **404** (not found), **413** (image over 10 MB) or **422** (invalid input).

### Objects

```jsonc
// Knowledge base
{ "id": "uuid", "name": "Manuals", "description": "", "created_at": "2026-10-31T10:00:00Z" }

// Document. status is one of: pending | ingesting | ready | error
{ "id": "uuid", "kb_id": "uuid", "title": "manual.pdf", "mime": "application/pdf",
  "pages": 42, "status": "ready", "error_msg": null, "created_at": "..." }

// Conversation (history list)
{ "id": "uuid", "kb_id": "uuid", "kb_name": "Manuals",
  "title": "How often is the filter replaced?", "created_at": "...", "last_at": "..." }

// Message
{ "id": "uuid", "conversation_id": "uuid", "role": "assistant",
  "text": "Replace it every 4000 hours [1].", "image_key": null,
  "citations": [ { "index": 1, "doc_title": "manual.pdf", "page": 12,
                   "snippet": "The oil filter must be replaced every 4000 running hours…",
                   "chunk_id": "uuid" } ],
  "timings": { "rewrite": 0.0, "retrieve": 0.38, "generate": 1.01, "total": 1.39 },
  "created_at": "..." }
```

### Asking a question (Server-Sent Events)

`POST /api/kb/{kb_id}/conversations/{conv_id}/ask` with `multipart/form-data`:

| Field | Required | |
|---|---|---|
| `question` | yes | The question text |
| `image` | no | JPEG/PNG/WebP, at most 10 MB. Needs a vision-capable chat model. |

The response is `text/event-stream`. Each event is one `data:` line with JSON:

```text
data: {"type": "token", "text": "Replace it"}
data: {"type": "token", "text": " every 4000 hours [1]."}
data: {"type": "done", "citations": [ {"index": 1, "doc_title": "manual.pdf", "page": 12, "snippet": "…", "chunk_id": "…"} ],
       "timings": {"rewrite": 0.0, "retrieve": 0.38, "generate": 1.01, "total": 1.39}}
```

If the knowledge base has no content to search, there is a single token event followed by `{"type": "done", "citations": [], "refused": true}`.

### Voice session (WebSocket)

`ws://localhost:8000/api/kb/{kb_id}/conversations/{conv_id}/voice`. One socket can carry many turns.

**Client → server**

| Message | Meaning |
|---|---|
| *binary* | One complete utterance (webm/opus, ogg, mp4 or wav). The server transcribes it and answers. |
| `{"type": "text", "text": "..."}` | Ask a typed question over the same socket (spoken answer) |
| `{"type": "cancel"}` | Barge-in: stop the current answer and its speech |

**Server → client**

| Message | Meaning |
|---|---|
| `{"type": "transcribing"}` | Audio received, speech-to-text running |
| `{"type": "transcript", "text": "..."}` | What was heard (this becomes the user's message) |
| `{"type": "thinking"}` | Retrieving and generating |
| `{"type": "token", "text": "..."}` | Answer text as it streams |
| *binary* | Answer audio: **24 kHz, 16-bit little-endian, mono PCM**, in ~100 ms chunks, in order |
| `{"type": "done", "citations": [...], "refused": false}` | Turn finished (sent after the last audio chunk) |
| `{"type": "asr_error" \| "tts_error" \| "error", "msg": "..."}` | Something failed; the socket stays open |

If an utterance transcribes to empty text (silence), the server replies with `done` straight away.

### Examples

**curl: create a knowledge base, upload a document and ask**

```bash
API=http://localhost:8000/api
KB=$(curl -s -X POST $API/kb -H 'Content-Type: application/json' -d '{"name":"Manuals"}' | jq -r .id)
curl -s -F "file=@manual.pdf" $API/kb/$KB/documents                 # wait for status "ready"
curl -s $API/kb/$KB/documents | jq '.[] | {title, status}'
CONV=$(curl -s -X POST $API/kb/$KB/conversations | jq -r .id)
curl -N -F "question=How often is the oil filter replaced?" $API/kb/$KB/conversations/$CONV/ask
curl -N -F "question=What is wrong here?" -F "image=@photo.jpg" $API/kb/$KB/conversations/$CONV/ask
```

**Python: stream an answer**

```python
import json, httpx

def ask(kb_id: str, conv_id: str, question: str) -> None:
    url = f"http://localhost:8000/api/kb/{kb_id}/conversations/{conv_id}/ask"
    with httpx.stream("POST", url, data={"question": question}, timeout=120) as r:
        for line in r.iter_lines():
            if not line.startswith("data: "):
                continue
            event = json.loads(line[6:])
            if event["type"] == "token":
                print(event["text"], end="", flush=True)
            elif event["type"] == "done":
                print("\nSources:", [(c["index"], c["doc_title"], c["page"]) for c in event["citations"]])
```

**Python: one voice turn** (`pip install websockets`)

```python
import asyncio, json, wave, websockets

async def voice_turn(kb_id: str, conv_id: str, wav_path: str) -> None:
    uri = f"ws://localhost:8000/api/kb/{kb_id}/conversations/{conv_id}/voice"
    async with websockets.connect(uri, max_size=None) as ws:
        await ws.send(open(wav_path, "rb").read())
        pcm = bytearray()
        while True:
            msg = await ws.recv()
            if isinstance(msg, bytes):
                pcm += msg                                  # 24 kHz s16le mono
                continue
            event = json.loads(msg)
            if event["type"] == "transcript":
                print("You said:", event["text"])
            elif event["type"] == "token":
                print(event["text"], end="", flush=True)
            elif event["type"] in ("done", "error", "asr_error", "tts_error"):
                break
    with wave.open("answer.wav", "wb") as w:                # save the spoken answer
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)

asyncio.run(voice_turn("<kb_id>", "<conv_id>", "question.wav"))
```

**JavaScript: play the voice stream in a browser.** `web/src/hooks/useVoice.ts` is a complete reference client. It records, sends, schedules the PCM chunks gap-free with the Web Audio API, and handles barge-in.

---

## Tuning

These constants live in the code; change them and restart the API.

| What | Default | Where |
|---|---|---|
| Chunk size and overlap | 400 / 60 tokens | `server/ingest/chunk.py` (`TARGET_TOKENS`, `OVERLAP_TOKENS`) |
| Candidates per search leg | 20 | `server/retrieval/hybrid.py` (`TOP_K_EACH`) |
| Passages given to the model | 8 | `server/retrieval/hybrid.py` (`FINAL_K`) |
| RRF constant | 60 | `server/retrieval/rrf.py` (`K`) |
| Prompt budget: passages / history | 3,000 / 2,000 tokens | `server/pipeline/prompt.py` |
| Answer length | 1,024 tokens | `server/pipeline/ask.py` (`max_tokens`) |
| System prompt | answer only from passages, cite `[n]` | `server/pipeline/prompt.py` (`SYSTEM_PROMPT`) |
| When to rewrite follow-ups | refers back, or ≤ 4 words | `server/pipeline/rewrite.py` (`needs_rewrite`) |
| Shortest sentence sent to TTS | 20 characters | `server/voice/sentences.py` (`MIN_CHARS`) |
| Full-text search language | `english` | `server/db/migrations/0002_documents.sql` and `server/db/repo.py` |
| Photo resize before upload | 1,600 px, JPEG 88% | `web/src/api/client.ts` (`downscaleImage`) |

---

## Project structure

```
voice-chatbot/
├─ server/
│  ├─ app/          main.py (FastAPI app, migrations on startup) · settings.py · deps.py
│  ├─ api/          health · kb · documents · chat (ask/SSE) · conversations (history, objects) · voice (WS)
│  ├─ providers/    base.py (protocols) · openai_compat.py (all provider clients and quirks)
│  ├─ ingest/       parse (PyMuPDF) · chunk · embed · jobs
│  ├─ retrieval/    hybrid (vector + FTS, in parallel) · rrf
│  ├─ pipeline/     ask · rewrite · prompt · citations
│  ├─ voice/        session (WS turn loop, ordered TTS, barge-in) · sentences
│  └─ db/           pool · repo (all SQL) · migrations/ (forward-only .sql files)
├─ web/
│  ├─ src/api/client.ts         REST + SSE client, image downscaling
│  ├─ src/hooks/useChat.ts      thread state, streaming, stop
│  ├─ src/hooks/useVoice.ts     recording, WebSocket, gap-free PCM playback, barge-in
│  ├─ src/components/           Sidebar · KbPicker · MessageView · Composer · SourcesPanel ·
│  │                            DocumentsDialog · ConfirmDialog · EmptyState
│  ├─ src/styles.css            design tokens, light/dark themes
│  └─ vite.config.ts            dev proxy for /api (ws: true for voice)
├─ scripts/smoke.py             one call to each provider
├─ docker-compose.yml · Dockerfile · web/Dockerfile · web/nginx.conf
├─ .env.example · pyproject.toml · Makefile
```

### Adding a provider that isn't OpenAI-compatible

Everything outside `server/providers/` depends only on the protocols in `server/providers/base.py` (`ChatProvider`, `EmbeddingProvider`, `TranscriptionProvider`, `SpeechProvider`, `RerankProvider`). Write a class that implements one, and return it from the matching function in `server/app/deps.py`.

### Database changes

Add a new numbered file in `server/db/migrations/` (e.g. `0005_add_x.sql`). Files run once each, in order, at startup, and are recorded in `_migration`. Never edit a migration that has already run; add a new one instead.

---

## Development

```bash
make install        # pip install -e ".[dev]" + npm install
make dev            # migrations, API on :8000, web on :5173  (needs GNU make)
make lint           # ruff + eslint
make type           # mypy
make smoke          # scripts/smoke.py
cd web && npx tsc --noEmit && npm run build    # type-check and production build of the UI
```

No `make` on Windows? Run the commands from [Quick start](#quick-start) directly.

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Voice stays on **"Transcribing…"** | The WebSocket never reached the API. The Vite proxy needs `ws: true` (already set in `vite.config.ts`), and your own reverse proxy must forward the `Upgrade` and `Connection` headers (see `web/nginx.conf`). The API log should show `WebSocket /api/…/voice [accepted]`. |
| "Microphone access was blocked" or no mic on a phone | Browsers allow the mic only on `localhost` or HTTPS. Serve the app over HTTPS to use it from other devices. |
| `400 … Unrecognized request argument: top_k` | `CHAT_VLLM=true` against a provider that isn't vLLM. Set it to `false`. |
| `expected 2048 dimensions, not 1536` (or similar) | `EMBED_DIMS` doesn't match the model's output or the DB column. See [Changing the embedding size](#changing-the-embedding-size). |
| Answers stopped finding anything after a provider change | You switched embedding model. Delete and re-upload your documents. |
| Document stuck on **Processing** | The API restarted during ingestion (it runs inside the API process). Delete the document and upload it again. |
| Document **Ready** with 0 pages | It's a scanned PDF with no text layer. Run OCR first (e.g. `ocrmypdf`). |
| Photo questions fail | The chat model doesn't accept images. Use a vision model. |
| Spoken answer is noise or plays at the wrong speed | `TTS_FORMAT` isn't `pcm`, or the provider's PCM isn't 24 kHz. |
| API in Docker can't reach models on your machine | Use `http://host.docker.internal:<port>/v1` instead of `localhost`. |
| Speech-to-text rejects the audio | Install ffmpeg so the server can convert webm to WAV. |
| Voice feels slow | Run the API close to the model servers. The first turn after a start is slower while connections open. |

---

## Security and production notes

- **There is no authentication.** Anyone who can reach the API can read every conversation and document. Keep it on `localhost` or a private network, or put it behind a reverse proxy that handles login (OAuth2 proxy, SSO, basic auth).
- CORS allows every origin (`server/app/main.py`). Restrict it to your web origin before you expose the API.
- Keys live only in `.env`, which is git-ignored. Don't commit it, and don't bake it into images; pass it at runtime.
- Uploaded files and photos are stored unencrypted in `OBJECT_DIR`. Back it up together with the database.
- Use HTTPS in production; the microphone needs it anyway.

---

## Limitations and roadmap

- Push-to-talk only; hands-free mode with voice activity detection is not built yet.
- Ingestion supports PDF, TXT and Markdown. It runs inside the API process (not a job queue), so a restart interrupts it.
- Full-text search uses English stemming; vector search works in any language your embedding model supports.
- Page images are embedded when `EMBED_IMAGES=true`, but search doesn't use those vectors yet.
- Single-tenant: no users, roles or per-user history.

---

## Contributing

1. Fork the repository and create a branch: `git checkout -b feat/my-change`.
2. Keep provider-specific code inside `server/providers/`, and put database changes in new migration files.
3. Run `make lint type` and `cd web && npx tsc --noEmit` before opening a pull request.
4. Describe what changed and how you tested it (which providers you used).
