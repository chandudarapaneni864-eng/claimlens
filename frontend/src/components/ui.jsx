import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import Icon from './Icon'
import { STATUS_LABEL, STATUS_TONE } from '../format'

export function StatusBadge({ status, label }) {
  return <span className={`badge tone-${STATUS_TONE[status] || 'gray'}`}>{label || STATUS_LABEL[status] || status}</span>
}

export function RiskMeter({ score = 0, level = 'low', showScore = true }) {
  const on = Math.max(score > 0 ? 1 : 0, Math.ceil(score / 20))
  return (
    <span className={`risk ${level}`} title={`Risk score ${score} of 100`}>
      <span className="risk-bars">
        {[0, 1, 2, 3, 4].map((i) => <i key={i} className={i < on ? 'on' : ''} />)}
      </span>
      {showScore && <span className="num">{score}</span>}
    </span>
  )
}

export function Severity({ level }) {
  return <span className={`sev ${level}`}>{level === 'high' ? 'Serious' : level === 'medium' ? 'Moderate' : 'Minor'}</span>
}

export function Loading({ label = 'Loading' }) {
  return <div className="loading" role="status"><div className="spinner" /><span>{label}</span></div>
}

export function Empty({ icon = 'inbox', title, children, action }) {
  return (
    <div className="empty">
      <Icon name={icon} size={34} stroke={1.6} />
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  )
}

export function Alert({ tone = 'info', title, children, icon }) {
  const ico = icon || (tone === 'error' ? 'alert' : tone === 'warn' ? 'alert' : tone === 'success' ? 'check' : 'info')
  return (
    <div className={`alert ${tone}`} role={tone === 'error' ? 'alert' : undefined}>
      <Icon name={ico} size={18} />
      <div>{title && <strong>{title}</strong>}{children}</div>
    </div>
  )
}

export function Modal({ title, onClose, children, footer, wide }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="modal-back" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-head">
          <h2>{title}</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><Icon name="x" /></button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  )
}

export function Field({ label, hint, error, children, full, htmlFor }) {
  return (
    <div className={`field ${full ? 'full' : ''}`}>
      {label && <label htmlFor={htmlFor}>{label}</label>}
      {children}
      {error ? <span className="err">{error}</span> : hint ? <span className="hint">{hint}</span> : null}
    </div>
  )
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button key={t.value} role="tab" aria-selected={value === t.value} className={`tab ${value === t.value ? 'active' : ''}`} onClick={() => onChange(t.value)}>
          {t.label}
          {t.count !== undefined && <span className="count">{t.count}</span>}
        </button>
      ))}
    </div>
  )
}

const ToastContext = createContext(() => {})

export function ToastProvider({ children }) {
  const [items, setItems] = useState([])
  const push = useCallback((message, tone = 'ok') => {
    const id = Math.random().toString(36).slice(2)
    setItems((list) => [...list, { id, message, tone }])
    setTimeout(() => setItems((list) => list.filter((t) => t.id !== id)), 4200)
  }, [])
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toasts" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`toast ${t.tone === 'error' ? 'error' : ''}`}>
            <Icon name={t.tone === 'error' ? 'alert' : 'check'} size={18} />
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
export const useToast = () => useContext(ToastContext)

export function useApi(loader, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const run = useCallback(() => {
    setState((s) => ({ ...s, loading: true, error: null }))
    return loader()
      .then((data) => setState({ data, error: null, loading: false }))
      .catch((error) => setState({ data: null, error, loading: false }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  useEffect(() => { run() }, [run])
  return { ...state, reload: run, setData: (data) => setState((s) => ({ ...s, data })) }
}
