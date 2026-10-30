import { forwardRef, useEffect, useImperativeHandle, useLayoutEffect, useRef, useState } from 'react'
import { ArrowUp, Check, ImagePlus, Mic, Square, Volume2, X } from 'lucide-react'
import { VoiceStatus } from '../hooks/useVoice'

export interface ComposerHandle {
  focus: () => void
  setText: (t: string) => void
  pickImage: () => void
}

interface Props {
  disabled: boolean
  disabledReason?: string
  busy: boolean
  voiceStatus: VoiceStatus
  kbName?: string
  onSend: (text: string, image: File | null) => void
  onStop: () => void
  onMicStart: () => void
  onMicStop: () => void
  onMicCancel: () => void
  onInterrupt: () => void
}

const VOICE_LABEL: Partial<Record<VoiceStatus, string>> = {
  recording: 'Listening… tap ✓ when you finish',
  transcribing: 'Transcribing…',
}

const Composer = forwardRef<ComposerHandle, Props>(function Composer(p, ref) {
  const [text, setText] = useState('')
  const [image, setImage] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const taRef = useRef<HTMLTextAreaElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  useImperativeHandle(ref, () => ({
    focus: () => taRef.current?.focus(),
    setText: t => { setText(t); taRef.current?.focus() },
    pickImage: () => fileRef.current?.click(),
  }))

  useLayoutEffect(() => {
    const ta = taRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = `${Math.min(ta.scrollHeight, 220)}px`
  }, [text])

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview) }, [preview])

  const attach = (f: File | null | undefined) => {
    if (!f || !f.type.startsWith('image/')) return
    setImage(f)
    setPreview(URL.createObjectURL(f))
  }
  const clearImage = () => { setImage(null); setPreview(null) }

  const canSend = !p.disabled && !p.busy && (text.trim().length > 0 || image !== null)
  const submit = () => {
    if (!canSend) return
    p.onSend(text.trim() || 'What is shown in this photo?', image)
    setText('')
    clearImage()
  }

  const voiceActive = p.voiceStatus === 'recording' || p.voiceStatus === 'transcribing'

  return (
    <div className="composer-wrap">
      <div
        className={`composer${dragging ? ' dragging' : ''}`}
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={e => { e.preventDefault(); setDragging(false); attach(e.dataTransfer.files[0]) }}
      >
        {voiceActive ? (
          <div className="voice-bar">
            <span className={`wave${p.voiceStatus === 'recording' ? ' rec' : ''}`}>
              <span /><span /><span /><span /><span />
            </span>
            <span className="status">{VOICE_LABEL[p.voiceStatus]}</span>
            {p.voiceStatus === 'recording' && (
              <>
                <button className="icon-btn" onClick={p.onMicCancel} title="Cancel"><X size={18} /></button>
                <button className="send-btn" onClick={p.onMicStop} title="Send voice message"><Check size={18} /></button>
              </>
            )}
          </div>
        ) : (
          <>
            {preview && (
              <div className="composer-attach">
                <div className="thumb">
                  <img src={preview} alt="Attachment" />
                  <button onClick={clearImage} title="Remove"><X size={12} /></button>
                </div>
              </div>
            )}
            <textarea
              ref={taRef}
              value={text}
              rows={1}
              disabled={p.disabled}
              placeholder={p.disabled ? p.disabledReason : `Ask anything about ${p.kbName ?? 'your documents'}…`}
              onChange={e => setText(e.target.value)}
              onPaste={e => { const f = e.clipboardData.files[0]; if (f) { e.preventDefault(); attach(f) } }}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); submit() }
              }}
            />
            <div className="composer-row">
              <button className="icon-btn" disabled={p.disabled} onClick={() => fileRef.current?.click()} title="Attach a photo">
                <ImagePlus size={19} />
              </button>
              <input ref={fileRef} type="file" accept="image/*" hidden onChange={e => { attach(e.target.files?.[0]); e.target.value = '' }} />
              <span className="grow" />
              {p.voiceStatus === 'speaking' && (
                <button className="btn btn-ghost" onClick={p.onInterrupt} title="Stop speaking">
                  <Volume2 size={16} /> Stop speaking
                </button>
              )}
              <button
                className="mic-btn"
                disabled={p.disabled || (p.busy && p.voiceStatus !== 'speaking')}
                onClick={p.onMicStart}
                title="Talk (tap, speak, then tap ✓)"
              ><Mic size={19} /></button>
              {p.busy && p.voiceStatus !== 'speaking' ? (
                <button className="send-btn" onClick={p.onStop} title="Stop generating"><Square size={14} fill="currentColor" /></button>
              ) : (
                <button className="send-btn" disabled={!canSend} onClick={submit} title="Send (Enter)"><ArrowUp size={18} /></button>
              )}
            </div>
          </>
        )}
      </div>
      <div className="composer-foot">Answers come only from your documents and cite their sources. Check important details.</div>
    </div>
  )
})

export default Composer
