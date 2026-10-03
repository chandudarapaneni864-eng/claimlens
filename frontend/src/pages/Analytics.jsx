import { Link } from 'react-router-dom'
import { get } from '../api'
import { ColumnChart, Donut, HBars } from '../components/Charts'
import { Alert, Empty, Loading, RiskMeter, useApi } from '../components/ui'
import { compactMoney, date, money } from '../format'

const STATUS_COLORS = {
  UNDER_REVIEW: '#2f5fa8', CORRECTION_REQUESTED: '#d39a2c', DOCS_REQUESTED: '#e8b65a', APPROVED: '#4fb8a6',
  REJECTED: '#b3322a', PAYMENT_INITIATED: '#6a4fb0', PAID: '#2f7d4a',
}
const FINDING_COLORS = { VIOLATION: '#b3322a', DUPLICATE: '#8e2a5c', MISSING_DOCUMENT: '#d39a2c', MISMATCH: '#2f5fa8', CONFLICT: '#6a4fb0', MISSING_INFO: '#8a95a3', OUTDATED_POLICY: '#5b6879', UNREADABLE: '#8a95a3' }

export default function Analytics() {
  const { data, error, loading } = useApi(() => get('/analytics/'), [])
  if (loading) return <Loading label="Crunching the numbers" />
  if (error) return <Alert tone="error">{error.message}</Alert>
  const t = data.totals

  return (
    <>
      <div className="page-head">
        <div><h1>Analytics</h1><p>Claims submitted across the company, how they were checked, and how quickly they were paid.</p></div>
      </div>

      <div className="ledger">
        <div><div className="k">Claims submitted</div><div className="v">{t.claims}</div><div className="s">{money(t.claimed_amount)} claimed</div></div>
        <div><div className="k">Approval rate</div><div className="v">{t.approval_rate}%</div><div className="s">{t.approved} approved, {t.rejected} rejected</div></div>
        <div><div className="k">Average time to decide</div><div className="v">{t.avg_decision_hours < 48 ? `${t.avg_decision_hours} h` : `${(t.avg_decision_hours / 24).toFixed(1)} d`}</div><div className="s">Submission to final decision</div></div>
        <div><div className="k">Reimbursed</div><div className="v teal">{compactMoney(t.reimbursed_amount)}</div><div className="s">{compactMoney(t.awaiting_payment_amount)} still to pay</div></div>
      </div>

      <div className="ledger" style={{ gridTemplateColumns: 'repeat(4, minmax(0,1fr))' }}>
        <div><div className="k">Waiting for review</div><div className="v">{t.pending_verification}</div><div className="s">{t.with_employee} sent back to employees</div></div>
        <div><div className="k">Policy violations</div><div className="v" style={{ color: 'var(--bad)' }}>{t.policy_violations}</div><div className="s">{t.conflicts} with conflicting policies</div></div>
        <div><div className="k">Missing documents</div><div className="v" style={{ color: 'var(--warn)' }}>{t.missing_documents}</div><div className="s">Claims flagged</div></div>
        <div><div className="k">Possible duplicates</div><div className="v" style={{ color: '#8e2a5c' }}>{t.duplicates}</div><div className="s">{t.delayed_payments} payment{t.delayed_payments === 1 ? "" : "s"} overdue now</div></div>
      </div>

      <div className="grid-2" style={{ marginBottom: 18 }}>
        <div className="card chart-card">
          <div className="card-head"><h2>Amount claimed per month</h2><span className="small muted">Number above each bar is the claim count</span></div>
          <div className="card-body"><ColumnChart data={data.monthly} valueKey="amount" secondaryKey="count" /></div>
        </div>
        <div className="card chart-card">
          <div className="card-head"><h2>Where claims are now</h2></div>
          <div className="card-body">
            <Donut center={{ value: t.claims, label: 'claims' }} items={data.by_status.filter((s) => s.count > 0).map((s) => ({ label: s.label, value: s.count, color: STATUS_COLORS[s.key] || '#8a95a3' }))} />
          </div>
        </div>
      </div>

      <div className="grid-3" style={{ marginBottom: 18 }}>
        <div className="card chart-card">
          <div className="card-head"><h2>By category</h2></div>
          <div className="card-body"><HBars items={data.by_category.map((c) => ({ label: c.label, value: c.amount }))} format={compactMoney} /></div>
        </div>
        <div className="card chart-card">
          <div className="card-head"><h2>Issues found</h2><span className="small muted">Claims affected</span></div>
          <div className="card-body">
            {data.findings.length === 0 ? <p className="muted">No issues found yet.</p> : <HBars items={data.findings.map((f) => ({ label: f.label, value: f.claims, color: FINDING_COLORS[f.kind] }))} />}
          </div>
        </div>
        <div className="card chart-card">
          <div className="card-head"><h2>Risk mix</h2></div>
          <div className="card-body">
            <Donut size={130} thickness={18} items={[
              { label: 'Low', value: data.risk.low, color: '#2f7d4a' },
              { label: 'Medium', value: data.risk.medium, color: '#d39a2c' },
              { label: 'High', value: data.risk.high, color: '#b3322a' },
            ]} />
            <div style={{ marginTop: 16 }}>
              <div className="label" style={{ marginBottom: 8 }}>Pending with</div>
              {data.workload.length === 0 ? <p className="small muted">No one has a queue right now.</p> : <HBars items={data.workload.map((w) => ({ label: w.label, value: w.count, color: '#2f5fa8' }))} />}
            </div>
          </div>
        </div>
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-head"><h2>Riskiest claims in review</h2></div>
          {data.flagged.length === 0 ? <Empty icon="shield" title="Nothing in review" /> : (
            <div className="table-wrap"><table className="table"><tbody>
              {data.flagged.map((c) => (
                <tr key={c.id}>
                  <td className="cell-title"><Link to={`/claims/${c.id}`}><strong>{c.title}</strong></Link><span>{c.claim_number}, {c.employee_name}</span></td>
                  <td className="right num">{money(c.amount)}</td>
                  <td><RiskMeter score={c.risk_score} level={c.risk_level} /></td>
                </tr>
              ))}
            </tbody></table></div>
          )}
        </div>
        <div className="card">
          <div className="card-head"><h2>Overdue payments</h2><span className="small muted">Average settlement {t.avg_settlement_days} days</span></div>
          {data.delayed.length === 0 ? <Empty icon="wallet" title="No overdue payments">Every approved claim is within its payment period.</Empty> : (
            <div className="table-wrap"><table className="table"><tbody>
              {data.delayed.map((p) => (
                <tr key={p.claim_id}>
                  <td className="cell-title"><Link to={`/claims/${p.claim_id}`}><strong>{p.claim_number}</strong></Link><span>{p.employee_name}</span></td>
                  <td className="right num">{money(p.amount)}</td>
                  <td className="small">Due {date(p.due_date)}<div style={{ color: 'var(--bad)' }}>{p.days_overdue} days late</div></td>
                </tr>
              ))}
            </tbody></table></div>
          )}
        </div>
      </div>
    </>
  )
}
