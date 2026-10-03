import { useState } from 'react'
import { del, get, patch, post } from '../api'
import { is, useAuth } from '../auth'
import Icon from '../components/Icon'
import { Alert, Empty, Field, Loading, Modal, Tabs, useApi, useToast } from '../components/ui'
import { CATEGORIES, DOC_LABEL, DOC_TYPES, date, money } from '../format'

const GRADES = ['L1', 'L2', 'L3', 'L4']

export default function Policies() {
  const { user } = useAuth()
  const [tab, setTab] = useState('kb')
  const [editing, setEditing] = useState(null)
  const list = useApi(() => get('/policies/'), [])
  const conflicts = useApi(() => get('/policies/conflicts/'), [])
  const admin = is(user, 'ADMIN')

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Policies</h1>
          <p>The rules every claim is checked against. Each policy is split into passages that the verification step searches when it explains a finding.</p>
        </div>
        {admin && <button className="btn primary" onClick={() => setEditing({})}><Icon name="plus" /> New policy</button>}
      </div>
      <Tabs value={tab} onChange={setTab} tabs={[
        { value: 'kb', label: 'Knowledge base', count: list.data?.length },
        { value: 'ask', label: 'Ask the policies' },
        { value: 'conflicts', label: 'Conflicts', count: conflicts.data?.length },
      ]} />
      {tab === 'kb' && <KnowledgeBase state={list} admin={admin} onEdit={setEditing} />}
      {tab === 'ask' && <Ask />}
      {tab === 'conflicts' && <Conflicts state={conflicts} />}
      {editing && <PolicyEditor policy={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); list.reload(); conflicts.reload() }} />}
    </>
  )
}

function KnowledgeBase({ state, admin, onEdit }) {
  const [cat, setCat] = useState('')
  const [expanded, setExpanded] = useState(null)
  if (state.loading) return <Loading />
  if (state.error) return <Alert tone="error">{state.error.message}</Alert>
  const rows = state.data.filter((p) => !cat || p.category === cat)
  return (
    <>
      <div className="toolbar">
        <select className="select" value={cat} onChange={(e) => setCat(e.target.value)} aria-label="Filter by category">
          <option value="">All categories</option>
          {[...CATEGORIES, { value: 'all', label: 'General (all categories)' }].map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
        </select>
      </div>
      <div className="card">
        {rows.length === 0 ? <Empty icon="book" title="No policies in this category" /> : rows.map((p) => {
          const live = p.is_active && (!p.effective_to || p.effective_to >= new Date().toISOString().slice(0, 10))
          return (
            <div key={p.id} className="policy-card">
              <div>
                <div className="code">{p.code} v{p.version}, {p.source_label}</div>
                <h3>{p.title}</h3>
                <div className="policy-meta">
                  <span>Category <b>{p.category_label}</b></span>
                  {p.limit_amount && <span>Limit <b>{money(p.limit_amount)} {p.limit_basis_label.toLowerCase()}</b></span>}
                  <span>Grades <b>{p.applicable_grades.length ? p.applicable_grades.join(', ') : 'All'}</b></span>
                  <span>From <b>{date(p.effective_from)}</b>{p.effective_to && <> to <b>{date(p.effective_to)}</b></>}</span>
                  {p.required_documents.length > 0 && <span>Needs <b>{p.required_documents.map((d) => DOC_LABEL[d] || d).join(', ')}</b></span>}
                  {p.preapproval_above && <span>Pre-approval above <b>{money(p.preapproval_above)}</b></span>}
                  {p.submission_window_days && <span>Submit within <b>{p.submission_window_days} days</b></span>}
                </div>
                {expanded === p.id && <p className="policy-text">{p.text}</p>}
              </div>
              <div className="stack-sm" style={{ alignItems: 'flex-end' }}>
                <span className={`badge ${live ? 'tone-green' : 'tone-gray'}`}>{!p.is_active ? 'Inactive' : live ? 'In force' : 'Expired'}</span>
                <div className="row">
                  <button className="btn sm ghost" onClick={() => setExpanded(expanded === p.id ? null : p.id)}>{expanded === p.id ? 'Hide text' : 'Read text'}</button>
                  {admin && <button className="btn sm" onClick={() => onEdit(p)}><Icon name="edit" size={14} /> Edit</button>}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </>
  )
}

function Ask() {
  const [q, setQ] = useState('')
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const examples = ['hotel limit per night in Mumbai', 'what documents for a medical claim', 'do flights need prior approval', 'can I claim alcohol']
  const go = async (query = q) => {
    if (!query.trim()) return
    setQ(query)
    setBusy(true)
    setError('')
    try { setRes(await get(`/policies/search/?q=${encodeURIComponent(query)}&k=5`)) } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const top = res?.results?.[0]?.score || 1
  return (
    <div className="card">
      <div className="card-body stack">
        <p className="muted">This is the retrieval step on its own. Type a question and see which policy passages the system would quote as evidence.</p>
        <form className="row" onSubmit={(e) => { e.preventDefault(); go() }}>
          <input className="input" style={{ flex: 1, minWidth: 220 }} value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. hotel limit per night" aria-label="Question" />
          <button className="btn primary" disabled={busy}>{busy ? <span className="spinner sm" /> : <Icon name="search" size={16} />} Search policies</button>
        </form>
        <div className="row">{examples.map((e) => <button key={e} className="btn sm ghost" onClick={() => go(e)}>{e}</button>)}</div>
        {error && <Alert tone="error">{error}</Alert>}
        {res && (res.results.length === 0 ? <Empty icon="search" title="No passages found">Try different words.</Empty> : (
          <div>
            {res.results.map((r) => (
              <div key={r.chunk_id} className="rag-result">
                <div className="spread">
                  <strong className="small">{r.policy_code} v{r.version}, {r.policy_title}</strong>
                  <span className="small muted nowrap">match {(r.score * 100).toFixed(0)}<span className="score-bar"><i style={{ width: `${(r.score / top) * 100}%` }} /></span></span>
                </div>
                <p className="policy-text" style={{ marginTop: 6 }}>{r.text.split('\n').slice(1).join('\n')}</p>
              </div>
            ))}
            <p className="small faint" style={{ marginTop: 10 }}>Ranked with {res.results[0].method === 'tfidf' ? 'TF-IDF keyword similarity' : 'sentence embeddings'}.</p>
          </div>
        ))}
      </div>
    </div>
  )
}

function Conflicts({ state }) {
  if (state.loading) return <Loading />
  if (state.error) return <Alert tone="error">{state.error.message}</Alert>
  if (state.data.length === 0) return <div className="card"><Empty icon="shield" title="No conflicts found">Active policies that overlap in time and audience all agree.</Empty></div>
  return (
    <>
      <Alert tone="warn" title="These policies overlap and say different things">Claims covered by both are flagged for HR clarification until one is updated or retired.</Alert>
      <div className="card" style={{ marginTop: 14 }}>
        {state.data.map((c, i) => (
          <div key={i} className="conflict-row">
            <div><div className="code small" style={{ fontWeight: 700, color: 'var(--teal-strong)' }}>{c.a.label}, {c.a.source}</div><div>{c.a.title}</div></div>
            <span className="vs"><Icon name="scale" size={16} /></span>
            <div><div className="code small" style={{ fontWeight: 700, color: 'var(--teal-strong)' }}>{c.b.label}, {c.b.source}</div><div>{c.b.title}</div><div className="small" style={{ color: 'var(--warn)', marginTop: 4 }}>{c.issues.join('; ')}</div></div>
          </div>
        ))}
      </div>
    </>
  )
}

const BLANK = { code: '', title: '', category: 'travel', version: 1, source: 'HR', effective_from: new Date().toISOString().slice(0, 10), effective_to: '', applicable_grades: [], applicable_departments: [], limit_amount: '', limit_basis: 'per_claim', required_documents: [], preapproval_above: '', submission_window_days: '', text: '', is_active: true }

function PolicyEditor({ policy, onClose, onSaved }) {
  const toast = useToast()
  const [f, setF] = useState({ ...BLANK, ...policy, effective_to: policy.effective_to || '', limit_amount: policy.limit_amount || '', preapproval_above: policy.preapproval_above || '', submission_window_days: policy.submission_window_days || '' })
  const [depts, setDepts] = useState((policy.applicable_departments || []).join(', '))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const toggle = (k, v) => setF({ ...f, [k]: f[k].includes(v) ? f[k].filter((x) => x !== v) : [...f[k], v] })

  const save = async () => {
    setBusy(true)
    setError('')
    const body = {
      ...f,
      applicable_departments: depts.split(',').map((d) => d.trim()).filter(Boolean),
      effective_to: f.effective_to || null,
      limit_amount: f.limit_amount || null,
      preapproval_above: f.preapproval_above || null,
      submission_window_days: f.submission_window_days || null,
    }
    delete body.chunks
    try {
      policy.id ? await patch(`/policies/${policy.id}/`, body) : await post('/policies/', body)
      toast(policy.id ? 'Policy updated and re-indexed' : 'Policy added to the knowledge base')
      onSaved()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const retire = async () => {
    if (!window.confirm('Delete this policy? Past claims keep their snapshot, but it will no longer be used.')) return
    try { await del(`/policies/${policy.id}/`); toast('Policy deleted'); onSaved() } catch (e) { setError(e.message) }
  }

  return (
    <Modal wide title={policy.id ? `Edit ${policy.code} v${policy.version}` : 'New policy'} onClose={onClose}
      footer={<>{policy.id && <button className="btn danger" style={{ marginRight: 'auto' }} onClick={retire}>Delete</button>}<button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save} disabled={busy}>{busy && <span className="spinner sm" />} Save policy</button></>}>
      <div className="stack">
        {error && <Alert tone="error">{error}</Alert>}
        <Alert tone="info">To change a rule from a date, add a new version with the same code instead of editing the old one. Older claims stay checked against the version that applied to them.</Alert>
        <div className="form-grid">
          <Field label="Code" hint="Shared by every version, e.g. TRV-ACC"><input className="input" value={f.code} onChange={set('code')} /></Field>
          <Field label="Version"><input className="input" type="number" min="1" value={f.version} onChange={set('version')} /></Field>
          <Field label="Title" full><input className="input" value={f.title} onChange={set('title')} /></Field>
          <Field label="Category">
            <select className="select" value={f.category} onChange={set('category')}>
              {[...CATEGORIES, { value: 'all', label: 'All categories' }].map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
          </Field>
          <Field label="Issued by">
            <select className="select" value={f.source} onChange={set('source')}><option value="HR">HR policy</option><option value="FINANCE">Finance circular</option><option value="ADMIN">Administration</option></select>
          </Field>
          <Field label="In force from"><input className="input" type="date" value={f.effective_from} onChange={set('effective_from')} /></Field>
          <Field label="Until" hint="Leave empty if open-ended."><input className="input" type="date" value={f.effective_to} onChange={set('effective_to')} /></Field>
          <Field label="Limit amount"><div className="input-prefix"><span>₹</span><input className="input" type="number" value={f.limit_amount} onChange={set('limit_amount')} /></div></Field>
          <Field label="Limit applies">
            <select className="select" value={f.limit_basis} onChange={set('limit_basis')}><option value="per_claim">Per claim</option><option value="per_day">Per day</option><option value="per_night">Per night</option><option value="per_month">Per month</option></select>
          </Field>
          <Field label="Pre-approval needed above"><div className="input-prefix"><span>₹</span><input className="input" type="number" value={f.preapproval_above} onChange={set('preapproval_above')} /></div></Field>
          <Field label="Submit within (days)"><input className="input" type="number" value={f.submission_window_days} onChange={set('submission_window_days')} /></Field>
          <div className="field full">
            <span className="label">Grades covered (none ticked means all)</span>
            <div className="row">{GRADES.map((g) => <label key={g} className="check"><input type="checkbox" checked={f.applicable_grades.includes(g)} onChange={() => toggle('applicable_grades', g)} />{g}</label>)}</div>
          </div>
          <Field label="Departments covered" full hint="Comma-separated. Leave empty for all departments."><input className="input" value={depts} onChange={(e) => setDepts(e.target.value)} /></Field>
          <div className="field full">
            <span className="label">Required documents</span>
            <div className="row">{DOC_TYPES.filter((d) => d.value !== 'other').map((d) => <label key={d.value} className="check"><input type="checkbox" checked={f.required_documents.includes(d.value)} onChange={() => toggle('required_documents', d.value)} />{d.label}</label>)}</div>
          </div>
          <Field label="Policy wording" full hint="Separate paragraphs with a blank line. Each paragraph becomes a searchable passage.">
            <textarea className="textarea" style={{ minHeight: 180 }} value={f.text} onChange={set('text')} />
          </Field>
          <label className="check"><input type="checkbox" checked={f.is_active} onChange={set('is_active')} /> Active</label>
        </div>
      </div>
    </Modal>
  )
}
