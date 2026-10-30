import { useCallback, useEffect, useRef, useState } from 'react'
import { Citation } from '../api/client'

export type VoiceStatus = 'idle' | 'recording' | 'transcribing' | 'thinking' | 'speaking' | 'error'

export interface VoiceTarget { kbId: string; convId: string }

export interface VoiceHandlers {
  onTranscript: (target: VoiceTarget, text: string) => void
  onToken: (text: string) => void
  onDone: (citations: Citation[], refused: boolean) => void
  onError: (message: string) => void
}

const SAMPLE_RATE = 24000
const OPEN_TIMEOUT_MS = 5000
const ANSWER_TIMEOUT_MS = 30000

function pickMime(): string {
  for (const m of ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4']) {
    if (MediaRecorder.isTypeSupported(m)) return m
  }
  return ''
}

export function useVoice(handlers: VoiceHandlers) {
  const [status, setStatus] = useState<VoiceStatus>('idle')
  const [muted, setMuted] = useState(false)
  const statusRef = useRef<VoiceStatus>('idle')
  const handlersRef = useRef(handlers)
  handlersRef.current = handlers

  const wsRef = useRef<WebSocket | null>(null)
  const wsTargetRef = useRef('')
  const targetRef = useRef<VoiceTarget | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const ctxRef = useRef<AudioContext | null>(null)
  const nextStartRef = useRef(0)
  const sourcesRef = useRef(new Set<AudioBufferSourceNode>())
  const answerDoneRef = useRef(false)
  const mutedRef = useRef(false)
  const watchdogRef = useRef<number>()

  const set = useCallback((s: VoiceStatus) => { statusRef.current = s; setStatus(s) }, [])

  const fail = useCallback((message: string) => {
    window.clearTimeout(watchdogRef.current)
    set('error')
    handlersRef.current.onError(message)
    window.setTimeout(() => { if (statusRef.current === 'error') set('idle') }, 2500)
  }, [set])

  const finishIfQuiet = useCallback(() => {
    if (answerDoneRef.current && sourcesRef.current.size === 0 && statusRef.current === 'speaking') set('idle')
  }, [set])

  // Chunks are scheduled back to back on one timeline, so playback has no gaps.
  const playPcm = useCallback((data: ArrayBuffer) => {
    const ctx = ctxRef.current
    if (!ctx || mutedRef.current) return
    const samples = new Int16Array(data)
    const buffer = ctx.createBuffer(1, samples.length, SAMPLE_RATE)
    const channel = buffer.getChannelData(0)
    for (let i = 0; i < samples.length; i++) channel[i] = samples[i] / 32768
    const src = ctx.createBufferSource()
    src.buffer = buffer
    src.connect(ctx.destination)
    const startAt = Math.max(ctx.currentTime + 0.02, nextStartRef.current)
    src.start(startAt)
    nextStartRef.current = startAt + buffer.duration
    sourcesRef.current.add(src)
    src.onended = () => { sourcesRef.current.delete(src); finishIfQuiet() }
  }, [finishIfQuiet])

  const stopPlayback = useCallback(() => {
    sourcesRef.current.forEach(s => { try { s.stop() } catch { /* already stopped */ } })
    sourcesRef.current.clear()
    nextStartRef.current = 0
  }, [])

  const openSocket = useCallback((target: VoiceTarget): Promise<WebSocket> => {
    const key = `${target.kbId}/${target.convId}`
    const existing = wsRef.current
    if (existing && wsTargetRef.current === key && existing.readyState === WebSocket.OPEN) {
      return Promise.resolve(existing)
    }
    existing?.close()
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${window.location.host}/api/kb/${target.kbId}/conversations/${target.convId}/voice`)
    ws.binaryType = 'arraybuffer'
    wsRef.current = ws
    wsTargetRef.current = key

    ws.onmessage = ev => {
      if (ev.data instanceof ArrayBuffer) { playPcm(ev.data); return }
      const msg = JSON.parse(ev.data as string)
      const h = handlersRef.current
      switch (msg.type) {
        case 'transcribing': set('transcribing'); break
        case 'transcript':
          window.clearTimeout(watchdogRef.current)
          if (targetRef.current) h.onTranscript(targetRef.current, msg.text)
          set('thinking'); break
        case 'thinking': set('thinking'); break
        case 'token': h.onToken(msg.text); if (statusRef.current !== 'speaking') set('speaking'); break
        case 'done':
          window.clearTimeout(watchdogRef.current)
          answerDoneRef.current = true
          h.onDone(msg.citations ?? [], msg.refused ?? false)
          if (statusRef.current !== 'speaking' || sourcesRef.current.size === 0) set('idle')
          break
        default:
          if (String(msg.type).endsWith('error')) fail(msg.msg || 'Voice failed')
      }
    }
    ws.onclose = () => { if (wsRef.current === ws) { wsRef.current = null; wsTargetRef.current = '' } }

    return new Promise((resolve, reject) => {
      const timer = window.setTimeout(() => { ws.close(); reject(new Error('Could not connect to voice (timeout).')) }, OPEN_TIMEOUT_MS)
      ws.onopen = () => { window.clearTimeout(timer); resolve(ws) }
      ws.onerror = () => { window.clearTimeout(timer); reject(new Error('Could not connect to voice.')) }
    })
  }, [playPcm, set, fail])

  /** Barge-in: silences the current answer and tells the server to stop. */
  const interrupt = useCallback(() => {
    stopPlayback()
    if (wsRef.current?.readyState === WebSocket.OPEN) wsRef.current.send(JSON.stringify({ type: 'cancel' }))
    if (statusRef.current === 'speaking' || statusRef.current === 'thinking') set('idle')
  }, [stopPlayback, set])

  const start = useCallback(async (resolveTarget: () => Promise<VoiceTarget>) => {
    if (recorderRef.current) return
    interrupt()
    try {
      // Created inside the click so the browser allows sound.
      if (!ctxRef.current) ctxRef.current = new AudioContext({ sampleRate: SAMPLE_RATE })
      await ctxRef.current.resume()
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      })
      const target = await resolveTarget()
      targetRef.current = target
      const socketReady = openSocket(target)
      const mime = pickMime()
      const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
      const chunks: Blob[] = []
      recorder.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data) }
      recorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop())
        const blob = new Blob(chunks, { type: recorder.mimeType })
        if (blob.size < 1200) { set('idle'); return }   // a tap, not speech
        try {
          const ws = await socketReady
          answerDoneRef.current = false
          ws.send(await blob.arrayBuffer())
          watchdogRef.current = window.setTimeout(
            () => fail('No answer from the voice service. Please try again.'), ANSWER_TIMEOUT_MS)
        } catch (e) { fail((e as Error).message) }
      }
      recorder.start()
      recorderRef.current = recorder
      set('recording')
    } catch (e) {
      const err = e as Error
      fail(err.name === 'NotAllowedError' ? 'Microphone access was blocked. Allow it in the address bar.' : err.message)
    }
  }, [interrupt, openSocket, set, fail])

  const stop = useCallback(() => {
    const recorder = recorderRef.current
    if (!recorder) return
    recorderRef.current = null
    recorder.stop()
    set('transcribing')
  }, [set])

  const cancelRecording = useCallback(() => {
    const recorder = recorderRef.current
    if (!recorder) return
    recorderRef.current = null
    recorder.ondataavailable = null
    recorder.onstop = () => recorder.stream.getTracks().forEach(t => t.stop())
    recorder.stop()
    set('idle')
  }, [set])

  const toggleMute = useCallback(() => {
    mutedRef.current = !mutedRef.current
    setMuted(mutedRef.current)
    if (mutedRef.current) stopPlayback()
  }, [stopPlayback])

  useEffect(() => () => {
    wsRef.current?.close()
    ctxRef.current?.close()
    window.clearTimeout(watchdogRef.current)
  }, [])

  return { status, muted, start, stop, cancelRecording, interrupt, toggleMute }
}
