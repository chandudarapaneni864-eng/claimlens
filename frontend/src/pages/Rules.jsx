import { useState } from 'react'
import { del, get, patch, post } from '../api'
import Icon from '../components/Icon'
import { Alert, Empty, Field, Loading, useApi, useToast } from '../components/ui'

const CONDITIONS = [
  { value: 'amount_gte', label: 'Claim amount is at least', hint: 'A number, e.g. 25000' },
  { value: 'risk_gte', label: 'Risk score is at least', hint: '0 to 100, e.g. 60' },
  { value: 'category_is', label: 'Category is', hint: 'travel, accommodation, food, medical or other' },
  { value: 'has_finding', label: 'Has a finding of type', hint: 'DUPLICATE, VIOLATION, CONFLICT, MISMATCH, MISSING_DOCUMENT' },
  { value: 'grade_in', label: 'Employee grade is one of', hint: 'Comma-separated, e.g. L3,L4' },
]
const ROLES = [{ value: 'DEPT_HEAD', label: 'Department head' }, { value: 'HR', label: 'HR' }, { value: 'FINANCE', label: 'Finance' }]

export default function Rules() {
  const toast = useToast()
  const { data, error, loading, reload } = useApi(() => get('/routing-rules/'), [])
  const [f, setF] = useState({ name: '', condition: 'amount_gte', value: '', add_role: 'DEPT_HEAD' })
  const [err, setErr] = useState('')
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  const add = async (e) => {
    e.preventDefault()
    setErr('')
    try { await post('/routing-rules/', f); setF({ ...f, name: '', value: '' }); toast('Rule added'); reload() } catch (x) { setErr(x.message) }
  }
  const toggle = async (r) => { await patch(`/routing-rules/${r.id}/`, { is_active: !r.is_active }); reload() }
  const remove = async (r) => { if (window.confirm(`Delete “${r.name}”?`)) { await del(`/routing-rules/${r.id}/`); reload() } }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Approval levels</h1>
          <p>Every claim goes to the employee's manager and then Finance. These rules add more approvers when a claim needs extra scrutiny. They apply to claims submitted from now on.</p>
        </div>
      </div>
      <div className="detail-grid">
        <div className="card">
          <div className="card-head"><h2>Active rules</h2></div>
          {loading ? <Loading /> : error ? <div className="card-body"><Alert tone="error">{error.message}</Alert></div> : data.length === 0 ? <Empty icon="sliders" title="No extra rules">Claims only need the manager and Finance.</Empty> : (
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Rule</th><th>When</th><th>Adds</th><th></th></tr></thead>
                <tbody>
                  {data.map((r) => (
                    <tr key={r.id} style={{ opacity: r.is_active ? 1 : 0.5 }}>
                      <td><strong>{r.name}</strong></td>
                      <td className="small">{r.condition_label} <b>{r.value}</b></td>
                      <td><span className="badge tone-teal plain">{r.add_role_label}</span></td>
                      <td className="right nowrap">
                        <button className="btn sm ghost" onClick={() => toggle(r)}>{r.is_active ? 'Turn off' : 'Turn on'}</button>
                        <button className="btn sm danger" onClick={() => remove(r)} aria-label={`Delete ${r.name}`}><Icon name="trash" size={14} /></button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
        <form className="card" onSubmit={add}>
          <div className="card-head"><h2>Add a rule</h2></div>
          <div className="card-body stack-sm">
            {err && <Alert tone="error">{err}</Alert>}
            <Field label="Name"><input className="input" value={f.name} onChange={set('name')} placeholder="e.g. Hotel claims above ₹20,000" required /></Field>
            <Field label="When">
              <select className="select" value={f.condition} onChange={set('condition')}>{CONDITIONS.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}</select>
            </Field>
            <Field label="Value" hint={CONDITIONS.find((c) => c.value === f.condition)?.hint}><input className="input" value={f.value} onChange={set('value')} required /></Field>
            <Field label="Add approver">
              <select className="select" value={f.add_role} onChange={set('add_role')}>{ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}</select>
            </Field>
            <button className="btn primary"><Icon name="plus" size={16} /> Add rule</button>
          </div>
        </form>
      </div>
    </>
  )
}
