import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { get, post } from '../api'
import Icon from '../components/Icon'
import { Alert, Field, Loading, Modal, RiskMeter, Severity, StatusBadge, useApi, useToast } from '../components/ui'
import { RECOMMENDATION, date, dateTime, money, money2 } from '../format'
import { DocumentCard } from './ClaimForm'

const KIND_ICON = {
  MISMATCH: 'scale', MISSING_INFO: 'info', MISSING_DOCUMENT: 'file', VIOLATION: 'alert',
  DUPLICATE: 'copy', CONFLICT: 'scale', OUTDATED_POLICY: 'clock', UNREADABLE: 'eye',
}
const EVENT_TONE = {
  VERIFIED: 'sys', ROUTED: 'sys', FORWARDED: 'sys', REVERIFIED: 'sys', APPROVED: 'good', APPROVED_STEP: 'good', PAID: 'good',
  REJECTED: 'bad', CORRECTION_REQUESTED: 'warn', DOCS_REQUESTED: 'warn', PAYMENT_INITIATED: 'sys',
}

function pipeline(c) {
  const s = c.status
  const steps = c.steps || []
  const approvedCount = steps.filter((x) => x.status === 'APPROVED').length
  const list = [
    { label: 'Drafted', sub: date(c.created_at), cls: 'done' },
    { label: 'Submitted', sub: c.submitted_at ? date(c.submitted_at) : 'Not yet', cls: c.submitted_at ? 'done' : 'current' },
    { label: 'Checked', sub: c.verified_at ? `Risk ${c.risk_score}` : 'Pending', cls: c.verified_at ? 'done' : '' },
    { label: 'Approvals', sub: steps.length ? `${approvedCount} of ${steps.length}` : 'Pending', cls: '' },
    { label: 'Payment', sub: c.payment ? c.payment.status_label : 'After approval', cls: '' },
    { label: 'Settled', sub: c.payment?.paid_at ? date(c.payment.paid_at) : '', cls: '' },
  ]
  if (s === 'UNDER_REVIEW') list[3].cls = 'current'
  if (['APPROVED', 'PAYMENT_INITIATED', 'PAID'].includes(s)) list[3].cls = 'done'
  if (s === 'APPROVED') list[4].cls = 'current'
  if (s === 'PAYMENT_INITIATED') { list[4].cls = 'current' }
  if (s === 'PAID') { list[4].cls = 'done'; list[5].cls = 'done' }
  if (s === 'REJECTED') { list[3].cls = 'failed'; list[3].sub = 'Rejected' }
  if (s === 'CORRECTION_REQUESTED' || s === 'DOCS_REQUESTED') { list[3].cls = 'waiting'; list[3].sub = 'Sent back to you' }
  return list
}

export default function ClaimDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { data: claim, error, loading, setData } = useApi(() => get(`/claims/${id}/`), [id])
  if (loading && !claim) return <Loading />
  if (error) return <Alert tone="error" title="Couldn't open this claim">{error.status === 404 ? "It doesn't exist or you don't have access to it." : error.message}</Alert>

  const c = claim
  const p = c.permissions
  const sentBack = ['CORRECTION_REQUESTED', 'DOCS_REQUESTED'].includes(c.status)
  const request = sentBack ? [...c.steps].reverse().find((s) => s.comment) : null
  const rejection = c.status === 'REJECTED' ? c.steps.find((s) => s.status === 'REJECTED') : null

  return (
    <>
      <button className="back btn ghost sm" style={{ paddingLeft: 0 }} onClick={() => (window.history.length > 1 ? navigate(-1) : navigate('/claims'))}><Icon name="back" size={16} /> Back</button>
      <div className="claim-title">
        <div>
          <div className="no">{c.claim_number}, {c.category_label}</div>
          <h1>{c.title}</h1>
          <div className="row" style={{ marginTop: 8 }}>
            <StatusBadge status={c.status} label={c.status_label} />
            <span className="small muted">by {c.employee_info.name}, {c.employee_info.designation || c.employee_info.grade}</span>
          </div>
        </div>
        <div className="stack-sm" style={{ alignItems: 'flex-end' }}>
          <div className="amount-big">
            {money2(c.amount)}
            {c.approved_amount && c.approved_amount !== c.amount && <small>Approved {money2(c.approved_amount)}</small>}
          </div>
          <div className="row">
            {p.edit && <Link to={`/claims/${c.id}/edit`} className="btn primary"><Icon name="edit" size={16} /> {sentBack ? 'Fix and resubmit' : 'Continue editing'}</Link>}
            {p.reverify && <Reverify id={c.id} onDone={setData} />}
          </div>
        </div>
      </div>

      <div className="pipeline">
        {pipeline(c).map((s, i) => (
          <div key={s.label} className={`pipe-step ${s.cls}`}>
            <span className="pipe-dot">{s.cls === 'done' ? <Icon name="check" size={15} stroke={3} /> : s.cls === 'failed' ? <Icon name="x" size={15} stroke={3} /> : i + 1}</span>
            <span className="pipe-label">{s.label}</span>
            <span className="pipe-sub">{s.sub}</span>
          </div>
        ))}
      </div>

      {request && (
        <div style={{ marginBottom: 18 }}>
          <Alert tone="warn" title={`${request.acted_by_name} (${request.role_label}) sent this back`}>
            {request.comment} {p.edit && <Link to={`/claims/${c.id}/edit`}>Make the changes</Link>}
          </Alert>
        </div>
      )}
      {rejection && (
        <div style={{ marginBottom: 18 }}>
          <Alert tone="error" title={`Rejected by ${rejection.acted_by_name}`}>{rejection.comment}</Alert>
        </div>
      )}

      <div className="detail-grid">
        <div className="stack">
          {p.decide && <Decision claim={c} onDone={setData} />}
          {(p.initiate_payment || p.complete_payment) && <PaymentAction claim={c} onDone={setData} />}

          <div className="card">
            <div className="card-head"><h2>Claim details</h2></div>
            <div className="card-body">
              <dl className="facts">
                <div><dt>Expense date</dt><dd>{date(c.expense_date)}</dd></div>
                {c.start_date && <div><dt>Period</dt><dd>{date(c.start_date)} to {date(c.end_date)}</dd></div>}
                <div><dt>Vendor</dt><dd>{c.vendor || '—'}</dd></div>
                <div><dt>Invoice number</dt><dd>{c.invoice_number || '—'}</dd></div>
                <div><dt>City</dt><dd>{c.city || '—'}</dd></div>
                <div><dt>Employee</dt><dd>{c.employee_info.name} ({c.employee_info.employee_id || 'no ID'})</dd></div>
                <div><dt>Department and grade</dt><dd>{c.employee_info.department}, {c.employee_info.grade}</dd></div>
                <div><dt>Submitted</dt><dd>{c.submitted_at ? dateTime(c.submitted_at) : 'Not yet'}</dd></div>
                <div><dt>Approval route</dt><dd>{c.verification_level || '—'}</dd></div>
              </dl>
              {c.description && <p className="desc">{c.description}</p>}
            </div>
          </div>

          <div className="card">
            <div className="card-head"><h2>Documents</h2><span className="small muted">{c.documents.length} uploaded</span></div>
            <div className="card-body stack-sm">
              {c.documents.length === 0 ? <p className="muted">No documents uploaded yet.</p> : c.documents.map((d) => <DocumentCard key={d.id} doc={d} form={c} />)}
            </div>
          </div>

          <div className="card">
            <div className="card-head"><h2>Activity</h2><span className="small muted">Full audit trail</span></div>
            <div className="card-body">
              <div className="timeline">
                {[...c.events].reverse().map((e) => (
                  <div key={e.id} className={`tl-item ${EVENT_TONE[e.action] || ''}`}>
                    <span className="tl-dot" />
                    <div>
                      <div className="tl-msg">{e.message}</div>
                      <div className="tl-meta">{e.actor_name}, {dateTime(e.created_at)}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="stack">
          <VerificationReceipt claim={c} />
          {c.steps.length > 0 && <ApprovalChain steps={c.steps} previous={c.previous_steps} />}
          {c.payment && <PaymentCard payment={c.payment} />}
          <PoliciesUsed snapshot={c.policy_snapshot} />
        </div>
      </div>
    </>
  )
}

function VerificationReceipt({ claim: c }) {
  const [open, setOpen] = useState(() => new Set(c.findings.filter((f) => f.severity === 'high').slice(0, 1).map((f) => f.id)))
  const toggle = (fid) => setOpen((s) => { const n = new Set(s); n.has(fid) ? n.delete(fid) : n.add(fid); return n })
  const rec = RECOMMENDATION[c.ai_recommendation]
  const order = { high: 0, medium: 1, low: 2 }
  const findings = [...c.findings].sort((a, b) => order[a.severity] - order[b.severity])
  const meterColor = c.risk_level === 'high' ? 'var(--bad)' : c.risk_level === 'medium' ? '#d39a2c' : 'var(--ok)'

  if (!c.verified_at) {
    return (
      <div className="receipt">
        <div className="receipt-head"><div><h2>Verification report</h2><p>Runs when you submit the claim.</p></div><span className="stamp none">Not checked</span></div>
        <p className="summary-text" style={{ marginTop: 16 }}>Once submitted, every document is read and compared with your form, the applicable policy version is found, limits and required documents are checked, and past claims are scanned for duplicates.</p>
      </div>
    )
  }

  return (
    <div className="receipt">
      <div className="receipt-head">
        <div>
          <h2>Verification report</h2>
          <p>Checked {dateTime(c.verified_at)}</p>
        </div>
        {rec && <span className={`stamp ${rec.tone} stamp-in`}>{rec.stamp}</span>}
      </div>
      <div className="risk-dial">
        <div className="score">{c.risk_score}<small>/100</small></div>
        <div style={{ flex: 1 }}>
          <div className="small muted" style={{ marginBottom: 6 }}>Risk score, {c.risk_level}</div>
          <div className="meter"><i style={{ width: `${Math.max(3, c.risk_score)}%`, background: meterColor }} /></div>
        </div>
      </div>
      <p className="summary-text">{c.verification_summary}</p>

      <div style={{ marginTop: 12 }}>
        {findings.length === 0 && <div className="all-clear"><Icon name="shield" size={20} /> All checks passed</div>}
        {findings.map((f) => (
          <div key={f.id} className={`finding ${open.has(f.id) ? 'open' : ''}`}>
            <button className="finding-btn" onClick={() => toggle(f.id)} aria-expanded={open.has(f.id)}>
              <Severity level={f.severity} />
              <span className="grow">
                <strong>{f.title}</strong>
                <span className="kind">{f.kind_label}</span>
              </span>
              <Icon name="chevron" size={16} />
            </button>
            {open.has(f.id) && (
              <div className="finding-body">
                <p>{f.explanation}</p>
                {f.evidence?.length > 0 && (
                  <table className="evidence">
                    <tbody>
                      {f.evidence.map((e, i) => (
                        <tr key={i}><td>{e.label}</td><td><strong>{e.value}</strong>{e.source && <span className="src">{e.source}</span>}</td></tr>
                      ))}
                    </tbody>
                  </table>
                )}
                {f.policy_excerpt && <div className="policy-quote"><b>{f.policy_label || 'Policy text'}</b>{f.policy_excerpt}</div>}
                {f.related_claim && <Link to={`/claims/${f.related_claim}`} className="small"><Icon name="copy" size={14} /> Open {f.related_claim_number}</Link>}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function ApprovalChain({ steps, previous }) {
  return (
    <div className="card">
      <div className="card-head"><h2>Approval route</h2><span className="small muted">{steps.length} level{steps.length > 1 ? 's' : ''}</span></div>
      <div className="card-body">
        <div className="chain">
          {steps.map((s) => (
            <div key={s.id} className={`chain-step ${s.status}`}>
              <span className="chain-dot">
                {s.status === 'APPROVED' ? <Icon name="check" size={14} stroke={3} /> : s.status === 'REJECTED' ? <Icon name="x" size={14} stroke={3} /> : s.status === 'PENDING' ? <Icon name="clock" size={14} /> : s.sequence}
              </span>
              <div>
                <div className="spread"><strong>{s.role_label}</strong><span className="small muted">{s.status_label}</span></div>
                <div className="small">{s.acted_by_name || s.approver_name || `Any ${s.role_label}`}{s.acted_at ? `, ${dateTime(s.acted_at)}` : ''}</div>
                <div className="reason">{s.reason}</div>
                {s.comment && <div className="comment">{s.comment}</div>}
              </div>
            </div>
          ))}
        </div>
        {previous?.length > 0 && (
          <details style={{ marginTop: 14 }}>
            <summary className="small muted" style={{ cursor: 'pointer' }}>Earlier review rounds ({previous.length} steps)</summary>
            <div className="stack-sm" style={{ marginTop: 10 }}>
              {previous.map((s) => (
                <div key={s.id} className="small">Round {s.round}: {s.role_label}, {s.status_label}{s.acted_by_name ? ` by ${s.acted_by_name}` : ''}{s.comment ? `: ${s.comment}` : ''}</div>
              ))}
            </div>
          </details>
        )}
      </div>
    </div>
  )
}

function PaymentCard({ payment: p }) {
  return (
    <div className="card">
      <div className="card-head">
        <h2>Payment</h2>
        {p.is_delayed ? <span className="badge tone-red">{p.status === 'PAID' ? `Paid ${p.days_overdue} days late` : `${p.days_overdue} days overdue`}</span> : <span className="badge tone-green plain">{p.status_label}</span>}
      </div>
      <div className="card-body">
        <dl className="facts" style={{ gridTemplateColumns: '1fr 1fr' }}>
          <div><dt>Approved</dt><dd className="num">{money2(p.approved_amount)}</dd></div>
          <div><dt>Deductions</dt><dd className="num">{money2(p.deductions)}</dd></div>
          <div><dt>Net payable</dt><dd className="num">{money2(p.net_amount)}</dd></div>
          <div><dt>Due by</dt><dd>{date(p.due_date)}</dd></div>
          <div><dt>Method</dt><dd>{p.method_label}</dd></div>
          <div><dt>Reference</dt><dd>{p.reference_number || '—'}</dd></div>
          {p.initiated_at && <div><dt>Initiated</dt><dd>{date(p.initiated_at)}{p.initiated_by_name ? `, ${p.initiated_by_name}` : ''}</dd></div>}
          {p.paid_at && <div><dt>Paid on</dt><dd>{date(p.paid_at)}</dd></div>}
        </dl>
        {p.deduction_reason && <p className="small muted" style={{ marginTop: 10 }}>Deduction: {p.deduction_reason}</p>}
      </div>
    </div>
  )
}

function PoliciesUsed({ snapshot }) {
  if (!snapshot?.applicable?.length) return null
  return (
    <div className="card">
      <div className="card-head"><h2>Policies applied</h2></div>
      <div className="card-body stack-sm">
        {snapshot.applicable.map((p) => (
          <div key={p.id} className="spread small">
            <span><strong>{p.code} v{p.version}</strong> {p.title}</span>
            <span className="muted nowrap">{p.limit_amount ? `${money(p.limit_amount)} ${p.limit_basis.toLowerCase()}` : 'Rules only'}</span>
          </div>
        ))}
        {snapshot.superseded?.length > 0 && <p className="small faint">Not used: {snapshot.superseded.map((p) => `${p.code} v${p.version} (${p.effective_to ? `ended ${date(p.effective_to)}` : `from ${date(p.effective_from)}`})`).join(', ')}</p>}
      </div>
    </div>
  )
}

function Decision({ claim, onDone }) {
  const toast = useToast()
  const [comment, setComment] = useState('')
  const [amount, setAmount] = useState('')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [confirm, setConfirm] = useState(null)
  const step = claim.steps.find((s) => s.status === 'PENDING')
  const overLimit = claim.findings.find((f) => f.kind === 'VIOLATION' && f.evidence?.find((e) => e.label === 'Allowed'))
  const suggested = overLimit?.evidence.find((e) => e.label === 'Allowed')?.value

  const act = async (action) => {
    setConfirm(null)
    if (action !== 'approve' && !comment.trim()) { setError('Add a comment so the employee knows what to do.'); return }
    setBusy(action)
    setError('')
    try {
      const updated = await post(`/claims/${claim.id}/decide/`, { action, comment, approved_amount: amount || null })
      onDone(updated)
      toast(action === 'approve' ? 'Approved' : action === 'reject' ? 'Claim rejected' : 'Sent back to the employee')
    } catch (e) { setError(e.message) } finally { setBusy('') }
  }

  return (
    <div className="card decision">
      <div className="card-head"><h2>Your decision as {step?.role_label}</h2><RiskMeter score={claim.risk_score} level={claim.risk_level} /></div>
      <div className="card-body stack-sm">
        {error && <Alert tone="error">{error}</Alert>}
        <p className="small muted">Read the verification report first. Approve, send it back for a fix, ask for more documents, or reject.</p>
        <div className="form-grid">
          <Field label="Comment" full hint="Required unless you approve.">
            <textarea className="textarea" style={{ minHeight: 70 }} value={comment} onChange={(e) => setComment(e.target.value)} placeholder="e.g. Please attach the pre-approval email from your manager." />
          </Field>
          <Field label="Approve a lower amount (optional)" hint={suggested ? `Policy allows ${suggested}.` : `Up to ${money2(claim.amount)}.`}>
            <div className="input-prefix"><span>₹</span><input className="input num" type="number" min="0" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder={String(claim.approved_amount || claim.amount)} /></div>
          </Field>
        </div>
        <div className="decision-actions">
          <button className="btn primary" disabled={Boolean(busy)} onClick={() => act('approve')}>{busy === 'approve' ? <span className="spinner sm" /> : <Icon name="check" size={16} />} Approve{amount ? ` ${money(amount)}` : ''}</button>
          <button className="btn" disabled={Boolean(busy)} onClick={() => act('request_correction')}><Icon name="edit" size={16} /> Request correction</button>
          <button className="btn" disabled={Boolean(busy)} onClick={() => act('request_documents')}><Icon name="file" size={16} /> Request documents</button>
          <button className="btn danger" disabled={Boolean(busy)} onClick={() => (comment.trim() ? setConfirm('reject') : setError('Add a reason before rejecting.'))}><Icon name="x" size={16} /> Reject</button>
        </div>
      </div>
      {confirm === 'reject' && (
        <Modal title="Reject this claim?" onClose={() => setConfirm(null)}
          footer={<><button className="btn" onClick={() => setConfirm(null)}>Cancel</button><button className="btn solid-danger" onClick={() => act('reject')}>Reject claim</button></>}>
          <p>{claim.employee_info.name} will see your reason: “{comment}”. The remaining approval steps will be skipped.</p>
        </Modal>
      )}
    </div>
  )
}

function PaymentAction({ claim, onDone }) {
  const toast = useToast()
  const [form, setForm] = useState({ method: 'bank_transfer', deductions: '', deduction_reason: '', remarks: '', reference_number: '', paid_on: new Date().toISOString().slice(0, 10) })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  const initiating = claim.permissions.initiate_payment

  const go = async () => {
    setBusy(true)
    setError('')
    try {
      const updated = initiating
        ? await post(`/claims/${claim.id}/payment/initiate/`, { method: form.method, deductions: form.deductions || 0, deduction_reason: form.deduction_reason, remarks: form.remarks })
        : await post(`/claims/${claim.id}/payment/complete/`, { reference_number: form.reference_number, paid_on: form.paid_on })
      onDone(updated)
      toast(initiating ? 'Payment initiated' : 'Payment recorded. Claim settled.')
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const net = Number(claim.payment?.approved_amount || 0) - Number(form.deductions || 0)
  return (
    <div className="card decision">
      <div className="card-head"><h2>{initiating ? 'Initiate payment' : 'Record the payment'}</h2><span className="num"><strong>{money2(initiating ? net : claim.payment?.net_amount)}</strong></span></div>
      <div className="card-body stack-sm">
        {error && <Alert tone="error">{error}</Alert>}
        {claim.payment?.is_delayed && <Alert tone="warn">This payment was due on {date(claim.payment.due_date)} and is {claim.payment.days_overdue} days late.</Alert>}
        {initiating ? (
          <div className="form-grid">
            <Field label="Payment method">
              <select className="select" value={form.method} onChange={set('method')}>
                <option value="bank_transfer">Bank transfer</option><option value="upi">UPI</option><option value="payroll">With salary</option><option value="cheque">Cheque</option>
              </select>
            </Field>
            <Field label="Deductions" hint="Non-reimbursable items found on the bill.">
              <div className="input-prefix"><span>₹</span><input className="input num" type="number" min="0" step="0.01" value={form.deductions} onChange={set('deductions')} /></div>
            </Field>
            {Number(form.deductions) > 0 && <Field label="Reason for deduction" full><input className="input" value={form.deduction_reason} onChange={set('deduction_reason')} placeholder="e.g. Minibar charges are not reimbursable" /></Field>}
            <Field label="Remarks" full><input className="input" value={form.remarks} onChange={set('remarks')} /></Field>
          </div>
        ) : (
          <div className="form-grid">
            <Field label="Bank or UPI reference"><input className="input" value={form.reference_number} onChange={set('reference_number')} placeholder="e.g. NEFT-HDFC-7781203" /></Field>
            <Field label="Paid on"><input className="input" type="date" value={form.paid_on} onChange={set('paid_on')} /></Field>
          </div>
        )}
        <div><button className="btn primary" onClick={go} disabled={busy}>{busy ? <span className="spinner sm" /> : <Icon name="bank" size={16} />} {initiating ? 'Initiate payment' : 'Mark as paid'}</button></div>
      </div>
    </div>
  )
}

function Reverify({ id, onDone }) {
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  return (
    <button className="btn" disabled={busy} onClick={async () => {
      setBusy(true)
      try { onDone(await post(`/claims/${id}/reverify/`)); toast('Checks re-run with the current policies') } catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
    }}>{busy ? <span className="spinner sm" /> : <Icon name="refresh" size={16} />} Re-run checks</button>
  )
}
