import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertCircle, CheckCircle2, FileText, Loader2, Trash2, Upload, X } from 'lucide-react'
import { api, Doc, KB } from '../api/client'

interface Props {
  kb: KB
  onClose: () => void
  onChanged: (docs: Doc[]) => void
}

const ACCEPT = '.pdf,.txt,.md'

function StatusBadge({ d }: { d: Doc }) {
  if (d.status === 'ready') return <span className="status ready"><CheckCircle2 size={12} /> Ready</span>
  if (d.status === 'error') return <span className="status error" title={d.error_msg ?? ''}><AlertCircle size={12} /> Failed</span>
  return <span className={`status ${d.status}`}><Loader2 size={12} className="spin" /> Processing</span>
}

export default function DocumentsDialog({ kb, onClose, onChanged }: Props) {
  const [docs, setDocs] = useState<Doc[]>([])
  const [over, setOver] = useState(false)
  const [uploading, setUploading] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const onChangedRef = useRef(onChanged)
  onChangedRef.current = onChanged

  const reload = useCallback(async () => {
    const list = await api.listDocs(kb.id)
    setDocs(list)
    onChangedRef.current(list)
    return list
  }, [kb.id])

  useEffect(() => { reload().catch(e => setError(String(e))) }, [reload])

  // Poll only while something is still being processed.
  const processing = docs.some(d => d.status === 'pending' || d.status === 'ingesting')
  useEffect(() => {
    if (!processing) return
    const t = window.setInterval(() => { reload().catch(() => {}) }, 2000)
    return () => window.clearInterval(t)
  }, [processing, reload])

  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', esc)
    return () => document.removeEventListener('keydown', esc)
  }, [onClose])

  const upload = async (files: FileList | File[]) => {
    setError(null)
    const list = Array.from(files)
    setUploading(n => n + list.length)
    for (const f of list) {
      try { await api.uploadDoc(kb.id, f) } catch (e) { setError(`${f.name}: ${(e as Error).message}`) }
      setUploading(n => n - 1)
    }
    await reload()
  }

  const remove = async (d: Doc) => {
    if (!window.confirm(`Remove "${d.title}" from ${kb.name}? Answers will no longer use it.`)) return
    await api.deleteDoc(kb.id, d.id)
    await reload()
  }

  return (
    <div className="overlay" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="dialog" role="dialog" aria-modal="true" aria-label="Documents">
        <div className="dialog-head">
          <div className="grow">
            <h2>Documents</h2>
            <p>Everything the assistant can answer from in <strong>{kb.name}</strong>.</p>
          </div>
          <button className="icon-btn" onClick={onClose} title="Close"><X size={18} /></button>
        </div>
        <div className="dialog-body">
          <div
            className={`dropzone${over ? ' over' : ''}`}
            onClick={() => fileRef.current?.click()}
            onDragOver={e => { e.preventDefault(); setOver(true) }}
            onDragLeave={() => setOver(false)}
            onDrop={e => { e.preventDefault(); setOver(false); upload(e.dataTransfer.files) }}
          >
            <div className="dz-icon">{uploading ? <Loader2 size={20} className="spin" /> : <Upload size={20} />}</div>
            <strong>{uploading ? `Uploading ${uploading}…` : 'Drop files here or click to upload'}</strong>
            <small>PDF, Markdown or plain text</small>
            <input ref={fileRef} type="file" multiple accept={ACCEPT} hidden
              onChange={e => { if (e.target.files) upload(e.target.files); e.target.value = '' }} />
          </div>

          {error && <div className="notice" style={{ marginTop: 12 }}><AlertCircle size={16} />{error}</div>}

          <div className="doc-list">
            {docs.length === 0 && <div className="history-empty">No documents yet. Upload one to start asking questions.</div>}
            {docs.map(d => (
              <div key={d.id} className="doc-row">
                <span className="doc-icon"><FileText size={16} /></span>
                <div className="doc-info">
                  <div className="name">{d.title}</div>
                  <div className="sub">
                    {d.status === 'error' ? d.error_msg : `${d.pages || '—'} page${d.pages === 1 ? '' : 's'} · added ${new Date(d.created_at).toLocaleDateString()}`}
                  </div>
                </div>
                <StatusBadge d={d} />
                <button className="icon-btn sm" title="Remove" onClick={() => remove(d)}><Trash2 size={14} /></button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
