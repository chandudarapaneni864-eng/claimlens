import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { get } from '../api'
import { is, useAuth, APPROVER_ROLES, OVERSIGHT_ROLES } from '../auth'
import { initials } from '../format'
import Icon, { BrandMark } from './Icon'

export default function Layout() {
  const { user, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const [waiting, setWaiting] = useState(0)
  const location = useLocation()
  const navigate = useNavigate()

  useEffect(() => { setOpen(false) }, [location.pathname, location.search])
  useEffect(() => {
    if (!is(user, APPROVER_ROLES)) return
    get('/dashboard/').then((d) => setWaiting(d.approvals_waiting)).catch(() => {})
  }, [user, location.pathname])

  const link = (to, icon, label, extra) => (
    <NavLink to={to} end={to === '/'} className={({ isActive }) => `nav-link ${isActive && !extra?.inactive ? 'active' : ''}`}>
      <Icon name={icon} size={18} />
      <span>{label}</span>
      {extra?.count > 0 && <span className="nav-count">{extra.count}</span>}
    </NavLink>
  )
  const scope = new URLSearchParams(location.search).get('scope') || 'mine'
  const onClaims = location.pathname === '/claims'

  return (
    <div className="shell">
      <aside className={`sidebar ${open ? 'open' : ''}`} aria-label="Main navigation">
        <div className="brand">
          <BrandMark />
          <div>
            <div className="brand-name">ClaimLens</div>
            <div className="brand-sub">Claims and settlement</div>
          </div>
        </div>

        <nav className="nav-group">
          {link('/', 'home', 'Overview')}
          <NavLink to="/claims" className={() => `nav-link ${onClaims && scope === 'mine' ? 'active' : ''}`}><Icon name="receipt" /><span>My claims</span></NavLink>
          {link('/claims/new', 'plus', 'New claim')}
        </nav>

        {is(user, APPROVER_ROLES) && (
          <nav className="nav-group">
            <div className="nav-title">Review</div>
            {link('/approvals', 'inbox', 'Approvals', { count: waiting })}
            {is(user, 'MANAGER', 'DEPT_HEAD') && (
              <NavLink to="/claims?scope=team" className={() => `nav-link ${onClaims && scope === 'team' ? 'active' : ''}`}><Icon name="team" /><span>Team claims</span></NavLink>
            )}
            {is(user, OVERSIGHT_ROLES) && (
              <NavLink to="/claims?scope=all" className={() => `nav-link ${onClaims && scope === 'all' ? 'active' : ''}`}><Icon name="layers" /><span>All claims</span></NavLink>
            )}
            {is(user, 'FINANCE', 'ADMIN') && link('/payments', 'wallet', 'Payments')}
            {is(user, OVERSIGHT_ROLES) && link('/analytics', 'chart', 'Analytics')}
          </nav>
        )}

        <nav className="nav-group">
          <div className="nav-title">Rules</div>
          {link('/policies', 'book', 'Policies')}
          {is(user, 'ADMIN') && link('/rules', 'sliders', 'Approval levels')}
          {is(user, 'ADMIN') && link('/users', 'users', 'People')}
        </nav>

        <div className="sidebar-foot">
          <div className="avatar">{initials(user.full_name)}</div>
          <div className="who">
            <strong>{user.full_name}</strong>
            <span>{user.role_label}, {user.grade}</span>
          </div>
          <button className="icon-btn" onClick={() => { logout(); navigate('/login') }} aria-label="Sign out" title="Sign out">
            <Icon name="logout" />
          </button>
        </div>
      </aside>
      {open && <div className="scrim" onClick={() => setOpen(false)} />}

      <div>
        <div className="topbar-mobile">
          <button className="icon-btn" onClick={() => setOpen(true)} aria-label="Open menu"><Icon name="menu" /></button>
          <BrandMark className="brand-mark" />
          <span className="brand-name">ClaimLens</span>
        </div>
        <main className="main">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
