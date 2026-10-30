import { useState } from 'react'
import { BookOpen, Camera, FileSearch, Mic, Sparkles, Upload, Wrench } from 'lucide-react'
import { Doc, KB } from '../api/client'

interface Props {
  kb: KB | null
  docs: Doc[]
  onAsk: (q: string) => void
  onPhoto: () => void
  onVoice: () => void
  onOpenDocs: () => void
  onCreateKb: (name: string) => Promise<void>
}

export default function EmptyState({ kb, docs, onAsk, onPhoto, onVoice, onOpenDocs, onCreateKb }: Props) {
  const [name, setName] = useState('')

  if (!kb) {
    return (
      <div className="empty">
        <div className="empty-logo"><Sparkles size={26} /></div>
        <h1>Create your first knowledge base</h1>
        <p>A knowledge base is a set of documents, such as manuals, procedures and guides. The assistant answers only from them, with citations.</p>
        <div className="menu-form" style={{ width: '100%', maxWidth: 420, marginTop: 24 }}>
          <input autoFocus value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Compressor manuals"
            onKeyDown={e => { if (e.key === 'Enter' && name.trim()) onCreateKb(name.trim()) }} />
          <button className="btn btn-primary" disabled={!name.trim()} onClick={() => onCreateKb(name.trim())}>Create</button>
        </div>
      </div>
    )
  }

  const ready = docs.filter(d => d.status === 'ready')
  if (docs.length === 0) {
    return (
      <div className="empty">
        <div className="empty-logo"><Upload size={24} /></div>
        <h1>Add documents to {kb.name}</h1>
        <p>Upload PDFs or text files. Once they are processed, you can ask questions by typing, talking or sending a photo.</p>
        <button className="btn btn-primary" style={{ marginTop: 24 }} onClick={onOpenDocs}><Upload size={16} /> Upload documents</button>
      </div>
    )
  }

  const first = ready[0]?.title.replace(/\.[a-z0-9]+$/i, '')
  const suggestions = [
    { icon: <BookOpen size={16} />, title: 'Summarize the key points', sub: first ? `of ${first}` : 'across all documents', run: () => onAsk(first ? `Summarize the key points of ${first}.` : 'Summarize the key points of these documents.') },
    { icon: <Wrench size={16} />, title: 'Troubleshoot a problem', sub: 'What should I check first?', run: () => onAsk('What are the first troubleshooting steps I should follow, and what safety precautions apply?') },
    { icon: <Camera size={16} />, title: 'Ask about a photo', sub: 'Attach a picture of the issue', run: onPhoto },
    { icon: <Mic size={16} />, title: 'Talk instead of typing', sub: 'Hands-free, answers read aloud', run: onVoice },
  ]

  return (
    <div className="empty">
      <div className="empty-logo"><Sparkles size={26} /></div>
      <h1>How can I help?</h1>
      <p>
        Answers come from <strong>{ready.length}</strong> document{ready.length === 1 ? '' : 's'} in {kb.name}
        {ready.length < docs.length && `, ${docs.length - ready.length} still processing`}.
      </p>
      <div className="suggestions">
        {suggestions.map(s => (
          <button key={s.title} className="suggestion" onClick={s.run}>
            <span className="s-title">{s.icon}{s.title}</span>
            <span className="s-sub">{s.sub}</span>
          </button>
        ))}
      </div>
      <button className="btn btn-ghost" style={{ marginTop: 18 }} onClick={onOpenDocs}><FileSearch size={15} /> Manage documents</button>
    </div>
  )
}
