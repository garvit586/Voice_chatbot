import { useEffect, useRef, useState } from 'react'
import { Check, ChevronsUpDown, Plus } from 'lucide-react'
import { KB } from '../api/client'

interface Props {
  kbs: KB[]
  kb: KB | null
  onSelect: (kb: KB) => void
  onCreate: (name: string) => Promise<void>
}

const initials = (name: string) =>
  name.split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]!.toUpperCase()).join('') || 'KB'

export default function KbPicker({ kbs, kb, onSelect, onCreate }: Props) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent) => { if (!rootRef.current?.contains(e.target as Node)) setOpen(false) }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', esc) }
  }, [open])

  const create = async () => {
    if (!name.trim() || saving) return
    setSaving(true)
    try { await onCreate(name.trim()); setName(''); setOpen(false) } finally { setSaving(false) }
  }

  return (
    <div className="kb-picker" ref={rootRef}>
      <button className={`kb-trigger${open ? ' open' : ''}`} onClick={() => setOpen(o => !o)}>
        <span className="kb-avatar">{kb ? initials(kb.name) : '+'}</span>
        <span className="kb-meta">
          <div className="label">Knowledge base</div>
          <div className="name">{kb?.name ?? 'Select or create'}</div>
        </span>
        <ChevronsUpDown size={15} color="var(--text-3)" />
      </button>
      {open && (
        <div className="menu" role="menu">
          {kbs.map(k => (
            <button key={k.id} className="menu-item" onClick={() => { onSelect(k); setOpen(false) }}>
              <span className="kb-avatar" style={{ width: 24, height: 24, fontSize: 11 }}>{initials(k.name)}</span>
              {k.name}
              {k.id === kb?.id && <Check size={15} className="check" />}
            </button>
          ))}
          {kbs.length > 0 && <div className="menu-sep" />}
          <div className="menu-form">
            <input
              value={name} onChange={e => setName(e.target.value)} placeholder="New knowledge base"
              onKeyDown={e => e.key === 'Enter' && create()}
            />
            <button className="btn btn-primary" onClick={create} disabled={!name.trim() || saving}><Plus size={15} /></button>
          </div>
        </div>
      )}
    </div>
  )
}
