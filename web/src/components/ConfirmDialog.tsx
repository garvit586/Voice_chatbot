import { useEffect } from 'react'

interface Props {
  title: string
  body: string
  confirmLabel: string
  onConfirm: () => void
  onCancel: () => void
}

export default function ConfirmDialog({ title, body, confirmLabel, onConfirm, onCancel }: Props) {
  useEffect(() => {
    const keys = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel()
      if (e.key === 'Enter') onConfirm()
    }
    document.addEventListener('keydown', keys)
    return () => document.removeEventListener('keydown', keys)
  }, [onConfirm, onCancel])

  return (
    <div className="overlay" onMouseDown={e => { if (e.target === e.currentTarget) onCancel() }}>
      <div className="dialog sm" role="alertdialog" aria-modal="true">
        <div className="dialog-head"><div className="grow"><h2>{title}</h2><p>{body}</p></div></div>
        <div className="dialog-foot" style={{ paddingTop: 20 }}>
          <button className="btn btn-outline" onClick={onCancel}>Cancel</button>
          <button className="btn btn-danger" onClick={onConfirm} autoFocus>{confirmLabel}</button>
        </div>
      </div>
    </div>
  )
}
