import { useCallback, useRef, useState } from 'react'
import { api, askStream, Citation, downscaleImage, Message } from '../api/client'

const now = () => new Date().toISOString()
const localId = (p: string) => `${p}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`

/** Messages of the open conversation, plus the answer being streamed into it. */
export function useChat(onConversationChanged: () => void) {
  const [messages, setMessages] = useState<Message[]>([])
  const [streaming, setStreaming] = useState<Message | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const textRef = useRef('')
  const abortRef = useRef<(() => void) | null>(null)
  const loadSeq = useRef(0)

  const busy = streaming !== null

  const finalize = useCallback((patch: Partial<Message>) => {
    const text = textRef.current
    textRef.current = ''
    abortRef.current = null
    setStreaming(null)
    setMessages(prev => [...prev, {
      id: localId('a'), role: 'assistant', text, citations: [], created_at: now(), ...patch,
    }])
    onConversationChanged()
  }, [onConversationChanged])

  const beginAnswer = useCallback((user: Message) => {
    textRef.current = ''
    setError(null)
    setMessages(prev => [...prev, user])
    setStreaming({ id: 'streaming', role: 'assistant', text: '', citations: [], created_at: now() })
  }, [])

  const appendToken = useCallback((t: string) => {
    textRef.current += t
    const text = textRef.current
    setStreaming(s => (s ? { ...s, text } : s))
  }, [])

  const load = useCallback(async (convId: string | null) => {
    const seq = ++loadSeq.current
    abortRef.current?.()
    abortRef.current = null
    textRef.current = ''
    setStreaming(null)
    setError(null)
    if (!convId) { setMessages([]); return }
    setLoading(true)
    try {
      const conv = await api.getConversation(convId)
      if (seq === loadSeq.current) setMessages(conv.messages)
    } catch (e) {
      if (seq === loadSeq.current) { setMessages([]); setError((e as Error).message) }
    } finally {
      if (seq === loadSeq.current) setLoading(false)
    }
  }, [])

  const send = useCallback(async (kbId: string, convId: string, question: string, image: File | null) => {
    const imageBlob = image ? await downscaleImage(image) : null
    beginAnswer({
      id: localId('u'), role: 'user', text: question, citations: [], created_at: now(), via: 'text',
      image_url: imageBlob ? URL.createObjectURL(imageBlob) : null,
    })
    abortRef.current = askStream(kbId, convId, question, imageBlob, {
      onToken: appendToken,
      onDone: (citations, refused) => finalize({ citations, refused }),
      onError: message => {
        setError(message)
        finalize({ error: message })
      },
    })
  }, [beginAnswer, appendToken, finalize])

  /** Stops generating; keeps what was already written. */
  const stop = useCallback(() => {
    if (!abortRef.current && !textRef.current) return
    abortRef.current?.()
    finalize({})
  }, [finalize])

  // Voice turns arrive over the WebSocket; these feed the same thread.
  const voice = {
    onTranscript: (text: string) => beginAnswer({
      id: localId('u'), role: 'user', text, citations: [], created_at: now(), via: 'voice',
    }),
    onToken: appendToken,
    onDone: (citations: Citation[], refused: boolean) => finalize({ citations, refused }),
  }

  return { messages, streaming, loading, busy, error, setError, load, send, stop, voice, setMessages }
}
