import { useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import Icon, { BrandMark } from '../components/Icon'
import { Alert } from '../components/ui'

const DEMO = [
  { username: 'ananya', name: 'Ananya Rao', role: 'Employee' },
  { username: 'karthik', name: 'Karthik S.', role: 'Employee' },
  { username: 'ravi.manager', name: 'Ravi Shankar', role: 'Manager' },
  { username: 'arjun.head', name: 'Arjun Mehta', role: 'Department head' },
  { username: 'meera.hr', name: 'Meera Krishnan', role: 'HR' },
  { username: 'priya.finance', name: 'Priya Nair', role: 'Finance' },
  { username: 'admin', name: 'Asha Menon', role: 'Administrator' },
]

export default function Login() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [form, setForm] = useState({ username: '', password: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to={location.state?.from?.pathname || '/'} replace />

  const submit = async (e, creds = form) => {
    e?.preventDefault()
    setBusy(true)
    setError('')
    try {
      await login(creds.username.trim(), creds.password)
      navigate(location.state?.from?.pathname || '/', { replace: true })
    } catch (err) {
      setError(err.status === 401 ? 'Wrong username or password.' : err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login">
      <section className="login-art">
        <div className="brand"><BrandMark /><div className="brand-name">ClaimLens</div></div>
        <div>
          <h1>Every receipt checked against policy before anyone signs off.</h1>
          <p className="lede">Submit a claim, upload the bills, and see exactly what the reviewer will see: what matched, what didn't, and which rule it comes from.</p>
          <div className="receipt-stage" aria-hidden="true">
            <div className="mini-receipt r1">
              <h4>The Orchid Residency</h4>
              <div className="line"><span>2 nights</span><span>₹11,600</span></div>
              <div className="line"><span>GST 12%</span><span>₹1,392</span></div>
              <div className="line total"><span>Total</span><span>₹12,992</span></div>
            </div>
            <div className="mini-receipt r2">
              <h4>Verification</h4>
              <div className="check-row"><span className="dot ok"><Icon name="check" size={10} stroke={3.5} /></span>Name matches employee</div>
              <div className="check-row"><span className="dot ok"><Icon name="check" size={10} stroke={3.5} /></span>Payment proof found</div>
              <div className="check-row"><span className="dot bad"><Icon name="x" size={10} stroke={3.5} /></span>₹500/night over TRV-ACC</div>
              <div className="check-row"><span className="dot warn"><Icon name="alert" size={10} stroke={3} /></span>Finance circular differs</div>
              <div className="check-row"><span className="dot ok"><Icon name="check" size={10} stroke={3.5} /></span>No duplicate invoice</div>
            </div>
          </div>
        </div>
        <p className="login-foot">Final-year project: claim verification with OCR, RAG policy retrieval and human approval.</p>
      </section>

      <section className="login-panel">
        <div className="login-box">
          <h2>Sign in</h2>
          <p className="muted" style={{ marginBottom: 22 }}>Use your company username and password.</p>
          <form onSubmit={submit} className="stack-sm">
            {error && <Alert tone="error">{error}</Alert>}
            <div className="field">
              <label htmlFor="username">Username</label>
              <input id="username" className="input" autoComplete="username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} required />
            </div>
            <div className="field">
              <label htmlFor="password">Password</label>
              <input id="password" type="password" className="input" autoComplete="current-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required />
            </div>
            <button className="btn primary block" disabled={busy} style={{ marginTop: 6, padding: '11px 16px' }}>
              {busy ? <span className="spinner sm" /> : null} Sign in
            </button>
          </form>
          <div className="demo-accounts">
            <div className="label">Demo accounts</div>
            <p className="small muted">All use the password Pass@123. Pick one to sign in.</p>
            <div className="demo-list">
              {DEMO.map((d) => (
                <button key={d.username} className="demo-pick" onClick={() => submit(null, { username: d.username, password: 'Pass@123' })} disabled={busy}>
                  <strong>{d.name}</strong>
                  <span>{d.role}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}
