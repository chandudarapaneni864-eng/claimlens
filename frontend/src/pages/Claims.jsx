import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { get } from '../api'
import { is, useAuth, OVERSIGHT_ROLES } from '../auth'
import Icon from '../components/Icon'
import { Alert, Empty, Loading, RiskMeter, StatusBadge, useApi } from '../components/ui'
import { CATEGORIES, STATUS_LABEL, date, money } from '../format'

const TITLES = {
  mine: ['My claims', 'Everything you have submitted, plus drafts.'],
  team: ['Team claims', 'Claims from people who report to you.'],
  all: ['All claims', 'Every submitted claim across the company.'],
}

export default function Claims() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const scope = params.get('scope') || 'mine'
  const [q, setQ] = useState(params.get('q') || '')
  const status = params.get('status') || ''
  const category = params.get('category') || ''

  useEffect(() => {
    const t = setTimeout(() => {
      const next = new URLSearchParams(params)
      q ? next.set('q', q) : next.delete('q')
      if (next.toString() !== params.toString()) setParams(next, { replace: true })
    }, 300)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q])

  const query = new URLSearchParams({ scope, ...(status && { status }), ...(category && { category }), ...(params.get('q') && { q: params.get('q') }) })
  const { data, error, loading } = useApi(() => get(`/claims/?${query}`), [query.toString()])

  const setFilter = (key, value) => {
    const next = new URLSearchParams(params)
    value ? next.set(key, value) : next.delete(key)
    setParams(next)
  }
  const showEmployee = scope !== 'mine'
  const [title, sub] = TITLES[scope] || TITLES.mine
  const allowed = scope === 'mine' || (scope === 'team' && is(user, 'MANAGER', 'DEPT_HEAD')) || (scope === 'all' && is(user, OVERSIGHT_ROLES))

  if (!allowed) return <Empty icon="shield" title="You don't have access to this list" />

  return (
    <>
      <div className="page-head">
        <div><h1>{title}</h1><p>{sub}</p></div>
        <Link to="/claims/new" className="btn primary"><Icon name="plus" /> New claim</Link>
      </div>

      <div className="toolbar">
        <div className="search">
          <Icon name="search" size={16} />
          <input className="input" placeholder="Search number, title, vendor or name" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search claims" />
        </div>
        <select className="select" value={status} onChange={(e) => setFilter('status', e.target.value)} aria-label="Filter by status">
          <option value="">All statuses</option>
          {Object.entries(STATUS_LABEL).filter(([k]) => scope === 'mine' || k !== 'DRAFT').map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select className="select" value={category} onChange={(e) => setFilter('category', e.target.value)} aria-label="Filter by category">
          <option value="">All categories</option>
          {CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
        </select>
      </div>

      <div className="card">
        {loading ? <Loading /> : error ? <div className="card-body"><Alert tone="error">{error.message}</Alert></div> : data.length === 0 ? (
          <Empty icon="receipt" title={status || category || params.get('q') ? 'No claims match these filters' : 'No claims here yet'}>
            {status || category || params.get('q') ? 'Clear a filter to see more.' : scope === 'mine' ? 'Create a claim to get reimbursed for a business expense.' : 'Claims will show up here once they are submitted.'}
          </Empty>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Claim</th>
                  {showEmployee && <th>Employee</th>}
                  <th>Category</th>
                  <th>Expense date</th>
                  <th className="right">Amount</th>
                  <th>Status</th>
                  <th>Risk</th>
                </tr>
              </thead>
              <tbody>
                {data.map((c) => (
                  <tr key={c.id} className="clickable" onClick={() => navigate(`/claims/${c.id}`)}>
                    <td className="cell-title">
                      <Link to={`/claims/${c.id}`} onClick={(e) => e.stopPropagation()} style={{ color: 'inherit' }}><strong>{c.title}</strong></Link>
                      <span>{c.claim_number}{c.waiting_on ? `, waiting on ${c.waiting_on}` : ''}</span>
                    </td>
                    {showEmployee && <td>{c.employee_name}</td>}
                    <td>{c.category_label}</td>
                    <td className="nowrap">{date(c.expense_date)}</td>
                    <td className="right num nowrap"><strong>{money(c.amount)}</strong></td>
                    <td><StatusBadge status={c.status} label={c.status_label} /></td>
                    <td>{c.status === 'DRAFT' ? <span className="faint small">Not checked</span> : <RiskMeter score={c.risk_score} level={c.risk_level} />}</td>
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
