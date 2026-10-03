import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { get } from '../api'
import { Alert, Empty, Loading, useApi } from '../components/ui'
import { date, money, money2 } from '../format'

const FILTERS = [
  { value: 'PENDING', label: 'Ready to pay' },
  { value: 'INITIATED', label: 'Initiated' },
  { value: 'DELAYED', label: 'Overdue' },
  { value: 'PAID', label: 'Paid' },
  { value: '', label: 'All' },
]

export default function Payments() {
  const navigate = useNavigate()
  const [filter, setFilter] = useState('PENDING')
  const { data, error, loading } = useApi(() => get('/payments/'), [])

  if (loading) return <Loading />
  if (error) return <Alert tone="error">{error.message}</Alert>

  const open = data.filter((p) => p.status !== 'PAID')
  const rows = data.filter((p) => (filter === 'DELAYED' ? p.is_delayed && p.status !== 'PAID' : filter ? p.status === filter : true))
  const sum = (list) => list.reduce((s, p) => s + Number(p.net_amount), 0)

  return (
    <>
      <div className="page-head">
        <div><h1>Payments</h1><p>Approved claims waiting for settlement. Anything past its due date is overdue.</p></div>
      </div>
      <div className="ledger">
        <div><div className="k">Ready to pay</div><div className="v">{money(sum(data.filter((p) => p.status === 'PENDING')))}</div><div className="s">{data.filter((p) => p.status === 'PENDING').length} claims</div></div>
        <div><div className="k">Initiated</div><div className="v">{money(sum(data.filter((p) => p.status === 'INITIATED')))}</div><div className="s">Waiting for bank confirmation</div></div>
        <div><div className="k">Overdue</div><div className="v" style={{ color: 'var(--bad)' }}>{open.filter((p) => p.is_delayed).length}</div><div className="s">Past the payment period</div></div>
        <div><div className="k">Paid so far</div><div className="v teal">{money(sum(data.filter((p) => p.status === 'PAID')))}</div><div className="s">{data.filter((p) => p.status === 'PAID' && p.is_delayed).length} paid late</div></div>
      </div>
      <div className="tabs">
        {FILTERS.map((f) => (
          <button key={f.label} className={`tab ${filter === f.value ? 'active' : ''}`} onClick={() => setFilter(f.value)}>{f.label}</button>
        ))}
      </div>
      <div className="card">
        {rows.length === 0 ? <Empty icon="wallet" title="Nothing in this list">Approved claims appear here automatically.</Empty> : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Claim</th><th>Employee</th><th className="right">Net amount</th><th>Due</th><th>Status</th><th>Reference</th></tr></thead>
              <tbody>
                {rows.map((p) => (
                  <tr key={p.id} className="clickable" onClick={() => navigate(`/claims/${p.claim_id}`)}>
                    <td className="cell-title"><strong>{p.claim_title}</strong><span>{p.claim_number}</span></td>
                    <td>{p.employee_name}</td>
                    <td className="right num"><strong>{money2(p.net_amount)}</strong></td>
                    <td className="nowrap">{date(p.due_date)}{p.is_delayed && <div className="small" style={{ color: 'var(--bad)' }}>{p.status === 'PAID' ? `paid ${p.days_overdue}d late` : `${p.days_overdue}d overdue`}</div>}</td>
                    <td><span className={`badge ${p.status === 'PAID' ? 'tone-green' : p.status === 'INITIATED' ? 'tone-violet' : p.is_delayed ? 'tone-red' : 'tone-teal'}`}>{p.status_label}</span></td>
                    <td className="small">{p.reference_number || <span className="faint">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  )
}
