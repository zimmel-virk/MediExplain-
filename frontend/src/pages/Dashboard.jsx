import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useAuth } from '../api/auth'

/**
 * This file provides the main role-based dashboard for MediExplain+. It loads the
 * consultations visible to the signed-in user and adapts the page for patients,
 * doctors, administrators, assistants and cross-check reviewers. Patients see
 * their released consultations and learning access, while doctors and administrators
 * can open cases, monitor consultation status, review basic workflow statistics and
 * optionally delegate eligible consultations to an authorised assistant for
 * pre-review. Assistant users are directed to their separate assigned-case queue,
 * and cross-check reviewers are limited to the consultations available through
 * their review workflow. The dashboard also tracks assistant-review status, displays
 * consultation language and progress, and keeps final clinical approval and release
 * under the treating doctor's control.
 */

function Status({value}) { return <span className={`badge ${value}`}>{String(value).replaceAll('_',' ')}</span> }
const langLabel = value => value === 'pa_shah' ? 'Punjabi (Shahmukhi)' : String(value || '').toUpperCase()

export default function Dashboard(){
  const {user}=useAuth()
  const [items,setItems]=useState([]),[assistants,setAssistants]=useState([]),[assistantState,setAssistantState]=useState({})
  const [choices,setChoices]=useState({}),[loading,setLoading]=useState(true),[busy,setBusy]=useState(null),[err,setErr]=useState(null),[notice,setNotice]=useState(null)

  async function load(){
    if(user.role==='assistant'){setItems([]);return}
    const data=await api.listConsultations(); setItems(data)
    if(user.role==='doctor'||user.role==='admin'){
      const pairs=await Promise.all(data.map(async c=>{try{return [c.id,await api.latestAssistantReview(c.id)]}catch{return [c.id,null]}}))
      setAssistantState(Object.fromEntries(pairs))
    }
  }
  useEffect(()=>{Promise.all([load(),(user.role==='doctor'||user.role==='admin')?api.listAssistants().then(setAssistants).catch(()=>setAssistants([])):Promise.resolve()]).catch(e=>setErr(e.message)).finally(()=>setLoading(false))},[user.role])

  async function sendToAssistant(c){
    const assistantId=choices[c.id]; if(!assistantId){setErr('Select an assistant first.');return}
    setBusy(c.id);setErr(null);setNotice(null)
    try{await api.assignAssistant({consultation_id:c.id,assistant_id:Number(assistantId)});await load();setNotice(`Consultation #${c.id} was sent for assistant pre-review. Final approval still belongs to the treating doctor.`)}catch(e){setErr(e.message)}finally{setBusy(null)}
  }

  const stats=useMemo(()=>({total:items.length,released:items.filter(x=>x.released_at).length,review:items.filter(x=>!x.released_at).length}),[items])
  const patientCopy={
    en:{title:'My care hub',subtitle:'Your doctor-released summaries, medication information and learning resources.',button:'Open learning centre',cases:'My released consultations'},
    ur:{title:'میرا کیئر پورٹل',subtitle:'ڈاکٹر کی جاری کردہ خلاصہ معلومات، ادویات اور سیکھنے کے وسائل۔',button:'سیکھنے کا مرکز کھولیں',cases:'میری جاری کردہ مشاورتیں'},
    pa_shah:{title:'میرا کیئر پورٹل',subtitle:'ڈاکٹر ولوں جاری کیتے خلاصے، دوائیاں تے سکھن دے وسیلے۔',button:'سکھن دا مرکز کھولو',cases:'میریاں جاری کیتیاں کنسلٹیشنز'},
  }[user.preferred_language]||null
  const title=user.role==='patient'?(patientCopy?.title||'My care hub'):user.role==='assistant'?'Assistant workspace':user.role==='cross_check_doctor'?'Clinical review workspace':'Doctor dashboard'
  const subtitle=user.role==='patient'?(patientCopy?.subtitle||'Your doctor-released summaries, medication information and learning resources.'):user.role==='assistant'?'Assigned pre-review cases only. Your check returns the case to the treating doctor; you cannot approve or release it.':user.role==='doctor'?'Manage consultations using the original MediExplain+ safety workflow, with optional delegated assistant pre-review.':'Review only cases assigned through the existing clinical cross-check workflow.'

  return <main className="page">
    <section className="hero-panel"><div><span className="eyebrow">SECURE · MULTILINGUAL · REVIEW-FIRST</span><h1>{title}</h1><p>{subtitle}</p></div><div className="hero-actions">{(user.role==='doctor'||user.role==='admin')&&<Link to="/new"><button>+ New consultation</button></Link>}{user.role==='assistant'&&<Link to="/assistant"><button>Open review queue</button></Link>}{user.role==='patient'&&<Link to="/learn"><button>{patientCopy?.button||'Open learning centre'}</button></Link>}</div></section>
    {user.role!=='assistant'&&<section className="stat-grid"><div className="stat-card"><span>Cases visible</span><strong>{stats.total}</strong></div><div className="stat-card"><span>Released / complete</span><strong>{stats.released}</strong></div><div className="stat-card"><span>Needs workflow action</span><strong>{stats.review}</strong></div><div className="stat-card accent-stat"><span>Role</span><strong className="role-stat">{user.role.replaceAll('_',' ')}</strong></div></section>}
    {notice&&<div className="success panel">{notice}</div>}{err&&<div className="error panel">{err}</div>}
    {user.role==='assistant'?<section className="card"><div className="empty-state"><strong>Use the assistant review queue</strong><span>Only explicitly assigned cases are exposed to the assistant role.</span><Link className="button-link" to="/assistant">Open assigned cases</Link></div></section>:<section className="card section-card">
      <div className="section-head"><div><h2>{user.role==='patient'?(patientCopy?.cases||'My released consultations'):'Consultations'}</h2><p>{user.role==='doctor'?'The direct path keeps the original doctor safety checks. The assistant path adds a read/check step before final doctor approval.':'Open a case to see the information available to your role.'}</p></div></div>
      {loading&&<div className="empty-state">Loading consultations…</div>}
      {!loading&&!err&&items.length===0&&<div className="empty-state"><strong>No consultations yet</strong><span>New cases will appear here.</span></div>}
      {!!items.length&&<div className="table-wrap"><table><thead><tr><th>Case</th><th>Status</th><th>Language</th><th>Created</th><th>{user.role==='doctor'?'Workflow action':'Action'}</th></tr></thead><tbody>{items.map(c=>{const ar=assistantState[c.id];const delegatable=(user.role==='doctor'||user.role==='admin')&&!c.approved_at&&!c.released_at&&!!c.patient_summary_en;return <tr key={c.id}>
        <td><strong>Consultation #{c.id}</strong>{ar&&<div className="field-note">Assistant: {ar.status==='pending'?'waiting for review':'checked & returned'}</div>}</td><td><Status value={c.status}/></td><td>{langLabel(c.patient_language)}</td><td>{new Date(c.created_at).toLocaleString()}</td>
        <td>{user.role==='doctor'&&delegatable?<div className="dashboard-actions"><Link className="button-link" to={`/consultation/${c.id}`}>{ar?.status==='reviewed'?'Final doctor review':'Review directly'}</Link>{!ar||ar.status!=='pending'?assistants.length?<div className="inline-delegate"><select aria-label={`Assistant for consultation ${c.id}`} value={choices[c.id]||''} onChange={e=>setChoices({...choices,[c.id]:e.target.value})}><option value="">Assistant…</option>{assistants.map(a=><option key={a.id} value={a.id}>{a.full_name}</option>)}</select><button className="secondary compact" disabled={busy===c.id||!choices[c.id]} onClick={()=>sendToAssistant(c)}>Send</button></div>:<span className="field-note">No assistant account available</span>:<span className="pill warn-pill">With assistant</span>}</div>:<Link className="text-link" to={`/consultation/${c.id}`}>Open case →</Link>}</td>
      </tr>})}</tbody></table></div>}
    </section>}
  </main>
}
