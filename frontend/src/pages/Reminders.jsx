import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { useAuth } from '../api/auth'


/**
 * This file provides the patient medication-reminders page in MediExplain+. It
 * loads the signed-in patient's active medication schedules and reminder events,
 * shows simple totals for scheduled medicines and pending alerts, and presents
 * each medication's doctor-confirmed dose, form, timing, duration and upcoming
 * reminder times. PRN or as-needed medicines are shown without creating fixed
 * alarms, while pending and snoozed events remain tied to the existing global
 * alarm and voice-reminder system. The page also includes patient-facing safety
 * messaging to make clear that reminder times come from confirmed medication
 * instructions and do not replace the prescription or clinical advice.
 */

function timeLabel(value){
  if(!value) return '—'
  return new Date(value).toLocaleString(undefined,{weekday:'short',day:'numeric',month:'short',hour:'numeric',minute:'2-digit'})
}

export default function Reminders(){
  const {user}=useAuth()
  const [items,setItems]=useState([])
  const [err,setErr]=useState(null)
  const [loading,setLoading]=useState(true)
  const t={
    en:{eyebrow:'PATIENT MEDICATION SUPPORT',title:'My reminders',desc:'Your original MediExplain+ rule-based schedule stays active while you move around the portal. Use the reminder control in the lower-right corner to enable alarm and voice.',important:'Important',warn:'Reminder times come only from doctor-confirmed medication instructions. They do not replace the prescription or clinical advice.',schedule:'Active medication schedules',empty:'No active fixed medication schedule is available.'},
    ur:{eyebrow:'مریض کے لیے ادویات کی مدد',title:'میری یاددہانیاں',desc:'اصل MediExplain+ شیڈول پورٹل میں رہتے ہوئے فعال رہتا ہے۔ الارم اور آواز چلانے کے لیے نیچے دائیں جانب reminder control استعمال کریں۔',important:'اہم',warn:'یاددہانی کے اوقات صرف ڈاکٹر کی تصدیق شدہ ادویات کی ہدایات سے بنتے ہیں۔ یہ نسخے یا طبی مشورے کی جگہ نہیں لیتے۔',schedule:'فعال ادویات کے شیڈول',empty:'کوئی فعال مقررہ دوائی شیڈول موجود نہیں۔'},
    pa_shah:{eyebrow:'مریض لئی دوائی دی مدد',title:'میریاں یاددہانیاں',desc:'اصل MediExplain+ دا rule-based شیڈول پورٹل وچ گھومدیاں وی چلد ا رہندا اے۔ الارم تے آواز لئی تھلے سجے پاسے reminder control ورتو۔',important:'اہم',warn:'یاددہانی دے ویلے صرف ڈاکٹر دی تصدیق شدہ دوائی دیاں ہدایتاں توں بن دے نیں۔ ایہ نسخے یا طبی مشورے دی جگہ نئیں لیندے۔',schedule:'فعال دوائیاں دے شیڈول',empty:'کوئی فعال مقررہ دوائی شیڈول موجود نئیں۔'}
  }[user?.preferred_language]||null
  const x=t||{eyebrow:'PATIENT MEDICATION SUPPORT',title:'My reminders',desc:'Medication reminders from released consultations.',important:'Important',warn:'Follow doctor-confirmed instructions.',schedule:'Active medication schedules',empty:'No active schedule.'}

  useEffect(()=>{api.mySchedules().then(setItems).catch(e=>setErr(e.message)).finally(()=>setLoading(false))},[])
  const totals=useMemo(()=>({meds:items.length,pending:items.flatMap(x=>x.events||[]).filter(e=>['pending','snoozed'].includes(e.status)).length}),[items])

  return <main className="page">
    <section className="hero-panel compact-hero"><div><span className="eyebrow">{x.eyebrow}</span><h1>{x.title}</h1><p>{x.desc}</p></div></section>
    <section className="stat-grid"><div className="stat-card"><span>Medicines scheduled</span><strong>{totals.meds}</strong></div><div className="stat-card"><span>Pending reminder events</span><strong>{totals.pending}</strong></div></section>
    <section className="card section-card">
      <div className="warning-panel"><strong>{x.important}</strong><span>{x.warn}</span></div>
      <div className="section-head"><div><h2>{x.schedule}</h2><p>The floating reminder control is the same original alarm/voice system and remains mounted globally so navigation does not stop an enabled reminder.</p></div></div>
      {err&&<div className="error">{err}</div>}
      {loading&&<div className="empty-state">Loading schedules…</div>}
      {!loading&&!items.length&&<div className="empty-state">{x.empty}</div>}
      <div className="schedule-grid">
        {items.map(s=>{const upcoming=(s.events||[]).filter(e=>['pending','snoozed'].includes(e.status)).slice(0,6);return <article className="schedule-card" key={s.id}>
          <div className="schedule-card-head"><div><span className="eyebrow">MEDICATION</span><h3>{s.medication_name}</h3></div><span className="pill">{s.frequency||'Instructions only'}</span></div>
          <div className="detail-grid"><div><span>Dose / strength</span><strong>{s.dose||s.strength||'—'}</strong></div><div><span>Form</span><strong>{s.dosage_form||'—'}</strong></div><div><span>Timing</span><strong>{s.timing||'—'}</strong></div><div><span>Duration</span><strong>{s.duration||'—'}</strong></div></div>
          {s.as_needed?<div className="quality-notice">PRN / as-needed instruction — no invented fixed alarms.</div>:<div><strong>Upcoming reminder times</strong>{upcoming.length?<ul className="clean-list">{upcoming.map(e=><li key={e.id}><span>{timeLabel(e.snoozed_until||e.scheduled_at)}</span><span className={`pill ${e.status}`}>{e.status}</span></li>)}</ul>:<div className="muted">No pending events.</div>}</div>}
        </article>})}
      </div>
    </section>
  </main>
}
