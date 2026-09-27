import { useEffect, useState } from 'react'
import { api } from '../api/client'

// This component lets the doctor review and correct one medication extracted from
// a consultation. It keeps the editable medication fields separate from the saved
// backend record, shows extraction and terminology-match confidence, allows lookup
// against the installed medication terminology index, and requires an explicit
// doctor confirmation before the medication identity and instructions are treated
// as confirmed.

export default function MedicationEditor({ consultationId, index, med, readOnly, onChange }) {
  const [draft,setDraft]=useState(med||{})
  const [suggestions,setSuggestions]=useState(med?.suggestions||[])
  const [busy,setBusy]=useState(false)
  const [err,setErr]=useState(null)
  useEffect(()=>{setDraft(med||{});setSuggestions(med?.suggestions||[])},[med])

    // Keep extraction confidence and terminology-match confidence separate so the
  // interface does not present recognition confidence as medication verification.

  const extraction=typeof draft.confidence==='number'?draft.confidence:null
  const match=typeof draft.match_confidence==='number'?draft.match_confidence:
              suggestions?.[0]?.score ?? null
  const set=(k,v)=>setDraft(x=>({...x,[k]:v}))

    // Save the doctor's current edits to the consultation. Confirmation is sent
  // separately so ordinary edits do not automatically mark either the medication
  // identity or its instructions as clinically confirmed.

  async function save(confirm=false){
    setBusy(true);setErr(null)
    try{
      const updated=await api.updateMedication(consultationId,index,{
        name:draft.name, concept_id:draft.concept_id,
        dose:draft.dose,strength:draft.strength,dose_unit:draft.dose_unit,
        dosage_form:draft.dosage_form,route:draft.route,frequency:draft.frequency,
        timing:draft.timing,food_instruction:draft.food_instruction,duration:draft.duration,
        as_needed:!!draft.as_needed,indication:draft.indication,notes:draft.notes,
        confirm_identity:confirm,confirm_instructions:confirm,
      })
      onChange?.(updated)
    }catch(e){setErr(e.message)}finally{setBusy(false)}
  }

    // Search the local medication terminology index using the current medication
  // name or the originally heard name and return possible identity matches for
  // the doctor to review.

  async function lookup(){
    const q=draft.name||draft.name_as_heard||''
    if(q.trim().length<2)return
    setBusy(true);setErr(null)
    try{setSuggestions(await api.suggestMedications(q,8))}
    catch(e){setErr(e.message)}finally{setBusy(false)}
  }
  function choose(s){
    // A terminology match helps verify which medicine was intended, but it must not
  // invent a usual dose or replace the instructions already extracted or entered.
    setDraft(x=>({
      ...x,concept_id:s.concept_id,name:s.display_name||s.generic_name,
      canonical_name:s.display_name,generic_name:s.generic_name,
      brand_name:s.brand_name,strength:x.strength||s.strength||'',
      dosage_form:x.dosage_form||s.dosage_form||'',
      match_confidence:s.score,doctor_confirmed:false,
    }))
  }

    // Medication removal requires an explicit confirmation before the record is
  // deleted from the consultation.
  
  async function remove(){
    if(!confirm('Remove this medication from the consultation?'))return
    setBusy(true)
    try{onChange?.(await api.removeMedication(consultationId,index))}
    catch(e){setErr(e.message)}finally{setBusy(false)}
  }

  return <div className="med-row">
    <div className="med-row-top" style={{display:'flex',gap:8,flexWrap:'wrap'}}>
      {extraction!=null?<span className="conf-badge">Extraction {Math.round(extraction*100)}%</span>:null}
      {match!=null?<span className="conf-badge">Drug match {Math.round(match*100)}%</span>:null}
      {draft.doctor_confirmed?<span className="conf-badge approved">✓ Doctor confirmed</span>:
        <span className="conf-badge medium">Needs doctor confirmation</span>}
      {draft.name_as_heard?<span className="muted">heard as: “{draft.name_as_heard}”</span>:null}
    </div>
    <div className="med-fields">
      <div><label>Medication name</label><input disabled={readOnly} value={draft.name||''} onChange={e=>set('name',e.target.value)} /></div>
      <div><label>Strength</label><input disabled={readOnly} value={draft.strength||''} onChange={e=>set('strength',e.target.value)} placeholder="e.g. 500 mg" /></div>
      <div><label>Dose</label><input disabled={readOnly} value={draft.dose||''} onChange={e=>set('dose',e.target.value)} placeholder="e.g. 1 tablet" /></div>
      <div><label>Frequency</label><input disabled={readOnly} value={draft.frequency||''} onChange={e=>set('frequency',e.target.value)} placeholder="e.g. twice daily" /></div>
      <div><label>Timing</label><input disabled={readOnly} value={draft.timing||''} onChange={e=>set('timing',e.target.value)} placeholder="morning / night" /></div>
      <div><label>Food instruction</label><input disabled={readOnly} value={draft.food_instruction||''} onChange={e=>set('food_instruction',e.target.value)} placeholder="after food" /></div>
      <div><label>Duration</label><input disabled={readOnly} value={draft.duration||''} onChange={e=>set('duration',e.target.value)} placeholder="e.g. 5 days" /></div>
      <div><label>Route / form</label><input disabled={readOnly} value={[draft.route,draft.dosage_form].filter(Boolean).join(' / ')} readOnly placeholder="oral / tablet" /></div>
      <div className="med-notes"><label>Notes</label><input disabled={readOnly} value={draft.notes||''} onChange={e=>set('notes',e.target.value)} /></div>
    </div>
    {!readOnly?<div className="med-actions">
      <button className="secondary" disabled={busy} onClick={()=>save(false)}>Save edits</button>
      <button className="secondary" disabled={busy} onClick={lookup}>Look up real medicine matches</button>
      <button disabled={busy} onClick={()=>save(true)}>Confirm identity & instructions</button>
      <button className="danger" disabled={busy} onClick={remove}>Remove</button>
    </div>:null}
    {err?<div className="error">{err}</div>:null}
    {suggestions?.length?<div className="sugg-list">
      <div className="muted">Candidate matches from installed RxNorm/DRAP terminology. Choosing one does not confirm a dose.</div>
      {suggestions.map((s,i)=><button key={i} type="button" className="sugg-item" onClick={()=>choose(s)} disabled={readOnly}>
        <div><strong>{s.display_name||s.generic_name}</strong> {s.source?<span className="muted">· {s.source.toUpperCase()}</span>:null}</div>
        <div className="muted">{s.brand_name?`Brand: ${s.brand_name} · `:''}{s.strength||''}{s.score!=null?` · match ${Math.round(s.score*100)}%`:''}</div>
      </button>)}
    </div>:null}
  </div>
}
