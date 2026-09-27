import { useEffect,useState } from 'react'
import { Link,useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useAuth } from '../api/auth'

export default function Register(){
  const {login}=useAuth();const nav=useNavigate()
  const [form,setForm]=useState({email:'',full_name:'',password:'',preferred_language:'en'})
  const [langs,setLangs]=useState([]);const [err,setErr]=useState(null)
  useEffect(()=>{api.languages().then(setLangs).catch(()=>{})},[])
  const update=(k,v)=>setForm(x=>({...x,[k]:v}))
  async function submit(e){
    e.preventDefault();setErr(null)
    try{await api.register(form);await login(form.email,form.password);nav('/')}
    catch(e){setErr(e.message)}
  }
  return <div className="auth-shell"><div className="auth-card">
    <h1>Create patient account</h1>
    <p>Doctor and reviewer accounts are verified accounts created by the system administrator.</p>
    <form onSubmit={submit}>
      <label>Full name</label><input required value={form.full_name} onChange={e=>update('full_name',e.target.value)} />
      <label>Email</label><input required type="email" value={form.email} onChange={e=>update('email',e.target.value)} />
      <label>Password</label><input required type="password" minLength={8} value={form.password} onChange={e=>update('password',e.target.value)} />
      <label>Preferred language</label>
      <select value={form.preferred_language} onChange={e=>update('preferred_language',e.target.value)}>
        {langs.map(l=><option key={l.code} value={l.code}>{l.name} — {l.native}</option>)}
      </select>
      {err?<div className="error">{err}</div>:null}
      <button style={{width:'100%',marginTop:20}}>Create patient account</button>
    </form>
    <div className="auth-switch">Already registered? <Link to="/login">Sign in</Link></div>
  </div></div>
}
