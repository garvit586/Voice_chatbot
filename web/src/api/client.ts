const BASE = '/api'

export interface KB { id: string; name: string; description: string; created_at: string }
export interface Doc {
  id: string; title: string; status: 'pending' | 'ingesting' | 'ready' | 'error'
  pages: number; error_msg: string | null; created_at: string
}
export interface Conversation {
  id: string; kb_id: string; kb_name: string; title: string; created_at: string; last_at: string
}
export interface Citation { index: number; doc_title: string; page: number; snippet: string; chunk_id: string }
export interface Message {
  id: string
  role: 'user' | 'assistant'
  text: string
  citations: Citation[]
  image_key?: string | null
  image_url?: string | null   // local preview before the server has stored it
  via?: 'voice' | 'text'
  refused?: boolean
  error?: string
  created_at: string
}

async function json<T>(res: Promise<Response>): Promise<T> {
  const r = await res
  if (!r.ok) {
    let detail = `${r.status} ${r.statusText}`
    try { detail = (await r.json()).detail ?? detail } catch { /* not JSON */ }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return r.status === 204 ? (undefined as T) : r.json()
}

const send = (url: string, method: string, body?: unknown) =>
  fetch(url, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })

export const api = {
  listKBs: () => json<KB[]>(fetch(`${BASE}/kb`)),
  createKB: (name: string, description = '') => json<KB>(send(`${BASE}/kb`, 'POST', { name, description })),

  listDocs: (kbId: string) => json<Doc[]>(fetch(`${BASE}/kb/${kbId}/documents`)),
  uploadDoc: (kbId: string, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return json<{ id: string; status: string }>(fetch(`${BASE}/kb/${kbId}/documents`, { method: 'POST', body: fd }))
  },
  deleteDoc: (kbId: string, docId: string) => json<void>(send(`${BASE}/kb/${kbId}/documents/${docId}`, 'DELETE')),

  listConversations: () => json<Conversation[]>(fetch(`${BASE}/conversations`)),
  getConversation: (id: string) =>
    json<Conversation & { messages: Message[] }>(fetch(`${BASE}/conversations/${id}`)),
  createConversation: (kbId: string) => json<Conversation>(send(`${BASE}/kb/${kbId}/conversations`, 'POST')),
  renameConversation: (id: string, title: string) => json<Conversation>(send(`${BASE}/conversations/${id}`, 'PATCH', { title })),
  deleteConversation: (id: string) => json<void>(send(`${BASE}/conversations/${id}`, 'DELETE')),

  objectUrl: (key: string) => `${BASE}/objects/${key}`,
}

export interface StreamHandlers {
  onToken: (t: string) => void
  onDone: (citations: Citation[], refused: boolean) => void
  onError: (e: string) => void
}

export function askStream(
  kbId: string, convId: string, question: string, image: Blob | null, h: StreamHandlers,
): () => void {
  const fd = new FormData()
  fd.append('question', question)
  if (image) fd.append('image', image, 'photo.jpg')
  const ctrl = new AbortController()

  ;(async () => {
    const res = await fetch(`${BASE}/kb/${kbId}/conversations/${convId}/ask`, {
      method: 'POST', body: fd, signal: ctrl.signal,
    })
    if (!res.ok || !res.body) { h.onError(`The server answered ${res.status}`); return }
    const reader = res.body.getReader()
    const dec = new TextDecoder()
    let buf = ''
    let finished = false
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const p = JSON.parse(line.slice(6))
        if (p.type === 'token') h.onToken(p.text)
        else if (p.type === 'done') { finished = true; h.onDone(p.citations ?? [], p.refused ?? false) }
      }
    }
    if (!finished) h.onError('The answer stopped before it finished.')
  })().catch(e => { if ((e as Error).name !== 'AbortError') h.onError(String(e)) })

  return () => ctrl.abort()
}

/** Shrinks a photo to at most 1600 px on its long side: smaller upload, faster vision call. */
export async function downscaleImage(file: File, maxSide = 1600): Promise<Blob> {
  const bitmap = await createImageBitmap(file)
  const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height))
  if (scale === 1 && file.type === 'image/jpeg') return file
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(bitmap.width * scale)
  canvas.height = Math.round(bitmap.height * scale)
  canvas.getContext('2d')!.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  return new Promise((resolve, reject) =>
    canvas.toBlob(b => (b ? resolve(b) : reject(new Error('image encode failed'))), 'image/jpeg', 0.88))
}
