import { useEffect, useRef } from 'react'
import { FileText, X } from 'lucide-react'
import { Citation } from '../api/client'

interface Props {
  citations: Citation[]
  focus?: number
  onClose: () => void
}

export default function SourcesPanel({ citations, focus, onClose }: Props) {
  const refs = useRef<Record<number, HTMLDivElement | null>>({})

  useEffect(() => {
    if (focus) refs.current[focus]?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [focus, citations])

  return (
    <aside className="panel" aria-label="Sources">
      <div className="panel-head">
        <span className="grow">Sources · {citations.length}</span>
        <button className="icon-btn" onClick={onClose} title="Close (Esc)"><X size={18} /></button>
      </div>
      <div className="panel-body">
        {citations.map(c => (
          <div key={c.index} ref={el => { refs.current[c.index] = el }} className={`source-card${c.index === focus ? ' focus' : ''}`}>
            <div className="head">
              <span className="cite" style={{ cursor: 'default' }}>{c.index}</span>
              <FileText size={14} color="var(--text-3)" />
              <span className="doc">{c.doc_title}</span>
              <span className="page">Page {c.page}</span>
            </div>
            <div className="snippet">{c.snippet}{c.snippet.length >= 600 ? '…' : ''}</div>
          </div>
        ))}
      </div>
    </aside>
  )
}
