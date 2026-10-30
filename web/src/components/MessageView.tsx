import { memo, useState } from 'react'
import ReactMarkdown, { Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { AlertCircle, Check, Copy, FileText, Mic, Sparkles } from 'lucide-react'
import { api, Citation, Message } from '../api/client'

interface Props {
  message: Message
  streaming?: boolean
  onOpenSources: (citations: Citation[], focus?: number) => void
}

const CITE = /\[(\d+)\]/g

/** Turns [n] into a link the renderer shows as a citation badge. */
const linkCitations = (text: string) => text.replace(CITE, (_, n) => `[${n}](#cite-${n})`)
const plainText = (text: string) => text.replace(/\s*\[\d+\]/g, '')

function AssistantBody({ message, streaming, onOpenSources }: Props) {
  const components: Components = {
    a: ({ href, children }) => {
      const m = href?.match(/^#cite-(\d+)$/)
      if (!m) return <a href={href} target="_blank" rel="noreferrer">{children}</a>
      const n = Number(m[1])
      const c = message.citations.find(x => x.index === n)
      return (
        <button
          className="cite"
          title={c ? `${c.doc_title} · p.${c.page}` : `Source ${n}`}
          onClick={() => c && onOpenSources(message.citations, n)}
        >{n}</button>
      )
    },
  }
  return (
    <div className="md">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {linkCitations(message.text)}
      </ReactMarkdown>
      {streaming && <span className="caret" />}
    </div>
  )
}

function MessageView({ message, streaming, onOpenSources }: Props) {
  const [copied, setCopied] = useState(false)

  if (message.role === 'user') {
    const img = message.image_url ?? (message.image_key ? api.objectUrl(message.image_key) : null)
    return (
      <div className="msg msg-user">
        <div className="bubble">
          {img && <img className="attached" src={img} alt="Attached photo" />}
          {message.via === 'voice' && <span className="via" title="Spoken"><Mic size={14} /></span>}
          {message.text}
        </div>
      </div>
    )
  }

  const copy = async () => {
    await navigator.clipboard.writeText(plainText(message.text))
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1500)
  }

  const thinking = streaming && !message.text
  return (
    <div className="msg">
      <div className="avatar"><Sparkles size={15} /></div>
      <div className="msg-body">
        {thinking ? (
          <div className="thinking"><span className="dots"><span /><span /><span /></span>Searching your documents…</div>
        ) : (
          <AssistantBody message={message} streaming={streaming} onOpenSources={onOpenSources} />
        )}

        {message.error && (
          <div className="notice" style={{ marginTop: 10 }}>
            <AlertCircle size={16} style={{ flexShrink: 0, marginTop: 2 }} />
            <span>{message.error}</span>
          </div>
        )}

        {message.citations.length > 0 && (
          <div className="sources">
            {message.citations.map(c => (
              <button key={c.index} className="source" onClick={() => onOpenSources(message.citations, c.index)}>
                <span className="n">{c.index}</span>
                <FileText size={13} style={{ flexShrink: 0 }} />
                <span className="t">{c.doc_title}</span>
                <span className="p">p.{c.page}</span>
              </button>
            ))}
          </div>
        )}

        {!streaming && message.text && (
          <div className="msg-actions">
            <button className="icon-btn sm" onClick={copy} title={copied ? 'Copied' : 'Copy'}>
              {copied ? <Check size={15} /> : <Copy size={15} />}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export default memo(MessageView)
