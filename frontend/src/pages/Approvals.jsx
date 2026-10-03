import { useState } from 'react'
import { Link } from 'react-router-dom'
import { get } from '../api'
import { useAuth } from '../auth'
import { Alert, Empty, Loading, RiskMeter, useApi } from '../components/ui'
import { RECOMMENDATION, dateTime, money } from '../format'

const REC_TONE = { approve: 'tone-green', review: 'tone-amber', reject: 'tone-red' }

export default function Approvals() {
  const { user } = useAuth()
  const [view, setView] = useState('queue')
  const { data, error, loading } = useApi(() => get(`/approvals/${view === 'history' ? '?view=history' : ''}`), [view])

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Approvals</h1>
          <p>Claims waiting for you as {user.role_label}. The riskiest ones are worth opening first.</p>
        </div>
      </div>
      <div className="tabs" role="tablist">
        <button className={`tab ${view === 'queue' ? 'active' : ''}`} onClick={() => setView('queue')}>Waiting for me {view === 'queue' && data && <span className="count">{data.length}</span>}</button>
        <button className={`tab ${view === 'history' ? 'active' : ''}`} onClick={() => setView('history')}>My decisions</button>
      </div>
      <div className="card">
        {loading ? <Loading /> : error ? <div className="card-body"><Alert tone="error">{error.message}</Alert></div> : data.length === 0 ? (
          <Empty icon="inbox" title={view === 'queue' ? 'Nothing waiting for you' : 'No decisions yet'}>
            {view === 'queue' ? 'New claims routed to you will appear here.' : 'Claims you approve, reject or send back will be listed here.'}
          </Empty>
        ) : (
          [...data].sort((a, b) => (view === 'queue' ? b.claim.risk_score - a.claim.risk_score : 0)).map((row) => {
            const c = row.claim
            const rec = RECOMMENDATION[c.ai_recommendation]
            return (
              <Link key={row.step_id} to={`/claims/${c.id}`} className="queue-card">
                <div>
                  <h3>{c.title}</h3>
                  <div className="meta">{c.claim_number}, {c.employee_name}, {c.department}, {c.category_label}</div>
                  <div className="row" style={{ marginTop: 10 }}>
                    {view === 'queue' ? (
                      <>
                        {rec && <span className={`badge plain ${REC_TONE[c.ai_recommendation]}`}>{rec.stamp}</span>}
                        <span className="small muted">{c.finding_count} finding{c.finding_count === 1 ? '' : 's'}</span>
                        <span className="small muted">Waiting {row.waiting_days ? `${row.waiting_days} day${row.waiting_days > 1 ? 's' : ''}` : 'since today'}</span>
                        <span className="small faint">{row.reason}</span>
                      </>
                    ) : (
                      <>
                        <span className="badge plain tone-gray">{row.status_label}</span>
                        <span className="small muted">{dateTime(row.acted_at)}</span>
                        {row.comment && <span className="small faint">“{row.comment}”</span>}
                      </>
                    )}
                  </div>
                </div>
                <div className="right">
                  <span className="amt">{money(c.amount)}</span>
                  <RiskMeter score={c.risk_score} level={c.risk_level} />
                </div>
              </Link>
            )
          })
        )}
      </div>
    </>
  )
}
