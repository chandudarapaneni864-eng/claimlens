import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { del, get, patch, post, upload } from '../api'
import { useAuth } from '../auth'
import Icon from '../components/Icon'
import { Alert, Field, Loading, Modal, useToast } from '../components/ui'
import { CATEGORIES, DOC_LABEL, DOC_TYPES, FIELD_LABEL, date, money, requirementMet, today } from '../format'

const EMPTY = { category: '', title: '', description: '', amount: '', expense_date: '', start_date: '', end_date: '', vendor: '', invoice_number: '', city: '' }
const DEFAULT_DOC = { travel: 'ticket', accommodation: 'invoice', food: 'bill', medical: 'medical_bill', other: 'invoice' }
const NEEDS_PERIOD = ['travel', 'accommodation']

function toForm(claim) {
  const f = { ...EMPTY }
  Object.keys(EMPTY).forEach((k) => { f[k] = claim[k] ?? '' })
  return f
}

function payload(form) {
  const p = { ...form }
  ;['start_date', 'end_date'].forEach((k) => { if (!p[k]) p[k] = null })
  if (!NEEDS_PERIOD.includes(p.category)) { p.start_date = null; p.end_date = null }
  return p
}

function validate(form) {
  const e = {}
  if (!form.category) e.category = 'Choose what kind of expense this is.'
  if (!form.title.trim()) e.title = 'Give the claim a short title.'
  if (!(Number(form.amount) > 0)) e.amount = 'Enter the amount you paid.'
  if (!form.expense_date) e.expense_date = 'Enter the date of the expense.'
  else if (form.expense_date > today()) e.expense_date = "The expense date can't be in the future."
  if (form.start_date && form.end_date && form.end_date < form.start_date) e.end_date = "End date can't be before the start date."
  return e
}

export default function ClaimForm() {
  const { id } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const { user } = useAuth()
  const [claim, setClaim] = useState(null)
  const [form, setForm] = useState(EMPTY)
  const [saved, setSaved] = useState(EMPTY)
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(Boolean(id))
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [policies, setPolicies] = useState(null)
  const [confirmSubmit, setConfirmSubmit] = useState(false)

  useEffect(() => {
    if (!id) { setClaim(null); setForm(EMPTY); setSaved(EMPTY); return }
    setLoading(true)
    get(`/claims/${id}/`).then((c) => { setClaim(c); setForm(toForm(c)); setSaved(toForm(c)) })
      .catch((e) => setError(e.message)).finally(() => setLoading(false))
  }, [id])

  useEffect(() => {
    if (!form.category) { setPolicies(null); return }
    const t = setTimeout(() => {
      const on = form.start_date || form.expense_date || today()
      get(`/policies/applicable/?category=${form.category}&date=${on}`).then(setPolicies).catch(() => setPolicies(null))
    }, 250)
    return () => clearTimeout(t)
  }, [form.category, form.expense_date, form.start_date])

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target ? e.target.value : e }))
  const dirty = JSON.stringify(form) !== JSON.stringify(saved)
  const docs = claim?.documents || []

  const save = async () => {
    const e = validate(form)
    setErrors(e)
    if (Object.keys(e).length) return null
    setError('')
    if (!id) {
      const created = await post('/claims/', payload(form))
      toast('Draft saved. Now add your documents.')
      navigate(`/claims/${created.id}/edit`, { replace: true })
      return created
    }
    const updated = await patch(`/claims/${id}/`, payload(form))
    setClaim(updated)
    setForm(toForm(updated))
    setSaved(toForm(updated))
    return updated
  }

  const run = (label, fn) => async () => {
    setBusy(label)
    try { await fn() } catch (e) { setError(e.message) } finally { setBusy('') }
  }

  const onSave = run('save', async () => { if (await save()) id && toast('Changes saved') })

  const onSubmit = run('submit', async () => {
    setConfirmSubmit(false)
    if (dirty && !(await save())) return
    await post(`/claims/${id}/submit/`)
    toast('Submitted. Verification is complete.')
    navigate(`/claims/${id}`)
  })

  if (loading) return <Loading />
  if (id && claim && !claim.permissions.edit) {
    return (
      <Alert tone="info" title="This claim can't be edited now">
        It has already been submitted. <Link to={`/claims/${id}`}>Open the claim</Link> to follow its progress.
      </Alert>
    )
  }

  const uploadedTypes = docs.map((d) => d.doc_type)
  const required = [...new Set((policies?.applicable || []).flatMap((p) => p.required_documents))]
  const sentBack = claim && ['CORRECTION_REQUESTED', 'DOCS_REQUESTED'].includes(claim.status)
  const lastRequest = sentBack ? [...(claim.steps || [])].reverse().find((s) => s.comment) : null

  return (
    <>
      <Link to={id ? `/claims/${id}` : '/claims'} className="back"><Icon name="back" size={16} /> {id ? 'Back to claim' : 'My claims'}</Link>
      <div className="page-head">
        <div>
          <h1>{id ? (sentBack ? 'Fix and resubmit' : 'Finish your claim') : 'New claim'}</h1>
          <p>{id ? `${claim.claim_number}. Add documents, check the policy panel, then submit.` : 'Tell us about the expense. You will add bills and payment proof on the next step.'}</p>
        </div>
      </div>

      {sentBack && lastRequest && (
        <div style={{ marginBottom: 18 }}>
          <Alert tone="warn" title={`${lastRequest.acted_by_name || lastRequest.role_label} asked for changes`}>{lastRequest.comment}</Alert>
        </div>
      )}
      {error && <div style={{ marginBottom: 18 }}><Alert tone="error">{error}</Alert></div>}

      <div className="detail-grid">
        <div className="stack">
          <div className="card">
            <div className="card-head"><h2>Expense details</h2>{id && dirty && <span className="badge tone-amber">Unsaved changes</span>}</div>
            <div className="card-body stack">
              <div className="field">
                <span className="label">What kind of expense?</span>
                <div className="category-picker" role="radiogroup" aria-label="Category">
                  {CATEGORIES.map((c) => (
                    <button type="button" key={c.value} role="radio" aria-checked={form.category === c.value}
                      className={`cat-option ${form.category === c.value ? 'selected' : ''}`} onClick={() => setForm((f) => ({ ...f, category: c.value }))}>
                      <Icon name={c.icon} size={20} />
                      <strong>{c.short || c.label}</strong>
                      <span className="small muted">{c.hint}</span>
                    </button>
                  ))}
                </div>
                {errors.category && <span className="err">{errors.category}</span>}
              </div>

              <div className="form-grid">
                <Field label="Title" full error={errors.title} htmlFor="title">
                  <input id="title" className="input" value={form.title} onChange={set('title')} placeholder="e.g. Hotel stay for client workshop in Mumbai" maxLength={200} />
                </Field>
                <Field label="Amount paid" error={errors.amount} htmlFor="amount" hint="Include taxes, as on the final bill.">
                  <div className="input-prefix"><span>₹</span><input id="amount" className="input num" type="number" min="0" step="0.01" value={form.amount} onChange={set('amount')} /></div>
                </Field>
                <Field label="Expense date" error={errors.expense_date} htmlFor="expense_date" hint="The bill or invoice date.">
                  <input id="expense_date" className="input" type="date" max={today()} value={form.expense_date} onChange={set('expense_date')} />
                </Field>
                {NEEDS_PERIOD.includes(form.category) && (
                  <>
                    <Field label={form.category === 'accommodation' ? 'Check-in' : 'Trip start'} htmlFor="start_date">
                      <input id="start_date" className="input" type="date" value={form.start_date || ''} onChange={set('start_date')} />
                    </Field>
                    <Field label={form.category === 'accommodation' ? 'Check-out' : 'Trip end'} error={errors.end_date} htmlFor="end_date">
                      <input id="end_date" className="input" type="date" value={form.end_date || ''} onChange={set('end_date')} />
                    </Field>
                  </>
                )}
                <Field label="Vendor" htmlFor="vendor" hint="Who you paid.">
                  <input id="vendor" className="input" value={form.vendor} onChange={set('vendor')} placeholder="e.g. The Orchid Residency" />
                </Field>
                <Field label="Invoice or bill number" htmlFor="invoice_number" hint="Used to match documents and catch duplicates.">
                  <input id="invoice_number" className="input" value={form.invoice_number} onChange={set('invoice_number')} />
                </Field>
                <Field label="City" htmlFor="city">
                  <input id="city" className="input" value={form.city} onChange={set('city')} />
                </Field>
                <Field label="Business purpose" full htmlFor="description" hint="Who it was for and why. Team meals need attendee names.">
                  <textarea id="description" className="textarea" value={form.description} onChange={set('description')} />
                </Field>
              </div>
              <div className="row" style={{ justifyContent: 'flex-end' }}>
                {id ? (
                  <button className="btn" onClick={onSave} disabled={!dirty || Boolean(busy)}>{busy === 'save' && <span className="spinner sm" />} Save changes</button>
                ) : (
                  <button className="btn primary" onClick={onSave} disabled={Boolean(busy)}>{busy === 'save' && <span className="spinner sm" />} Save and add documents</button>
                )}
              </div>
            </div>
          </div>

          {id && (
            <Documents claim={claim} form={form} onChange={(documents) => setClaim((c) => ({ ...c, documents }))}
              onFill={(fields) => setForm((f) => ({ ...f, ...fields }))} onError={setError} />
          )}
        </div>

        <div className="stack">
          <PolicyPanel policies={policies} form={form} required={required} uploadedTypes={uploadedTypes} hasClaim={Boolean(id)} grade={user.grade} />
          {id && (
            <div className="card card-pad stack-sm">
              <h3 style={{ fontSize: 17 }}>Ready to submit?</h3>
              <p className="small muted">Submitting runs the automatic checks and sends the claim to {claim.employee_info.manager || 'your manager'}. You can't edit it after that unless a reviewer sends it back.</p>
              <button className="btn primary block" disabled={Boolean(busy) || docs.length === 0} onClick={() => setConfirmSubmit(true)}>
                {busy === 'submit' ? <span className="spinner sm" /> : <Icon name="send" size={16} />} {sentBack ? 'Resubmit for verification' : 'Submit for verification'}
              </button>
              {docs.length === 0 && <span className="small faint">Upload at least one document first.</span>}
            </div>
          )}
        </div>
      </div>

      {confirmSubmit && (
        <Modal title="Submit this claim?" onClose={() => setConfirmSubmit(false)}
          footer={<><button className="btn" onClick={() => setConfirmSubmit(false)}>Keep editing</button><button className="btn primary" onClick={onSubmit}>Submit claim</button></>}>
          <p>{money(form.amount)} for {form.title || 'this expense'}, with {docs.length} document{docs.length === 1 ? '' : 's'}.</p>
          {required.some((r) => !requirementMet(r, uploadedTypes)) && (
            <div style={{ marginTop: 14 }}>
              <Alert tone="warn" title="Some required documents are missing">
                {required.filter((r) => !requirementMet(r, uploadedTypes)).map((r) => DOC_LABEL[r] || r).join(', ')}. The claim will be flagged and may be sent back.
              </Alert>
            </div>
          )}
        </Modal>
      )}
    </>
  )
}

function PolicyPanel({ policies, form, required, uploadedTypes, hasClaim, grade }) {
  if (!form.category) {
    return (
      <div className="card card-pad">
        <h3 style={{ fontSize: 17, marginBottom: 6 }}>Policy check</h3>
        <p className="small muted">Pick a category to see the limit and documents your grade ({grade}) needs.</p>
      </div>
    )
  }
  if (!policies) return <div className="card"><Loading label="Finding the policy" /></div>
  const specific = policies.applicable.filter((p) => p.category !== 'all')
  const nights = form.start_date && form.end_date ? Math.max(1, (new Date(form.end_date) - new Date(form.start_date)) / 864e5) : 1
  const days = form.start_date && form.end_date ? nights + 1 : 1
  const units = (p) => (p.limit_basis === 'per_night' ? nights : p.limit_basis === 'per_day' ? days : 1)

  return (
    <div className="card">
      <div className="card-head"><h2>Policy check</h2><span className="small muted">Grade {grade}</span></div>
      <div className="card-body stack">
        {specific.length === 0 && <Alert tone="error" title="No policy covers this">This category isn't reimbursable for your grade on this date.</Alert>}
        {specific.map((p) => {
          const allowed = p.limit_amount ? Number(p.limit_amount) * units(p) : null
          const over = allowed !== null && Number(form.amount) > allowed
          return (
            <div key={p.id} className="policy-pill">
              <div className="code">{p.code} v{p.version}, {p.source_label}</div>
              <strong>{p.title}</strong>
              {p.limit_amount && (
                <>
                  <div className="limit-line"><span className="muted">Limit</span><span className="num">{money(p.limit_amount)} {p.limit_basis_label.toLowerCase()}</span></div>
                  {units(p) > 1 && <div className="limit-line"><span className="muted">For this trip</span><span className="num">{money(allowed)}</span></div>}
                  {Number(form.amount) > 0 && (
                    <div className="limit-line" style={{ color: over ? 'var(--bad)' : 'var(--ok)', fontWeight: 600, marginTop: 4 }}>
                      <span>{over ? 'Over the limit by' : 'Within limit'}</span>
                      <span className="num">{over ? money(Number(form.amount) - allowed) : <Icon name="check" size={16} />}</span>
                    </div>
                  )}
                </>
              )}
              {p.preapproval_above && <p className="small muted" style={{ marginTop: 6 }}>Pre-approval needed above {money(p.preapproval_above)}.</p>}
              {p.submission_window_days && <p className="small muted">Submit within {p.submission_window_days} days.</p>}
            </div>
          )
        })}
        {policies.conflicts.length > 0 && (
          <Alert tone="warn" title="These policies disagree">
            {policies.conflicts[0].message}. A reviewer will decide which applies.
          </Alert>
        )}
        {required.length > 0 && (
          <div>
            <div className="label" style={{ marginBottom: 8 }}>Documents needed</div>
            <div className="req-list">
              {required.map((r) => {
                const met = hasClaim && requirementMet(r, uploadedTypes)
                return (
                  <div key={r} className={`req ${met ? 'met' : ''}`}>
                    <span className="tick"><Icon name="check" size={12} stroke={3} /></span>
                    <span>{DOC_LABEL[r] || r}</span>
                  </div>
                )
              })}
            </div>
          </div>
        )}
        {policies.superseded.length > 0 && (
          <p className="small faint">Older versions not used: {policies.superseded.map((p) => `${p.code} v${p.version}`).join(', ')}.</p>
        )}
      </div>
    </div>
  )
}

function Documents({ claim, form, onChange, onFill, onError }) {
  const toast = useToast()
  const input = useRef(null)
  const [docType, setDocType] = useState(DEFAULT_DOC[claim.category] || 'invoice')
  const [over, setOver] = useState(false)
  const [uploading, setUploading] = useState(false)
  const docs = claim.documents

  useEffect(() => { setDocType(DEFAULT_DOC[form.category] || 'invoice') }, [form.category])

  const send = async (files) => {
    if (!files?.length) return
    setUploading(true)
    const added = []
    for (const file of files) {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('doc_type', docType)
      try {
        added.push(await upload(`/claims/${claim.id}/documents/`, fd))
      } catch (e) {
        onError(`${file.name}: ${e.message}`)
      }
    }
    if (added.length) {
      onChange([...docs, ...added])
      toast(`${added.length} document${added.length > 1 ? 's' : ''} uploaded and read`)
    }
    setUploading(false)
    if (input.current) input.current.value = ''
  }

  const remove = async (doc) => {
    try {
      await del(`/documents/${doc.id}/`)
      onChange(docs.filter((d) => d.id !== doc.id))
    } catch (e) { onError(e.message) }
  }

  return (
    <div className="card">
      <div className="card-head"><h2>Supporting documents</h2><span className="small muted">PDF, JPG, PNG or TXT, up to 10 MB</span></div>
      <div className="card-body stack">
        <div className="row">
          <label className="label" htmlFor="doctype">This file is a</label>
          <select id="doctype" className="select" style={{ width: 'auto' }} value={docType} onChange={(e) => setDocType(e.target.value)}>
            {DOC_TYPES.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
          </select>
        </div>
        <div className={`dropzone ${over ? 'over' : ''}`} role="button" tabIndex={0}
          onClick={() => input.current?.click()} onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && input.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
          onDrop={(e) => { e.preventDefault(); setOver(false); send([...e.dataTransfer.files]) }}>
          {uploading ? <div className="spinner" style={{ margin: '0 auto' }} /> : <Icon name="upload" size={28} />}
          <strong>{uploading ? 'Uploading and reading…' : `Drop your ${DOC_LABEL[docType].toLowerCase()} here, or click to browse`}</strong>
          <span className="small muted">Text is read from the file so you can check it against your form.</span>
          <input ref={input} type="file" hidden multiple accept=".pdf,.png,.jpg,.jpeg,.webp,.txt" onChange={(e) => send([...e.target.files])} />
        </div>
        {docs.map((d) => <DocumentCard key={d.id} doc={d} form={form} onRemove={() => remove(d)} onFill={onFill} />)}
      </div>
    </div>
  )
}

export function DocumentCard({ doc, form, onRemove, onFill }) {
  const fields = doc.extracted
  const value = (k) => fields.find((f) => f.key === k)?.value
  const compare = (key, v) => {
    if (!form) return ''
    if (key === 'amount' && form.amount) return Math.abs(Number(v) - Number(form.amount)) <= Math.max(1, Number(form.amount) * 0.01) ? 'match' : 'differs'
    if (key === 'invoice_number' && form.invoice_number) return String(v).replace(/\W/g, '').toUpperCase() === form.invoice_number.replace(/\W/g, '').toUpperCase() ? 'match' : 'differs'
    return ''
  }
  const fillable = onFill && form && (
    (!form.vendor && value('vendor')) || (!form.invoice_number && value('invoice_number')) || (!form.amount && value('amount')) || (!form.expense_date && value('date'))
  )
  const ext = doc.original_name.split('.').pop().toUpperCase().slice(0, 4)
  const show = fields.filter((f) => f.key !== 'category')

  return (
    <div className="doc-card">
      <div className="doc-top">
        <span className="doc-ico">{ext}</span>
        <div className="grow">
          <strong>{doc.original_name}</strong>
          <span className="small muted">{doc.doc_type_label}, read by {doc.extraction_method || 'not read'}</span>
        </div>
        <a className="btn sm" href={doc.file} target="_blank" rel="noreferrer"><Icon name="eye" size={15} /> View</a>
        {onRemove && <button className="btn sm danger" onClick={onRemove} aria-label={`Remove ${doc.original_name}`}><Icon name="trash" size={15} /></button>}
      </div>
      {doc.extraction_status === 'done' && show.length > 0 ? (
        <dl className="doc-fields">
          {show.map((f) => {
            const tone = compare(f.key, f.value)
            const shown = f.key === 'amount' ? money(f.value) : ['date', 'check_in', 'check_out'].includes(f.key) ? date(f.value) : String(f.value)
            return (
              <div key={f.key}>
                <dt>{FIELD_LABEL[f.key] || f.key}</dt>
                <dd className={tone} title={f.source ? `Found in: ${f.source}` : undefined}>
                  {shown}{tone === 'differs' && ' (form differs)'}
                </dd>
              </div>
            )
          })}
        </dl>
      ) : (
        <div className="doc-note">{doc.extraction_error || 'Nothing could be read automatically. A reviewer will check it by hand.'}</div>
      )}
      {fillable && (
        <div style={{ padding: '0 14px 12px' }}>
          <button className="btn sm" onClick={() => onFill({
            ...(!form.vendor && value('vendor') ? { vendor: value('vendor') } : {}),
            ...(!form.invoice_number && value('invoice_number') ? { invoice_number: value('invoice_number') } : {}),
            ...(!form.amount && value('amount') ? { amount: String(value('amount')) } : {}),
            ...(!form.expense_date && value('date') ? { expense_date: value('date') } : {}),
          })}><Icon name="copy" size={15} /> Fill empty fields from this document</button>
        </div>
      )}
    </div>
  )
}
