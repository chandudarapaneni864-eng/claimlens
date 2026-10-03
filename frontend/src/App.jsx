import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { is, useAuth, APPROVER_ROLES, OVERSIGHT_ROLES } from './auth'
import Layout from './components/Layout'
import { Empty, Loading } from './components/ui'
import Analytics from './pages/Analytics'
import Approvals from './pages/Approvals'
import ClaimDetail from './pages/ClaimDetail'
import ClaimForm from './pages/ClaimForm'
import Claims from './pages/Claims'
import Dashboard from './pages/Dashboard'
import Login from './pages/Login'
import Payments from './pages/Payments'
import Policies from './pages/Policies'
import Rules from './pages/Rules'
import Users from './pages/Users'

function Protected({ children, roles }) {
  const { user, ready } = useAuth()
  const location = useLocation()
  if (!ready) return <Loading label="Starting ClaimLens" />
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />
  if (roles && !is(user, roles)) {
    return <Empty icon="shield" title="You don't have access to this page">Ask an administrator if you need it.</Empty>
  }
  return children
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Protected><Layout /></Protected>}>
        <Route index element={<Dashboard />} />
        <Route path="claims" element={<Claims />} />
        <Route path="claims/new" element={<ClaimForm />} />
        <Route path="claims/:id" element={<ClaimDetail />} />
        <Route path="claims/:id/edit" element={<ClaimForm />} />
        <Route path="approvals" element={<Protected roles={APPROVER_ROLES}><Approvals /></Protected>} />
        <Route path="payments" element={<Protected roles={['FINANCE', 'ADMIN']}><Payments /></Protected>} />
        <Route path="analytics" element={<Protected roles={OVERSIGHT_ROLES}><Analytics /></Protected>} />
        <Route path="policies" element={<Policies />} />
        <Route path="rules" element={<Protected roles={['ADMIN']}><Rules /></Protected>} />
        <Route path="users" element={<Protected roles={['ADMIN']}><Users /></Protected>} />
        <Route path="*" element={<Empty icon="search" title="Page not found">The link may be broken or the page was moved.</Empty>} />
      </Route>
    </Routes>
  )
}
