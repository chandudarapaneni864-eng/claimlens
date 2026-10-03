import { Link } from 'react-router-dom'
import { get } from '../api'
import { is, useAuth, APPROVER_ROLES, OVERSIGHT_ROLES } from '../auth'
import Icon from '../components/Icon'
import { Alert, Empty, Loading, StatusBadge, useApi } from '../components/ui'
import { CATEGORY_ICON, date, money } from '../format'

export function ClaimMini({ claim }) {
  return (
    <Link to={`/claims/${claim.id}`} className="claim-mini">
      <span className="cat-ico"><Icon name={CATEGORY_ICON[claim.category] || 'box'} /></span>
      <span className="grow">
        <strong>{claim.title}</strong>
        <span>{claim.claim_number}, {date(claim.expense_date)}</span>
      </span>
      <StatusBadge status={claim.status} label={claim.status_label} />
      <span className="amt">{money(claim.amount)}</span>
    </Link>
  )
}

export default function Dashboard() {
  const { user } = useAuth()
  const { data, error, loading } = useApi(() => get('/dashboard/'), [])
  if (loading) return <Loading />
  if (error) return <Alert tone="error" title="Couldn't load your overview">{error.message}</Alert>

  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'
  const { counts, amounts } = data

  return (
    <>
      <div className="hello">
        <div>
          <h1>{greeting}, {user.first_name || user.username}</h1>
          <p>{user.designation ? `${user.designation}, ${user.department}` : user.department}</p>
        </div>
        <div className="page-actions">
          {is(user, APPROVER_ROLES) && data.approvals_waiting > 0 && (
            <Link to="/approvals" className="btn dark"><Icon name="inbox" /> Review {data.approvals_waiting} claim{data.approvals_waiting > 1 ? 's' : ''}</Link>
          )}
          <Link to="/claims/new" className="btn primary"><Icon name="plus" /> New claim</Link>
        </div>
      </div>

      <div className="ledger">
        <div><div className="k">Claimed so far</div><div className="v">{money(amounts.claimed)}</div><div className="s">{counts.total} submitted claim{counts.total === 1 ? '' : 's'}</div></div>
        <div><div className="k">Being reviewed</div><div className="v">{counts.in_review}</div><div className="s">{counts.action_needed} waiting on you</div></div>
        <div><div className="k">Approved, not yet paid</div><div className="v">{money(amounts.awaiting_payment)}</div><div className="s">{counts.approved} claim{counts.approved === 1 ? '' : 's'}</div></div>
        <div><div className="k">Reimbursed to you</div><div className="v teal">{money(amounts.settled)}</div><div className="s">{counts.settled} settled, {counts.rejected} rejected</div></div>
      </div>

      {data.action_needed.length > 0 && (
        <div className="stack-sm" style={{ marginBottom: 22 }}>
          <h2 className="section-title">Needs your attention</h2>
          <div className="attention">
            {data.action_needed.map((c) => (
              <div key={c.id} className="attention-item">
                <Icon name="alert" size={20} />
                <div className="grow">
                  <strong>{c.title}</strong>
                  <span className="small">{c.status_label}. Open the claim to see what the reviewer asked for.</span>
                </div>
                <Link className="btn sm" to={`/claims/${c.id}`}>Open claim</Link>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="detail-grid">
        <div className="card">
          <div className="card-head">
            <h2>Recent claims</h2>
            <Link to="/claims" className="btn ghost sm">See all</Link>
          </div>
          {data.recent.length === 0 ? (
            <Empty icon="receipt" title="No claims yet" action={<Link to="/claims/new" className="btn primary">Create your first claim</Link>}>
              Start a claim, upload the bill, and the system checks it against policy before your manager sees it.
            </Empty>
          ) : (
            data.recent.map((c) => <ClaimMini key={c.id} claim={c} />)
          )}
        </div>

        <div className="stack">
          <div className="card card-pad">
            <h3 style={{ fontSize: 17, marginBottom: 12 }}>How a claim moves</h3>
            <ol className="stack-sm" style={{ margin: 0, paddingLeft: 18, color: '#34425a', fontSize: 14 }}>
              <li>You fill in the claim and upload bills, tickets or payment proof.</li>
              <li>The system reads each document and compares it with what you typed.</li>
              <li>It finds the policy version that applies and checks limits and required documents.</li>
              <li>It looks for duplicates across everyone's past claims.</li>
              <li>Your manager, and other approvers if needed, review the findings and decide.</li>
              <li>Finance pays the approved amount and records the reference number.</li>
            </ol>
          </div>
          {is(user, OVERSIGHT_ROLES) && (
            <Link to="/analytics" className="card card-pad" style={{ color: 'inherit', textDecoration: 'none' }}>
              <div className="spread">
                <div>
                  <h3 style={{ fontSize: 17 }}>Company analytics</h3>
                  <p className="small muted" style={{ marginTop: 4 }}>Volumes, violations, duplicates and payment delays.</p>
                </div>
                <Icon name="chart" size={26} />
              </div>
            </Link>
          )}
        </div>
      </div>
    </>
  )
}
