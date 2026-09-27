import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../api/auth'

export default function Nav() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const loc = useLocation()
  if (!user || loc.pathname.startsWith('/share/')) return null
  const link = ({isActive}) => isActive ? 'nav-link active' : 'nav-link'
  const patientNav = user.role === 'patient' ? ({
    ur:{dashboard:'ڈیش بورڈ',reminders:'میری یاددہانیاں',learn:'سیکھنے کا مرکز',support:'مدد اور حفاظت',signout:'سائن آؤٹ'},
    pa_shah:{dashboard:'ڈیش بورڈ',reminders:'میریاں یاددہانیاں',learn:'سکھن دا مرکز',support:'مدد تے حفاظت',signout:'سائن آؤٹ'},
    en:{dashboard:'Dashboard',reminders:'My reminders',learn:'Learning centre',support:'Support & safety',signout:'Sign out'},
  }[user.preferred_language] || null) : null
  return <>
    <header className="topbar">
      <div className="brand" onClick={() => navigate('/')}>
        <div className="brand-mark">M+</div>
        <div><strong>MediExplain+</strong><span>Patient communication platform</span></div>
      </div>
      <div className="user-chip">
        <div className="avatar">{user.full_name?.slice(0,1)?.toUpperCase()}</div>
        <div><strong>{user.full_name}</strong><span>{user.role.replaceAll('_',' ')}</span></div>
        <button className="ghost compact" onClick={() => { logout(); navigate('/login') }}>{patientNav?.signout || 'Sign out'}</button>
      </div>
    </header>
    <nav className="nav-strip" aria-label="Primary">
      <NavLink className={link} to="/">{patientNav?.dashboard || 'Dashboard'}</NavLink>
      {(user.role === 'doctor' || user.role === 'admin') && <NavLink className={link} to="/new">New consultation</NavLink>}
      {user.role === 'assistant' && <NavLink className={link} to="/assistant">Assistant review</NavLink>}
      {['doctor', 'cross_check_doctor', 'admin'].includes(user.role) && <NavLink className={link} to="/cross-check">Clinical cross-check</NavLink>}
      {user.role === 'patient' && <NavLink className={link} to="/reminders">{patientNav?.reminders || 'My reminders'}</NavLink>}
      <NavLink className={link} to="/learn">{patientNav?.learn || 'Learning centre'}</NavLink>
      <NavLink className={link} to="/support">{patientNav?.support || 'Support & safety'}</NavLink>
    </nav>
  </>
}
