import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AlertCircle, Library, Loader2, PanelLeftOpen, SquarePen, Volume2, VolumeX } from 'lucide-react'
import { api, Citation, Conversation, Doc, KB } from './api/client'
import { useChat } from './hooks/useChat'
import { useVoice } from './hooks/useVoice'
import Sidebar from './components/Sidebar'
import MessageView from './components/MessageView'
import Composer, { ComposerHandle } from './components/Composer'
import SourcesPanel from './components/SourcesPanel'
import DocumentsDialog from './components/DocumentsDialog'
import ConfirmDialog from './components/ConfirmDialog'
import EmptyState from './components/EmptyState'

type Theme = 'light' | 'dark'
const store = {
  get: (k: string) => localStorage.getItem(`vc.${k}`),
  set: (k: string, v: string | null) => (v === null ? localStorage.removeItem(`vc.${k}`) : localStorage.setItem(`vc.${k}`, v)),
}
const convFromHash = () => window.location.hash.match(/^#\/c\/([0-9a-f-]{36})$/)?.[1] ?? null
const isNarrow = () => window.matchMedia('(max-width: 760px)').matches

export default function App() {
  const [theme, setTheme] = useState<Theme>(() =>
    (store.get('theme') as Theme) ?? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'))
  const [collapsed, setCollapsed] = useState(() => isNarrow() || store.get('sidebar') === 'closed')
  const [kbs, setKbs] = useState<KB[]>([])
  const [kbId, setKbId] = useState<string | null>(() => store.get('kb'))
  const [docs, setDocs] = useState<Doc[]>([])
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeId, setActiveId] = useState<string | null>(() => convFromHash() ?? store.get('conv'))
  const [sources, setSources] = useState<{ citations: Citation[]; focus?: number } | null>(null)
  const [docsOpen, setDocsOpen] = useState(false)
  const [toDelete, setToDelete] = useState<Conversation | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [scrolled, setScrolled] = useState(false)

  const composerRef = useRef<ComposerHandle>(null)
  const threadRef = useRef<HTMLDivElement>(null)
  const pinnedRef = useRef(true)
  const activeRef = useRef(activeId)
  activeRef.current = activeId
  const skipLoadRef = useRef<string | null>(null)

  const kb = kbs.find(k => k.id === kbId) ?? null
  const active = conversations.find(c => c.id === activeId) ?? null

  const showToast = useCallback((m: string) => {
    setToast(m)
    window.setTimeout(() => setToast(t => (t === m ? null : t)), 3500)
  }, [])

  const refreshConversations = useCallback(() => {
    api.listConversations().then(setConversations).catch(() => {})
  }, [])

  const chat = useChat(refreshConversations)

  // ── Boot ───────────────────────────────────────────────────────────────────
  useEffect(() => {
    Promise.all([api.listKBs(), api.listConversations()]).then(([k, c]) => {
      setKbs(k)
      setConversations(c)
      const open = c.find(x => x.id === activeRef.current)
      if (open) setKbId(open.kb_id)
      else {
        setActiveId(null)
        setKbId(id => (id && k.some(x => x.id === id) ? id : k[0]?.id ?? null))
      }
    }).catch(e => showToast(`Could not reach the server: ${(e as Error).message}`))
  }, [showToast])

  useEffect(() => { document.documentElement.dataset.theme = theme; store.set('theme', theme) }, [theme])
  useEffect(() => { store.set('sidebar', collapsed ? 'closed' : 'open') }, [collapsed])
  useEffect(() => { store.set('kb', kbId) }, [kbId])

  useEffect(() => {
    store.set('conv', activeId)
    window.history.replaceState(null, '', activeId ? `#/c/${activeId}` : '#/')
    if (skipLoadRef.current === activeId) { skipLoadRef.current = null; return }
    setSources(null)
    pinnedRef.current = true
    chat.load(activeId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId])

  const kbIdRef = useRef(kbId)
  kbIdRef.current = kbId
  const refreshDocs = useCallback(() => {
    if (!kbId) { setDocs([]); return }
    const id = kbId
    api.listDocs(id)
      .then(list => { if (kbIdRef.current === id) setDocs(list) })   // ignore a stale KB's reply
      .catch(() => {})
  }, [kbId])

  useEffect(() => { setDocs([]); refreshDocs() }, [refreshDocs])

  // Keep the document list current while anything is still being indexed,
  // whether or not the Documents window is open.
  const indexing = docs.filter(d => d.status === 'pending' || d.status === 'ingesting').length
  useEffect(() => {
    if (!indexing) return
    const t = window.setInterval(refreshDocs, 2000)
    return () => window.clearInterval(t)
  }, [indexing, refreshDocs])

  // ── Conversation helpers ──────────────────────────────────────────────────
  const ensureConversation = useCallback(async (): Promise<string> => {
    if (activeRef.current) return activeRef.current
    if (!kbId) throw new Error('Choose a knowledge base first')
    const conv = await api.createConversation(kbId)
    skipLoadRef.current = conv.id
    activeRef.current = conv.id
    setActiveId(conv.id)
    return conv.id
  }, [kbId])

  const voice = useVoice({
    onTranscript: (target, text) => { if (target.convId === activeRef.current) chat.voice.onTranscript(text) },
    onToken: t => chat.voice.onToken(t),
    onDone: (c, r) => chat.voice.onDone(c, r),
    onError: m => { chat.stop(); showToast(m) },
  })

  const startNewChat = useCallback(() => {
    voice.interrupt()
    setActiveId(null)
    if (isNarrow()) setCollapsed(true)
    window.setTimeout(() => composerRef.current?.focus(), 0)
  }, [voice])

  const openConversation = (c: Conversation) => {
    if (c.id === activeId) return
    voice.interrupt()
    setKbId(c.kb_id)
    setActiveId(c.id)
    if (isNarrow()) setCollapsed(true)
  }

  const send = async (text: string, image: File | null) => {
    if (!kbId) return
    try {
      const convId = await ensureConversation()
      pinnedRef.current = true
      await chat.send(kbId, convId, text, image)
    } catch (e) { showToast((e as Error).message) }
  }

  const startVoice = () => {
    if (chat.busy) chat.stop()   // barge-in keeps what was said so far
    voice.start(async () => ({ kbId: kbId!, convId: await ensureConversation() }))
  }

  const confirmDelete = async () => {
    const c = toDelete
    setToDelete(null)
    if (!c) return
    try {
      await api.deleteConversation(c.id)
      if (c.id === activeId) startNewChat()
      refreshConversations()
    } catch (e) { showToast((e as Error).message) }
  }

  const rename = async (id: string, title: string) => {
    try { await api.renameConversation(id, title); refreshConversations() } catch (e) { showToast((e as Error).message) }
  }

  const createKb = async (name: string) => {
    const created = await api.createKB(name)
    setKbs(k => [created, ...k])
    setKbId(created.id)
    setActiveId(null)
    setDocsOpen(true)
  }

  const selectKb = (k: KB) => { setKbId(k.id); startNewChat() }

  // ── Keyboard ───────────────────────────────────────────────────────────────
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'o') { e.preventDefault(); startNewChat() }
      if (e.key === 'Escape' && !docsOpen && !toDelete) setSources(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [startNewChat, docsOpen, toDelete])

  // ── Scrolling: follow the answer unless the reader scrolled up ────────────
  const onScroll = () => {
    const el = threadRef.current
    if (!el) return
    setScrolled(el.scrollTop > 4)
    pinnedRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120
  }
  useEffect(() => {
    const el = threadRef.current
    if (el && pinnedRef.current) el.scrollTop = el.scrollHeight
  }, [chat.messages, chat.streaming])

  const thread = useMemo(() => chat.streaming ? [...chat.messages, chat.streaming] : chat.messages,
    [chat.messages, chat.streaming])
  const showEmpty = !chat.loading && thread.length === 0
  const disabledReason = !kb ? 'Create a knowledge base to start' : docs.length === 0 ? 'Upload documents to start asking' : undefined

  return (
    <div className="app">
      <Sidebar
        collapsed={collapsed} onCollapse={() => setCollapsed(true)}
        conversations={conversations} activeId={activeId}
        onSelect={openConversation} onNew={startNewChat}
        onRename={rename} onDelete={setToDelete}
        kbs={kbs} kb={kb} onSelectKb={selectKb} onCreateKb={createKb}
        onOpenDocs={() => setDocsOpen(true)}
        theme={theme} onToggleTheme={() => setTheme(t => (t === 'dark' ? 'light' : 'dark'))}
      />

      <main className="main">
        <header className={`topbar${scrolled ? ' scrolled' : ''}`}>
          {collapsed && (
            <>
              <button className="icon-btn" onClick={() => setCollapsed(false)} title="Open sidebar"><PanelLeftOpen size={18} /></button>
              <button className="icon-btn" onClick={startNewChat} title="New chat"><SquarePen size={18} /></button>
            </>
          )}
          <div className="topbar-title">
            <span className="conv">{active?.title || (activeId ? 'Conversation' : 'New chat')}</span>
            {kb && <span className="chip" title="Knowledge base"><Library size={12} />{kb.name}</span>}
            {indexing > 0 && (
              <button className="chip chip-muted" onClick={() => setDocsOpen(true)} title="Open Documents">
                <Loader2 size={12} className="spin" />Indexing {indexing} document{indexing === 1 ? '' : 's'}…
              </button>
            )}
          </div>
          <span className="topbar-spacer" />
          <button className="icon-btn" onClick={voice.toggleMute} title={voice.muted ? 'Unmute spoken answers' : 'Mute spoken answers'}>
            {voice.muted ? <VolumeX size={18} /> : <Volume2 size={18} />}
          </button>
        </header>

        {showEmpty ? (
          <EmptyState
            kb={kb} docs={docs}
            onAsk={q => send(q, null)}
            onPhoto={() => composerRef.current?.pickImage()}
            onVoice={startVoice}
            onOpenDocs={() => setDocsOpen(true)}
            onCreateKb={createKb}
          />
        ) : (
          <div className="thread" ref={threadRef} onScroll={onScroll}>
            <div className="thread-inner">
              {chat.loading && <div className="thinking" style={{ justifyContent: 'center', padding: 40 }}><span className="dots"><span /><span /><span /></span></div>}
              {thread.map(m => (
                <MessageView
                  key={m.id} message={m} streaming={m.id === 'streaming'}
                  onOpenSources={(citations, focus) => setSources({ citations, focus })}
                />
              ))}
              {chat.error && !chat.busy && thread.length === 0 && (
                <div className="notice"><AlertCircle size={16} />{chat.error}</div>
              )}
            </div>
          </div>
        )}

        <Composer
          ref={composerRef}
          disabled={!!disabledReason}
          disabledReason={disabledReason}
          busy={chat.busy}
          voiceStatus={voice.status}
          kbName={kb?.name}
          onSend={send}
          onStop={chat.stop}
          onMicStart={startVoice}
          onMicStop={voice.stop}
          onMicCancel={voice.cancelRecording}
          onInterrupt={() => { voice.interrupt(); if (chat.busy) chat.stop() }}
        />
      </main>

      {sources && <SourcesPanel citations={sources.citations} focus={sources.focus} onClose={() => setSources(null)} />}
      {docsOpen && kb && (
        <DocumentsDialog kb={kb} onClose={() => { setDocsOpen(false); refreshDocs() }} onChanged={setDocs} />
      )}
      {toDelete && (
        <ConfirmDialog
          title="Delete chat?"
          body={`"${toDelete.title || 'Untitled chat'}" will be permanently deleted.`}
          confirmLabel="Delete"
          onConfirm={confirmDelete}
          onCancel={() => setToDelete(null)}
        />
      )}
      {toast && <div className="toast" role="status"><AlertCircle size={16} />{toast}</div>}
    </div>
  )
}
