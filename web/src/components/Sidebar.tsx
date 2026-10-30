import { useMemo, useState } from 'react'
import {
  Check, FolderOpen, MessageSquare, Moon, PanelLeftClose, Pencil, Search, SquarePen, Sun, Trash2, X,
} from 'lucide-react'
import { Conversation, KB } from '../api/client'
import KbPicker from './KbPicker'

interface Props {
  collapsed: boolean
  onCollapse: () => void
  conversations: Conversation[]
  activeId: string | null
  onSelect: (c: Conversation) => void
  onNew: () => void
  onRename: (id: string, title: string) => void
  onDelete: (c: Conversation) => void
  kbs: KB[]
  kb: KB | null
  onSelectKb: (kb: KB) => void
  onCreateKb: (name: string) => Promise<void>
  onOpenDocs: () => void
  theme: 'light' | 'dark'
  onToggleTheme: () => void
}

const DAY = 86_400_000

function groupByDate(items: Conversation[]): [string, Conversation[]][] {
  const startOfToday = new Date().setHours(0, 0, 0, 0)
  const buckets: [string, (t: number) => boolean][] = [
    ['Today', t => t >= startOfToday],
    ['Yesterday', t => t >= startOfToday - DAY],
    ['Previous 7 days', t => t >= startOfToday - 7 * DAY],
    ['Previous 30 days', t => t >= startOfToday - 30 * DAY],
    ['Older', () => true],
  ]
  const groups = new Map<string, Conversation[]>()
  for (const c of items) {
    const t = new Date(c.last_at).getTime()
    const label = buckets.find(([, test]) => test(t))![0]
    groups.set(label, [...(groups.get(label) ?? []), c])
  }
  return buckets.map(([l]) => [l, groups.get(l) ?? []] as [string, Conversation[]]).filter(([, v]) => v.length)
}

function HistoryItem({ c, active, onSelect, onRename, onDelete }: {
  c: Conversation; active: boolean
  onSelect: () => void; onRename: (t: string) => void; onDelete: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(c.title)
  const title = c.title || 'Untitled chat'

  if (editing) {
    const save = () => { setEditing(false); if (draft.trim() && draft.trim() !== c.title) onRename(draft.trim()) }
    return (
      <div className="history-item active">
        <input
          autoFocus value={draft} onChange={e => setDraft(e.target.value)} onBlur={save}
          onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') setEditing(false) }}
        />
        <button className="icon-btn sm" onMouseDown={e => e.preventDefault()} onClick={save}><Check size={14} /></button>
      </div>
    )
  }
  return (
    <div className={`history-item${active ? ' active' : ''}`} onClick={onSelect} title={`${title} · ${c.kb_name}`}>
      <span className="title">{title}</span>
      <span className="actions" onClick={e => e.stopPropagation()}>
        <button className="icon-btn sm" title="Rename" onClick={() => { setDraft(c.title); setEditing(true) }}><Pencil size={13} /></button>
        <button className="icon-btn sm" title="Delete" onClick={onDelete}><Trash2 size={13} /></button>
      </span>
    </div>
  )
}

export default function Sidebar(p: Props) {
  const [query, setQuery] = useState('')
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return q ? p.conversations.filter(c => `${c.title} ${c.kb_name}`.toLowerCase().includes(q)) : p.conversations
  }, [query, p.conversations])
  const groups = useMemo(() => groupByDate(filtered), [filtered])

  return (
    <nav className={`sidebar${p.collapsed ? ' collapsed' : ''}`} aria-label="Conversations">
      <div className="sidebar-top">
        <div className="brand">
          <span className="brand-name">
            <span className="brand-mark"><MessageSquare size={15} /></span>
            Voice Assistant
          </span>
          <button className="icon-btn" onClick={p.onCollapse} title="Close sidebar"><PanelLeftClose size={18} /></button>
        </div>
        <button className="new-chat" onClick={p.onNew}>
          <SquarePen size={16} /> New chat <kbd>Ctrl ⇧ O</kbd>
        </button>
        <label className="sidebar-search">
          <Search size={15} />
          <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search chats" />
          {query && <button className="icon-btn sm" onClick={() => setQuery('')}><X size={14} /></button>}
        </label>
      </div>

      <div className="history">
        {groups.length === 0 && (
          <div className="history-empty">{query ? 'No chats match your search.' : 'Your conversations will appear here.'}</div>
        )}
        {groups.map(([label, items]) => (
          <div key={label} className="history-group">
            <div className="history-label">{label}</div>
            {items.map(c => (
              <HistoryItem
                key={c.id} c={c} active={c.id === p.activeId}
                onSelect={() => p.onSelect(c)}
                onRename={t => p.onRename(c.id, t)}
                onDelete={() => p.onDelete(c)}
              />
            ))}
          </div>
        ))}
      </div>

      <div className="sidebar-bottom">
        <KbPicker kbs={p.kbs} kb={p.kb} onSelect={p.onSelectKb} onCreate={p.onCreateKb} />
        <div style={{ display: 'flex', gap: 4 }}>
          <button className="btn btn-ghost" style={{ flex: 1 }} onClick={p.onOpenDocs} disabled={!p.kb}>
            <FolderOpen size={16} /> Documents
          </button>
          <button className="icon-btn" style={{ width: 36, height: 36 }} onClick={p.onToggleTheme} title="Toggle theme">
            {p.theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}
          </button>
        </div>
      </div>
    </nav>
  )
}
