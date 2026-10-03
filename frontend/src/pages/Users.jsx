import { useState } from 'react'
import { get, patch, post } from '../api'
import Icon from '../components/Icon'
import { Alert, Field, Loading, Modal, useApi, useToast } from '../components/ui'
import { initials } from '../format'

const ROLES = [['EMPLOYEE', 'Employee'], ['MANAGER', 'Manager'], ['DEPT_HEAD', 'Department head'], ['HR', 'HR'], ['FINANCE', 'Finance'], ['ADMIN', 'Administrator']]

export default function Users() {
  const { data, error, loading, reload } = useApi(() => get('/auth/users/'), [])
  const [editing, setEditing] = useState(null)
  if (loading) return <Loading />
  if (error) return <Alert tone="error">{error.message}</Alert>
  return (
    <>
      <div className="page-head">
        <div><h1>People</h1><p>Roles decide what each person can do. Grade and department decide which policies apply to their claims. The manager is the first approver.</p></div>
        <button className="btn primary" onClick={() => setEditing({})}><Icon name="plus" /> Add person</button>
      </div>
      <div className="card"><div className="table-wrap">
        <table className="table">
          <thead><tr><th>Name</th><th>Role</th><th>Grade</th><th>Department</th><th>Reports to</th><th></th></tr></thead>
          <tbody>
            {data.map((u) => (
              <tr key={u.id} style={{ opacity: u.is_active ? 1 : 0.5 }}>
                <td><div className="row" style={{ flexWrap: 'nowrap' }}><span className="avatar sm">{initials(u.full_name)}</span><div className="cell-title"><strong>{u.full_name}</strong><span>{u.username}{u.employee_id ? `, ${u.employee_id}` : ''}</span></div></div></td>
                <td>{u.role_label}</td>
                <td>{u.grade}</td>
                <td>{u.department || '—'}</td>
                <td>{u.manager_name || '—'}</td>
                <td className="right"><button className="btn sm" onClick={() => setEditing(u)}><Icon name="edit" size={14} /> Edit</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div></div>
      {editing && <UserEditor user={editing} people={data} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); reload() }} />}
    </>
  )
}

function UserEditor({ user, people, onClose, onSaved }) {
  const toast = useToast()
  const [f, setF] = useState({ username: '', first_name: '', last_name: '', email: '', role: 'EMPLOYEE', grade: 'L1', department: '', designation: '', employee_id: '', is_active: true, password: '', ...user, manager: user.manager || '' })
  const [error, setError] = useState('')
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const save = async () => {
    setError('')
    const body = { ...f, manager: f.manager || null, employee_id: f.employee_id || null }
    if (!body.password) delete body.password
    try {
      user.id ? await patch(`/auth/users/${user.id}/`, body) : await post('/auth/users/', body)
      toast(user.id ? 'Saved' : `${f.first_name || f.username} added`)
      onSaved()
    } catch (e) { setError(e.message) }
  }
  return (
    <Modal title={user.id ? `Edit ${user.full_name}` : 'Add person'} onClose={onClose} wide
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save}>Save</button></>}>
      <div className="stack-sm">
        {error && <Alert tone="error">{error}</Alert>}
        <div className="form-grid">
          <Field label="First name"><input className="input" value={f.first_name} onChange={set('first_name')} /></Field>
          <Field label="Last name"><input className="input" value={f.last_name} onChange={set('last_name')} /></Field>
          <Field label="Username"><input className="input" value={f.username} onChange={set('username')} disabled={Boolean(user.id)} /></Field>
          <Field label={user.id ? 'New password' : 'Password'} hint={user.id ? 'Leave empty to keep the current one.' : 'Defaults to Pass@123 if empty.'}><input className="input" type="password" value={f.password} onChange={set('password')} /></Field>
          <Field label="Email"><input className="input" type="email" value={f.email} onChange={set('email')} /></Field>
          <Field label="Employee ID"><input className="input" value={f.employee_id || ''} onChange={set('employee_id')} /></Field>
          <Field label="Role"><select className="select" value={f.role} onChange={set('role')}>{ROLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
          <Field label="Grade"><select className="select" value={f.grade} onChange={set('grade')}>{['L1', 'L2', 'L3', 'L4'].map((g) => <option key={g}>{g}</option>)}</select></Field>
          <Field label="Department"><input className="input" value={f.department} onChange={set('department')} /></Field>
          <Field label="Designation"><input className="input" value={f.designation} onChange={set('designation')} /></Field>
          <Field label="Reports to" full>
            <select className="select" value={f.manager} onChange={set('manager')}>
              <option value="">No manager</option>
              {people.filter((p) => p.id !== user.id && p.is_active).map((p) => <option key={p.id} value={p.id}>{p.full_name}, {p.role_label}</option>)}
            </select>
          </Field>
          <label className="check"><input type="checkbox" checked={f.is_active} onChange={set('is_active')} /> Active</label>
        </div>
      </div>
    </Modal>
  )
}
